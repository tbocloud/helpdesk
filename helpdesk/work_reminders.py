"""Deadline reminders and escalation for tasks and tickets.

Tasks (daily): due soon -> assignees; overdue -> project lead (or its managers
when there is no lead); overdue for ESCALATE_AFTER_DAYS -> project managers.
Tickets (hourly): SLA due soon -> assignees; breached -> assignees and Agent
Managers; breached for ESCALATE_AFTER_DAYS -> Agent Managers again.

Each stage is sent once per person and item (Notification Log dedupe on the
stage-specific subject), so nobody is nagged every run.
"""

import json

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import (
    enqueue_create_notification,
)
from frappe.utils import add_days, add_to_date, getdate, now_datetime, nowdate

TASK_DUE_SOON_DAYS = 2
TICKET_DUE_SOON_HOURS = 4
ESCALATE_AFTER_DAYS = 3
MANAGER_PROJECT_ROLE = "Project Manager"
SKIP = {"Administrator", "Guest"}


def _assignees(raw) -> list[str]:
    try:
        return json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []


def _notify(users, doctype: str, name: str, subject: str):
    users = {u for u in users if u and u not in SKIP}
    # Frappe 15 has no dedupe_on, so skip anyone already told about this
    already = set(
        frappe.get_all(
            "Notification Log",
            filters={
                "for_user": ("in", list(users) or [""]),
                "document_type": doctype,
                "document_name": str(name),
                "subject": subject,
            },
            pluck="for_user",
        )
    )
    users = sorted(users - already)
    if not users:
        return
    enqueue_create_notification(
        users,
        {
            "type": "Alert",
            "document_type": doctype,
            "document_name": str(name),
            "subject": subject,
            "from_user": "Administrator",
        },
    )


def _project_managers(project: str) -> list[str]:
    owner = frappe.db.get_value("Project", project, "owner")
    listed = frappe.get_all(
        "Project User",
        filters={
            "parenttype": "Project",
            "parent": project,
            "custom_role": MANAGER_PROJECT_ROLE,
        },
        pluck="user",
    )
    return [owner, *listed]


def _agent_managers() -> list[str]:
    return frappe.get_all(
        "Has Role",
        filters={"role": "Agent Manager", "parenttype": "User"},
        pluck="parent",
    )


def send_task_reminders():
    """Daily: remind and escalate open tasks around their due date."""
    today = getdate(nowdate())
    tasks = frappe.get_all(
        "Task",
        filters={
            "status": ("not in", ["Completed", "Cancelled", "Template"]),
            "exp_end_date": ("<=", add_days(today, TASK_DUE_SOON_DAYS)),
        },
        fields=["name", "subject", "project", "exp_end_date", "is_key", "_assign"],
    )
    for task in tasks:
        due = getdate(task.exp_end_date)
        label = (_("Key task") + ": ") if task.is_key else ""
        title = f"{label}{task.subject}"
        due_text = frappe.utils.formatdate(due)
        assignees = _assignees(task._assign)

        if due >= today:
            _notify(
                assignees,
                "Task",
                task.name,
                _("Due {0}: {1}").format(due_text, title),
            )
            continue

        lead = (
            frappe.db.get_value("Project", task.project, "project_lead")
            if task.project
            else None
        )
        managers = _project_managers(task.project) if task.project else []
        _notify(
            [*assignees, *([lead] if lead else managers)],
            "Task",
            task.name,
            _("Overdue since {0}: {1}").format(due_text, title),
        )
        if (today - due).days >= ESCALATE_AFTER_DAYS:
            _notify(
                managers,
                "Task",
                task.name,
                _("Escalated, {0} days overdue: {1}").format((today - due).days, title),
            )


def send_ticket_reminders():
    """Hourly: SLA reminders and escalation for open tickets."""
    now = now_datetime()
    tickets = frappe.get_all(
        "HD Ticket",
        filters=[
            ["status_category", "=", "Open"],
            # a ticket without an SLA has no due time; "<=" alone would match it
            ["resolution_by", "is", "set"],
            ["resolution_by", "<=", add_to_date(now, hours=TICKET_DUE_SOON_HOURS)],
        ],
        fields=["name", "subject", "priority", "resolution_by", "_assign"],
    )
    managers = None
    for ticket in tickets:
        title = _("Ticket #{0}: {1}").format(ticket.name, ticket.subject)
        assignees = _assignees(ticket._assign)
        due_text = frappe.utils.format_datetime(ticket.resolution_by, "d MMM, HH:mm")

        if ticket.resolution_by > now:
            _notify(
                assignees,
                "HD Ticket",
                ticket.name,
                _("SLA due {0}: {1}").format(due_text, title),
            )
            continue

        if managers is None:
            managers = _agent_managers()
        _notify(
            [*assignees, *managers],
            "HD Ticket",
            ticket.name,
            _("SLA breached ({0}): {1}").format(due_text, title),
        )
        if (now - ticket.resolution_by).days >= ESCALATE_AFTER_DAYS:
            _notify(
                managers,
                "HD Ticket",
                ticket.name,
                _("Escalated, SLA breached {0} days ago: {1}").format(
                    (now - ticket.resolution_by).days, title
                ),
            )
