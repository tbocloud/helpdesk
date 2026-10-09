"""Tasky API — checklist-driven project management on ERPNext Project/Task."""

import json

import frappe
from frappe import _
from frappe.query_builder import Order

from helpdesk.api.content_board import user_full_names
from helpdesk.api.project_files import file_counts
from helpdesk.github_sync import get_pull_requests
from helpdesk.tasky.permissions import (
    MANAGER_PROJECT_ROLE,
    can_add_tasks,
    can_manage_project,
    can_move_task,
    get_assigners,
    is_assigner,
    is_project_owner,
    is_tasky_admin,
)
from helpdesk.utils import add_assignment, csv_safe, remove_assignment

# member roles a project lead is rotated among
LEAD_ROTATION_ROLES = ("Developer",)
ON_HOLD = "On Hold"
PENDING_REVIEW_STATUS = "Pending Review"
TASK_DONE = ("Completed", "Cancelled")
# what task lists select so a held task shows why, since when and who held it
TASK_HOLD_FIELDS = ["hold_reason", "hold_note", "hold_since", "hold_by"]
# how many projects Recent projects keeps per person
RECENT_PROJECTS = 8
# the most one completion may log; longer work belongs on a manual timesheet
MAX_HOURS_PER_COMPLETION = 24
# a template task goes to a project member with this role (round robin), else to anyone
CATEGORY_TO_ROLE = {
    "Functional": "Functional Consultant",
    "Development": "Developer",
    "DevOps": "DevOps Engineer",
    "Support": "Support Engineer",
    "Digital Marketing": "Digital Marketing Specialist",
    "Social Media": "Social Media Executive",
    "Content Writing": "Content Writer / Copywriter",
    "Graphic Design": "Graphic Designer",
    "Video": "Videographer cum Editor",
    "Motion Graphics": "Motion Graphics Artist / Animator",
    "Coordination": "Project Coordinator",
}


def _resolve_project(project, ptype="read"):
    """Find project by name or project_name and check the user may `ptype` it."""
    name = (
        project
        if frappe.db.exists("Project", project)
        else frappe.db.get_value("Project", {"project_name": project}, "name")
    )
    if not name:
        frappe.throw(_("Project not found: {0}").format(project))
    frappe.has_permission("Project", ptype, name, throw=True)
    return name


def _task_dict(doc):
    """as_dict() leaves out `_assign`, which the frontend needs for assignees."""
    data = doc.as_dict()
    data["_assign"] = frappe.db.get_value("Task", doc.name, "_assign")
    return data


def hold_by_names(tasks) -> dict[str, str]:
    """Full names of whoever put these tasks on hold, from one User query for the list."""
    return user_full_names({t.get("hold_by") for t in tasks if t.get("hold_by")})


def hold_by_name(user: str | None, names: dict[str, str] | None = None) -> str | None:
    """`names` comes from hold_by_names() for a list; a single task looks the user up."""
    if not user:
        return None
    if names is None:
        return frappe.utils.get_fullname(user)
    return names.get(user) or user


def _format_tasks(tasks) -> list[dict]:
    """_format_task for a list, with the holders' names fetched once."""
    names = hold_by_names(tasks)
    return [_format_task(t, names) for t in tasks]


def _format_task(task, hold_names: dict[str, str] | None = None):
    """Normalize a Task dict for frontend consumption.

    Lists pass `hold_names` (see _format_tasks) so held tasks don't look up User one by one.
    """
    assign_raw = task.pop("_assign", None) or ""
    try:
        assigned = json.loads(assign_raw)
    except (json.JSONDecodeError, TypeError):
        assigned = []
    return {
        **task,
        "category": task.get("custom_category") or "",
        "phase": task.get("custom_phase") or "",
        "module": task.get("custom_module") or "",
        "estimated_hours": task.get("custom_estimated_hours") or 0,
        "actual_hours": task.get("custom_actual_hours") or 0,
        "start_date": task.get("exp_start_date"),
        "due_date": task.get("exp_end_date"),
        "assigned_to": assigned[0] if assigned else None,
        # cached per request, so a board of tasks doesn't query User per card
        "assigned_to_name": frappe.utils.get_fullname(assigned[0])
        if assigned
        else None,
        "assignees": assigned,
        "custom_timer_start": task.get("custom_timer_start"),
        "custom_timer_elapsed": task.get("custom_timer_elapsed") or 0,
        "is_key": bool(task.get("is_key")),
        "hd_ticket": task.get("hd_ticket"),
        "hold_reason": task.get("hold_reason"),
        "hold_note": task.get("hold_note"),
        "hold_since": task.get("hold_since"),
        "hold_by": task.get("hold_by"),
        "hold_by_name": hold_by_name(task.get("hold_by"), hold_names),
        "hold_days_total": task.get("hold_days_total") or 0,
        "is_milestone": bool(task.get("is_milestone")),
        "ai_estimated": bool(task.get("ai_estimated")),
        "estimate_note": task.get("estimate_note"),
        "ai_description": bool(task.get("custom_ai_description")),
        "slip_count": task.get("slip_count") or 0,
        **_dependency_info(task.get("depends_on_task")),
    }


def _dependency_info(depends_on: str | None) -> dict:
    """What the task waits on, and whether that's still open (the UI shows a lock)."""
    if not depends_on:
        return {"depends_on_task": None, "depends_on_subject": None, "blocked": False}
    dep = frappe.db.get_value("Task", depends_on, ["subject", "status"], as_dict=True)
    return {
        "depends_on_task": depends_on,
        "depends_on_subject": dep.subject if dep else None,
        "blocked": bool(dep) and dep.status not in ("Completed", "Cancelled"),
    }


def add_assigners(tasks: list[dict]) -> list[dict]:
    """Add who assigned each task (`assigned_by`, `assigned_by_name`) and whether
    the viewer may move it to another project (`can_move`).

    Takes formatted tasks (name, project, status, assignees); a few queries for
    the whole list, plus one permission lookup per project.
    """
    user = frappe.session.user
    assigners = get_assigners(
        {t["name"]: t["assignees"][0] for t in tasks if t.get("assignees")}
    )
    names = user_full_names(set(assigners.values()))
    manages = {}
    for t in tasks:
        by = assigners.get(t["name"])
        t["assigned_by"] = by
        t["assigned_by_name"] = names.get(by, by) if by else None
        project = t.get("project")
        if not project or t.get("status") in TASK_DONE:
            t["can_move"] = False
            continue
        if project not in manages:
            manages[project] = can_manage_project(project)
        t["can_move"] = manages[project] or is_assigner(
            by, t.get("assignees") or [], user
        )
    return tasks


@frappe.whitelist()
def complete_task(
    task: str, hours_worked: float | str | None = None, notes: str | None = None
) -> dict:
    """Complete a task and log the time spent on it to the user's timesheet.

    Hours and a note are required. The timesheet is part of the completion: if
    it can't be saved, the task stays as it was.
    """
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("write")
    if doc.status == "Completed":
        frappe.throw(_("This task is already completed."))
    hours = _completion_hours(hours_worked)
    notes = _completion_notes(notes)

    frappe.db.savepoint("complete_task")
    try:
        _mark_completed(doc, hours)
        timesheet = _log_completion_time(doc, hours, notes)
    except Exception:
        # undo the status change too, so the task never completes without its time
        frappe.db.rollback(save_point="complete_task")
        raise
    return {
        **_format_task(_task_dict(doc)),
        "timesheet": timesheet.name,
        "timesheet_status": timesheet.status,
        "hours_logged": hours,
    }


def _completion_hours(value: float | str | None) -> float:
    try:
        hours = float(value)
    except (TypeError, ValueError):
        hours = 0
    # also refuses NaN, which compares false with everything
    if not hours > 0:
        frappe.throw(_("Enter the hours you worked on this task."))
    if hours > MAX_HOURS_PER_COMPLETION:
        frappe.throw(
            _(
                "You can log at most {0} hours when completing a task. Log longer work on a timesheet."
            ).format(MAX_HOURS_PER_COMPLETION)
        )
    return round(hours, 2)


def _completion_notes(value: str | None) -> str:
    notes = str(value or "").strip()
    if not notes:
        frappe.throw(_("Add a note on what was done."))
    return notes


def _mark_completed(doc, hours: float):
    """Set Completed (the controller may route it to review) and stop the timer.

    Pausing the timer already added its time to actual hours, and the hours
    logged now cover that time, so it is swapped out rather than counted twice.
    """
    counted = frappe.utils.flt(doc.custom_timer_elapsed)
    doc.status = "Completed"
    doc.custom_actual_hours = (
        max(frappe.utils.flt(doc.custom_actual_hours) - counted, 0) + hours
    )
    doc.custom_timer_start = None
    doc.custom_timer_elapsed = 0
    doc.save()


def _log_completion_time(task_doc, hours: float, notes: str):
    """Insert and submit the user's timesheet for the completed task.

    An insert failure propagates. A submit failure leaves the timesheet as a
    Draft (logged, and reported through its status) rather than losing the time.
    """
    user = frappe.session.user
    from_time = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-hours)
    ts = frappe.get_doc(
        {
            "doctype": "Timesheet",
            "title": _("Task: {0}").format(task_doc.subject),
            "employee": frappe.db.get_value("Employee", {"user_id": user}, "name"),
            "time_logs": [
                {
                    "task": task_doc.name,
                    "project": task_doc.project,
                    "from_time": from_time,
                    "hours": hours,
                    "description": notes,
                    "completed": 1,
                }
            ],
        }
    )
    # The user's own timesheet for a task they were just allowed to complete;
    # that check is the permission decision, whatever their Timesheet role says.
    ts.flags.ignore_permissions = True
    ts.insert()

    frappe.db.savepoint("complete_task_timesheet_submit")
    try:
        ts.submit()
    except Exception:
        # keep the draft (the time is recorded) and report it through timesheet_status
        frappe.db.rollback(save_point="complete_task_timesheet_submit")
        frappe.log_error(
            title=f"Timesheet submit failed for {ts.name}",
            message=frappe.get_traceback(),
        )
        ts.reload()
    return ts


def _compute_due_date(project_start, phase_order, task_sort_order):
    """Compute start and end dates based on project start + phase delay + task stagger."""
    if not project_start:
        return None, None
    from datetime import timedelta

    base = project_start
    if isinstance(base, str):
        base = frappe.utils.get_datetime(base)
    phase_days = phase_order * 7
    start = base + timedelta(days=phase_days + (task_sort_order or 0))
    end = start + timedelta(days=3)
    if hasattr(start, "date"):
        start = start.date()
    if hasattr(end, "date"):
        end = end.date()
    return start, end


@frappe.whitelist()
def create_project(
    project_name: str,
    expected_start_date: str | None = None,
    expected_end_date: str | None = None,
    members: str | list = "[]",
    customer: str | None = None,
    project_lead: str | None = None,
    review_before_done: bool = False,
    project_type: str | None = None,
    department: str | None = None,
):
    """Create a new ERPNext Project with optional team members and lead."""
    import json

    existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
    if existing:
        frappe.throw(_("Project with this name already exists: {0}").format(existing))

    members_list = (
        json.loads(str(members)) if isinstance(members, str) else (members or [])
    )

    doc = frappe.get_doc(
        {
            "doctype": "Project",
            "project_name": project_name,
            "customer": customer or None,
            "expected_start_date": expected_start_date or None,
            "expected_end_date": expected_end_date or None,
            "status": "Open",
            "review_before_done": 1 if review_before_done else 0,
            "project_type": project_type or None,
            "custom_department": _pick_department(department),
        }
    )
    for m in members_list:
        doc.append(
            "users",
            {
                "user": m.get("user", ""),
                "custom_role": m.get("custom_role", ""),
            },
        )
    if frappe.session.user not in [u.user for u in doc.users]:
        doc.append(
            "users", {"user": frappe.session.user, "custom_role": MANAGER_PROJECT_ROLE}
        )
    if project_lead:
        if project_lead not in [u.user for u in doc.users]:
            doc.append("users", {"user": project_lead, "custom_role": "Developer"})
        doc.project_lead = project_lead
    doc.insert()
    return {
        "name": doc.name,
        "project_name": doc.project_name,
        "customer": doc.customer,
        "status": doc.status,
        "department": doc.custom_department,
    }


def _pick_department(department: str | None) -> str | None:
    """The department to save on a project; Project.validate refuses a newly picked inactive one."""
    return (department or "").strip() or None


@frappe.whitelist()
def generate_checklist(project: str, template: str):
    """Clone template tasks into ERPNext Project + Tasks."""
    project = _resolve_project(str(project), "write")
    template_name = str(template)

    if not frappe.db.exists("HD Task Template", template_name):
        frappe.throw(_("Template not found"))

    template_doc = frappe.get_doc("HD Task Template", template_name)
    template_doc.check_permission("read")

    project_users = frappe.get_all(
        "Project User", {"parent": project}, ["user", "custom_role"]
    )
    project_start = frappe.db.get_value("Project", project, "expected_start_date")

    # Collect distinct phase names in order
    phases_seen = []
    for ttask in template_doc.tasks:
        if ttask.phase_name and ttask.phase_name not in phases_seen:
            phases_seen.append(ttask.phase_name)

    role_pool = {}
    for u in project_users:
        role = u.get("custom_role") or "Common"
        if role not in role_pool:
            role_pool[role] = []
        role_pool[role].append(u["user"])

    role_counter = {}
    all_users = [u["user"] for u in project_users]

    def pick_user(category):
        role = CATEGORY_TO_ROLE.get(category, "Common")
        pool = role_pool.get(role, [])
        if pool:
            idx = role_counter.get(role, 0) % len(pool)
            user = pool[idx]
            role_counter[role] = idx + 1
            return user
        if all_users:
            idx = role_counter.get("__all__", 0) % len(all_users)
            user = all_users[idx]
            role_counter["__all__"] = idx + 1
            return user
        return None

    for ttask in template_doc.tasks:
        task_start, task_end = _compute_due_date(
            project_start,
            (
                phases_seen.index(ttask.phase_name)
                if ttask.phase_name in phases_seen
                else 0
            ),
            ttask.sort_order,
        )

        task_doc = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": ttask.task_name,
                "project": project,
                "description": ttask.description or "",
                "custom_category": ttask.category,
                "custom_phase": ttask.phase_name or "",
                "custom_module": ttask.module_name or "",
                "custom_estimated_hours": ttask.estimated_hours or 0,
                "priority": ttask.default_priority or "Medium",
                "status": "Open",
                "exp_start_date": task_start,
                "exp_end_date": task_end,
            }
        )
        task_doc.insert()
        _assign_user(task_doc, pick_user(ttask.category))

    return {"tasks_created": len(template_doc.tasks)}


def _is_project_member(project, user):
    return bool(
        frappe.db.exists(
            "Project User", {"parenttype": "Project", "parent": project, "user": user}
        )
    ) or (frappe.db.get_value("Project", project, "owner") == user)


def _add_member_for_assignment(project: str, user: str):
    """Assigning an agent from outside the team adds them to it as a Developer.

    Only reached by the project's manager or lead for an assignable agent (both
    checked by the caller); leads can't edit the project itself, hence
    ignore_permissions.
    """
    doc = frappe.get_doc("Project", project)
    doc.append("users", {"user": user, "custom_role": "Developer"})
    doc.save(ignore_permissions=True)
    doc.add_comment(
        "Info",
        _("{0} was added to the project when a task was assigned to them.").format(
            frappe.utils.escape_html(user)
        ),
    )


def _estimate_if_undated(task_doc):
    """No due date given: the AI sets one in the background (see helpdesk.task_estimates)."""
    from helpdesk.task_estimates import queue_estimate, should_estimate

    if should_estimate(task_doc):
        queue_estimate(task_doc)


@frappe.whitelist()
def estimate_undated_tasks(project: str) -> dict:
    """Managers and leads: let the AI set due dates for open tasks that have none."""
    from helpdesk.task_estimates import get_settings, queue_estimate

    project = _resolve_project(str(project))
    if not can_manage_project(project):
        frappe.throw(
            _("Only the project's manager or lead can do this."), frappe.PermissionError
        )
    if not get_settings().ai_task_estimates:
        frappe.throw(_("AI task estimates are turned off in HD Work Settings."))
    tasks = frappe.get_all(
        "Task",
        filters={
            "project": project,
            "exp_end_date": ("is", "not set"),
            "status": ("not in", ["Completed", "Cancelled", "Template"]),
        },
        pluck="name",
    )
    for name in tasks:
        queue_estimate(frappe._dict(name=name))
    return {"queued": len(tasks)}


def _assign_user(
    task_doc,
    user,
    ignore_permissions=False,
    assigned_by: str | None = None,
    note: str | None = None,
):
    """Assign an inserted Task to a user.

    Goes through a ToDo, which is what sets `_assign`; Frappe drops `_assign`
    when it is set on a document before insert. `ignore_permissions` is for
    callers that already checked the user may raise this task (ticket -> task).
    A background job passes `assigned_by` (else the session user is the assigner)
    and may pass `note`, which the assignment notification shows.
    """
    if not user:
        return
    user = str(user).strip()
    if frappe.db.exists("User", user):
        args = {"doctype": "Task", "name": task_doc.name, "assign_to": [user]}
        if assigned_by:
            args["assigned_by"] = assigned_by
        if note:
            args["description"] = note
        add_assignment(args, ignore_permissions=ignore_permissions)


@frappe.whitelist()
def add_task(
    project: str,
    task_name: str,
    phase: str = "",
    category: str = "Functional",
    priority: str = "Medium",
    estimated_hours: float | str = 0,
    assigned_to: str = "",
    due_date: str | None = None,
    description: str = "",
    is_key: bool = False,
    is_milestone: bool = False,
    depends_on_task: str | None = None,
    ai_description: bool = False,
):
    """Add a single task to a project, optionally assigned to one of its members.

    `ai_description`: the description is an unedited "Write with AI" draft.
    """
    project = _resolve_project(str(project))
    if not can_add_tasks(project):
        frappe.throw(
            _("Only people on this project can add tasks to it."),
            frappe.PermissionError,
        )
    if not str(task_name or "").strip():
        frappe.throw(_("Task name is required"))
    assigned_to = str(assigned_to or "").strip()
    manages = can_manage_project(project)
    if assigned_to and not _is_assignable(assigned_to):
        frappe.throw(_("{0} is not an active agent.").format(assigned_to))
    if assigned_to and not _is_project_member(project, assigned_to):
        # adding people to the team is the manager's call
        if not manages:
            frappe.throw(
                _(
                    "{0} isn't on this project. Ask the project's manager or lead to add them."
                ).format(assigned_to),
                frappe.PermissionError,
            )
        _add_member_for_assignment(project, assigned_to)
    doc = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": str(task_name).strip(),
            "description": str(description or ""),
            "project": project,
            "custom_category": str(category),
            "custom_phase": str(phase) if phase else "",
            "custom_estimated_hours": float(estimated_hours) or 0,
            "priority": str(priority),
            "status": "Open",
            "exp_end_date": due_date if due_date and due_date != "null" else None,
            "is_key": 1 if is_key else 0,
            "is_milestone": 1 if is_milestone else 0,
            "depends_on_task": depends_on_task or None,
            "custom_ai_description": 1
            if ai_description and str(description or "").strip()
            else 0,
        }
    )
    doc.insert()
    # a member may add work for a teammate; the rules above already allowed it
    _assign_user(doc, assigned_to, ignore_permissions=not manages)
    _estimate_if_undated(doc)
    doc.reload()
    return _format_task(_task_dict(doc))


@frappe.whitelist()
def get_my_tasks(
    project: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    """Get tasks assigned to current user."""
    user = frappe.session.user

    filters = {"_assign": ("like", f'%"{user}"%')}
    if project:
        filters["project"] = _resolve_project(str(project))
    if status:
        filters["status"] = str(status)

    tasks = frappe.get_list(
        "Task",
        filters=filters,
        fields=[
            "name",
            "subject",
            "project",
            "custom_category",
            "custom_phase",
            "status",
            "priority",
            "exp_end_date",
            "custom_estimated_hours",
            # due today and past its estimate is overdue too (isOverdue in taskMeta.ts)
            "custom_timer_start",
            "custom_timer_elapsed",
            "is_key",
            "hd_ticket",
            *TASK_HOLD_FIELDS,
            "is_milestone",
            "slip_count",
            "depends_on_task",
            "_assign",
        ],
        order_by="custom_phase asc",
        limit=limit,
    )
    project_names = dict(
        frappe.get_all(
            "Project",
            filters={"name": ("in", list({t.project for t in tasks if t.project}))},
            fields=["name", "project_name"],
            as_list=True,
        )
    )
    return add_assigners(
        [
            {**t, "project_name": project_names.get(t.get("project"))}
            for t in _format_tasks(tasks)
        ]
    )


@frappe.whitelist()
def get_task_detail(task: str):
    """Get a single task with all fields."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    return {
        **add_assigners([_format_task(_task_dict(doc))])[0],
        "pull_requests": get_pull_requests([doc.name]).get(doc.name, []),
    }


@frappe.whitelist()
def update_task_status(task: str, status: str):
    """Update a task's status."""
    frappe.has_permission("Task", "write", str(task), throw=True)
    _reject_direct_hold(str(status))
    _reject_completion_without_time(str(status))
    return {"status": _save_status(str(task), str(status))}


def _reject_completion_without_time(new_status: str):
    """Done work goes through complete_task, which logs the hours and notes."""
    if new_status in ("Completed", PENDING_REVIEW_STATUS):
        frappe.throw(
            _(
                "Use Complete on the task so your hours and notes are saved to the timesheet."
            )
        )


def _reject_direct_hold(new_status: str):
    if new_status == ON_HOLD:
        frappe.throw(_("Use Put on hold so you can say why the task is on hold."))


def _changes_hold(task: str, new_status: str) -> bool:
    """Holds need a reason and resuming moves the due date, so they go through the controller."""
    _reject_direct_hold(new_status)
    return frappe.db.get_value("Task", task, "status") == ON_HOLD


def _save_status(task: str, status: str) -> str:
    doc = frappe.get_doc("Task", task)
    doc.status = status
    doc.save()
    return doc.status


@frappe.whitelist()
def hold_task(task: str, reason: str, note: str = "") -> dict:
    """Pause a task (e.g. a broken laptop); it stops counting as overdue until resumed."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("write")
    if doc.status in ("Completed", "Cancelled"):
        frappe.throw(_("Completed or cancelled tasks can't be put on hold."))
    if doc.status == ON_HOLD:
        frappe.throw(_("This task is already on hold."))
    doc.status = ON_HOLD
    doc.hold_reason = reason
    doc.hold_note = (note or "").strip()
    doc.save()
    return _format_task(_task_dict(doc))


@frappe.whitelist()
def resume_task(task: str, extend_due_date: bool = True) -> dict:
    """End a hold; by default the days on hold are added to the due date."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("write")
    if doc.status != ON_HOLD:
        frappe.throw(_("This task isn't on hold."))
    doc.status = doc.hold_previous_status or "Open"
    doc.flags.extend_due_date = bool(extend_due_date)
    doc.save()
    return _format_task(_task_dict(doc))


@frappe.whitelist()
def request_help(
    task: str,
    teammate: str,
    task_name: str,
    description: str = "",
    due_date: str | None = None,
) -> dict:
    """The assignee asks a teammate for something their task needs.

    The teammate gets a new task in the same project and the asking task waits
    on it, so it shows as blocked until the help is done. The lead is told.
    """
    from helpdesk.work_reminders import notify_users

    doc = _get_own_task(task)
    teammate = _teammate(doc, teammate)
    if teammate == frappe.session.user:
        frappe.throw(_("Pick a teammate to ask, not yourself."))
    _check_no_open_dependency(doc)
    if not _is_on_team(doc.project, teammate):
        _add_member_for_assignment(doc.project, teammate)

    helper = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": _required_task_name(task_name),
            "description": str(description or ""),
            "project": doc.project,
            "custom_category": doc.custom_category,
            "custom_phase": doc.custom_phase,
            "priority": doc.priority,
            "status": "Open",
            "exp_end_date": _help_due_date(doc, due_date),
        }
    )
    # developers can't create tasks; _get_own_task checked this one is theirs
    helper.insert(ignore_permissions=True)
    _assign_user(helper, teammate, ignore_permissions=True)
    _estimate_if_undated(helper)

    doc.depends_on_task = helper.name
    doc.save()

    asker = _full_name(frappe.session.user)
    helper.add_comment(
        "Info",
        frappe.utils.escape_html(
            _("{0} asked for this to finish {1}: {2}").format(
                asker, doc.name, doc.subject
            )
        ),
    )
    doc.add_comment(
        "Info",
        frappe.utils.escape_html(
            _("Waiting on {0} ({1}), asked of {2} by {3}").format(
                helper.name, helper.subject, _full_name(teammate), asker
            )
        ),
    )
    notify_users(
        [teammate],
        "Task",
        helper.name,
        _("{0} needs your help: {1}").format(asker, helper.subject),
    )
    notify_users(
        [
            u
            for u in doc.leads_or_managers()
            if u not in (frappe.session.user, teammate)
        ],
        "Task",
        doc.name,
        _("{0} asked {1} for help, so {2} waits on it").format(
            asker, _full_name(teammate), doc.subject
        ),
    )
    helper.reload()
    return {
        "task": _format_task(_task_dict(doc)),
        "help_task": _format_task(_task_dict(helper)),
    }


@frappe.whitelist()
def hand_over_task(task: str, teammate: str, reason: str) -> dict:
    """The assignee passes their task to a teammate and says why; the lead is told."""
    from helpdesk.work_reminders import notify_users

    doc = _get_own_task(task)
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Say why you're handing it over."))
    teammate = _teammate(doc, teammate)
    previous = doc.assignees()
    if teammate in previous:
        frappe.throw(_("{0} already has this task.").format(_full_name(teammate)))
    if doc.custom_timer_start:
        frappe.throw(_("Stop the timer first, so your time on it is saved."))

    _reassign(doc, previous, teammate, ignore_permissions=True)
    doc.add_comment(
        "Info", frappe.utils.escape_html(_("Handed over: {0}").format(reason))
    )

    giver = _full_name(frappe.session.user)
    notify_users(
        [teammate],
        "Task",
        doc.name,
        _("{0} handed you a task: {1}").format(giver, doc.subject),
    )
    notify_users(
        [
            u
            for u in doc.leads_or_managers()
            if u not in (frappe.session.user, teammate)
        ],
        "Task",
        doc.name,
        _("{0} handed {1} to {2}: {3}").format(
            giver, doc.subject, _full_name(teammate), reason
        ),
    )
    return _format_task(_task_dict(doc))


def _get_own_task(task: str):
    """An open project task the caller is assigned to, or manages."""
    doc = frappe.get_doc("Task", str(task))
    if frappe.session.user not in doc.assignees() and not can_manage_project(
        doc.project
    ):
        frappe.throw(
            _("Only the task's assignee or the project lead can do this."),
            frappe.PermissionError,
        )
    if not doc.project:
        frappe.throw(_("Only tasks in a project can do this."))
    if doc.status in TASK_DONE:
        frappe.throw(_("This task is already closed."))
    return doc


def _teammate(doc, user: str) -> str:
    """An active agent on the task's project; leads and managers may pick anyone."""
    user = str(user or "").strip()
    if not user:
        frappe.throw(_("Pick a teammate."))
    if not _is_assignable(user):
        frappe.throw(_("{0} is not an active agent.").format(user))
    if not _is_on_team(doc.project, user) and not can_manage_project(doc.project):
        frappe.throw(
            _(
                "Pick someone on the project team. The project lead can add other people."
            )
        )
    return user


def _is_on_team(project: str, user: str) -> bool:
    return _is_project_member(project, user) or (
        frappe.db.get_value("Project", project, "project_lead") == user
    )


def _check_no_open_dependency(doc):
    """A task waits on one other task; an open one has to stay."""
    if not doc.depends_on_task:
        return
    dependency = frappe.db.get_value(
        "Task", doc.depends_on_task, ["status", "subject"], as_dict=True
    )
    if dependency and dependency.status not in TASK_DONE:
        frappe.throw(
            _(
                "This task already waits on {0} ({1}). Ask the project lead to change that first."
            ).format(doc.depends_on_task, dependency.subject)
        )


def _help_due_date(doc, due_date: str | None) -> str | None:
    """None lets the AI estimate it; a date must fit before the asking task is due."""
    if not due_date or due_date == "null":
        return None
    day = frappe.utils.getdate(due_date)
    if day < frappe.utils.getdate(frappe.utils.nowdate()):
        frappe.throw(_("The date can't be in the past."))
    if doc.exp_end_date and day > frappe.utils.getdate(doc.exp_end_date):
        frappe.throw(
            _(
                "Pick a date on or before {0}, when your task is due. Ask the project lead if your task needs more time."
            ).format(frappe.utils.formatdate(doc.exp_end_date))
        )
    return str(day)


def _full_name(user: str) -> str:
    return frappe.db.get_value("User", user, "full_name") or user


def _get_managed_task(task: str):
    doc = frappe.get_doc("Task", str(task))
    if not can_manage_project(doc.project):
        frappe.throw(
            _("Only the project's manager or lead can do this."),
            frappe.PermissionError,
        )
    return doc


@frappe.whitelist()
def update_task_plan(
    task: str,
    due_date: str | None = None,
    reason: str = "",
    is_key: bool | None = None,
    is_milestone: bool | None = None,
    depends_on_task: str | None = None,
    clear_dependency: bool = False,
) -> dict:
    """Leads and managers reschedule, flag and link tasks; moving a date later needs a reason."""
    doc = _get_managed_task(task)
    if due_date and str(due_date) != str(doc.exp_end_date or ""):
        later = doc.exp_end_date and frappe.utils.getdate(
            due_date
        ) > frappe.utils.getdate(doc.exp_end_date)
        if later and not (reason or "").strip():
            frappe.throw(_("Say why the due date is moving later."))
        doc.exp_end_date = due_date
        doc.flags.slip_reason = (reason or "").strip()
    if is_key is not None:
        doc.is_key = 1 if is_key else 0
    if is_milestone is not None:
        doc.is_milestone = 1 if is_milestone else 0
    if clear_dependency:
        doc.depends_on_task = None
    elif depends_on_task:
        doc.depends_on_task = depends_on_task
    doc.save()
    return _format_task(_task_dict(doc))


@frappe.whitelist()
def update_task(
    task: str,
    task_name: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    phase: str | None = None,
    estimated_hours: float | str | None = None,
    assigned_to: str | None = None,
    ai_description: bool | None = None,
) -> dict:
    """Edit a task's details. Leads and managers change anything; its assignee only the description.

    `ai_description`: the description sent is an unedited "Write with AI" draft.

    Only the fields passed change. Dates, key, milestone and dependency go through
    update_task_plan, which asks why a due date moves later.
    """
    doc = frappe.get_doc("Task", str(task))
    details = {
        "task_name": task_name,
        "priority": priority,
        "category": category,
        "phase": phase,
        "estimated_hours": estimated_hours,
        "assigned_to": assigned_to,
    }
    _check_can_edit(doc, details)

    if task_name is not None:
        doc.subject = _required_task_name(task_name)
    if description is not None:
        doc.description = str(description)
        if ai_description and doc.description.strip():
            doc.custom_ai_description = 1
            doc.flags.ai_description = True
    if priority is not None:
        doc.priority = _task_option("priority", str(priority), _("Priority"))
    if category is not None:
        doc.custom_category = (
            _task_option("custom_category", str(category), _("Category"))
            if str(category)
            else ""
        )
    if phase is not None:
        doc.custom_phase = str(phase).strip()
    if estimated_hours is not None:
        doc.custom_estimated_hours = _estimated_hours(estimated_hours)
    new_assignee = None if assigned_to is None else str(assigned_to).strip()
    if new_assignee and not _is_assignable(new_assignee):
        frappe.throw(_("{0} is not an active agent.").format(new_assignee))

    previous_assignees = doc.assignees()
    # saved before reassigning: save() writes the loaded `_assign` back, which
    # would undo the ToDo changes below
    doc.save()
    if new_assignee is not None:
        _reassign(doc, previous_assignees, new_assignee)
    return _format_task(_task_dict(doc))


def _check_can_edit(doc, details: dict):
    """Leads and managers edit everything; the assignee may only rewrite the description."""
    if can_manage_project(doc.project):
        return
    if frappe.session.user not in doc.assignees():
        frappe.throw(_("You can't edit this task."), frappe.PermissionError)
    if any(value is not None for value in details.values()):
        frappe.throw(
            _(
                "Only the project's manager or lead can change this. You can edit the description."
            ),
            frappe.PermissionError,
        )


def _required_task_name(task_name: str) -> str:
    task_name = str(task_name).strip()
    if not task_name:
        frappe.throw(_("Task name is required"))
    return task_name


def _task_option(fieldname: str, value: str, label: str) -> str:
    """The value, if it's one of the Task select field's options."""
    options = [
        o
        for o in (frappe.get_meta("Task").get_options(fieldname) or "").split("\n")
        if o
    ]
    if value not in options:
        frappe.throw(
            _("{0} must be one of: {1}").format(label, ", ".join(options)),
        )
    return value


def _estimated_hours(value: float | str) -> float:
    try:
        hours = float(value or 0)
    except (TypeError, ValueError):
        frappe.throw(_("Estimated hours must be a number."))
    if hours < 0:
        frappe.throw(_("Estimated hours can't be negative."))
    return hours


def _reassign(
    doc, previous: list[str], new_assignee: str, ignore_permissions: bool = False
):
    """Hand the task to `new_assignee` ("" = nobody) through ToDos.

    Going through assign_to keeps `_assign` in step, cancels the old assignee's
    ToDo and sends the new one Frappe's assignment notification.
    `ignore_permissions` is for an assignee handing their own task over: once
    their ToDo is cancelled they can no longer read it to assign the next person.
    """
    new = [new_assignee] if new_assignee else []
    if set(previous) == set(new):
        return
    if (
        new_assignee
        and doc.project
        and not _is_project_member(doc.project, new_assignee)
    ):
        _add_member_for_assignment(doc.project, new_assignee)
    for user in previous:
        if user not in new:
            # the caller manages the project or hands over their own task (checked by the caller)
            remove_assignment("Task", doc.name, user, ignore_permissions=True)
    if new_assignee and new_assignee not in previous:
        _assign_user(doc, new_assignee, ignore_permissions=ignore_permissions)

    doc.add_comment(
        "Info",
        frappe.utils.escape_html(
            _("Reassigned from {0} to {1} by {2}").format(
                ", ".join(_full_name(u) for u in previous) or _("nobody"),
                _full_name(new_assignee) if new_assignee else _("nobody"),
                _full_name(frappe.session.user),
            )
        ),
    )


@frappe.whitelist()
def approve_task(task: str) -> dict:
    """Lead signs off a reviewed task."""
    doc = _get_managed_task(task)
    if doc.status != "Pending Review":
        frappe.throw(_("Only tasks waiting for review can be approved."))
    doc.status = "Completed"
    doc.save()
    doc.add_comment("Info", _("Approved."))
    return _format_task(_task_dict(doc))


@frappe.whitelist()
def send_back_task(task: str, note: str) -> dict:
    """Lead returns a reviewed task with what still needs doing."""
    from helpdesk.work_reminders import notify_users

    doc = _get_managed_task(task)
    if doc.status != "Pending Review":
        frappe.throw(_("Only tasks waiting for review can be sent back."))
    note = (note or "").strip()
    if not note:
        frappe.throw(_("Say what still needs doing."))
    doc.status = "Open"
    doc.save()
    doc.add_comment("Info", frappe.utils.escape_html(_("Sent back: {0}").format(note)))
    notify_users(
        [u for u in doc.assignees() if u != frappe.session.user],
        "Task",
        doc.name,
        _("Sent back on {0}: {1}").format(
            frappe.utils.formatdate(frappe.utils.nowdate()), doc.subject
        ),
    )
    return _format_task(_task_dict(doc))


@frappe.whitelist(methods=["POST"])
def move_task_to_project(task: str, project: str) -> dict:
    """Move a task made in the wrong project to another one.

    Whoever assigned it, the project's managers and lead, and admins may move it;
    its assignee may not. The target must be an open project the mover can add
    tasks to. A phase the target doesn't have and dependencies (which stay within
    one project) are cleared; the assignee keeps the task and is told.
    """
    from helpdesk.work_reminders import notify_users

    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    assignees = doc.assignees()
    assigner = (
        get_assigners({doc.name: assignees[0]}).get(doc.name) if assignees else None
    )
    if not can_move_task(doc.project, assigner, assignees):
        frappe.throw(
            _(
                "Only the person who assigned this task, or the project's manager or lead, can move it."
            ),
            frappe.PermissionError,
        )
    if doc.status in TASK_DONE:
        frappe.throw(_("Closed tasks stay in their project."))
    target = _move_target(doc, str(project))

    source = doc.project
    moved = _move_to_project(doc, target)
    # the checks above are the decision: an assigner who doesn't manage either
    # project has no write permission on a task assigned to someone else
    doc.save(ignore_permissions=True)
    moved["dependents_released"] = _release_dependents(doc.name)
    moved["not_on_team"] = _join_target_team(target, assignees)

    mover = _full_name(frappe.session.user)
    target_name = _project_label(target)
    doc.add_comment(
        "Info", frappe.utils.escape_html(_move_note(source, target_name, mover, moved))
    )
    notify_users(
        [u for u in assignees if u != frappe.session.user],
        "Task",
        doc.name,
        _("{0} moved {1} to {2}").format(mover, doc.subject, target_name),
    )
    return {**add_assigners([_format_task(_task_dict(doc))])[0], **moved}


def _move_target(doc, project: str) -> str:
    """The project to move to: another open one the caller may add tasks to."""
    target = _resolve_project(project)
    if target == doc.project:
        frappe.throw(_("The task is already in this project."))
    if not can_add_tasks(target):
        frappe.throw(
            _("You can only move it to a project you can add tasks to."),
            frappe.PermissionError,
        )
    if frappe.db.get_value("Project", target, "status") != "Open":
        frappe.throw(_("Pick an open project."))
    return target


def _move_to_project(doc, target: str) -> dict:
    """Point the task at `target`, dropping what only made sense in the old project."""
    phase = doc.custom_phase or ""
    keeps_phase = not phase or bool(
        frappe.db.exists("Task", {"project": target, "custom_phase": phase})
    )
    cleared = {
        "phase_cleared": "" if keeps_phase else phase,
        "dependency_cleared": doc.depends_on_task or "",
    }
    doc.project = target
    if not keeps_phase:
        doc.custom_phase = ""
    # a task only waits on tasks in its own project
    doc.depends_on_task = None
    return cleared


def _release_dependents(task: str) -> int:
    """Tasks left behind that waited on the moved one stop waiting on it."""
    table = frappe.qb.DocType("Task")
    dependents = (
        frappe.qb.from_(table)
        .select(table.name)
        .where(table.depends_on_task == task)
        .run(pluck=True)
    )
    for name in dependents:
        frappe.db.set_value("Task", name, "depends_on_task", None)
    return len(dependents)


def _join_target_team(target: str, assignees: list[str]) -> list[str]:
    """The assignees join the new project's team when the mover may add people
    (its managers and lead); otherwise the ones still outside it are returned."""
    outside = [u for u in assignees if not _is_on_team(target, u)]
    if not outside or not can_manage_project(target):
        return outside
    joined = [u for u in outside if _is_assignable(u)]
    for user in joined:
        _add_member_for_assignment(target, user)
    return [u for u in outside if u not in joined]


def _project_label(project: str) -> str:
    return frappe.db.get_value("Project", project, "project_name") or project


def _move_note(source: str, target_name: str, mover: str, moved: dict) -> str:
    note = _("Moved from {0} to {1} by {2}.").format(
        _project_label(source), target_name, mover
    )
    if moved["phase_cleared"]:
        note += " " + _("Phase {0} cleared: the new project has no such phase.").format(
            moved["phase_cleared"]
        )
    if moved["dependency_cleared"]:
        note += " " + _("It no longer waits on {0}.").format(
            moved["dependency_cleared"]
        )
    if moved["dependents_released"]:
        note += " " + _("{0} task(s) in the old project no longer wait on it.").format(
            moved["dependents_released"]
        )
    return note


@frappe.whitelist()
def get_project_dashboard(project: str):
    """Get aggregate stats and phase data for the PM dashboard.

    Built from the tasks the user can see, so members get stats for their own
    tasks and managers for the whole project.
    """
    project = _resolve_project(str(project))

    tasks = frappe.get_list(
        "Task",
        filters={"project": project},
        fields=[
            "name",
            "subject",
            "custom_category",
            "custom_phase",
            "status",
            "priority",
            "exp_end_date",
            "custom_estimated_hours",
            "custom_timer_start",
            "custom_timer_elapsed",
            "is_key",
            "hd_ticket",
            *TASK_HOLD_FIELDS,
            "is_milestone",
            "slip_count",
            "depends_on_task",
            "_assign",
            "creation",
        ],
        order_by="custom_phase asc, subject asc",
    )

    # helpdesk.api.work imports this module, so it's imported here, not at the top
    from helpdesk.api.work import is_task_overdue

    today = frappe.utils.getdate(frappe.utils.today())

    def due(task):
        return frappe.utils.getdate(task.exp_end_date) if task.exp_end_date else None

    def count(status):
        return sum(1 for t in tasks if t.status == status)

    total_tasks = len(tasks)
    completed = count("Completed")
    cancelled = count("Cancelled")
    overdue = sum(1 for t in tasks if is_task_overdue(t, due(t), today))
    progress_pct = round((completed / total_tasks * 100), 1) if total_tasks > 0 else 0

    # phases in order of their first task's creation
    phase_stats = {}
    for t in sorted(tasks, key=lambda t: t.creation):
        if not t.custom_phase:
            continue
        stats = phase_stats.setdefault(
            t.custom_phase, {"total_count": 0, "completed_count": 0}
        )
        stats["total_count"] += 1
        stats["completed_count"] += t.status == "Completed"

    phases = [
        {
            "name": phase,
            "phase_name": phase,
            "total_count": st["total_count"],
            "completed_count": st["completed_count"],
            "progress_pct": round(st["completed_count"] / st["total_count"] * 100, 1),
        }
        for phase, st in phase_stats.items()
    ]

    for t in tasks:
        t.pop("creation", None)

    milestones = sorted(
        (
            {
                "name": t.name,
                "subject": t.subject,
                "status": t.status,
                "due_date": t.exp_end_date,
                "slip_count": t.slip_count or 0,
                "is_overdue": is_task_overdue(t, due(t), today),
            }
            for t in tasks
            if t.is_milestone
        ),
        key=lambda m: str(m["due_date"] or "9999-12-31"),
    )

    return {
        "phases": phases,
        "milestones": milestones,
        "tasks": _format_tasks(tasks),
        "stats": {
            "total": total_tasks,
            "completed": completed,
            "in_progress": count("Working"),
            "pending": count("Open"),
            "reviewing": count("Pending Review"),
            "on_hold": count(ON_HOLD),
            "rescheduled": sum(1 for t in tasks if t.slip_count),
            "cancelled": cancelled,
            "blocked": cancelled,
            "overdue": overdue,
            "completion_pct": progress_pct,
        },
    }


@frappe.whitelist()
def get_phase_tasks(project: str, phase: str):
    """Get all tasks in a phase for the given project."""
    project = _resolve_project(str(project))
    phase = str(phase)
    tasks = frappe.get_list(
        "Task",
        filters={"project": project, "custom_phase": phase},
        fields=[
            "name",
            "subject",
            "custom_category",
            "custom_phase",
            "status",
            "priority",
            "exp_end_date",
            "custom_estimated_hours",
            # due today and past its estimate is overdue too (isOverdue in taskMeta.ts)
            "custom_timer_start",
            "custom_timer_elapsed",
            "is_key",
            "hd_ticket",
            *TASK_HOLD_FIELDS,
            "is_milestone",
            "slip_count",
            "depends_on_task",
            "_assign",
        ],
        order_by="subject asc",
    )
    return _format_tasks(tasks)


@frappe.whitelist()
def get_kanban_tasks(project: str | None = None):
    """Tasks grouped by status for the board: one project's, or without `project` the
    current user's own tasks across every project (the sidebar's Board)."""
    if project:
        filters = {"project": _resolve_project(str(project))}
        or_filters = None
    else:
        user = frappe.session.user
        filters = {
            "_assign": ("like", f'%"{user}"%'),
            "status": ("!=", "Template"),
        }
        # finished work stays a month, so the done columns don't grow forever
        month_ago = frappe.utils.add_days(frappe.utils.nowdate(), -30)
        or_filters = {
            "status": ("not in", ["Completed", "Cancelled"]),
            "modified": (">=", month_ago),
        }
    tasks = frappe.get_list(
        "Task",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name",
            "subject",
            "project",
            "custom_category",
            "custom_phase",
            "status",
            "priority",
            "exp_end_date",
            "custom_estimated_hours",
            "is_key",
            "hd_ticket",
            *TASK_HOLD_FIELDS,
            "is_milestone",
            "slip_count",
            "depends_on_task",
            "_assign",
            "custom_timer_start",
            "custom_timer_elapsed",
            "custom_recurring_task",
        ],
        order_by="custom_phase asc, subject asc",
    )
    if not project:
        # LIKE reads `_` and `%` in the user ID as wildcards, so keep exact matches only
        tasks = [t for t in tasks if user in json.loads(t._assign or "[]")]

    # one query for the whole board; a card shows its most recently active open PR
    open_prs = get_pull_requests([t.name for t in tasks], open_only=True)

    columns = {
        "Open": [],
        "Working": [],
        "Pending Review": [],
        ON_HOLD: [],
        "Completed": [],
        "Cancelled": [],
    }
    # across projects each card says which one it belongs to
    project_names = (
        {}
        if project
        else dict(
            frappe.get_all(
                "Project",
                filters={"name": ("in", list({t.project for t in tasks if t.project}))},
                fields=["name", "project_name"],
                as_list=True,
            )
        )
    )
    for t in add_assigners(_format_tasks(tasks)):
        t["project_name"] = project_names.get(t.get("project"))
        status = t.get("status") or "Open"
        if status not in columns:
            status = "Open"
        prs = open_prs.get(t["name"])
        columns[status].append({**t, "pull_request": prs[0] if prs else None})

    return {"columns": columns}


@frappe.whitelist()
def get_templates():
    """List all available implementation templates."""
    return frappe.get_list(
        "HD Task Template", fields=["name", "template_name", "industry", "description"]
    )


@frappe.whitelist()
def create_template(
    template_name: str,
    industry: str = "",
    description: str = "",
    tasks: str | list = "[]",
):
    """Create a new HD Task Template with tasks."""
    import json

    tasks_list = json.loads(str(tasks)) if isinstance(tasks, str) else tasks

    existing = frappe.db.exists("HD Task Template", {"template_name": template_name})
    if existing:
        frappe.throw(_("Template '{0}' already exists").format(template_name))

    doc = frappe.get_doc(
        {
            "doctype": "HD Task Template",
            "template_name": template_name,
            "industry": industry,
            "description": description,
            "tasks": [],
        }
    )
    for t in tasks_list:
        doc.append(
            "tasks",
            {
                "task_name": t.get("task_name", ""),
                "phase_name": t.get("phase_name", ""),
                "category": t.get("category", "Functional"),
                "default_priority": t.get("default_priority", "Medium"),
                "estimated_hours": t.get("estimated_hours", 0),
            },
        )
    doc.insert()
    return {"name": doc.name, "template_name": doc.template_name}


@frappe.whitelist()
def get_template(template: str):
    """Get a single template with all tasks."""
    doc = frappe.get_doc("HD Task Template", str(template))
    doc.check_permission("read")
    return {
        "name": doc.name,
        "template_name": doc.template_name,
        "industry": doc.industry or "",
        "description": doc.description or "",
        "tasks": [
            {
                "task_name": t.task_name,
                "phase_name": t.phase_name or "",
                "category": t.category,
                "default_priority": t.default_priority,
                "estimated_hours": t.estimated_hours,
                "sort_order": t.sort_order,
            }
            for t in doc.tasks
        ],
    }


@frappe.whitelist()
def update_template(
    template: str,
    template_name: str,
    industry: str = "",
    description: str = "",
    tasks: str | list = "[]",
):
    """Update an existing HD Task Template."""
    import json

    tasks_list = json.loads(str(tasks)) if isinstance(tasks, str) else tasks
    doc = frappe.get_doc("HD Task Template", str(template))
    doc.template_name = template_name
    doc.industry = industry
    doc.description = description
    doc.tasks = []
    for t in tasks_list:
        doc.append(
            "tasks",
            {
                "task_name": t.get("task_name", ""),
                "phase_name": t.get("phase_name", ""),
                "category": t.get("category", "Functional"),
                "default_priority": t.get("default_priority", "Medium"),
                "estimated_hours": t.get("estimated_hours", 0),
            },
        )
    doc.save()
    return {"name": doc.name, "template_name": doc.template_name}


@frappe.whitelist()
def get_project_detail(project: str):
    """Get ERPNext project details."""
    project = _resolve_project(str(project))
    doc = frappe.get_doc("Project", project)
    return {
        "name": doc.name,
        "project_name": doc.project_name,
        "customer": doc.customer,
        "status": doc.status,
        "priority": doc.priority,
        "expected_start_date": (
            str(doc.expected_start_date) if doc.expected_start_date else None
        ),
        "expected_end_date": (
            str(doc.expected_end_date) if doc.expected_end_date else None
        ),
        "users": (
            [
                {"user": u.user, "full_name": u.full_name, "role": u.custom_role}
                for u in doc.users
            ]
            if doc.users
            else []
        ),
        "can_manage": can_manage_project(doc.name),
        "can_add_tasks": can_add_tasks(doc.name),
        "can_change_lead": is_project_owner(doc.name),
        "project_lead": doc.project_lead,
        "project_lead_name": (
            frappe.db.get_value("User", doc.project_lead, "full_name")
            if doc.project_lead
            else None
        ),
        "review_before_done": bool(doc.review_before_done),
        "project_type": doc.project_type,
        "department": doc.custom_department,
        "file_count": file_counts([doc.name]).get(doc.name, 0),
    }


@frappe.whitelist()
def get_users() -> list[dict]:
    """People who can be on a project or get a task: active agents whose account is enabled."""
    agent = frappe.qb.DocType("HD Agent")
    user = frappe.qb.DocType("User")
    return (
        frappe.qb.from_(agent)
        .join(user)
        .on(agent.user == user.name)
        .select(user.name, user.full_name, user.email, user.user_image)
        .where((agent.is_active == 1) & (user.enabled == 1))
        .orderby(user.full_name)
        .run(as_dict=True)
    )


def _is_assignable(user: str) -> bool:
    return bool(
        frappe.db.exists("HD Agent", {"user": user, "is_active": 1})
        and frappe.db.get_value("User", user, "enabled")
    )


@frappe.whitelist()
def get_projects():
    """List projects visible to the current user."""
    projects = frappe.get_list(
        "Project",
        fields=[
            "name",
            "project_name",
            "customer",
            "status",
            "expected_start_date",
            "expected_end_date",
            "priority",
            "project_lead",
            "custom_department as department",
        ],
    )
    lead_names = dict(
        frappe.get_all(
            "User",
            filters={
                "name": ("in", [p.project_lead for p in projects if p.project_lead])
            },
            fields=["name", "full_name"],
            as_list=True,
        )
    )
    files = file_counts([p.name for p in projects])
    for p in projects:
        p["file_count"] = files.get(p.name, 0)
        p["can_manage"] = can_manage_project(p["name"])
        p["can_add_tasks"] = can_add_tasks(p["name"])
        p["can_edit"] = is_project_owner(p["name"])
        p["project_lead_name"] = lead_names.get(p.project_lead)
    return projects


@frappe.whitelist(methods=["POST"])
def record_project_view(project: str) -> None:
    """Remember that the user opened a project, for Recent projects.

    Kept in Frappe's View Log (one row per person and project, its `modified`
    the last visit), so it follows the user across devices; only the latest
    RECENT_PROJECTS are kept.
    """
    project = _resolve_project(str(project))
    user = frappe.session.user
    existing = frappe.db.get_value(
        "View Log",
        {"viewed_by": user, "reference_doctype": "Project", "reference_name": project},
    )
    if existing:
        frappe.db.set_value(
            "View Log", existing, "modified", frappe.utils.now(), update_modified=False
        )
    else:
        frappe.get_doc(
            {
                "doctype": "View Log",
                "viewed_by": user,
                "reference_doctype": "Project",
                "reference_name": project,
            }
        ).insert(ignore_permissions=True)
    _trim_recent_projects(user)


def _recent_project_logs(user: str) -> list:
    log = frappe.qb.DocType("View Log")
    return (
        frappe.qb.from_(log)
        .select(log.name, log.reference_name)
        .where((log.viewed_by == user) & (log.reference_doctype == "Project"))
        .orderby(log.modified, order=Order.desc)
        .run(as_dict=True)
    )


def _trim_recent_projects(user: str):
    old = [row.name for row in _recent_project_logs(user)[RECENT_PROJECTS:]]
    if old:
        frappe.db.delete("View Log", {"name": ("in", old)})


@frappe.whitelist()
def get_recent_projects() -> list[dict]:
    """The projects the user opened lately, newest first: only those they can
    still read, so deleted projects and ones they left drop out."""
    names = list(
        dict.fromkeys(
            row.reference_name
            for row in _recent_project_logs(frappe.session.user)[:RECENT_PROJECTS]
        )
    )
    if not names:
        return []
    projects = {
        p.name: p
        for p in frappe.get_list(
            "Project",
            filters={"name": ("in", names)},
            fields=["name", "project_name", "customer", "status"],
            limit_page_length=RECENT_PROJECTS,
        )
    }
    return [projects[name] for name in names if name in projects]


@frappe.whitelist()
def update_project(
    project: str,
    project_name: str,
    customer: str | None = None,
    expected_start_date: str | None = None,
    expected_end_date: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    members: str | list | None = None,
    project_lead: str | None = None,
    review_before_done: bool | None = None,
    project_type: str | None = None,
    department: str | None = None,
):
    """Edit a project's details, members and lead. Project owners only.

    Leaving `department` out keeps the project's department; an empty one clears it.
    """
    project = _resolve_project(str(project))
    if not is_project_owner(project):
        frappe.throw(
            _("Only the project's manager can edit it."), frappe.PermissionError
        )

    project_name = (project_name or "").strip()
    if not project_name:
        frappe.throw(_("Project name is required"))
    clash = frappe.db.get_value(
        "Project", {"project_name": project_name, "name": ("!=", project)}, "name"
    )
    if clash:
        frappe.throw(_("Another project already has this name: {0}").format(clash))

    doc = frappe.get_doc("Project", project)
    doc.project_name = project_name
    doc.customer = customer or None
    doc.expected_start_date = expected_start_date or None
    doc.expected_end_date = expected_end_date or None
    if status:
        doc.status = status
    if priority:
        doc.priority = priority
    if review_before_done is not None:
        doc.review_before_done = 1 if review_before_done else 0
    if project_type is not None:
        doc.project_type = project_type or None
    if department is not None:
        doc.custom_department = _pick_department(department)

    if members is not None:
        members_list = json.loads(members) if isinstance(members, str) else members
        doc.set("users", [])
        for m in members_list or []:
            if m.get("user"):
                doc.append(
                    "users",
                    {"user": m["user"], "custom_role": m.get("custom_role") or ""},
                )
        # an editing manager stays on the project (admins manage without being members)
        me = frappe.session.user
        if not is_tasky_admin(me) and me not in [u.user for u in doc.users]:
            doc.append("users", {"user": me, "custom_role": MANAGER_PROJECT_ROLE})

    lead = (project_lead or "").strip() or None
    if lead and lead not in [u.user for u in doc.users]:
        doc.append("users", {"user": lead, "custom_role": "Developer"})
    if lead != doc.project_lead:
        _change_lead(doc, lead)
    else:
        doc.save()
    return {"name": doc.name, "project_name": doc.project_name}


@frappe.whitelist()
def set_project_lead(project: str, user: str | None = None):
    """Make a project member the project lead (or clear it). Project owners only."""
    project = _resolve_project(str(project))
    if not is_project_owner(project):
        frappe.throw(
            _("Only the project's manager can change its lead."), frappe.PermissionError
        )
    doc = frappe.get_doc("Project", project)
    user = (user or "").strip() or None
    if user and user not in [u.user for u in doc.users]:
        frappe.throw(
            _("{0} is not a member of this project. Add them first.").format(user)
        )
    _change_lead(doc, user)
    return {"project_lead": doc.project_lead}


@frappe.whitelist()
def rotate_project_lead(project: str):
    """Hand the lead to the next developer in the member list, wrapping around."""
    project = _resolve_project(str(project))
    if not is_project_owner(project):
        frappe.throw(
            _("Only the project's manager can change its lead."), frappe.PermissionError
        )
    doc = frappe.get_doc("Project", project)
    candidates = [u.user for u in doc.users if u.custom_role in LEAD_ROTATION_ROLES]
    if not candidates:
        frappe.throw(_("Add developers to the project to rotate the lead among them."))
    current = (
        candidates.index(doc.project_lead) if doc.project_lead in candidates else -1
    )
    _change_lead(doc, candidates[(current + 1) % len(candidates)])
    return {"project_lead": doc.project_lead}


def _change_lead(doc, user):
    previous = doc.project_lead
    if previous == user:
        return
    doc.project_lead = user
    doc.save()
    name = lambda u: frappe.db.get_value("User", u, "full_name") or u  # noqa: E731
    doc.add_comment(
        "Info",
        _("Project lead changed from {0} to {1}").format(
            name(previous) if previous else _("nobody"),
            name(user) if user else _("nobody"),
        ),
    )


# === Timer ===


@frappe.whitelist(methods=["POST"])
def start_timer(task: str):
    """Resume the paused timer of a task in progress.

    Only this task's timer, and only when asked: pausing (stop_timer) keeps the
    task in Working with its time banked, and nothing else starts it again.
    """
    task_id = str(task)
    frappe.has_permission("Task", "write", task_id, throw=True)
    status, running = frappe.db.get_value(
        "Task", task_id, ["status", "custom_timer_start"]
    )
    if status != "Working":
        frappe.throw(_("Start the task first; its timer runs while it's in progress."))
    if not running:
        frappe.db.set_value("Task", task_id, "custom_timer_start", frappe.utils.now())
    return {"ok": 1}


@frappe.whitelist(methods=["POST"])
def stop_timer(task: str):
    """Pause the timer: bank the time so far; the task stays in progress."""
    task_id = str(task)
    frappe.has_permission("Task", "write", task_id, throw=True)
    timer_start = frappe.db.get_value("Task", task_id, "custom_timer_start")
    if not timer_start:
        return {"elapsed": 0}
    elapsed = _timer_hours(timer_start)
    actual = frappe.db.get_value("Task", task_id, "custom_actual_hours") or 0
    paused = frappe.db.get_value("Task", task_id, "custom_timer_elapsed") or 0
    frappe.db.set_value("Task", task_id, "custom_timer_start", None)
    frappe.db.set_value(
        "Task", task_id, "custom_actual_hours", actual + round(elapsed, 2)
    )
    frappe.db.set_value(
        "Task", task_id, "custom_timer_elapsed", paused + round(elapsed, 2)
    )
    return {"elapsed": round(elapsed, 2)}


@frappe.whitelist()
def move_task(task: str, new_status: str):
    """Move a task column — update timer, status, elapsed. No doc.save() to prevent deadlock."""
    task_id = str(task)
    frappe.has_permission("Task", "write", task_id, throw=True)
    old_status = frappe.db.get_value("Task", task_id, "status")
    elapsed_paused = frappe.db.get_value("Task", task_id, "custom_timer_elapsed") or 0
    timer_start = frappe.db.get_value("Task", task_id, "custom_timer_start")
    actual = frappe.db.get_value("Task", task_id, "custom_actual_hours") or 0
    elapsed_this_move = 0

    if old_status == new_status:
        return {"status": old_status, "elapsed": 0}
    _reject_completion_without_time(new_status)
    if _changes_hold(task_id, new_status):
        return {"status": _save_status(task_id, new_status), "elapsed": 0}

    # Leaving Working: accumulate elapsed from running timer
    if old_status == "Working" and timer_start:
        elapsed_this_move = _timer_hours(timer_start)
        frappe.db.set_value("Task", task_id, "custom_timer_start", None)
        frappe.db.set_value(
            "Task", task_id, "custom_actual_hours", actual + round(elapsed_this_move, 2)
        )

        # Pausing to Open or PendingReview: save elapsed so timer resumes
        if new_status in ("Open", "Pending Review"):
            frappe.db.set_value(
                "Task",
                task_id,
                "custom_timer_elapsed",
                (elapsed_paused or 0) + round(elapsed_this_move, 2),
            )

    # Entering Working: start timer (fresh or resume)
    if new_status == "Working":
        frappe.db.set_value("Task", task_id, "custom_timer_start", frappe.utils.now())

    # the controller checks dependencies, review and ticket hand-back
    status = _save_status(task_id, new_status)
    return {"status": status, "elapsed": round(elapsed_this_move, 2)}


@frappe.whitelist()
def get_timer(task: str):
    """Get current timer state for a task."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    if not doc.custom_timer_start:
        return {"running": False, "elapsed": 0, "timer_start": None}
    elapsed = _timer_hours(doc.custom_timer_start)
    return {
        "running": True,
        "elapsed": round(elapsed, 2),
        "timer_start": str(doc.custom_timer_start),
    }


def _timer_hours(timer_start) -> float:
    """Hours the timer has run. The start was stored in the site's time zone, so
    compare with now in that zone, not the server clock (UTC on our servers)."""
    started = frappe.utils.get_datetime(timer_start)
    elapsed = (frappe.utils.now_datetime() - started).total_seconds() / 3600.0
    return max(elapsed, 0.0)


@frappe.whitelist()
def get_my_timesheets(
    limit: int = 20,
    team: bool = False,
    agent: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    """My timesheets with project info; `team` shows everyone's that a lead or manager may see.

    `agent` narrows the team view to one person; `from_date` / `to_date` to when it was logged.
    """
    # get_list applies the timesheet permission rules: a lead sees the
    # timesheets on their projects, admins see all
    timesheets = frappe.get_list(
        "Timesheet",
        filters=_timesheet_filters(team, agent, from_date, to_date),
        fields=[
            "name",
            "title",
            "status",
            "total_hours",
            "creation",
            "modified",
            "owner",
        ],
        order_by="modified desc",
        limit_page_length=frappe.utils.cint(limit) or 20,
        # a date filter joins the time logs; one row per timesheet
        distinct=True,
    )
    names = {}
    for ts in timesheets:
        projects = frappe.db.sql(
            """
            SELECT DISTINCT td.project
            FROM `tabTimesheet Detail` td
            WHERE td.parent = %s AND td.project IS NOT NULL AND td.project != ''
            LIMIT 3
        """,
            ts["name"],
            as_dict=True,
        )
        ts["projects"] = [p["project"] for p in projects]
        if ts["projects"]:
            proj_name = frappe.db.get_value(
                "Project", ts["projects"][0], "project_name"
            )
            ts["project_name"] = proj_name
        if ts.owner not in names:
            names[ts.owner] = _full_name(ts.owner)
        ts["owner_name"] = names[ts.owner]
    return timesheets


@frappe.whitelist()
def get_timesheet_agents() -> list[dict]:
    """Everyone with a timesheet the lead or manager may see, for the team filter."""
    _timesheet_filters(team=True)
    owners = frappe.get_list(
        "Timesheet", fields=["owner"], distinct=True, limit_page_length=0
    )
    people = [{"user": o.owner, "full_name": _full_name(o.owner)} for o in owners]
    return sorted(people, key=lambda p: p["full_name"].lower())


@frappe.whitelist()
def export_timesheets_csv(
    team: bool = False,
    agent: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    """Download the timesheets on screen as CSV, one row per time log."""
    import csv
    import io

    sheets = _visible_timesheets(
        team, agent, from_date, to_date, ["name", "title", "status", "owner"]
    )
    logs = (
        frappe.get_all(
            "Timesheet Detail",
            filters=_time_log_filters(sheets, from_date, to_date),
            fields=[
                "parent",
                "from_time",
                "hours",
                "project",
                "task",
                "description",
                "custom_billable",
            ],
            order_by="from_time asc",
        )
        if sheets
        else []
    )
    projects = _names_of("Project", "project_name", {log.project for log in logs})
    tasks = _names_of("Task", "subject", {log.task for log in logs})

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            _("Date"),
            _("Agent"),
            _("Timesheet"),
            _("Title"),
            _("Status"),
            _("Project"),
            _("Task"),
            _("Hours"),
            _("Notes"),
            _("Billable"),
        ]
    )
    for log in logs:
        ts = sheets[log.parent]
        cells = [
            frappe.utils.getdate(log.from_time) if log.from_time else "",
            _full_name(ts.owner),
            ts.name,
            ts.title,
            _(ts.status),
            projects.get(log.project, log.project or ""),
            tasks.get(log.task, log.task or ""),
            log.hours,
            frappe.utils.strip_html(log.description or ""),
            _("Yes") if log.custom_billable else _("No"),
        ]
        writer.writerow([csv_safe(cell) for cell in cells])
    period = "-".join(d for d in (from_date, to_date) if d) or "all"
    frappe.response.filename = f"timesheets-{period}.csv"
    frappe.response.filecontent = out.getvalue()
    frappe.response.type = "download"


@frappe.whitelist()
def get_timesheet_summary(
    team: bool = False,
    agent: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Hours in the time logs on screen: in total, by person and by project.

    Counts each time log in the chosen dates, not each timesheet's total, so a
    timesheet spanning several projects or days splits correctly.
    """
    sheets = _visible_timesheets(team, agent, from_date, to_date, ["name", "owner"])
    rows = (
        frappe.get_all(
            "Timesheet Detail",
            filters=_time_log_filters(sheets, from_date, to_date),
            fields=["parent", "project", "sum(hours) as hours"],
            group_by="parent, project",
        )
        if sheets
        else []
    )
    by_person, by_project = {}, {}
    for row in rows:
        hours = frappe.utils.flt(row.hours)
        owner = sheets[row.parent].owner
        by_person[owner] = by_person.get(owner, 0) + hours
        by_project[row.project or ""] = by_project.get(row.project or "", 0) + hours
    project_names = _names_of("Project", "project_name", set(by_project))
    people = [
        {"user": user, "full_name": _full_name(user), "hours": round(hours, 2)}
        for user, hours in by_person.items()
    ]
    projects = [
        {
            "project": project or None,
            "project_name": project_names.get(project) if project else None,
            "hours": round(hours, 2),
        }
        for project, hours in by_project.items()
    ]
    return {
        "hours": round(sum(by_person.values()), 2),
        "people": sorted(people, key=lambda p: (-p["hours"], p["full_name"].lower())),
        "projects": sorted(projects, key=lambda p: (-p["hours"], p["project"] or "")),
    }


def _visible_timesheets(team, agent, from_date, to_date, fields: list) -> dict:
    """Every timesheet the viewer may see under the filters, by name."""
    return {
        ts.name: ts
        for ts in frappe.get_list(
            "Timesheet",
            filters=_timesheet_filters(team, agent, from_date, to_date),
            fields=fields,
            limit_page_length=0,
            distinct=True,
        )
    }


def _time_log_filters(sheets: dict, from_date=None, to_date=None) -> dict:
    """Only the time logs in the chosen dates, from timesheets the viewer may see."""
    filters = {"parent": ["in", list(sheets)], "parenttype": "Timesheet"}
    log_range = _log_date_range(from_date, to_date)
    if log_range:
        filters["from_time"] = log_range
    return filters


def _timesheet_filters(team=False, agent=None, from_date=None, to_date=None) -> list:
    """Filters for the timesheets list; only leads and managers see the team's."""
    from helpdesk.api.work import can_see_overview

    team = frappe.utils.cint(team)
    if team and not can_see_overview():
        frappe.throw(
            _("Only project leads and managers can see the team's timesheets."),
            frappe.PermissionError,
        )
    filters = []
    if not team:
        filters.append(["Timesheet", "owner", "=", frappe.session.user])
    elif agent:
        filters.append(["Timesheet", "owner", "=", agent])
    log_range = _log_date_range(from_date, to_date)
    if log_range:
        # the day the work was done, not when the timesheet was saved
        filters.append(["Timesheet Detail", "from_time", *log_range])
    return filters


def _log_date_range(from_date=None, to_date=None) -> list | None:
    """A [operator, value] filter on a time log's start for the chosen dates."""
    start = f"{frappe.utils.getdate(from_date)} 00:00:00" if from_date else None
    end = f"{frappe.utils.getdate(to_date)} 23:59:59" if to_date else None
    if start and end:
        return ["between", [start, end]]
    if start:
        return [">=", start]
    if end:
        return ["<=", end]
    return None


def _names_of(doctype: str, field: str, names: set) -> dict:
    names = [n for n in names if n]
    if not names:
        return {}
    return dict(
        frappe.get_all(
            doctype,
            filters={"name": ["in", names]},
            fields=["name", field],
            as_list=True,
        )
    )


@frappe.whitelist()
def get_project_tasks(project: str):
    """Get all active tasks in a project for dropdown."""
    project = _resolve_project(str(project))
    return frappe.get_list(
        "Task",
        filters={"project": project, "status": ("not in", ["Completed", "Cancelled"])},
        fields=["name", "subject"],
        order_by="subject asc",
    )


@frappe.whitelist()
def create_timesheet(
    title: str,
    project: str | None = None,
    task: str | None = None,
    hours: float | str = 0,
    notes: str = "",
    billable: bool | int | str = True,
):
    """Manually create a timesheet. Non-billable time doesn't use up a customer's support hours."""
    if task:
        frappe.has_permission("Task", "read", task, throw=True)
    if project:
        _resolve_project(str(project))
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    from_time = frappe.utils.now()
    ts = frappe.get_doc(
        {
            "doctype": "Timesheet",
            "title": title,
            "employee": employee,
            "time_logs": [
                {
                    "task": task,
                    "project": project,
                    "from_time": from_time,
                    "hours": float(hours) or 0,
                    "description": notes,
                    "custom_billable": int(frappe.utils.sbool(billable)),
                }
            ],
        }
    )
    ts.flags.ignore_mandatory = True
    ts.insert()
    try:
        ts.submit()
    except (
        Exception
    ):  # noqa: BLE001 - keep the draft timesheet, but say why it wasn't submitted
        frappe.log_error(
            title=f"Timesheet submit failed for {ts.name}",
            message=frappe.get_traceback(),
        )
    return {
        "name": ts.name,
        "title": title,
        "total_hours": float(hours),
        "status": ts.status,
    }
