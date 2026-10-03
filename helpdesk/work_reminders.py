"""Deadline reminders and escalation for tasks and tickets.

Tasks (daily): due soon -> assignees; overdue -> project lead (or its managers
when there is no lead); overdue for ESCALATE_AFTER_DAYS -> project managers.
Tasks on hold get no due-date reminders; a hold that lasts ESCALATE_AFTER_DAYS
goes to the project lead and managers.
Tickets (every 15 minutes), for the first reply and for resolution: due soon
-> assignees (the chat channel when nobody is assigned); breached -> assignees,
Agent Managers and the channel; resolution breached for ESCALATE_AFTER_DAYS ->
Agent Managers again.

Each stage is sent once per person and item (deduped on the stage-specific
subject), so nobody is nagged every run. Reminders show in the helpdesk
notification panel and are emailed through the outgoing email account.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, getdate, now_datetime, nowdate

from helpdesk.automation import automation_user

TASK_DUE_SOON_DAYS = 2
TICKET_DUE_SOON_HOURS = 4
FIRST_REPLY_DUE_SOON_MINUTES = 30
ESCALATE_AFTER_DAYS = 3
MANAGER_PROJECT_ROLE = "Project Manager"
ON_HOLD = "On Hold"
SKIP = {"Administrator", "Guest"}


def _assignees(raw) -> list[str]:
    try:
        return json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []


def notify_users(users, doctype: str, name: str, subject: str, escalate: bool = False):
    """Reminder in the helpdesk notification panel, plus an email or chat message
    (see HDNotification); `escalate` also posts it to the team's chat channel.

    Sent once per person, document and subject, so a daily run doesn't repeat itself.
    """
    from helpdesk.chat_notifications import post_escalation

    if escalate:
        post_escalation(subject, helpdesk_path(doctype, name))
    users = sorted({u for u in users if u and u not in SKIP})
    if not users:
        return
    already = set(
        frappe.get_all(
            "HD Notification",
            filters={
                "user_to": ("in", users),
                "notification_type": "Reminder",
                "reference_doctype": doctype,
                "reference_name": str(name),
                "message": subject,
            },
            pluck="user_to",
        )
    )
    link = helpdesk_path(doctype, name)
    for user in users:
        if user in already:
            continue
        frappe.get_doc(
            {
                "doctype": "HD Notification",
                "notification_type": "Reminder",
                "user_from": automation_user(),
                "user_to": user,
                "reference_doctype": doctype,
                "reference_name": str(name),
                "reference_ticket": str(name) if doctype == "HD Ticket" else None,
                "link": link,
                "message": subject,
            }
        ).insert(ignore_permissions=True)


def helpdesk_path(doctype: str, name: str) -> str:
    """Where the reminder opens inside /helpdesk (agents can't use /app)."""
    if doctype == "HD Work Summary":
        return f"/work-summary/{name}"
    if doctype == "HD Ticket":
        return f"/tickets/{name}"
    if doctype == "HD Article":
        return f"/kb/articles/{name}"
    project = (
        frappe.db.get_value(doctype, name, "project") if doctype == "Task" else None
    )
    return f"/projects/{project}" if project else "/my-work"


def get_project_managers(project: str) -> list[str]:
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
            "status": ("not in", ["Completed", "Cancelled", "Template", ON_HOLD]),
            "exp_end_date": ("<=", add_days(today, TASK_DUE_SOON_DAYS)),
        },
        fields=[
            "name",
            "subject",
            "project",
            "exp_end_date",
            "is_key",
            "is_milestone",
            "_assign",
        ],
    )
    for task in tasks:
        due = getdate(task.exp_end_date)
        label = ""
        if task.is_milestone:
            label = _("Milestone") + ": "
        elif task.is_key:
            label = _("Key task") + ": "
        title = f"{label}{task.subject}"
        due_text = frappe.utils.formatdate(due)
        assignees = _assignees(task._assign)

        if due >= today:
            notify_users(
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
        managers = get_project_managers(task.project) if task.project else []
        notify_users(
            [*assignees, *([lead] if lead else managers)],
            "Task",
            task.name,
            _("Overdue since {0}: {1}").format(due_text, title),
        )
        if (today - due).days >= ESCALATE_AFTER_DAYS:
            notify_users(
                managers,
                "Task",
                task.name,
                # dated, not counted, so it's sent once rather than every day
                _("Escalated, overdue since {0}: {1}").format(due_text, title),
                escalate=True,
            )


def send_hold_reminders():
    """Daily: flag tasks that have been on hold for a while, so someone unblocks them."""
    since = add_days(getdate(nowdate()), -ESCALATE_AFTER_DAYS)
    tasks = frappe.get_all(
        "Task",
        filters={"status": ON_HOLD, "hold_since": ("<=", since)},
        fields=["name", "subject", "project", "hold_reason", "hold_since"],
    )
    for task in tasks:
        if not task.project:
            continue
        lead = frappe.db.get_value("Project", task.project, "project_lead")
        # the subject names the hold's start, so each hold is flagged once
        notify_users(
            [lead, *get_project_managers(task.project)],
            "Task",
            task.name,
            _("On hold for over {0} days since {1} ({2}): {3}").format(
                ESCALATE_AFTER_DAYS,
                frappe.utils.formatdate(task.hold_since),
                task.hold_reason,
                task.subject,
            ),
            escalate=True,
        )


def send_ticket_reminders():
    """Every 15 minutes: SLA reminders and escalation for open tickets.

    Paused tickets (waiting on the customer or a task) are left alone, like the
    SLA clock. A ticket nobody is assigned to goes to the team's chat channel
    as soon as it is due soon, since no one would hear about it otherwise.
    """
    now = now_datetime()
    managers = _agent_managers()
    remind_first_replies(now, managers)
    remind_resolutions(now, managers)


def remind_first_replies(now, managers: list[str]):
    tickets = frappe.get_all(
        "HD Ticket",
        filters=[
            ["status_category", "=", "Open"],
            ["first_responded_on", "is", "not set"],
            # a ticket without an SLA has no due time; "<=" alone would match it
            ["response_by", "is", "set"],
            [
                "response_by",
                "<=",
                add_to_date(now, minutes=FIRST_REPLY_DUE_SOON_MINUTES),
            ],
        ],
        fields=["name", "subject", "response_by", "_assign"],
    )
    for ticket in tickets:
        title = _("Ticket #{0}: {1}").format(ticket.name, ticket.subject)
        assignees = _assignees(ticket._assign)
        due_text = frappe.utils.format_datetime(ticket.response_by, "d MMM, HH:mm")
        if ticket.response_by > now:
            notify_users(
                assignees,
                "HD Ticket",
                ticket.name,
                _("First reply due {0}: {1}").format(due_text, title),
                escalate=not assignees,
            )
            continue
        notify_users(
            [*assignees, *managers],
            "HD Ticket",
            ticket.name,
            _("First reply overdue ({0}): {1}").format(due_text, title),
            escalate=True,
        )


def remind_resolutions(now, managers: list[str]):
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
    for ticket in tickets:
        title = _("Ticket #{0}: {1}").format(ticket.name, ticket.subject)
        assignees = _assignees(ticket._assign)
        due_text = frappe.utils.format_datetime(ticket.resolution_by, "d MMM, HH:mm")

        if ticket.resolution_by > now:
            notify_users(
                assignees,
                "HD Ticket",
                ticket.name,
                _("SLA due {0}: {1}").format(due_text, title),
                escalate=not assignees,
            )
            continue

        notify_users(
            [*assignees, *managers],
            "HD Ticket",
            ticket.name,
            _("SLA breached ({0}): {1}").format(due_text, title),
            escalate=True,
        )
        if (now - ticket.resolution_by).days >= ESCALATE_AFTER_DAYS:
            notify_users(
                managers,
                "HD Ticket",
                ticket.name,
                _("Escalated, SLA breached since {0}: {1}").format(due_text, title),
                escalate=True,
            )
