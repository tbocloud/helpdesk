# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Copilot Run: one run per ticket at a time, moved through a fixed set of states.

A run is queued when a Copilot-enabled customer's ticket arrives (or an agent
presses Start Copilot), claimed by a worker under a lease, and moved on by the
router once the worker reports. Every change of state writes an HDS Copilot
Event, updates the ticket's Copilot fields and tells open ticket pages.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from helpdesk.copilot import settings as copilot_settings
from helpdesk.copilot.registry import apps_for, registry_for_ticket
from helpdesk.utils import get_doc_room, publish_event

REALTIME_EVENT = "helpdesk:copilot-run"
MAX_PAYLOAD_BYTES = 16 * 1024

# who moves a run: the worker holding the lease, the hub itself, an agent, the customer
WORKER, SYSTEM, AGENT, CUSTOMER = "worker", "system", "agent", "customer"

# nobody waits on Copilot in these states, so a new run may start for the ticket
SETTLED_STATES = ("Answered", "Closed", "Failed", "Cancelled", "Escalated", "Handed Over")
FINISHED_STATES = ("Closed", "Failed", "Cancelled")

TRANSITIONS = {
    ("Queued", "Investigating"): {WORKER},
    ("Investigating", "Queued"): {SYSTEM},
    ("Investigating", "Failed"): {WORKER, SYSTEM},
    ("Investigating", "Explaining"): {SYSTEM},
    ("Investigating", "Preparing Fix"): {SYSTEM},
    ("Investigating", "Handed Over"): {SYSTEM},
    ("Explaining", "Answered"): {SYSTEM, AGENT},
    ("Answered", "Closed"): {CUSTOMER, AGENT, SYSTEM},
    ("Answered", "Escalated"): {CUSTOMER, AGENT},
    ("Preparing Fix", "Escalated"): {CUSTOMER, AGENT},
    ("Preparing Fix", "Closed"): {CUSTOMER, AGENT, SYSTEM},
    ("Handed Over", "Escalated"): {CUSTOMER, AGENT},
    ("Handed Over", "Closed"): {CUSTOMER, AGENT, SYSTEM},
    ("Escalated", "Closed"): {CUSTOMER, AGENT, SYSTEM},
}
CANCELLABLE = ("Queued", "Investigating", "Explaining", "Answered", "Preparing Fix", "Handed Over")

# the stage the customer sees when a run enters a state; the router sets the others
STAGE_FOR_STATE = {
    "Investigating": "Working on it",
    "Explaining": "Working on it",
    "Preparing Fix": "Working on it",
    "Handed Over": "With our team",
    "Escalated": "With our team",
    "Failed": "With our team",
}


def active_run(ticket: str):
    """The run of a ticket that Copilot is still working on, if any."""
    name = frappe.db.get_value(
        "HDS Copilot Run", {"ticket": ticket, "state": ["not in", SETTLED_STATES]}, "name"
    )
    return frappe.get_doc("HDS Copilot Run", name) if name else None


def start_run(ticket: str, kind: str = "investigate", actor: str = SYSTEM):
    """Queues a run for a ticket; when one is already active, that one is returned instead."""
    from helpdesk.content_sync import get_client_connection

    existing = active_run(ticket)
    if existing:
        return existing
    info = frappe.db.get_value(
        "HD Ticket", ticket, ["customer", "custom_qcs_connection"], as_dict=True
    )
    registry = registry_for_ticket(ticket)
    run = frappe.get_doc(
        {
            "doctype": "HDS Copilot Run",
            "ticket": ticket,
            "customer": info.customer,
            "connection": info.custom_qcs_connection or get_client_connection(info.customer),
            "registry": registry.name if registry else None,
            "kind": kind,
            "state": "Queued",
            "queued_at": now_datetime(),
        }
    ).insert(ignore_permissions=True)
    add_event(run, "state_change", {"from": None, "to": "Queued"}, actor)
    update_ticket(run)
    if kind == "investigate":
        send_stage(run, "Received")  # a follow-up keeps "Waiting for you" until a worker picks it up
    publish_run(run)
    return run


def on_ticket_insert(doc, method=None):
    """after_insert hook: a new ticket of a Copilot-enabled customer gets a run."""
    if not doc.customer or not copilot_settings.is_enabled():
        return
    if not frappe.db.get_value("HD Customer", doc.customer, "custom_copilot_enabled"):
        return
    try:
        start_run(doc.name)
    except Exception:
        frappe.log_error(
            title=f"Copilot run not started for {doc.name}", message=frappe.get_traceback()
        )


def transition(run, to: str, actor: str, note: str = "", **fields):
    """Moves a run to `to` under a row lock; refused unless TRANSITIONS allows it for `actor`."""
    name = run if isinstance(run, str) else run.name
    frappe.db.get_value("HDS Copilot Run", name, "state", for_update=True)
    return _move(frappe.get_doc("HDS Copilot Run", name), to, actor, note, **fields)


def _move(doc, to: str, actor: str, note: str = "", **fields):
    allowed = TRANSITIONS.get((doc.state, to), set())
    cancel = to == "Cancelled" and actor in (AGENT, SYSTEM) and doc.state in CANCELLABLE
    if actor not in allowed and not cancel:
        frappe.throw(
            _("A Copilot run cannot go from {0} to {1} ({2})").format(doc.state, to, actor)
        )
    previous = doc.state
    doc.state = to
    doc.update(fields)
    if previous == "Investigating" and to not in ("Investigating", "Cancelled"):
        # the lease ends with the work; a cancelled run keeps it so the worker hears "cancel"
        doc.lease_token_hash = None
        doc.lease_expires = None
    if to in FINISHED_STATES:
        doc.finished_at = now_datetime()
    doc.save(ignore_permissions=True)
    add_event(doc, "state_change", {"from": previous, "to": to, "note": note}, actor)
    update_ticket(doc)
    if STAGE_FOR_STATE.get(to):
        send_stage(doc, STAGE_FOR_STATE[to])
    publish_run(doc)
    return doc


def add_event(run, event_type: str, payload: dict | None = None, actor: str = SYSTEM, seq: int | None = None) -> bool:
    """Writes an event; a worker's `seq` makes it idempotent (a repeat is ignored and returns False)."""
    name = run if isinstance(run, str) else run.name
    key = f"{name}:w:{seq}" if seq is not None else f"{name}:h:{frappe.generate_hash(length=10)}"
    if seq is not None and frappe.db.exists("HDS Copilot Event", {"event_key": key}):
        return False
    text = json.dumps(payload or {}, default=str)
    truncated = len(text.encode()) > MAX_PAYLOAD_BYTES
    if truncated:
        text = json.dumps({"_truncated": True, "text": text[: MAX_PAYLOAD_BYTES - 64]})
    frappe.db.savepoint("copilot_event")
    try:
        frappe.get_doc(
            {
                "doctype": "HDS Copilot Event",
                "run": name,
                "seq": seq or 0,
                "event_key": key,
                "event_type": event_type[:140],
                "actor": actor,
                "payload": text,
                "truncated": int(truncated),
            }
        ).insert(ignore_permissions=True)
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
        frappe.db.rollback(save_point="copilot_event")
        return False
    return True


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def lease_minutes() -> int:
    return copilot_settings.get_settings().lease_minutes or 5


def claim(worker_id: str, capabilities: str = ""):
    """Hands the oldest queued run to a worker for the lease time; (None, None) when the queue is empty."""
    candidates = frappe.get_all(
        "HDS Copilot Run",
        filters={"state": "Queued"},
        order_by="queued_at asc, creation asc",
        limit=5,
        pluck="name",
    )
    for name in candidates:
        if frappe.db.get_value("HDS Copilot Run", name, "state", for_update=True) != "Queued":
            continue  # another worker got it first
        token = frappe.generate_hash(length=32)
        doc = _move(
            frappe.get_doc("HDS Copilot Run", name),
            "Investigating",
            WORKER,
            note=f"claimed by {worker_id}",
            worker_id=worker_id,
            lease_token_hash=_hash(token),
            lease_expires=add_to_date(now_datetime(), minutes=lease_minutes()),
            claimed_at=now_datetime(),
        )
        add_event(
            doc,
            "lease",
            {"worker_id": worker_id, "capabilities": capabilities, "expires": str(doc.lease_expires)},
            WORKER,
        )
        return doc, token
    return None, None


def check_lease(run, token: str):
    """The run as a document when `token` is its live lease; PermissionError otherwise."""
    doc = frappe.get_doc("HDS Copilot Run", run) if isinstance(run, str) else run
    if not token or not doc.lease_token_hash or _hash(token) != doc.lease_token_hash:
        frappe.throw(_("This lease is not valid for run {0}").format(doc.name), frappe.PermissionError)
    if doc.state != "Investigating":
        frappe.throw(
            _("Run {0} is {1}; the lease has ended").format(doc.name, doc.state),
            frappe.PermissionError,
        )
    if get_datetime(doc.lease_expires) < now_datetime():
        frappe.throw(_("The lease on run {0} expired").format(doc.name), frappe.PermissionError)
    return doc


def heartbeat(run: str, token: str) -> dict:
    """Extends the lease; tells a worker whose run was cancelled to stop."""
    doc = frappe.get_doc("HDS Copilot Run", run)
    if doc.state == "Cancelled" and doc.lease_token_hash and _hash(token) == doc.lease_token_hash:
        return {"ok": True, "action": "cancel"}
    doc = check_lease(doc, token)
    expires = add_to_date(now_datetime(), minutes=lease_minutes())
    doc.db_set("lease_expires", expires, update_modified=False)
    return {"ok": True, "action": "continue", "lease_expires": str(expires)}


def expire_stale_leases():
    """Cron: a run whose worker stopped reporting goes back to the queue, or fails after too many losses."""
    limit = copilot_settings.get_settings().max_lease_losses or 3
    stale = frappe.get_all(
        "HDS Copilot Run",
        filters={"state": "Investigating", "lease_expires": ["<", now_datetime()]},
        pluck="name",
    )
    for name in stale:
        frappe.db.get_value("HDS Copilot Run", name, "state", for_update=True)
        doc = frappe.get_doc("HDS Copilot Run", name)
        if doc.state != "Investigating" or get_datetime(doc.lease_expires) >= now_datetime():
            continue  # a heartbeat or a result arrived meanwhile
        losses = (doc.lease_losses or 0) + 1
        if losses >= limit:
            _move(
                doc,
                "Failed",
                SYSTEM,
                note="lease lost too often",
                lease_losses=losses,
                failure_reason=f"The worker stopped reporting {losses} times",
            )
            tell_people(doc, _("Copilot gave up on ticket {0}: the worker kept stopping").format(doc.ticket))
        else:
            _move(doc, "Queued", SYSTEM, note="lease expired", lease_losses=losses, worker_id=None)
        frappe.db.commit()  # one run at a time; a failure on the next must not undo this - nosemgrep


def tell_people(run, subject: str):
    """A reminder (and the chat channel) for the Agent Managers: Copilot needs a person here."""
    from helpdesk.work_reminders import notify_users

    managers = frappe.get_all(
        "Has Role", filters={"role": "Agent Manager", "parenttype": "User"}, pluck="parent"
    )
    enabled = (
        frappe.get_all("User", filters={"name": ["in", managers], "enabled": 1}, pluck="name")
        if managers
        else []
    )
    notify_users(enabled, "HD Ticket", run.ticket, subject, escalate=True)


def send_stage(run, stage: str, context: dict | None = None) -> bool:
    """The customer's stage, delivered by helpdesk.copilot.customer (imported late: it imports this module)."""
    from helpdesk.copilot.customer import send_stage as deliver

    return deliver(run, stage, context)


def update_ticket(run, stage: str | None = None, root_cause: str | None = None):
    """Mirrors the run on its ticket (latest run, stage, root cause) without touching `modified`."""
    values = {"custom_copilot_run": run.name}
    if stage:
        values["custom_copilot_stage"] = stage
    if root_cause:
        values["custom_root_cause"] = root_cause
    frappe.db.set_value("HD Ticket", run.ticket, values, update_modified=False)


def publish_run(run):
    # IDs only: the ticket room can be joined by anyone who knows the ticket number
    publish_event(
        REALTIME_EVENT,
        room=get_doc_room("HD Ticket", run.ticket),
        data={"ticket": run.ticket, "run": run.name},
    )


def run_context(run) -> dict:
    """What a worker gets with a claim: the ticket, its triage, the customer, the site, the conversation.

    Never credentials: the worker reaches the customer site only through the hub.
    """
    ticket = frappe.get_doc("HD Ticket", run.ticket)
    registry = frappe.get_doc("HDS Site Registry", run.registry) if run.registry else None
    customer = (
        frappe.db.get_value(
            "HD Customer",
            run.customer,
            ["customer_name", "custom_copilot_enabled", "custom_assigned_developer"],
            as_dict=True,
        )
        if run.customer
        else None
    )
    return {
        "run": run.name,
        "kind": run.kind,
        "ticket": {
            "name": ticket.name,
            "subject": ticket.subject,
            "description": ticket.description,
            "status": ticket.status,
            "priority": ticket.priority,
            "ticket_type": ticket.ticket_type,
            "customer": ticket.customer,
            "raised_by": ticket.raised_by,
            "created": str(ticket.creation),
            "root_cause": ticket.get("custom_root_cause"),
        },
        "triage": {
            key: ticket.get(f"custom_triage_{key}")
            for key in ("status", "category", "priority", "complexity", "summary", "recommended_track")
        },
        "customer": customer,
        "site": {
            "registry": registry.name,
            "environment": registry.environment,
            "site_url": registry.site_url,
            "apps": apps_for(registry),
        }
        if registry
        else None,
        "connection": run.connection,
        "conversation": _conversation(ticket.name),
        "files": frappe.get_all(
            "File",
            filters={"attached_to_doctype": "HD Ticket", "attached_to_name": ticket.name},
            fields=["file_name", "file_url", "is_private", "file_size"],
        ),
        "previous_runs": frappe.get_all(
            "HDS Copilot Run",
            filters={"ticket": ticket.name, "name": ["!=", run.name]},
            fields=["name", "state", "root_cause_category", "summary"],
            order_by="creation asc",
        ),
    }


def _conversation(ticket: str, limit: int = 20) -> list[dict]:
    messages = [
        {
            "kind": "email",
            "direction": c.sent_or_received,
            "sender": c.sender,
            "content": c.content,
            "at": str(c.creation),
        }
        for c in frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Ticket", "reference_name": ticket},
            fields=["sent_or_received", "sender", "content", "creation"],
            order_by="creation desc",
            limit=limit,
        )
    ]
    messages += [
        {"kind": "comment", "sender": c.commented_by, "content": c.content, "at": str(c.creation)}
        for c in frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": ticket},
            fields=["commented_by", "content", "creation"],
            order_by="creation desc",
            limit=limit,
        )
    ]
    return sorted(messages, key=lambda m: m["at"])[-limit:]
