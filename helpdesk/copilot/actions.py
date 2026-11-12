# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Action approvals (Phase 18): one record and one card for an action someone asks Copilot to
run: a Press action, an AWS change, a repair.

What is approved is the exact payload (the method and its arguments, or the AWS command),
hashed, so what runs is what the approver saw. Nobody approves their own request; the heavy
actions take a senior; every record expires. The caller executes after Approve and marks the
record executed, so the record is the audit trail (docs/tbo-copilot.md, Action approvals).
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_url, now_datetime

from helpdesk.copilot import approvals

ACTION = "HDS Action Approval"
KINDS = ("Press", "AWS", "Repair")
RISKS = ("normal", "senior")
PENDING, APPROVED, REJECTED, EXPIRED, EXECUTED, FAILED = (
    "Pending",
    "Approved",
    "Rejected",
    "Expired",
    "Executed",
    "Failed",
)
EXPIRES_MINUTES = 60  # an approval not acted on in an hour is void: ask again
REMIND_MINUTES = 15
ESCALATE_MINUTES = 45
LOG_CHARS = 2000


def payload_hash(payload) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def waited_minutes(approval, now=None) -> float:
    since = approval.assigned_at or approval.creation
    return ((now or now_datetime()) - get_datetime(since)).total_seconds() / 60


def is_expired(approval, now=None) -> bool:
    return bool(
        approval.expires_at
        and get_datetime(approval.expires_at) <= (now or now_datetime())
    )


# --- asking -------------------------------------------------------------------------------


def open_request(kind: str, digest: str, user: str):
    """The person's own live request for the same payload: Pending, or Approved and not yet run."""
    name = frappe.db.get_value(
        ACTION,
        {
            "kind": kind,
            "payload_hash": digest,
            "requested_by": user,
            "status": ["in", (PENDING, APPROVED)],
            "expires_at": [">", now_datetime()],
        },
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc(ACTION, name) if name else None


def pick_approver(risk: str, exclude: set[str] | None = None) -> str | None:
    """A senior for a senior action, else the least loaded approver; never the requester."""
    allowed = (
        approvals.seniors()
        if risk == "senior"
        else list(dict.fromkeys(approvals.approvers() + approvals.seniors()))
    )
    candidates = [user for user in allowed if user not in (exclude or set())]
    if not candidates:
        return None

    def load(user: str):
        pending = frappe.db.count(ACTION, {"assigned_to": user, "status": PENDING})
        last = frappe.db.get_value(
            ACTION, {"assigned_to": user}, "assigned_at", order_by="assigned_at desc"
        )
        return (pending, get_datetime(last) if last else get_datetime("2000-01-01"))

    return min(candidates, key=load)


def request(
    kind: str,
    title: str,
    details: str,
    payload: dict,
    risk: str = "normal",
    user: str | None = None,
    via: str = "Web",
    ticket: str | None = None,
):
    """A Pending approval for the exact payload, assigned and announced; asking twice for the
    same thing returns the live request instead of a second card."""
    if kind not in KINDS:
        frappe.throw(_("Unknown action kind {0}").format(kind))
    if risk not in RISKS:
        frappe.throw(_("Unknown risk {0}").format(risk))
    if not str(title or "").strip():
        frappe.throw(_("The action needs a title."))
    if not isinstance(payload, dict) or not payload:
        frappe.throw(_("The action needs a payload: what exactly would run."))
    user = user or frappe.session.user
    digest = payload_hash(payload)
    existing = open_request(kind, digest, user)
    if existing:
        return existing
    approver = pick_approver(risk, exclude={user})
    now = now_datetime()
    doc = frappe.get_doc(
        {
            "doctype": ACTION,
            "kind": kind,
            "title": str(title).strip()[:140],
            "details": str(details or "")[:LOG_CHARS],
            "payload": json.dumps(payload, indent=1, default=str, ensure_ascii=False),
            "payload_hash": digest,
            "risk": risk,
            "status": PENDING,
            "requested_by": user,
            "requested_via": via,
            "ticket": ticket,
            "assigned_to": approver,
            "assigned_at": now,
            "expires_at": add_to_date(now, minutes=EXPIRES_MINUTES),
        }
    ).insert(ignore_permissions=True)
    announce(
        doc,
        _("{0} asks to run: {1}").format(frappe.utils.get_fullname(user), doc.title),
    )
    return doc


# --- deciding ----------------------------------------------------------------------------


def may_decide(approval, user: str) -> str | None:
    """Why `user` may not decide `approval`, or None when they may."""
    if user == approval.requested_by:
        return _("You asked for this action, so someone else must approve it.")
    if approval.risk == "senior" and user not in approvals.seniors():
        return _("This action is a heavy one; only a senior approver may approve it.")
    if (
        user not in approvals.approvers()
        and user not in approvals.seniors()
        and user not in approvals.managers()
    ):
        return _(
            "Only the Copilot approvers and the Agent Managers may decide actions."
        )
    return None


def decide(name: str, user: str, approve: bool, note: str = "", via: str = "Web"):
    """The first decision wins; an expired request is refused and marked so."""
    frappe.db.get_value(ACTION, name, "status", for_update=True)
    approval = frappe.get_doc(ACTION, name)
    if approval.status != PENDING:
        who = (
            frappe.utils.get_fullname(approval.decided_by)
            if approval.decided_by
            else _("the hub")
        )
        frappe.throw(
            _("This action is already {0} by {1}.").format(approval.status.lower(), who)
        )
    if is_expired(approval):
        expire(approval)
        frappe.throw(
            _("This request expired after {0} minutes; ask again.").format(
                EXPIRES_MINUTES
            )
        )
    reason = may_decide(approval, user)
    if reason:
        frappe.throw(reason, frappe.PermissionError)
    approval.db_set(
        {
            "status": APPROVED if approve else REJECTED,
            "decided_by": user,
            "decided_at": now_datetime(),
            "decided_via": via,
            "note": (note or "")[:LOG_CHARS],
        },
        update_modified=False,
    )
    refresh_cards(name)
    return {"outcome": "approved" if approve else "rejected", "approval": name}


def expire(approval):
    approval.db_set(
        {"status": EXPIRED, "note": approval.note or _("Not decided in time")},
        update_modified=False,
    )
    refresh_cards(approval.name)


# --- executing ---------------------------------------------------------------------------


def approved_for(kind: str, payload: dict, user: str):
    """The person's live approval of exactly this payload, if someone else approved it."""
    name = frappe.db.get_value(
        ACTION,
        {
            "kind": kind,
            "payload_hash": payload_hash(payload),
            "requested_by": user,
            "status": APPROVED,
            "expires_at": [">", now_datetime()],
        },
        "name",
        order_by="decided_at desc",
    )
    return frappe.get_doc(ACTION, name) if name else None


def mark_executed(name: str, ok: bool, log: str = ""):
    """After the caller ran the approved action: the outcome, kept on the record."""
    frappe.db.get_value(ACTION, name, "status", for_update=True)
    approval = frappe.get_doc(ACTION, name)
    if approval.status != APPROVED:
        frappe.throw(
            _("Only an approved action can be marked as run; this one is {0}.").format(
                approval.status.lower()
            )
        )
    approval.db_set(
        {
            "status": EXECUTED if ok else FAILED,
            "executed_at": now_datetime(),
            "execution_log": (log or "")[:LOG_CHARS],
        },
        update_modified=False,
    )
    refresh_cards(name)
    return approval


# --- reminders and expiry -----------------------------------------------------------------


def remind_and_escalate(now=None):
    """Cron: remind the approver after 15 minutes, hand to the managers after 45, and void what
    was not decided or run within the hour."""
    now = now or now_datetime()
    for name in frappe.get_all(
        ACTION, filters={"status": ["in", (PENDING, APPROVED)]}, pluck="name"
    ):
        approval = frappe.get_doc(ACTION, name)
        if is_expired(approval, now):
            expire(approval)
        elif approval.status == PENDING:
            waited = waited_minutes(approval, now)
            if waited >= ESCALATE_MINUTES and not approval.escalated_at:
                approval.db_set("escalated_at", now, update_modified=False)
                announce(
                    approval,
                    _("An action has waited {0} minutes for approval: {1}").format(
                        int(waited), approval.title
                    ),
                    also=approvals.managers(),
                    escalate=True,
                )
            elif waited >= REMIND_MINUTES and not approval.reminded_at:
                approval.db_set("reminded_at", now, update_modified=False)
                announce(
                    approval,
                    _("Reminder: an action waits for your approval: {0}").format(
                        approval.title
                    ),
                )
        frappe.db.commit()  # one record at a time; a failure on the next must not undo this - nosemgrep


# --- cards ---------------------------------------------------------------------------------


def card(approval) -> dict:
    """The action waiting for approval, with Approve and Reject (a reason)."""
    from helpdesk.copilot.assistant import button
    from helpdesk.copilot.assistant import card as make_card

    if isinstance(approval, str):
        approval = frappe.get_doc(ACTION, approval)
    if approval.status != PENDING:
        return decided_card(approval)
    return make_card(
        _("{0} action needs your approval: {1}").format(approval.kind, approval.title),
        [
            approval.details,
            _("Asked by {0} via {1}").format(
                frappe.utils.get_fullname(approval.requested_by),
                approval.requested_via or _("the hub"),
            ),
            _("Expires at {0}").format(
                frappe.utils.format_datetime(approval.expires_at, "d MMM, HH:mm")
            ),
        ],
        facts=[
            (_("Kind"), approval.kind),
            (
                _("Risk"),
                _("senior approver needed")
                if approval.risk == "senior"
                else _("normal"),
            ),
            (_("Ticket"), approval.ticket),
        ],
        links=[
            (
                _("Open the ticket"),
                get_url(f"/helpdesk/tickets/{approval.ticket}")
                if approval.ticket
                else None,
            )
        ],
        actions=[
            button(_("Approve"), "action_approve", "positive", approval=approval.name),
            button(_("Reject"), "action_reject", "destructive", approval=approval.name),
        ],
        inputs=[
            {"id": "reason", "label": _("Reason (needed to reject)"), "multiline": True}
        ],
    )


def decided_card(approval) -> dict:
    from helpdesk.copilot.assistant import card as make_card

    who = (
        frappe.utils.get_fullname(approval.decided_by)
        if approval.decided_by
        else _("TBO Support")
    )
    when = (
        frappe.utils.format_datetime(approval.decided_at, "d MMM, HH:mm")
        if approval.decided_at
        else ""
    )
    status = {
        APPROVED: _("Approved"),
        REJECTED: _("Rejected"),
        EXPIRED: _("Expired"),
        EXECUTED: _("Approved and run"),
        FAILED: _("Approved, but it failed"),
    }.get(approval.status, approval.status)
    lines = [_("{0} by {1}{2}").format(status, who, f" at {when}" if when else "")]
    if approval.status == EXPIRED:
        lines = [
            _("Not decided within {0} minutes; ask again.").format(EXPIRES_MINUTES)
        ]
    if approval.note:
        lines.append(approval.note)
    if approval.execution_log:
        lines.append(approval.execution_log[:300])
    return make_card(
        _("{0}: {1}").format(approval.title, status.lower()),
        lines,
        links=[
            (
                _("Open the ticket"),
                get_url(f"/helpdesk/tickets/{approval.ticket}")
                if approval.ticket
                else None,
            )
        ],
        tone="good"
        if approval.status in (APPROVED, EXECUTED)
        else "warning"
        if approval.status == FAILED
        else "default",
    )


def send_card(person: str, approval) -> str | None:
    """The action's card to one person (Teams, else the panel); the channel used. Never stops the caller."""
    from helpdesk.copilot import assistant

    try:
        return assistant.send(
            person,
            card(approval),
            action_approval=approval.name,
            ticket=approval.ticket,
        )
    except Exception:
        frappe.log_error(
            title=f"Copilot could not send the action card of {approval.name}"
        )
        return None


def announce(
    approval, subject: str, also: list[str] | None = None, escalate: bool = False
):
    """The approver (or, with none, the Agent Managers) gets the card with its buttons: in Teams
    when the bot can reach them, else in the TBO Support panel plus the usual chat message or email."""
    from helpdesk.work_reminders import helpdesk_path, new_notification, notify_users

    people = [approval.assigned_to] if approval.assigned_to else approvals.managers()
    people = list(dict.fromkeys(people + (also or [])))
    doctype, name = (
        ("HD Ticket", approval.ticket) if approval.ticket else (ACTION, approval.name)
    )
    by_bot = []
    for person in people:
        if send_card(person, approval) == "Teams":
            by_bot.append(person)
            new_notification(
                person,
                doctype,
                name,
                subject,
                helpdesk_path(doctype, name),
                deliver=False,
            )
    notify_users(
        [p for p in people if p not in by_bot],
        doctype,
        name,
        subject,
        escalate=escalate,
        once=False,
    )


def refresh_cards(name: str):
    """After a decision or the run, every copy of the card shows it."""
    from helpdesk.copilot import teams
    from helpdesk.copilot.assistant import MESSAGE

    try:
        approval = frappe.get_doc(ACTION, name)
        if approval.status == PENDING:
            return
        reply = decided_card(approval)
        for row in frappe.get_all(
            MESSAGE,
            filters={
                "action_approval": name,
                "direction": "Out",
                "card": ["is", "set"],
            },
            fields=["name", "user", "teams_activity"],
        ):
            frappe.db.set_value(
                MESSAGE,
                row.name,
                "card",
                json.dumps(reply, ensure_ascii=False),
                update_modified=False,
            )
            if row.teams_activity and teams.enabled():
                teams.update_card(row.user, row.teams_activity, reply)
            frappe.publish_realtime(
                "helpdesk:copilot-chat",
                {"message": row.name},
                user=row.user,
                after_commit=True,
            )
    except Exception:
        frappe.log_error(title=f"Copilot could not update the cards of {name}")


def as_dict(approval) -> dict:
    """What a caller (the desktop plugin, the panel) needs to know about a request."""
    return {
        "name": approval.name,
        "kind": approval.kind,
        "title": approval.title,
        "status": approval.status,
        "risk": approval.risk,
        "requested_by": approval.requested_by,
        "assigned_to": approval.assigned_to,
        "decided_by": approval.decided_by,
        "decided_at": str(approval.decided_at or "") or None,
        "note": approval.note,
        "expires_at": str(approval.expires_at or "") or None,
        "executed_at": str(approval.executed_at or "") or None,
        "execution_log": approval.execution_log,
        "payload_hash": approval.payload_hash,
        "ticket": approval.ticket,
    }
