"""Tasky API — checklist-driven project management on ERPNext Project/Task."""

import json

import frappe
from frappe import _


def _resolve_project(project):
    """Find project by name or project_name."""
    if frappe.db.exists("Project", project):
        return project
    name = frappe.db.get_value("Project", {"project_name": project}, "name")
    if name:
        return name
    frappe.throw(_("Project not found: {0}").format(project))


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
        "due_date": task.get("exp_end_date"),
        "assigned_to": assigned[0] if assigned else None,
        "assignees": assigned,
    }


@frappe.whitelist()
def create_project(project_name, expected_start_date=None, expected_end_date=None):
    """Create a new ERPNext Project."""
    existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
    if existing:
        frappe.throw(_("Project with this name already exists: {0}").format(existing))

    doc = frappe.get_doc({
        "doctype": "Project",
        "project_name": project_name,
        "expected_start_date": expected_start_date or None,
        "expected_end_date": expected_end_date or None,
        "status": "Open",
    })
    doc.insert()
    frappe.db.commit()
    return {"name": doc.name, "project_name": doc.project_name, "status": doc.status}


@frappe.whitelist()
def generate_checklist(project, template):
    """Clone template tasks into ERPNext Project + Tasks."""
    project = _resolve_project(str(project))
    template_name = str(template)

    if not frappe.db.exists("Project", project):
        frappe.throw(_("Project not found"))
    if not frappe.db.exists("Tasky Template", template_name):
        frappe.throw(_("Template not found"))

    template_doc = frappe.get_doc("Tasky Template", template_name)

    project_users = frappe.get_all("Project User", {"parent": project}, ["user"], pluck="user")

    created_count = 0
    for i, ttask in enumerate(template_doc.tasks):
        task_doc = frappe.get_doc({
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
        })
        if project_users:
            _assign_user(task_doc, project_users[i % len(project_users)])
        task_doc.insert()
        created_count += 1

    frappe.db.commit()
    return {"tasks_created": created_count}


def _assign_user(task_doc, user):
    """Set _assign field on a Task document to assign it to a user."""
    if not user:
        return
    user = str(user).strip()
    if frappe.db.exists("User", user):
        import json
        task_doc._assign = json.dumps([user])


@frappe.whitelist()
def add_task(project, task_name, phase="", category="Functional", priority="Medium", estimated_hours=0, assigned_to=""):
    """Add a single task to a project's checklist."""
    project = _resolve_project(str(project))
    doc = frappe.get_doc({
        "doctype": "Task",
        "subject": str(task_name),
        "project": project,
        "custom_category": str(category),
        "custom_phase": str(phase) if phase else "",
        "custom_estimated_hours": float(estimated_hours) or 0,
        "priority": str(priority),
        "status": "Open",
    })
    _assign_user(doc, assigned_to)
    doc.insert()
    frappe.db.commit()
    return _format_task(doc.as_dict())


@frappe.whitelist()
@frappe.whitelist()
def get_my_tasks(project=None, status=None, limit=50):
    """Get tasks assigned to current user."""
    user = frappe.session.user

    filters = {"_assign": ("like", f"%{user}%")}
    if project:
        filters["project"] = _resolve_project(str(project)) if not frappe.db.exists("Project", project) else str(project)
    if status:
        filters["status"] = str(status)

    tasks = frappe.get_all(
        "Task",
        filters=filters,
        fields=["name", "subject", "project", "custom_category", "custom_phase",
                "status", "priority", "exp_end_date", "custom_estimated_hours", "_assign"],
        order_by="custom_phase asc",
        limit=limit,
    )
    return [_format_task(t) for t in tasks]


@frappe.whitelist()
def get_task_detail(task):
    """Get a single task with all fields."""
    task = str(task)
    doc = frappe.get_doc("Task", task)
    return _format_task(doc.as_dict())


@frappe.whitelist()
def update_task_status(task, status):
    """Update a task's status."""
    doc = frappe.get_doc("Task", str(task))
    doc.status = status
    doc.save()
    return {"status": doc.status}


@frappe.whitelist()
def get_project_dashboard(project):
    """Get aggregate stats and phase data for the PM dashboard."""
    project = _resolve_project(str(project))

    total_tasks = frappe.db.count("Task", {"project": project})
    completed = frappe.db.count("Task", {"project": project, "status": "Completed"})
    in_progress = frappe.db.count("Task", {"project": project, "status": "Working"})
    pending = frappe.db.count("Task", {"project": project, "status": "Open"})
    reviewing = frappe.db.count("Task", {"project": project, "status": "Pending Review"})
    cancelled = frappe.db.count("Task", {"project": project, "status": "Cancelled"})
    overdue = frappe.db.count("Task", {
        "project": project,
        "exp_end_date": ("<", frappe.utils.today()),
        "status": ("not in", ["Completed", "Cancelled"]),
    })
    progress_pct = round((completed / total_tasks * 100), 1) if total_tasks > 0 else 0

    phase_rows = frappe.db.sql("""
        SELECT custom_phase, COUNT(*) as total_count,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_count
        FROM `tabTask`
        WHERE project = %s AND custom_phase IS NOT NULL AND custom_phase != ''
        GROUP BY custom_phase
        ORDER BY MIN(creation) ASC
    """, project, as_dict=True)

    phases = []
    for row in phase_rows:
        pc = row["total_count"]
        cc = row["completed_count"] or 0
        phases.append({
            "name": row["custom_phase"],
            "phase_name": row["custom_phase"],
            "total_count": pc,
            "completed_count": cc,
            "progress_pct": round((cc / pc * 100), 1) if pc > 0 else 0,
        })

    tasks = frappe.get_all("Task",
        filters={"project": project},
        fields=["name", "subject", "custom_category", "custom_phase", "status",
                "priority", "exp_end_date", "custom_estimated_hours", "_assign"],
        order_by="custom_phase asc, subject asc")

    formatted_tasks = [_format_task(t) for t in tasks]

    return {
        "phases": phases,
        "tasks": formatted_tasks,
        "stats": {
            "total": total_tasks,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "reviewing": reviewing,
            "cancelled": cancelled,
            "blocked": cancelled,
            "overdue": overdue,
            "completion_pct": progress_pct,
        },
    }


@frappe.whitelist()
def get_phase_tasks(project, phase):
    """Get all tasks in a phase for the given project."""
    project = _resolve_project(str(project))
    phase = str(phase)
    tasks = frappe.get_all("Task",
        filters={"project": project, "custom_phase": phase},
        fields=["name", "subject", "custom_category", "custom_phase", "status",
                "priority", "exp_end_date", "custom_estimated_hours", "_assign"],
        order_by="subject asc")
    return [_format_task(t) for t in tasks]


@frappe.whitelist()
def get_kanban_tasks(project):
    """Get tasks grouped by status for kanban board."""
    project = _resolve_project(str(project))
    tasks = frappe.get_all("Task",
        filters={"project": project},
        fields=["name", "subject", "custom_category", "custom_phase", "status",
                "priority", "exp_end_date", "custom_estimated_hours", "_assign"],
        order_by="custom_phase asc, subject asc")

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
    return frappe.get_all("Tasky Template",
        fields=["name", "template_name", "industry", "description"])


@frappe.whitelist()
def get_project_detail(project):
    """Get ERPNext project details."""
    project = _resolve_project(str(project))
    doc = frappe.get_doc("Project", project)
    return {
        "name": doc.name,
        "project_name": doc.project_name,
        "status": doc.status,
        "expected_start_date": str(doc.expected_start_date) if doc.expected_start_date else None,
        "expected_end_date": str(doc.expected_end_date) if doc.expected_end_date else None,
        "users": [{"user": u.user, "full_name": u.full_name} for u in doc.users] if doc.users else [],
    }


@frappe.whitelist()
def get_projects():
    """List all ERPNext Projects."""
    return frappe.get_all("Project",
        fields=["name", "project_name", "status", "expected_start_date", "expected_end_date", "priority"])
