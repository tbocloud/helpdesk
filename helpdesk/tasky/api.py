"""Tasky API endpoints — checklist-driven project management."""

import frappe
from frappe import _

CATEGORY_TO_ROLE = {
	"Functional": "Functional Consultant",
	"Development": "Developer",
	"Support": "Support Engineer",
	"Common": None,
}


@frappe.whitelist()
def generate_checklist(project, template):
	"""Clone phases and tasks from template into project with auto-assignment."""
	project = str(project)
	template = str(template)

	if not frappe.db.exists("Tasky Project", project):
		frappe.throw(_("Project not found"))

	if not frappe.db.exists("Tasky Template", template):
		frappe.throw(_("Template not found"))

	template_doc = frappe.get_doc("Tasky Template", template)
	project_doc = frappe.get_doc("Tasky Project", project)

	team = {m.role_in_project: m.user for m in project_doc.team}

	created_count = 0
	for tphase in template_doc.phases:
		phase = frappe.get_doc({
			"doctype": "Tasky Phase",
			"project": project,
			"phase_name": tphase.phase_name,
			"sort_order": tphase.sort_order,
			"status": "Not Started",
		})
		phase.insert()

		for ttask in tphase.tasks:
			role = CATEGORY_TO_ROLE.get(ttask.category)
			assigned_to = team.get(role) if role else None

			task = frappe.get_doc({
				"doctype": "Tasky Task",
				"project": project,
				"phase": phase.name,
				"task_name": ttask.task_name,
				"description": ttask.description or "",
				"module_name": ttask.module_name or "",
				"category": ttask.category,
				"assigned_to": assigned_to,
				"priority": ttask.default_priority,
				"estimated_hours": ttask.estimated_hours or 0,
				"sort_order": ttask.sort_order,
				"status": "Pending",
			})
			task.insert()
			created_count += 1

	frappe.db.commit()
	return {"tasks_created": created_count}


@frappe.whitelist()
def get_my_tasks(project=None, status=None, limit=50):
	"""Get tasks assigned to current user, optionally filtered."""
	user = frappe.session.user

	filters = {"assigned_to": user}
	if project:
		filters["project"] = str(project)
	if status:
		filters["status"] = str(status)

	tasks = frappe.get_all(
		"Tasky Task",
		filters=filters,
		fields=["name", "task_name", "project", "phase", "category", "status",
				"priority", "due_date", "estimated_hours", "actual_hours", "sort_order"],
		order_by="sort_order asc",
		limit=limit,
	)
	return tasks


@frappe.whitelist()
def update_task_status(task, status):
	"""Update a task's status."""
	doc = frappe.get_doc("Tasky Task", str(task))
	doc.status = status
	doc.save()
	return {"status": doc.status}


@frappe.whitelist()
def get_project_dashboard(project):
	"""Get aggregate stats for the PM dashboard."""
	project = str(project)

	phases = frappe.get_all("Tasky Phase", filters={"project": project},
		fields=["name", "phase_name", "status", "sort_order"],
		order_by="sort_order asc")

	total_tasks = frappe.db.count("Tasky Task", {"project": project})
	completed = frappe.db.count("Tasky Task", {"project": project, "status": "Completed"})
	pending = frappe.db.count("Tasky Task", {"project": project, "status": "Pending"})
	in_progress = frappe.db.count("Tasky Task", {"project": project, "status": "In Progress"})
	blocked = frappe.db.count("Tasky Task", {"project": project, "status": "Blocked"})

	overdue = frappe.db.count("Tasky Task", {
		"project": project,
		"due_date": ("<", frappe.utils.today()),
		"status": ("not in", ["Completed", "Cancelled"]),
	})

	progress_pct = round((completed / total_tasks * 100), 1) if total_tasks > 0 else 0

	return {
		"phases": phases,
		"total_tasks": total_tasks,
		"completed": completed,
		"pending": pending,
		"in_progress": in_progress,
		"blocked": blocked,
		"overdue": overdue,
		"progress_pct": progress_pct,
	}


@frappe.whitelist()
def get_phase_progress(project, phase):
	"""Get task counts for a specific phase."""
	phase = str(phase)

	total = frappe.db.count("Tasky Task", {"phase": phase})
	completed = frappe.db.count("Tasky Task", {"phase": phase, "status": "Completed"})
	blocked = frappe.db.count("Tasky Task", {"phase": phase, "status": "Blocked"})

	return {
		"total": total,
		"completed": completed,
		"blocked": blocked,
		"progress_pct": round((completed / total * 100), 1) if total > 0 else 0,
	}


@frappe.whitelist()
def get_phase_tasks(phase):
	"""Get all tasks in a phase."""
	phase = str(phase)
	tasks = frappe.get_all("Tasky Task",
		filters={"phase": phase},
		fields=["name", "task_name", "category", "assigned_to", "status",
				"priority", "due_date", "estimated_hours", "sort_order"],
		order_by="sort_order asc")
	return tasks


@frappe.whitelist()
def get_templates():
	"""List all available implementation templates."""
	return frappe.get_all("Tasky Template",
		fields=["name", "template_name", "industry", "description"])


@frappe.whitelist()
def get_project_detail(project):
	"""Get full project with team and phases."""
	project = str(project)
	doc = frappe.get_doc("Tasky Project", project)
	return {
		"name": doc.name,
		"project_name": doc.project_name,
		"client_name": doc.client_name,
		"status": doc.status,
		"start_date": str(doc.start_date) if doc.start_date else None,
		"go_live_date": str(doc.go_live_date) if doc.go_live_date else None,
		"description": doc.description,
		"team": [{"user": m.user, "role": m.role_in_project} for m in doc.team],
	}


@frappe.whitelist()
def get_projects():
	"""List all projects."""
	return frappe.get_all("Tasky Project",
		fields=["name", "project_name", "client_name", "status", "start_date", "go_live_date"])
