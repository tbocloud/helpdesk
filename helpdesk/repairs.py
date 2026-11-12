# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Auto-repair (TBO Copilot Phase 19): what TBO Support keeps of the watcher's repairs.

The watcher runs the runbooks; the hub holds the switch and the record:
- the **switch**: auto-repair paused or not, the runbooks turned off, the hourly cap (HDS Hub
  Settings → Auto-repair; Teams "pause auto-repair" / "resume auto-repair");
- one **HDS Repair** per attempt, credited to TBO AI, with the evidence, the exact action and the
  check after; its note goes on the alert's ticket;
- an approval-level repair is an **action approval** of kind Repair, requested by the watcher's
  user; the watcher runs it once it is approved and says how it went;
- a failed repair puts the ticket with the internal project's DevOps Engineers;
- every Monday, the week's repairs to the channel, and a root-cause task for a repair that keeps
  coming back (docs/tbo-copilot.md, Auto-repair).
"""

import json
from datetime import timedelta

import frappe
import requests
from frappe import _
from frappe.utils import escape_html, now_datetime

from helpdesk import intake, monitor
from helpdesk.automation import automation_user
from helpdesk.copilot import actions, approvals
from helpdesk.utils import add_assignment

REPAIR = "HDS Repair"
SETTINGS = "HDS Hub Settings"
KIND = "Repair"
LEVELS = ("Automatic", "Approval")
OUTCOMES = ("Fixed", "Not fixed", "Refused", "Paused", "Skipped")
DEFAULT_MAX_PER_HOUR = 6
DEVOPS_ROLE = "DevOps Engineer"
RECUR_COUNT = 3  # the same runbook on the same target this often in RECUR_DAYS: find the root cause
RECUR_DAYS = 7
JSON_CHARS = 6000
TEXT_CHARS = 2000
NAME_CHARS = 140


def _json(value) -> str | None:
    if value in (None, "", {}, []):
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return json.dumps({"text": value[:JSON_CHARS]})
    return json.dumps(value, indent=1, ensure_ascii=False, default=str)[:JSON_CHARS]


def _clean(value, limit: int = NAME_CHARS) -> str:
    return " ".join(str(value or "").split())[:limit]


# --- the switch -------------------------------------------------------------------------------


def policy() -> dict:
    """What the watcher reads every minute."""
    doc = frappe.get_cached_doc(SETTINGS)
    return {
        "paused": bool(doc.get("auto_repair_paused")),
        "paused_by": doc.get("auto_repair_paused_by"),
        "paused_at": str(doc.get("auto_repair_paused_at") or "") or None,
        "reason": doc.get("auto_repair_pause_reason"),
        "off": [
            line.strip()
            for line in (doc.get("auto_repair_off") or "").splitlines()
            if line.strip()
        ],
        "max_per_hour": int(
            doc.get("auto_repair_max_per_hour") or DEFAULT_MAX_PER_HOUR
        ),
    }


def devops_engineers() -> list[str]:
    """The enabled DevOps Engineers of the internal project."""
    from helpdesk.ticket_assignment import project_members

    project = monitor.settings()["internal_project"]
    people = project_members([project], [DEVOPS_ROLE]) if project else []
    return [u for u in people if frappe.db.get_value("User", u, "enabled")]


def may_pause(user: str) -> bool:
    return (
        user in approvals.managers()
        or user in devops_engineers()
        or "System Manager" in frappe.get_roles(user)
    )


def set_paused(user: str, paused: bool, reason: str = "") -> dict:
    """Pause or resume every repair; the channel hears either way."""
    if not may_pause(user):
        frappe.throw(
            _(
                "Only the Agent Managers and the internal project's DevOps Engineers may pause or resume auto-repair."
            ),
            frappe.PermissionError,
        )
    frappe.db.set_single_value(
        SETTINGS,
        {
            "auto_repair_paused": 1 if paused else 0,
            "auto_repair_paused_by": user if paused else None,
            "auto_repair_paused_at": now_datetime() if paused else None,
            "auto_repair_pause_reason": _clean(reason, TEXT_CHARS) if paused else None,
        },
    )
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    who = frappe.utils.get_fullname(user)
    if paused:
        text = _(
            'Auto-repair is paused by {0}{1}. The watcher still watches and opens tickets; it repairs nothing until someone says "resume auto-repair".'
        ).format(who, f" ({_clean(reason, 200)})" if reason else "")
    else:
        text = _("Auto-repair is running again ({0}).").format(who)
    tell_channel(text)
    return policy()


# --- the record -------------------------------------------------------------------------------


def started(
    key: str,
    runbook: str,
    level: str = "Automatic",
    target: str = "",
    attempt: int = 1,
    evidence=None,
    action=None,
) -> dict:
    """One attempt begins: the record, linked to the alert's open ticket if there is one."""
    key = monitor.normalise_key(key)
    if level not in LEVELS:
        frappe.throw(_("Unknown repair level {0}").format(level))
    doc = frappe.get_doc(
        {
            "doctype": REPAIR,
            "runbook": _clean(runbook),
            "target": _clean(target),
            "level": level,
            "status": "Running",
            "alert_key": key,
            "ticket": monitor.find_open(key),
            "attempt": max(int(attempt or 1), 1),
            "evidence": _json(evidence),
            "action": _json(action),
            "started_at": now_datetime(),
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert()
    doc.db_set("owner", automation_user(), update_modified=False)  # the hub's own work
    return {"repair": doc.name, "ticket": doc.ticket}


def finished(
    repair: str,
    outcome: str,
    text: str = "",
    verify=None,
    escalate: bool = False,
) -> dict:
    """The attempt's outcome: the note on the ticket, Teams for a fix or a hand-over, and the
    ticket to DevOps when the watcher gives up."""
    if outcome not in OUTCOMES:
        frappe.throw(_("Unknown repair outcome {0}").format(outcome))
    doc = frappe.get_doc(REPAIR, repair)
    if doc.status != "Running":
        return {"repair": doc.name, "outcome": doc.status, "ticket": doc.ticket}
    ticket = doc.ticket or monitor.find_open(doc.alert_key)
    note = _clean(text, TEXT_CHARS)
    doc.db_set(
        {
            "status": outcome,
            "text": note,
            "verify": _json(verify),
            "finished_at": now_datetime(),
            "ticket": ticket,
        },
        update_modified=False,
    )
    if ticket:
        intake.add_comment(
            ticket,
            "<p><b>{0}</b> {1}</p>".format(
                escape_html(
                    _("Copilot repair ({0}, attempt {1}): {2}.").format(
                        doc.runbook, doc.attempt, outcome.lower()
                    )
                ),
                escape_html(note),
            ),
        )
    assigned = None
    if escalate:
        assigned = assign_to_devops(
            ticket,
            _("Copilot could not repair it ({0}): {1}").format(doc.runbook, note[:300]),
        )
        doc.db_set({"escalated": 1, "assigned_to": assigned}, update_modified=False)
        tell_channel(
            _("⚠️ Copilot could not repair {0} ({1}); {2} has the ticket. {3}").format(
                doc.target or doc.alert_key,
                doc.runbook,
                frappe.utils.get_fullname(assigned) if assigned else _("nobody yet"),
                note[:300],
            ),
            ticket,
        )
    elif outcome == "Fixed" and doc.level == "Automatic":
        tell_channel(
            _("🔧 Fixed by Copilot: {0} ({1}). {2}").format(
                doc.target or doc.alert_key, doc.runbook, note[:400]
            ),
            ticket,
        )
    return {
        "repair": doc.name,
        "outcome": outcome,
        "ticket": ticket,
        "assigned_to": assigned,
    }


def assign_to_devops(ticket: str | None, why: str) -> str | None:
    """The least busy DevOps Engineer of the internal project, else the least busy Agent
    Manager; nobody when there is no ticket."""
    from helpdesk.ticket_assignment import _open_assignees, least_busy

    if not ticket:
        return None
    people = devops_engineers() or approvals.managers()
    current = _open_assignees(ticket)
    already = [p for p in current if p in people]
    if already:
        return already[0]
    to = least_busy(people)
    if not to:
        return None
    add_assignment(
        {
            "assign_to": [to],
            "doctype": "HD Ticket",
            "name": str(ticket),
            "description": why[:500],
            "assigned_by": automation_user(),
        },
        ignore_permissions=True,
    )
    return to


# --- repairs that wait for an approver --------------------------------------------------------


def request(
    key: str,
    runbook: str,
    target: str,
    title: str,
    why: str,
    details: str,
    payload: dict,
    risk: str = "normal",
) -> dict:
    """An action approval of kind Repair, asked by the watcher's user, on the alert's ticket.

    The stored payload keeps the runbook, the target and the key beside what the watcher sent,
    so `approved` can hand all four back; the watcher matches on `payload_hash`, the hash of the
    payload exactly as it sent it.
    """
    if not isinstance(payload, dict) or not payload:
        frappe.throw(_("A repair request needs its payload."))
    key = monitor.normalise_key(key)
    stored = {
        "runbook": _clean(runbook),
        "target": _clean(target),
        "key": key,
        "payload": payload,
    }
    doc = actions.request(
        KIND,
        _clean(title) or _("Repair: {0} on {1}").format(runbook, target),
        "\n".join(
            part
            for part in (
                _("Why: {0}").format(_clean(why, 600)) if why else "",
                str(details or "")[:1200],
            )
            if part
        ),
        stored,
        risk=risk if risk in actions.RISKS else "normal",
        user=monitor.USER,
        via="Watcher",
        ticket=monitor.find_open(key),
    )
    return {
        "approval": doc.name,
        "status": doc.status,
        "assigned_to": doc.assigned_to,
        "expires_at": str(doc.expires_at or "") or None,
    }


def approved() -> list[dict]:
    """The watcher's repairs that someone approved and nobody has run yet."""
    rows = frappe.get_all(
        actions.ACTION,
        filters={
            "kind": KIND,
            "requested_by": monitor.USER,
            "status": actions.APPROVED,
            "expires_at": [">", now_datetime()],
        },
        fields=["name", "title", "payload", "decided_by", "ticket"],
        order_by="decided_at asc",
    )
    out = []
    for row in rows:
        stored = frappe.parse_json(row.payload or "{}") or {}
        inner = stored.get("payload") or {}
        out.append(
            {
                "approval": row.name,
                "runbook": stored.get("runbook"),
                "target": stored.get("target"),
                "key": stored.get("key"),
                "payload": inner,
                "payload_hash": actions.payload_hash(inner),
                "title": row.title,
                "decided_by": row.decided_by,
                "ticket": row.ticket,
            }
        )
    return out


def executed(approval: str, ok, log: str = "") -> dict:
    doc = frappe.get_doc(actions.ACTION, approval)
    if doc.kind != KIND or doc.requested_by != monitor.USER:
        frappe.throw(_("Not one of the watcher's repairs."), frappe.PermissionError)
    return actions.as_dict(actions.mark_executed(approval, bool(ok), log or ""))


# --- the week -----------------------------------------------------------------------------------


def week_rows(now=None) -> list[dict]:
    since = (now or now_datetime()) - timedelta(days=RECUR_DAYS)
    return frappe.get_all(
        REPAIR,
        filters={"started_at": [">=", since], "status": ["!=", "Running"]},
        fields=["runbook", "target", "status", "escalated", "started_at"],
        order_by="started_at asc",
    )


def weekly(now=None):
    """Monday 09:00: the week's repairs to the channel; a repair that came back RECUR_COUNT
    times on the same target becomes a root-cause task for DevOps."""
    from helpdesk.ticket_assignment import least_busy

    rows = week_rows(now)
    if not rows:
        return
    by_runbook, by_target = {}, {}
    for row in rows:
        by_runbook[row.runbook] = by_runbook.get(row.runbook, 0) + 1
        by_target.setdefault((row.runbook, row.target), []).append(row.started_at)
    fixed = sum(1 for r in rows if r.status == "Fixed")
    handed = sum(1 for r in rows if r.escalated)
    parts = ", ".join(
        f"{name} {count}"
        for name, count in sorted(by_runbook.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    tell_channel(
        _("Repairs last week: {0} ({1}); {2} worked, {3} went to DevOps.").format(
            len(rows), parts, fixed, handed
        )
    )
    assignee = None
    for (runbook, target), times in by_target.items():
        if len(times) < RECUR_COUNT:
            continue
        assignee = assignee or least_busy(devops_engineers())
        when = ", ".join(
            frappe.utils.format_datetime(t, "EEE d MMM HH:mm") for t in times
        )
        try:
            monitor.followup(
                f"root-cause:{runbook}:{target}",
                _("Find the root cause: {0} on {1} ran {2} times this week").format(
                    runbook, target or _("the servers"), len(times)
                ),
                _(
                    "Copilot repaired it each time ({0}); something keeps causing it."
                ).format(when),
                priority="High",
                category="DevOps",
                assign_to=assignee,
            )
        except frappe.ValidationError:
            frappe.log_error(title="Auto-repair: root-cause task not filed")


# --- the channel ----------------------------------------------------------------------------------


def tell_channel(text: str, ticket: str | None = None):
    """A line to the team's channel after the commit (an alert ticket's line when there is one)."""
    from helpdesk.chat_notifications import is_enabled

    if not is_enabled():
        return
    frappe.enqueue(
        "helpdesk.repairs.post_now",
        text=text,
        path=f"/tickets/{ticket}" if ticket else None,
        queue="short",
        enqueue_after_commit=True,
    )


def post_now(text: str, path: str | None = None):
    from helpdesk.chat_notifications import ChatError, helpdesk_url, post_to_channel

    try:
        post_to_channel(text, helpdesk_url(path) if path else None)
    except (ChatError, requests.RequestException) as e:
        # not log_error: the error digest posts to the same channel, which just failed
        frappe.logger("helpdesk").warning(f"Repair line not posted to the channel: {e}")
