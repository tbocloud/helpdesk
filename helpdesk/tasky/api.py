"""Tasky API — checklist-driven project management on ERPNext Project/Task."""

import json

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.query_builder.functions import Count

from helpdesk.tasky.permissions import (
    MANAGER_PROJECT_ROLE,
    can_manage_project,
    is_project_owner,
    is_tasky_admin,
)
from helpdesk.tasky.setup import erpnext_customer_for
from helpdesk.tasky.task_events import notify_ticket_task_completed

# member roles a project lead is rotated among
LEAD_ROTATION_ROLES = ("Developer",)


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


def _format_task(task):
    """Normalize a Task dict for frontend consumption."""
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
        "assignees": assigned,
        "custom_timer_start": task.get("custom_timer_start"),
        "custom_timer_elapsed": task.get("custom_timer_elapsed") or 0,
        "is_key": bool(task.get("is_key")),
        "hd_ticket": task.get("hd_ticket"),
    }


def _default_activity_type() -> str | None:
    """The activity the user logged last, else the site's most used one (some sites require it)."""
    Detail = frappe.qb.DocType("Timesheet Detail")
    Sheet = frappe.qb.DocType("Timesheet")
    last = (
        frappe.qb.from_(Detail)
        .join(Sheet)
        .on(Sheet.name == Detail.parent)
        .select(Detail.activity_type)
        .where(Sheet.owner == frappe.session.user)
        .where(Detail.activity_type.isnotnull())
        .orderby(Detail.creation, order=frappe.qb.desc)
        .limit(1)
        .run(pluck=True)
    )
    if last:
        return last[0]
    top = (
        frappe.qb.from_(Detail)
        .select(Detail.activity_type)
        .where(Detail.activity_type.isnotnull())
        .groupby(Detail.activity_type)
        .orderby(Count("*"), order=frappe.qb.desc)
        .limit(1)
        .run(pluck=True)
    )
    return (
        top[0] if top else frappe.db.get_value("Activity Type", {"disabled": 0}, "name")
    )


@frappe.whitelist()
def complete_task(task: str, hours_worked: float | str = 0, notes: str = ""):
    """Complete a task with optional timesheet entry."""
    doc = frappe.get_doc("Task", str(task))
    doc.status = "Completed"
    doc.custom_actual_hours = (doc.custom_actual_hours or 0) + (
        float(hours_worked) or 0
    )
    doc.custom_timer_start = None
    doc.custom_timer_elapsed = 0
    doc.save()

    if float(hours_worked) > 0:
        try:
            employee = frappe.db.get_value(
                "Employee", {"user_id": frappe.session.user}, "name"
            )
            ts = frappe.get_doc(
                {
                    "doctype": "Timesheet",
                    "title": f"Task: {doc.subject}",
                    "employee": employee,
                    "time_logs": [
                        {
                            "task": doc.name,
                            "activity_type": _default_activity_type(),
                            "from_time": frappe.utils.now(),
                            "hours": float(hours_worked),
                            "description": notes or f"Completed task: {doc.subject}",
                            "project": doc.project,
                            "completed": 1,
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
        except Exception:
            frappe.log_error(title="complete_task Timesheet Error")

    return _format_task(_task_dict(doc))


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
            "hd_customer": customer or None,
            "customer": erpnext_customer_for(customer),
            "expected_start_date": expected_start_date or None,
            "expected_end_date": expected_end_date or None,
            "status": "Open",
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
        "customer": doc.hd_customer,
        "status": doc.status,
    }


@frappe.whitelist()
def generate_checklist(project: str, template: str):
    """Clone template tasks into ERPNext Project + Tasks."""
    project = _resolve_project(str(project), "write")
    template_name = str(template)

    if not frappe.db.exists("HD Task Template", template_name):
        frappe.throw(_("Template not found"))

    CATEGORY_TO_ROLE = {
        "Functional": "Functional Consultant",
        "Development": "Developer",
        "Support": "Support Engineer",
    }

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


def _assign_user(task_doc, user, ignore_permissions=False):
    """Assign an inserted Task to a user.

    Goes through a ToDo, which is what sets `_assign`; Frappe drops `_assign`
    when it is set on a document before insert. `ignore_permissions` is for
    callers that already checked the user may raise this task (ticket -> task).
    """
    if not user:
        return
    user = str(user).strip()
    if frappe.db.exists("User", user):
        assign_to.add(
            {"doctype": "Task", "name": task_doc.name, "assign_to": [user]},
            ignore_permissions=ignore_permissions,
        )


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
):
    """Add a single task to a project, optionally assigned to one of its members."""
    project = _resolve_project(str(project))
    if not can_manage_project(project):
        frappe.throw(
            _("Only the project's manager or lead can add tasks."),
            frappe.PermissionError,
        )
    if not str(task_name or "").strip():
        frappe.throw(_("Task name is required"))
    assigned_to = str(assigned_to or "").strip()
    if assigned_to and not _is_project_member(project, assigned_to):
        frappe.throw(
            _(
                "{0} is not a member of this project. Add them to the project first."
            ).format(assigned_to)
        )
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
        }
    )
    doc.insert()
    _assign_user(doc, assigned_to)
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
            "is_key",
            "hd_ticket",
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
    return [
        {**_format_task(t), "project_name": project_names.get(t.project)} for t in tasks
    ]


@frappe.whitelist()
def get_task_detail(task: str):
    """Get a single task with all fields."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    return _format_task(_task_dict(doc))


@frappe.whitelist()
def update_task_status(task: str, status: str):
    """Update a task's status."""
    frappe.has_permission("Task", "write", str(task), throw=True)
    frappe.db.set_value("Task", str(task), "status", str(status))
    if str(status) == "Completed":
        # set_value skips the controller, so hand the linked ticket back here
        notify_ticket_task_completed(frappe.get_doc("Task", str(task)))
    return {"status": str(status)}


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
            "is_key",
            "hd_ticket",
            "_assign",
            "creation",
        ],
        order_by="custom_phase asc, subject asc",
    )

    today = frappe.utils.getdate(frappe.utils.today())

    def count(status):
        return sum(1 for t in tasks if t.status == status)

    total_tasks = len(tasks)
    completed = count("Completed")
    cancelled = count("Cancelled")
    overdue = sum(
        1
        for t in tasks
        if t.exp_end_date
        and frappe.utils.getdate(t.exp_end_date) < today
        and t.status not in ("Completed", "Cancelled")
    )
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

    return {
        "phases": phases,
        "tasks": [_format_task(t) for t in tasks],
        "stats": {
            "total": total_tasks,
            "completed": completed,
            "in_progress": count("Working"),
            "pending": count("Open"),
            "reviewing": count("Pending Review"),
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
            "is_key",
            "hd_ticket",
            "_assign",
        ],
        order_by="subject asc",
    )
    return [_format_task(t) for t in tasks]


@frappe.whitelist()
def get_kanban_tasks(project: str):
    """Get tasks grouped by status for kanban board."""
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
            "is_key",
            "hd_ticket",
            "_assign",
            "custom_timer_start",
            "custom_timer_elapsed",
        ],
        order_by="custom_phase asc, subject asc",
    )

    columns = {
        "Open": [],
        "Working": [],
        "Pending Review": [],
        "Completed": [],
        "Cancelled": [],
    }
    for t in tasks:
        status = t.get("status") or "Open"
        if status not in columns:
            status = "Open"
        columns[status].append(_format_task(t))

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
        "customer": doc.hd_customer,
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
        "can_change_lead": is_project_owner(doc.name),
        "project_lead": doc.project_lead,
        "project_lead_name": (
            frappe.db.get_value("User", doc.project_lead, "full_name")
            if doc.project_lead
            else None
        ),
    }


@frappe.whitelist()
def get_users():
    """List enabled users for assignment dropdowns."""
    return frappe.get_all(
        "User",
        {"enabled": 1},
        ["name", "full_name", "email", "user_image"],
        order_by="full_name asc",
    )


@frappe.whitelist()
def get_projects():
    """List projects visible to the current user."""
    projects = frappe.get_list(
        "Project",
        fields=[
            "name",
            "project_name",
            "hd_customer as customer",
            "status",
            "expected_start_date",
            "expected_end_date",
            "priority",
            "project_lead",
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
    for p in projects:
        p["can_manage"] = can_manage_project(p["name"])
        p["can_edit"] = is_project_owner(p["name"])
        p["project_lead_name"] = lead_names.get(p.project_lead)
    return projects


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
):
    """Edit a project's details, members and lead. Project owners only."""
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
    doc.hd_customer = customer or None
    doc.customer = erpnext_customer_for(customer) or doc.customer
    doc.expected_start_date = expected_start_date or None
    doc.expected_end_date = expected_end_date or None
    if status:
        doc.status = status
    if priority:
        doc.priority = priority

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


@frappe.whitelist()
def start_timer(task: str):
    """Start the timer on a task."""
    frappe.has_permission("Task", "write", str(task), throw=True)
    frappe.db.set_value("Task", str(task), "custom_timer_start", frappe.utils.now())
    return {"ok": 1}


@frappe.whitelist()
def stop_timer(task: str):
    """Stop the timer and persist elapsed."""
    task_id = str(task)
    frappe.has_permission("Task", "write", task_id, throw=True)
    timer_start = frappe.db.get_value("Task", task_id, "custom_timer_start")
    if not timer_start:
        return {"elapsed": 0}
    from datetime import datetime

    start = timer_start
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    elapsed = (datetime.now() - start).total_seconds() / 3600.0
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

    # Leaving Working: accumulate elapsed from running timer
    if old_status == "Working" and timer_start:
        from datetime import datetime

        start = timer_start
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        elapsed_this_move = (datetime.now() - start).total_seconds() / 3600.0
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

    frappe.db.set_value("Task", task_id, "status", new_status)
    if new_status == "Completed":
        # set_value skips the controller, so hand the linked ticket back here
        notify_ticket_task_completed(frappe.get_doc("Task", task_id))
    return {"status": new_status, "elapsed": round(elapsed_this_move, 2)}


@frappe.whitelist()
def get_timer(task: str):
    """Get current timer state for a task."""
    doc = frappe.get_doc("Task", str(task))
    doc.check_permission("read")
    if not doc.custom_timer_start:
        return {"running": False, "elapsed": 0, "timer_start": None}
    from datetime import datetime

    start = doc.custom_timer_start
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    elapsed = (datetime.now() - start).total_seconds() / 3600.0
    return {"running": True, "elapsed": round(elapsed, 2), "timer_start": str(start)}


@frappe.whitelist()
def get_my_timesheets(limit: int = 20):
    """List my timesheets with project info."""
    timesheets = frappe.get_all(
        "Timesheet",
        filters={"owner": frappe.session.user},
        fields=["name", "title", "status", "total_hours", "creation", "modified"],
        order_by="modified desc",
        limit=limit,
    )
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
    return timesheets


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
):
    """Manually create a timesheet."""
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
