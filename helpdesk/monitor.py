# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Monitor intake (Phase 18): machines tell the hub what they see.

The watcher server opens and resolves alerts, files follow-up tasks and sends a heartbeat.
The hub turns an alert into one ticket for the internal customer (raised by TBO AI, one per
key while it is open, "Resolved by monitor" when healthy again), a follow-up into one task in
the internal project, and tells the Agent Managers when the watcher goes quiet. The hub's own
self-check hands the watcher the numbers it cannot see from outside
(docs/tbo-copilot.md, Monitor intake).
"""

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import escape_html, get_datetime, now_datetime

from helpdesk import intake
from helpdesk.automation import as_automation_user, automation_user
from helpdesk.consts import ALERT_TICKET_TYPE
from helpdesk.intake import AlertSubject
from helpdesk.utils import add_assignment

ROLE = "TBO Monitor"
USER = "watcher@teambackoffice.com"
SETTINGS = "HDS Hub Settings"
SOURCES = ("watcher",)
OPEN_STATES = ("open", "firing", "alerting")
RESOLVED_STATES = intake.RESOLVED_STATES | {"resolve", "resolved"}
SEVERITIES = ("critical", "high", "warning", "info")
SEVERITY_PRIORITY = {
    "critical": "Urgent",
    "high": "High",
    "warning": "Medium",
    "info": "Low",
}
DEFAULT_QUIET_MINUTES = 3
TEXT_CHARS = 4000
EVIDENCE_CHARS = 6000
HEARTBEAT_KEY = "monitor:heartbeat:{source}"
LAST_SEEN_KEY = "monitor:last-seen:{source}"
QUIET_TOLD_KEY = "monitor:quiet-told:{source}"
QUIET_ONCE_KEY = "monitor:quiet-once:{source}"
OPEN_TASK_STATES = ("Open", "Working", "Pending Review", "On Hold", "Overdue")


# --- the role and the user, made on migrate ------------------------------------------------


def ensure_role():
    """API-only, so no desk access: it may open alerts, tasks and heartbeats, nothing else."""
    if frappe.db.exists("Role", ROLE):
        return
    frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0}).insert(
        ignore_permissions=True
    )


def ensure_user() -> str:
    """The watcher's own user: a website user with the monitor role; DevOps makes its API key."""
    ensure_role()
    if not frappe.db.exists("User", USER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": USER,
                "first_name": "TBO Watcher",
                "user_type": "Website User",
                "send_welcome_email": 0,
                "enabled": 1,
                "roles": [{"role": ROLE}],
            }
        ).insert(ignore_permissions=True)
    elif ROLE not in frappe.get_roles(USER):
        frappe.get_doc("User", USER).add_roles(ROLE)
    return USER


def monitor_only():
    # frappe.only_for is a no-op in tests, so the role is checked directly
    if ROLE not in frappe.get_roles():
        frappe.throw(_("Only a monitor may call this."), frappe.PermissionError)


def settings() -> dict:
    doc = frappe.get_cached_doc(SETTINGS)
    return {
        "internal_customer": doc.get("internal_customer"),
        "internal_project": doc.get("internal_project"),
        "quiet_minutes": max(
            int(doc.get("monitor_quiet_minutes") or DEFAULT_QUIET_MINUTES), 1
        ),
    }


# --- alerts ----------------------------------------------------------------------------------


def normalise_key(key) -> str:
    key = " ".join(str(key or "").split()).casefold()[: intake.MAX_KEY_LENGTH]
    if not key:
        frappe.throw(_("An alert needs a key."))
    return key


def find_open(key: str) -> str | None:
    """The open alert ticket for the key, if any (the same lookup the mail intake uses)."""
    return intake.open_alert(AlertSubject(resolved=False, key=key, labels=frozenset()))


def _text(value, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, indent=1, ensure_ascii=False, default=str)
    return value[:limit]


def describe(
    text: str, severity: str, evidence, runbook: str | None, source: str
) -> str:
    facts = [(_("Severity"), severity), (_("Source"), source)]
    if runbook:
        facts.append((_("Runbook"), runbook))
    html = ""
    if text:
        html += f"<p>{escape_html(text)}</p>"
    html += (
        "<p>"
        + " · ".join(
            f"<b>{escape_html(str(k))}:</b> {escape_html(str(v))}" for k, v in facts
        )
        + "</p>"
    )
    if evidence:
        html += f"<pre>{escape_html(_text(evidence, EVIDENCE_CHARS))}</pre>"
    return html


def monitor_update(text: str, evidence=None) -> str:
    html = "<p><b>{0}</b> {1}</p>".format(
        escape_html(_("Monitor update:")), escape_html(text or "")
    )
    if evidence:
        html += f"<pre>{escape_html(_text(evidence, EVIDENCE_CHARS))}</pre>"
    return html


def open_alert(
    key: str,
    title: str,
    text: str = "",
    severity: str = "warning",
    evidence=None,
    runbook: str | None = None,
    source: str = "watcher",
) -> dict:
    """The ticket for the key: the open one, with this update on it, or a new one."""
    existing = find_open(key)
    if existing:
        if text or evidence:
            intake.add_comment(existing, monitor_update(text, evidence))
        return {"ticket": existing, "action": "updated"}
    customer = settings()["internal_customer"]
    if not customer:
        frappe.throw(
            _(
                "Set the internal customer in HDS Hub Settings before the monitor opens tickets."
            )
        )
    values = {
        "doctype": "HD Ticket",
        "subject": " ".join(str(title or key).split())[:140],
        "description": describe(text, severity, evidence, runbook, source),
        "raised_by": automation_user(),
        "customer": customer,
        "ticket_type": ALERT_TICKET_TYPE,
        "alert_key": key,
    }
    priority = SEVERITY_PRIORITY.get(severity)
    if priority and frappe.db.exists("HD Ticket Priority", priority):
        values["priority"] = priority
    with as_automation_user():
        ticket = frappe.get_doc(values)
        ticket.flags.skip_acknowledgement = True  # nobody to acknowledge to: it is us
        ticket.flags.no_copilot_run = (
            True  # an infrastructure alert, not a customer's problem
        )
        ticket.insert(ignore_permissions=True)  # after_insert announces the alert
    return {"ticket": ticket.name, "action": "opened"}


def resolve_alert(key: str, text: str = "", evidence=None) -> dict:
    """Healthy again: the open ticket is resolved by the monitor; nothing open, nothing done."""
    existing = find_open(key)
    if not existing:
        return {"ticket": None, "action": "noop"}
    intake.add_comment(existing, monitor_update(text or _("Resolved"), evidence))
    doc = frappe.get_doc("HD Ticket", existing)
    doc.status = intake.resolved_status()
    intake.save_as_automation(doc)
    intake.announce(existing, _("Alert resolved: {0}").format(doc.subject))
    return {"ticket": existing, "action": "resolved"}


def alert(
    key,
    state: str,
    title: str = "",
    text: str = "",
    severity: str = "warning",
    evidence=None,
    runbook: str | None = None,
    source: str = "watcher",
) -> dict:
    key = normalise_key(key)
    state = str(state or "").strip().casefold()
    severity = severity if severity in SEVERITIES else "warning"
    text = _text(text, TEXT_CHARS)
    if state in OPEN_STATES:
        return open_alert(key, title, text, severity, evidence, runbook, source)
    if state in RESOLVED_STATES:
        return resolve_alert(key, text, evidence)
    frappe.throw(_("Unknown alert state {0}: open or resolved.").format(state))


# --- follow-up tasks -----------------------------------------------------------------------


def open_followup(key: str) -> str | None:
    return frappe.db.get_value(
        "Task",
        {"custom_monitor_key": key, "status": ["in", OPEN_TASK_STATES]},
        "name",
        order_by="creation desc",
    )


def followup(
    key,
    subject: str,
    details: str = "",
    priority: str = "Medium",
    category: str = "DevOps",
    assign_to: str | None = None,
) -> dict:
    """A slow-burning issue becomes one task in the internal project, once per key while open;
    infrastructure work, so a DevOps task, given to `assign_to` when there is one."""
    key = normalise_key(key)
    existing = open_followup(key)
    if existing:
        return {"task": existing, "action": "exists"}
    project = settings()["internal_project"]
    if not project:
        frappe.throw(
            _(
                "Set the internal project in HDS Hub Settings before the monitor files tasks."
            )
        )
    if priority not in ("Low", "Medium", "High", "Urgent"):
        priority = "Medium"
    with as_automation_user():
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": " ".join(str(subject or key).split())[:140],
                "description": f"<p>{escape_html(_text(details, TEXT_CHARS))}</p>"
                if details
                else "",
                "project": project,
                "status": "Open",
                "priority": priority,
                "custom_category": category,
                "custom_monitor_key": key,
            }
        ).insert(ignore_permissions=True)
    if assign_to:
        add_assignment(
            {
                "assign_to": [assign_to],
                "doctype": "Task",
                "name": task.name,
                "assigned_by": automation_user(),
            },
            ignore_permissions=True,
        )
    return {"task": task.name, "action": "created"}


# --- heartbeats ------------------------------------------------------------------------------


def check_source(source: str) -> str:
    if source not in SOURCES:
        frappe.throw(_("Unknown monitor {0}.").format(source))
    return source


def heartbeat(source: str = "watcher") -> dict:
    """Every minute from the watcher; silence for the quiet time tells the managers."""
    source = check_source(source)
    now = now_datetime()
    frappe.cache.set_value(
        HEARTBEAT_KEY.format(source=source),
        str(now),
        expires_in_sec=settings()["quiet_minutes"] * 60,
    )
    frappe.cache.set_value(LAST_SEEN_KEY.format(source=source), str(now))
    return {"ok": True, "at": str(now)}


def _read(key: str):
    # expires=True: read Redis, never a value this request cached earlier (a lapsed heartbeat
    # must read as gone, a new one as there)
    return frappe.cache.get_value(key, expires=True)


def last_heartbeat(source: str):
    value = _read(HEARTBEAT_KEY.format(source=source))
    return get_datetime(value) if value else None


def last_seen(source: str):
    value = _read(LAST_SEEN_KEY.format(source=source))
    return get_datetime(value) if value else None


def watch_heartbeats(now=None):
    """Every 5 minutes: a monitor that has gone quiet is reported to the Agent Managers, once an
    hour while it lasts, and once more when it is back. A monitor never heard from is not missed."""
    from helpdesk.copilot.pilot import _once, _tell_managers

    now = now or now_datetime()
    quiet_minutes = settings()["quiet_minutes"]
    for source in SOURCES:
        seen = last_seen(source)
        if not seen:
            continue
        told_key = QUIET_TOLD_KEY.format(source=source)
        if last_heartbeat(source):
            if _read(told_key):
                frappe.cache.delete_value(told_key)
                _tell_managers(
                    _(
                        "The {0} is back: its heartbeat reached TBO Support again."
                    ).format(source),
                    SETTINGS,
                )
            continue
        if now - seen < timedelta(minutes=quiet_minutes):
            continue
        frappe.cache.set_value(told_key, str(now), expires_in_sec=7 * 86400)
        if _once(QUIET_ONCE_KEY.format(source=source), 3600):
            _tell_managers(
                _(
                    "The {0} has been quiet since {1}: no heartbeat for {2} minutes. Nobody is watching the servers until it is back."
                ).format(
                    source,
                    frappe.utils.format_datetime(seen, "d MMM, HH:mm"),
                    int((now - seen).total_seconds() // 60),
                ),
                SETTINGS,
            )


# --- the hub's own numbers ----------------------------------------------------------------


def _last_run(method: str):
    """When a scheduled job last completed, from its logs."""
    job_type = frappe.db.get_value("Scheduled Job Type", {"method": method}, "name")
    if not job_type:
        return None
    rows = frappe.get_all(
        "Scheduled Job Log",
        filters={"scheduled_job_type": job_type, "status": "Complete"},
        fields=["creation"],
        order_by="creation desc",
        limit_page_length=1,
    )
    return str(rows[0].creation) if rows else None


def _last_job_at():
    rows = frappe.get_all(
        "Scheduled Job Log",
        fields=["creation"],
        order_by="creation desc",
        limit_page_length=1,
    )
    return str(rows[0].creation) if rows else None


def _queues() -> dict:
    from frappe.utils.background_jobs import get_queue, get_queue_list

    lengths = {}
    for name in get_queue_list():
        try:
            lengths[name] = get_queue(name).count
        except Exception:
            lengths[name] = None
    return lengths


def _failed_jobs() -> int | None:
    from frappe.utils.background_jobs import get_queue, get_queue_list
    from rq.registry import FailedJobRegistry

    total = 0
    for name in get_queue_list():
        total += FailedJobRegistry(queue=get_queue(name)).count
    return total


def _guard(fn, default=None):
    try:
        return fn()
    except Exception:
        frappe.log_error(title=f"Monitor self-check: {fn.__name__} failed")
        return default


def self_check() -> dict:
    """What the watcher cannot see from outside: the scheduler, the queues, stuck mail, the
    error rate, and when the watches last ran. Numbers only; the watcher applies the thresholds."""
    from frappe.utils.scheduler import is_scheduler_disabled

    now = now_datetime()
    return {
        "now": str(now),
        "scheduler_enabled": _guard(lambda: not is_scheduler_disabled(), None),
        "last_scheduled_job_at": _guard(_last_job_at),
        "queues": _guard(_queues, {}),
        "failed_jobs": _guard(_failed_jobs),
        "email_queue_stuck": _guard(
            lambda: frappe.db.count(
                "Email Queue",
                {
                    "status": "Not Sent",
                    "creation": ["<", now - timedelta(minutes=30)],
                },
            )
        ),
        "error_log_10m": _guard(
            lambda: frappe.db.count(
                "Error Log", {"creation": [">=", now - timedelta(minutes=10)]}
            )
        ),
        "error_watch_last_run": _guard(
            lambda: _last_run("helpdesk.copilot.watch.run_due")
        ),
        "deploy_train_last_run": _guard(
            lambda: _last_run("helpdesk.copilot.deploy.run_due")
        ),
        "worker_last_seen": _guard(_worker_last_seen),
    }


def _worker_last_seen():
    from helpdesk.copilot import board

    workers = board.workers()
    seen = [w.get("last_seen") for w in workers if w.get("last_seen")]
    return str(max(seen)) if seen else None
