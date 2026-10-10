"""Notifications to people: the helpdesk notification panel, plus chat or email.

`notify_users` is the one way the hub tells someone about a document. The scheduled
reminders and escalations for tasks and tickets live in helpdesk.follow_ups
(docs/follow-ups.md), which posts through `new_notification` here too.
"""

import json

import frappe

from helpdesk.automation import automation_user

MANAGER_PROJECT_ROLE = "Project Manager"
SKIP = {"Administrator", "Guest"}


def _assignees(raw) -> list[str]:
    try:
        return json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []


def notify_users(
    users,
    doctype: str,
    name: str,
    subject: str,
    escalate: bool = False,
    link: str | None = None,
    notification_type: str = "Reminder",
    user_from: str | None = None,
    once: bool = True,
):
    """Reminder in the helpdesk notification panel, plus an email or chat message
    (see HDNotification); `escalate` also posts it to the team's chat channel.
    `link` replaces the usual page, e.g. a pull request on GitHub. Another
    `notification_type` (e.g. Task Completed) stays in the panel only.

    Sent once per person, document and subject, so a daily run doesn't repeat itself;
    `once=False` sends it again, for events that can happen more than once.
    """
    from helpdesk.chat_notifications import post_escalation

    link = link or helpdesk_path(doctype, name)
    if escalate:
        post_escalation(subject, link)
    users = enabled_users(users)
    if not users:
        return
    already = once and set(
        frappe.get_all(
            "HD Notification",
            filters={
                "user_to": ("in", users),
                "notification_type": notification_type,
                "reference_doctype": doctype,
                "reference_name": str(name),
                "message": subject,
            },
            pluck="user_to",
        )
    )
    for user in users:
        if already and user in already:
            continue
        new_notification(
            user,
            doctype,
            name,
            subject,
            link,
            notification_type=notification_type,
            user_from=user_from,
        )


def enabled_users(users) -> list[str]:
    """The people among `users` who can get a notification, sorted.

    A task can still be assigned to someone whose account was deleted or disabled;
    their reminder would fail and stop the rest of the run, so they're left out.
    """
    users = sorted({u for u in users if u and u not in SKIP})
    if not users:
        return []
    return frappe.qb.get_query(
        "User",
        fields=["name"],
        filters={"name": ("in", users), "enabled": 1},
        order_by="name asc",
    ).run(pluck=True)


def new_notification(
    user: str,
    doctype: str,
    name: str,
    subject: str,
    link: str | None,
    notification_type: str = "Reminder",
    user_from: str | None = None,
    dedupe_key: str | None = None,
    deliver: bool = True,
):
    """One HD Notification. `deliver=False` keeps it in the panel only: no chat
    message or email (follow-ups reach chat in the digest instead)."""
    doc = frappe.get_doc(
        {
            "doctype": "HD Notification",
            "notification_type": notification_type,
            "user_from": user_from or automation_user(),
            "user_to": user,
            "reference_doctype": doctype,
            "reference_name": str(name),
            "reference_ticket": str(name) if doctype == "HD Ticket" else None,
            "link": link,
            "message": subject,
            "dedupe_key": dedupe_key,
        }
    )
    doc.flags.skip_delivery = not deliver
    doc.insert(ignore_permissions=True)
    return doc


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
