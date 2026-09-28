"""Tasky permission rules.

Hierarchy:
- Admins (System Manager, Agent Manager) see and manage everything.
- Project Managers create projects and manage the ones they created or are
  listed on with the "Project Manager" project role.
- Other members (developers, consultants, support engineers) see the projects
  they are listed on, and only the tasks assigned to them.

Role permissions on the doctypes decide *what* a role may do; these hooks only
narrow *which* records. Frappe hooks can deny but never grant, so every hook
returns False to deny or None to defer to role permissions.
"""

import json

import frappe

ADMIN_ROLES = ("System Manager", "Agent Manager")
PROJECT_MANAGER_ROLE = "Project Manager"
# Value of Project User.custom_role that makes a member a manager of that project
MANAGER_PROJECT_ROLE = "Project Manager"


def is_tasky_admin(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return user == "Administrator" or bool(set(ADMIN_ROLES) & set(frappe.get_roles(user)))


def is_project_manager(user: str | None = None) -> bool:
    """Whether the user may create projects and templates."""
    user = user or frappe.session.user
    return is_tasky_admin(user) or PROJECT_MANAGER_ROLE in frappe.get_roles(user)


def get_managed_projects(user: str) -> list[str]:
    """Projects the user created or is listed on as the project's manager."""
    owned = frappe.get_all("Project", filters={"owner": user}, pluck="name")
    listed = frappe.get_all(
        "Project User",
        filters={"parenttype": "Project", "user": user, "custom_role": MANAGER_PROJECT_ROLE},
        pluck="parent",
    )
    return list(set(owned) | set(listed))


def can_manage_project(project: str | None, user: str | None = None) -> bool:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return True
    return bool(project) and project in get_managed_projects(user)


def is_project_member(project: str, user: str) -> bool:
    return bool(
        frappe.db.exists("Project User", {"parenttype": "Project", "parent": project, "user": user})
    )


def is_assigned(doc, user: str) -> bool:
    try:
        return user in json.loads(doc.get("_assign") or "[]")
    except (json.JSONDecodeError, TypeError):
        return False


def _managed_projects_subquery(user: str) -> str:
    u = frappe.db.escape(user)
    role = frappe.db.escape(MANAGER_PROJECT_ROLE)
    return (
        f"select `name` from `tabProject` where `owner` = {u} "
        f"union select `parent` from `tabProject User` "
        f"where `parenttype` = 'Project' and `user` = {u} and `custom_role` = {role}"
    )


# --- permission_query_conditions ---


def project_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    u = frappe.db.escape(user)
    return (
        f"(`tabProject`.`owner` = {u} or `tabProject`.`name` in "
        f"(select `parent` from `tabProject User` where `parenttype` = 'Project' and `user` = {u}))"
    )


def task_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    # _assign stores a JSON list, so match the quoted email to avoid partial matches
    assigned = frappe.db.escape(f'%"{user}"%')
    return (
        f"(`tabTask`.`project` in ({_managed_projects_subquery(user)}) "
        f"or `tabTask`.`_assign` like {assigned})"
    )


def timesheet_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    u = frappe.db.escape(user)
    return (
        f"(`tabTimesheet`.`owner` = {u} or `tabTimesheet`.`name` in "
        f"(select `parent` from `tabTimesheet Detail` where `project` in ({_managed_projects_subquery(user)})))"
    )


# --- has_permission ---


def project_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool | None:
    user = user or frappe.session.user
    if ptype == "create" or is_tasky_admin(user):
        return None
    if can_manage_project(doc.name, user):
        return None
    if ptype in ("read", "print", "email", "report") and is_project_member(doc.name, user):
        return None
    return False


def task_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool | None:
    user = user or frappe.session.user
    if is_tasky_admin(user) or can_manage_project(doc.project, user):
        return None
    if ptype in ("create", "delete"):
        return False
    return None if is_assigned(doc, user) else False


def timesheet_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool | None:
    user = user or frappe.session.user
    if ptype == "create" or is_tasky_admin(user) or doc.owner == user:
        return None
    managed = set(get_managed_projects(user))
    if ptype == "read" and any(log.project in managed for log in doc.get("time_logs", [])):
        return None
    return False
