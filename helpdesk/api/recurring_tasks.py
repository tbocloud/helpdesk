"""Recurring tasks of a project (Project -> Recurring tab).

Whoever sees every task of the project sees all its schedules; other members see
the ones that make their tasks or that they set up. Admins and the project's
managers and lead create, change, pause and delete them. The doctype gives role
access to System Manager only; every call checks here. See docs/recurring-tasks.md.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_fullname, getdate, nowdate

from helpdesk.helpdesk.doctype.hd_recurring_task.hd_recurring_task import (
    CLOSED_PROJECT,
    RECURRING_TASK,
    HDRecurringTask,
)
from helpdesk.recurrence import ENDS, FREQUENCIES, WEEKDAYS, describe, time_label
from helpdesk.tasky.permissions import (
    can_manage_project,
    get_project_team,
    sees_all_tasks,
)

# what the dialog may set; the progress fields are the daily job's
EDITABLE = (
    "subject",
    "description",
    "category",
    "priority",
    "estimated_hours",
    "assignee",
    "is_key",
    "frequency",
    "interval",
    "weekdays",
    "month_day",
    "last_day_of_month",
    "start_date",
    "ends",
    "end_date",
    "max_occurrences",
    "lead_days",
    "due_time",
    "skip_non_working_days",
)
LIST_FIELDS = (
    "name",
    "is_active",
    "inactive_reason",
    "next_due_date",
    "next_create_on",
    "occurrences_created",
    "last_task",
    "owner",
    *EDITABLE,
)
PREVIEW_COUNT = 5


@frappe.whitelist()
def get_recurring_tasks(project: str) -> dict:
    """The project's schedules, active first, with what each will do next."""
    project = _check_project(project)
    rules = frappe.qb.get_query(
        RECURRING_TASK,
        fields=list(LIST_FIELDS),
        filters={"project": project},
        order_by="is_active desc, next_due_date asc, creation asc",
    ).run(as_dict=True)
    if not sees_all_tasks(project):
        # like the tasks themselves: a member sees only the work that is theirs
        user = frappe.session.user
        rules = [r for r in rules if user in (r.assignee, r.owner)]
    last_tasks = _readable_tasks([r.last_task for r in rules if r.last_task])
    closed = _project_closed(project)
    return {
        "rules": [_rule_dict(r, last_tasks, closed) for r in rules],
        "can_manage": can_manage_project(project),
    }


@frappe.whitelist()
def get_recurring_task_form(project: str, task: str | None = None) -> dict:
    """The project's team for the assignee, and with `task`, values copied from it
    ("Make recurring…" on a task)."""
    project = _check_manage(project)
    team = [
        {"user": u, "full_name": get_fullname(u)} for u in get_project_team(project)
    ]
    return {
        "team": team,
        "categories": HDRecurringTask.task_options("custom_category"),
        "priorities": HDRecurringTask.task_options("priority"),
        "frequencies": list(FREQUENCIES),
        "ends": list(ENDS),
        "prefill": _prefill_from_task(project, task, team) if task else None,
    }


@frappe.whitelist()
def preview_recurring_task(
    project: str, values: dict | str, name: str | None = None
) -> dict:
    """The schedule in words and its next due dates, for the dialog's live preview.

    With `name` (editing), the tasks it already created count towards "after N".
    A rule that can't produce dates yet answers with `error` instead of failing,
    so the preview can say what to fix while the person is still typing.
    Nothing is saved.
    """
    project = _check_manage(project)
    if name:
        doc = _get_rule(name, manage=True)
        if doc.project != project:
            frappe.throw(_("This recurring task belongs to another project."))
    else:
        doc = frappe.new_doc(RECURRING_TASK)
        doc.project = project
    _apply(doc, values)
    try:
        upcoming = doc.preview(PREVIEW_COUNT)
    except frappe.ValidationError as e:
        frappe.clear_messages()
        return {"schedule": "", "dates": [], "error": cstr(e)}
    return {
        "schedule": describe(doc),
        "dates": [
            {"due": str(o.due), "create_on": str(o.create_on), "on": str(o.on)}
            for o in upcoming
        ],
        "error": None,
    }


@frappe.whitelist(methods=["POST"])
def save_recurring_task(
    project: str, values: dict | str, name: str | None = None
) -> dict:
    """Creates a schedule, or with `name` changes one. A changed schedule starts from
    today: its dates already past are skipped, and the tasks it created stay."""
    project = _check_manage(project)
    if name:
        doc = _get_rule(name, manage=True)
        if doc.project != project:
            frappe.throw(_("This recurring task belongs to another project."))
        _apply(doc, values)
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.new_doc(RECURRING_TASK)
        doc.project = project
        _apply(doc, values)
        doc.insert(ignore_permissions=True)
    return _rule_dict(
        frappe._dict(doc.as_dict()),
        _readable_tasks([doc.last_task] if doc.last_task else []),
        _project_closed(project),
    )


@frappe.whitelist(methods=["POST"])
def set_recurring_task_active(name: str, active: bool) -> dict:
    """Pause or resume. Resuming starts from today: dates that went past while it was
    paused are skipped, not created late."""
    doc = _get_rule(name, manage=True)
    doc.is_active = 1 if active else 0
    if not active:
        doc.inactive_reason = _("Paused by {0}").format(get_fullname())
    doc.save(ignore_permissions=True)
    return {"is_active": bool(doc.is_active), "next_due_date": doc.next_due_date}


@frappe.whitelist(methods=["POST"])
def delete_recurring_task(name: str) -> None:
    """Deletes the schedule; the tasks it created stay in the project."""
    doc = _get_rule(name, manage=True)
    frappe.delete_doc(RECURRING_TASK, doc.name, ignore_permissions=True)


# --- helpers ---


def _check_project(project: str) -> str:
    project = cstr(project)
    if not frappe.db.exists("Project", project):
        frappe.throw(
            _("Project not found: {0}").format(project), frappe.DoesNotExistError
        )
    frappe.has_permission("Project", "read", doc=project, throw=True)
    return project


def _check_manage(project: str) -> str:
    project = _check_project(project)
    if not can_manage_project(project):
        frappe.throw(
            _("Only the project's manager or lead can set up recurring tasks."),
            frappe.PermissionError,
        )
    return project


def _get_rule(name: str, manage: bool = False):
    name = cstr(name)
    if not frappe.db.exists(RECURRING_TASK, name):
        frappe.throw(_("Recurring task not found"), frappe.DoesNotExistError)
    doc = frappe.get_doc(RECURRING_TASK, name)
    if manage:
        _check_manage(doc.project)
    else:
        _check_project(doc.project)
    return doc


def _apply(doc, values: dict | str):
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict):
        frappe.throw(_("Send the recurring task's values as an object."))
    for field in EDITABLE:
        if field in values:
            doc.set(field, values[field])
    if isinstance(values.get("weekdays"), list):
        doc.weekdays = ",".join(cstr(day) for day in values["weekdays"])
    # frappe.new_doc fills an empty Time field with the current time; a rule saved
    # without a due time must stay without one
    if doc.is_new() and not values.get("due_time"):
        doc.due_time = None
    doc.due_time = doc.due_time or None
    doc.assignee = doc.assignee or None


def _readable_tasks(names: list[str]) -> dict:
    """The last tasks the viewer may open (a plain member reads only their own)."""
    if not names:
        return {}
    rows = frappe.get_list(
        "Task",
        filters={"name": ("in", names)},
        fields=["name", "subject", "status", "exp_end_date"],
        limit_page_length=0,
    )
    return {r.name: r for r in rows}


def _project_closed(project: str) -> bool:
    return frappe.db.get_value("Project", project, "status") in CLOSED_PROJECT


def _state(rule, project_closed: bool) -> str:
    """active, paused (by someone), finished (no dates left) or stopped (project closed)."""
    if rule.is_active:
        return "active"
    if project_closed:
        return "stopped"
    return "paused" if rule.next_due_date else "finished"


def _rule_dict(rule, last_tasks: dict, project_closed: bool) -> dict:
    task = last_tasks.get(rule.last_task) if rule.last_task else None
    return {
        **{field: rule.get(field) for field in LIST_FIELDS if field != "last_task"},
        "weekdays": [name for name in (rule.weekdays or "").split(",") if name],
        "is_active": bool(rule.is_active),
        "state": _state(rule, project_closed),
        "is_key": bool(rule.is_key),
        "last_day_of_month": bool(rule.last_day_of_month),
        "skip_non_working_days": bool(rule.skip_non_working_days),
        "due_time": time_label(rule.due_time) or None,
        "schedule": describe(rule),
        "assignee_name": get_fullname(rule.assignee) if rule.assignee else None,
        "owner_name": get_fullname(rule.owner),
        "last_task": (
            {
                "name": task.name,
                "subject": task.subject,
                "status": task.status,
                "due_date": task.exp_end_date,
            }
            if task
            else None
        ),
        "has_last_task": bool(rule.last_task),
    }


def _prefill_from_task(project: str, task: str, team: list[dict]) -> dict:
    task = cstr(task)
    doc = frappe.get_doc("Task", task)
    doc.check_permission("read")
    if doc.project != project:
        frappe.throw(_("Task {0} isn't in this project.").format(task))
    assignees = frappe.parse_json(doc.get("_assign") or "[]") or []
    members = {m["user"] for m in team}
    due = getdate(doc.exp_end_date or nowdate())
    return {
        "subject": doc.subject,
        "description": doc.description or "",
        "category": doc.get("custom_category") or "",
        "priority": doc.priority or "Medium",
        "estimated_hours": flt(doc.get("custom_estimated_hours")),
        "assignee": next((u for u in assignees if u in members), None),
        "is_key": bool(cint(doc.is_key)),
        "frequency": "Monthly",
        "interval": 1,
        "weekdays": [WEEKDAYS[due.weekday()]],
        "month_day": due.day,
        "start_date": str(max(due, getdate(nowdate()))),
    }
