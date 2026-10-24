"""Newly assigned tasks: the assignee is told once, and the task stays marked New
(or Reassigned) in My Work and My Tasks until they open it.

Every assignment is a ToDo, so the notice hangs off the ToDo's insert and catches
every way a task is given out. Callers that already tell the new assignee in their
own words (hand over, ask for help, content posts, stand-up help) run inside
`told_by_caller()`. See docs/workspace-pages.md, "New tasks".
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import get_datetime, get_fullname, now_datetime

from helpdesk.automation import SYSTEM_USERS, acting_user, automation_user

SEEN = "HD Task Seen"
ASSIGNMENT = "Assignment"
# set while a caller sends its own notice for the assignments it makes
TOLD_FLAG = "task_assignment_told_by_caller"
NEW = "new"
REASSIGNED = "reassigned"


@contextmanager
def told_by_caller():
    """Assignments made in this block send no notice of their own: the caller tells
    the new assignee itself."""
    previous = frappe.flags.get(TOLD_FLAG)
    frappe.flags[TOLD_FLAG] = True
    try:
        yield
    finally:
        frappe.flags[TOLD_FLAG] = previous


def notify_assignee(doc, method=None):
    """ToDo hook (after_insert): tell the person a task was just given to."""
    if not is_task_assignment(doc):
        return
    assigner = assigner_of(doc)
    if doc.allocated_to in (assigner, automation_user(), *SYSTEM_USERS):
        return
    send_notice(doc.allocated_to, doc.reference_name, assigner, assignment_kind(doc))


def is_task_assignment(doc) -> bool:
    return (
        doc.reference_type == "Task"
        and bool(doc.reference_name)
        and doc.status == "Open"
        and not frappe.flags.get(TOLD_FLAG)
    )


def assigner_of(doc) -> str:
    """Who gave the task: the ToDo's assigner, or the hub when a job did."""
    assigner = doc.assigned_by or frappe.session.user
    if assigner == frappe.session.user:
        # Administrator in the browser is a person; a job running as them is the hub
        return acting_user()
    return automation_user() if assigner in SYSTEM_USERS else assigner


def assignment_kind(doc) -> str:
    """ "again" when the person had this task before, "reassigned" when it was taken
    off someone else, else "new"."""
    earlier = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Task",
            "reference_name": doc.reference_name,
            "name": ("!=", doc.name),
        },
        fields=["allocated_to", "status"],
    )
    if any(t.allocated_to == doc.allocated_to for t in earlier):
        return "again"
    if any(t.status == "Cancelled" for t in earlier):
        return REASSIGNED
    return NEW


def notice_text(kind: str, assigner: str, subject: str) -> str:
    name = get_fullname(assigner)
    if kind == "again":
        return _("{0} assigned you {1} again").format(name, subject)
    if kind == REASSIGNED:
        return _("{0} reassigned a task to you: {1}").format(name, subject)
    return _("{0} assigned you a new task: {1}").format(name, subject)


def send_notice(user: str, task: str, assigner: str, kind: str):
    """One Assignment notification (panel, open tabs, phones) and, when chat is on, one
    direct message. No email from here: Frappe's own assignment notice already emails
    the person, as their Notification Settings allow."""
    from helpdesk.chat_notifications import is_enabled as chat_enabled
    from helpdesk.work_reminders import enabled_users, helpdesk_path, new_notification

    if not enabled_users([user]):
        return
    subject = frappe.db.get_value("Task", task, "subject") or task
    notice = new_notification(
        user,
        "Task",
        task,
        notice_text(kind, assigner, subject),
        helpdesk_path("Task", task),
        notification_type=ASSIGNMENT,
        user_from=assigner,
    )
    if notice and chat_enabled():
        notice.queue_chat()


def notify_given_tasks(given: dict[str, int], project: str):
    """One notice per person for tasks handed out in bulk (a checklist from a template),
    instead of one per task."""
    from helpdesk.chat_notifications import is_enabled as chat_enabled
    from helpdesk.work_reminders import enabled_users, new_notification

    assigner = acting_user()
    project_name = frappe.db.get_value("Project", project, "project_name") or project
    for user in enabled_users(given):
        if user == assigner:
            continue
        notice = new_notification(
            user,
            "Project",
            project,
            _("{0} assigned you {1} new tasks in {2}").format(
                get_fullname(assigner), given[user], project_name
            ),
            "/my-work",
            notification_type=ASSIGNMENT,
            user_from=assigner,
        )
        if notice and chat_enabled():
            notice.queue_chat()


# --- New and Reassigned marks ---


def assignment_states(user: str, tasks: list[str]) -> dict[str, str]:
    """{task: "new" | "reassigned"} for the tasks among `tasks` that `user` hasn't
    opened since they were given them. "reassigned" means they had the task before.
    Two queries for any number of tasks."""
    if not tasks:
        return {}
    todo = frappe.qb.DocType("ToDo")
    rows = (
        frappe.qb.from_(todo)
        .select(todo.reference_name, todo.status, todo.creation)
        .where(
            (todo.reference_type == "Task")
            & (todo.allocated_to == user)
            & todo.reference_name.isin(list(tasks))
        )
        .run(as_dict=True)
    )
    given = {}
    for row in rows:
        if row.status == "Open":
            given[row.reference_name] = max(
                row.creation, given.get(row.reference_name, row.creation)
            )
    if not given:
        return {}
    seen = dict(
        frappe.get_all(
            SEEN,
            filters={"user": user, "task": ("in", list(given))},
            fields=["task", "seen_on"],
            as_list=True,
        )
    )
    states = {}
    for task, assigned_on in given.items():
        if seen.get(task) and get_datetime(seen[task]) >= assigned_on:
            continue
        had_before = any(
            r.reference_name == task and r.creation < assigned_on for r in rows
        )
        states[task] = REASSIGNED if had_before else NEW
    return states


@frappe.whitelist(methods=["POST"])
def mark_task_seen(task: str) -> dict:
    """The person opened the task: it stops showing as New for them."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    seen_on = now_datetime()
    record_seen(frappe.session.user, doc.name, seen_on)
    return {"task": doc.name, "seen_on": str(seen_on)}


def record_seen(user: str, task: str, seen_on):
    name = frappe.db.get_value(SEEN, {"user": user, "task": task})
    if name:
        frappe.db.set_value(SEEN, name, "seen_on", seen_on, update_modified=False)
        return
    try:
        frappe.get_doc(
            {"doctype": SEEN, "user": user, "task": task, "seen_on": seen_on}
        ).insert(ignore_permissions=True)
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        frappe.clear_last_message()  # Frappe's "must be unique" note
        # the same task opened in two tabs at once; the other one's row stands
        frappe.db.set_value(
            SEEN,
            {"user": user, "task": task},
            "seen_on",
            seen_on,
            update_modified=False,
        )
