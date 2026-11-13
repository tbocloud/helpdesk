# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Pilot feedback: "report a problem" from Teams, the panel or the desktop app becomes a task
(TBO Copilot Phase 21).

The task goes to the feedback project in HDS Copilot Settings (else the hub's internal project),
created by TBO AI so the person needs no rights in that project. It holds what the person wrote,
who and where, and their last Copilot actions by id (tool, status, record, time), never the text
of those actions, so no customer data travels into the feedback project.
"""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import escape_html, get_url

from helpdesk.automation import as_automation_user

MAX_TEXT = 4000
RECENT_ACTIONS = 5
REPORTS_PER_HOUR = 10
CATEGORY = "Development"


def project() -> str:
    from helpdesk.copilot import settings as copilot_settings

    chosen = copilot_settings.get_settings().get(
        "feedback_project"
    ) or frappe.db.get_single_value("HDS Hub Settings", "internal_project")
    if not chosen:
        frappe.throw(
            _("Set where feedback goes: HDS Copilot Settings, Feedback tasks go to.")
        )
    return chosen


def check_rate(user: str):
    key = frappe.cache.make_key(f"copilot-feedback:{user}")
    count = int(frappe.cache.incr(key))
    if count == 1:
        frappe.cache.expire(key, 3600)
    if count > REPORTS_PER_HOUR:
        frappe.throw(
            _("That is {0} reports this hour; write the rest in one.").format(
                REPORTS_PER_HOUR
            )
        )


def recent_actions(user: str) -> list[dict]:
    """The person's last Copilot actions, by id only."""
    return frappe.get_all(
        "HDS Copilot Call Log",
        filters={"user": user},
        fields=["creation", "kind", "tool", "status", "ticket", "task", "run"],
        order_by="creation desc",
        limit=RECENT_ACTIONS,
    )


def describe(user: str, channel: str, text: str) -> str:
    rows = recent_actions(user)
    actions = "".join(
        "<li>{0} · {1} · {2} · {3}{4}</li>".format(
            escape_html(str(r.creation)[:16]),
            escape_html(r.kind or ""),
            escape_html(r.tool or ""),
            escape_html(r.status or ""),
            escape_html(" · " + ", ".join(x for x in (r.ticket, r.task, r.run) if x))
            if (r.ticket or r.task or r.run)
            else "",
        )
        for r in rows
    )
    return (
        f"<p>{escape_html(text)}</p>"
        f"<p><b>{escape_html(_('From'))}:</b> {escape_html(user)} · {escape_html(channel)}</p>"
        + (
            f"<p><b>{escape_html(_('Their last Copilot actions'))}:</b></p><ul>{actions}</ul>"
            if actions
            else ""
        )
    )


def report(user: str, channel: str, text: str) -> dict:
    """The person's report as a task in the feedback project; answers with its name and link."""
    text = (
        " ".join(str(text or "").split())
        if "\n" not in str(text or "")
        else str(text).strip()
    )
    if not text:
        frappe.throw(
            _(
                'Write what went wrong after "report a problem:": what you asked, and what happened.'
            )
        )
    text = text[:MAX_TEXT]
    check_rate(user)
    first_line = text.split("\n")[0]
    subject = _("Copilot feedback: {0}").format(
        first_line[:110] + ("…" if len(first_line) > 110 else "")
    )
    with as_automation_user():
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": subject[:140],
                "project": project(),
                "status": "Open",
                "priority": "Medium",
                "custom_category": CATEGORY,
                "description": describe(user, channel, text),
            }
        ).insert(ignore_permissions=True)
    from helpdesk.copilot import assistant

    assistant.log_action(
        user, channel, "report_problem", "OK", {"task": task.name, "text": text}
    )
    # My Work opens the task's details (?task=), as the hub's reminders link it
    return {
        "task": task.name,
        "url": get_url("/helpdesk/my-work?" + urlencode({"task": task.name})),
        "project": task.project,
    }
