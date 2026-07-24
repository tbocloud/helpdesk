"""Tasky API — checklist-driven project management on ERPNext Project/Task."""

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


@frappe.whitelist()
def generate_checklist(project, template):
    """Clone template phases and tasks into ERPNext Project + Tasks."""
    project = _resolve_project(str(project))
    template_name = str(template)

    if not frappe.db.exists("Project", project):
        frappe.throw(_("Project not found"))

    if not frappe.db.exists("Tasky Template", template_name):
        frappe.throw(_("Template not found"))

    template_doc = frappe.get_doc("Tasky Template", template_name)

    created_count = 0
    for ttask in template_doc.tasks:
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
        task_doc.insert()
        created_count += 1

    frappe.db.commit()
    return {"tasks_created": created_count}


@frappe.whitelist()
def get_my_tasks(project=None, status=None, limit=50):
    """Get tasks assigned to current user."""
    user = frappe.session.user

    filters = {"_assign": ("like", f"%{user}%")}
    if project:
        filters["project"] = str(project)
    if status:
        filters["status"] = str(status)

    tasks = frappe.get_all(
        "Task",
        filters=filters,
        fields=["name", "subject", "project", "custom_category", "custom_phase",
                "status", "priority", "exp_end_date", "custom_estimated_hours"],
        order_by="custom_phase asc",
        limit=limit,
    )
    return tasks


@frappe.whitelist()
def update_task_status(task, status):
    """Update a task's status."""
    doc = frappe.get_doc("Task", str(task))
    doc.status = status
    doc.save()
    return {"status": doc.status}


@frappe.whitelist()
def get_project_dashboard(project):
    """Get aggregate stats for the PM dashboard from ERPNext Project."""
    project = _resolve_project(str(project))

    total_tasks = frappe.db.count("Task", {"project": project})
    completed = frappe.db.count("Task", {"project": project, "status": "Completed"})
    in_progress = frappe.db.count("Task", {"project": project, "status": "Working"})
    blocked = frappe.db.count("Task", {"project": project, "status": "Cancelled"})
    overdue = frappe.db.count("Task", {
        "project": project,
        "exp_end_date": ("<", frappe.utils.today()),
        "status": ("not in", ["Completed", "Cancelled"]),
    })

    progress_pct = round((completed / total_tasks * 100), 1) if total_tasks > 0 else 0

    phases = frappe.db.sql("""
        SELECT DISTINCT custom_phase, COUNT(*) as task_count
        FROM `tabTask`
        WHERE project = %s AND custom_phase IS NOT NULL
        GROUP BY custom_phase
        ORDER BY custom_phase
    """, project, as_dict=True)

    return {
        "phases": phases,
        "total_tasks": total_tasks,
        "completed": completed,
        "in_progress": in_progress,
        "blocked": blocked,
        "overdue": overdue,
        "progress_pct": progress_pct,
    }


@frappe.whitelist()
def get_phase_tasks(phase):
    """Get all tasks in a phase."""
    phase = str(phase)
    tasks = frappe.get_all("Task",
        filters={"custom_phase": phase},
        fields=["name", "subject", "custom_category", "status", "priority",
                "exp_end_date", "custom_estimated_hours", "_assign"],
        order_by="subject asc")
    return tasks


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
