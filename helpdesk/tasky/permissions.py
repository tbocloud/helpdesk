"""Tasky permission rules — non-PM roles see only assigned tasks."""

import frappe


def task_permission_query(user=None):
	"""Filter Tasky Task list to only show tasks assigned to the user,
	unless they are a Project Manager on any active project."""
	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None

	is_pm = frappe.db.exists(
		"Tasky Project Member",
		{"user": user, "role_in_project": "Project Manager"},
	)
	if is_pm:
		return None

	return f'`tabTasky Task`.`assigned_to` = "{user}"'


def has_task_permission(doc, ptype=None, user=None):
	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return True

	is_pm = frappe.db.exists(
		"Tasky Project Member",
		{"user": user, "role_in_project": "Project Manager"},
	)
	if is_pm:
		return True

	if doc.assigned_to == user:
		return True

	return False
