"""Daily morning brief for every assignee (cron at 10:00, site time).

One message per person with open work: what's overdue, due today and in the
next few days, key and at-risk items, tasks assigned since yesterday, work on
hold and tickets whose SLA ends today. Tasks nobody is assigned to, when they
are late, due soon or at risk, go to the project lead (or, without one, the
project's managers) so they aren't missed. It goes through notify_users, so it
lands in the notification panel and in Teams/Slack or email, once a day.
Nothing is sent on the weekly off day or to people with nothing open.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, get_datetime, getdate, nowdate

from helpdesk.api.work import OPEN_TASK_FILTER, TASK_FIELDS, TICKET_FIELDS, _items
from helpdesk.task_estimates import get_settings, is_working_day
from helpdesk.work_reminders import SKIP, get_project_managers, notify_users

SOON_DAYS = 3
LIST_CAP = 5


def send_morning_briefs():
    if not get_settings().morning_brief or not is_working_day(nowdate()):
        return
    work = open_work_by_assignee()
    unassigned = unassigned_work_by_lead()
    for user in sorted(set(work) | set(unassigned)):
        tasks, tickets = work.get(user, ([], []))
        try:
            send_brief(user, tasks, tickets, unassigned.get(user, []))
        except Exception:  # noqa: BLE001 - one person's brief must not stop the rest
            frappe.log_error(title=f"Morning brief failed for {user}")


def open_work_by_assignee() -> dict:
    work = {}
    tasks = frappe.get_all(
        "Task",
        filters={"status": OPEN_TASK_FILTER, "_assign": ("like", '%"%')},
        fields=[*TASK_FIELDS, "creation"],
    )
    tickets = frappe.get_all(
        "HD Ticket",
        filters={
            "status_category": ("in", ["Open", "Paused"]),
            "_assign": ("like", '%"%'),
        },
        fields=TICKET_FIELDS,
    )
    for index, rows in ((0, tasks), (1, tickets)):
        for row in rows:
            for user in _assignees(row._assign):
                if user in SKIP or not frappe.db.get_value("User", user, "enabled"):
                    continue
                work.setdefault(user, ([], []))[index].append(row)
    return work


def unassigned_work_by_lead() -> dict:
    """Open tasks with nobody assigned, by who should hand them out."""
    tasks = frappe.get_all(
        "Task",
        filters={"status": OPEN_TASK_FILTER, "project": ("is", "set")},
        fields=[*TASK_FIELDS, "creation"],
    )
    tasks = [t for t in tasks if not _assignees(t._assign)]
    owners_of = {}
    by_user = {}
    for task in tasks:
        if task.project not in owners_of:
            owners_of[task.project] = _project_owners(task.project)
        for user in owners_of[task.project]:
            by_user.setdefault(user, []).append(task)
    return by_user


def _project_owners(project: str) -> list[str]:
    """The project lead, or its managers when there's no lead or the lead can't receive it."""

    def reachable(users) -> list[str]:
        return [
            u
            for u in dict.fromkeys(users)
            if u and u not in SKIP and frappe.db.get_value("User", u, "enabled")
        ]

    lead = frappe.db.get_value("Project", project, "project_lead")
    return reachable([lead]) or reachable(get_project_managers(project))


def _assignees(raw) -> list[str]:
    try:
        return json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []


def send_brief(user: str, tasks, tickets, unassigned=()):
    today = getdate(nowdate())
    title = _("Morning brief for {0}").format(formatdate(today))
    already = frappe.db.exists(
        "HD Notification",
        {
            "user_to": user,
            "notification_type": "Reminder",
            "reference_doctype": "User",
            "reference_name": user,
            "message": ("like", f"{title}%"),
        },
    )
    if already:
        return
    new_since = get_datetime(add_days(today, -1))
    new_names = {t.name for t in tasks if get_datetime(t.creation) >= new_since}
    text = compose(
        user,
        title,
        _items(tasks, tickets),
        new_names,
        today,
        _items(list(unassigned), []) if unassigned else [],
    )
    if text:
        notify_users([user], "User", user, text)


def compose(
    user: str,
    title: str,
    items: list[dict],
    new_names: set,
    today,
    unassigned: list[dict] | None = None,
) -> str:
    """Plain text, one line per item; empty when there's nothing worth a brief."""
    soon = add_days(today, SOON_DAYS)

    def due_on(item):
        return getdate(item["deadline"]) if item["deadline"] else None

    # only the ones that need someone soon: late, due within SOON_DAYS, or at risk
    needs_owner = [
        i
        for i in unassigned or []
        if i["is_overdue"] or (due_on(i) and due_on(i) <= soon) or i["risks"]
    ]
    overdue = [i for i in items if i["is_overdue"]]
    due_today = [i for i in items if not i["is_overdue"] and due_on(i) == today]
    due_soon = [
        i
        for i in items
        if not i["is_overdue"]
        and due_on(i)
        and today < due_on(i) <= soon
        and i["status"] != "On Hold"
    ]
    at_risk = [i for i in items if i["risks"] and i not in due_today]
    key = [
        i
        for i in items
        if i["is_key"] and i not in overdue and i not in due_today and i not in due_soon
    ]
    new = [i for i in items if i["kind"] == "task" and i["name"] in new_names]
    on_hold = [i for i in items if i["status"] == "On Hold"]
    if not any((overdue, due_today, due_soon, at_risk, key, new, needs_owner)):
        return ""

    first_name = (frappe.db.get_value("User", user, "first_name") or "").strip()
    lines = [
        title,
        _(
            "Good morning {0}. {1} overdue, {2} due today, {3} due in the next {4} days."
        ).format(first_name, len(overdue), len(due_today), len(due_soon), SOON_DAYS),
    ]
    sections = (
        (_("Not assigned to anyone yet: assign or do"), needs_owner),
        (_("Overdue, start here"), overdue),
        (_("Due today"), due_today),
        (_("Due soon"), due_soon),
        (_("At risk"), at_risk),
        (_("Key work"), key),
        (_("New since yesterday"), new),
        (_("On hold"), on_hold),
    )
    for heading, section in sections:
        if not section:
            continue
        lines.append("")
        lines.append(heading)
        lines.extend(f"- {describe(item)}" for item in section[:LIST_CAP])
        if len(section) > LIST_CAP:
            lines.append(_("- and {0} more in My Work").format(len(section) - LIST_CAP))
    return "\n".join(lines)


def describe(item: dict) -> str:
    where = item.get("project_name") or item.get("customer") or ""
    label = f"#{item['name']} " if item["kind"] == "ticket" else ""
    text = f"{label}{item['title']}"
    if where:
        text += f" ({where})"
    if item["deadline"]:
        text += " · " + _("due {0}").format(formatdate(getdate(item["deadline"])))
    if item["risks"]:
        text += " · " + item["risks"][0]
    return text
