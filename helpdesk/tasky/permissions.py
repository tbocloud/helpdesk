"""Tasky permission rules.

Hierarchy:
- Admins (System Manager, Agent Manager) see and manage everything.
- Project Managers create projects and manage the ones they created or are
  listed on with the "Project Manager" project role.
- The Project Lead (one developer per project, rotated by the PM) sees every
  task in that project and can create and assign tasks there, but cannot create
  projects, edit the project, or change its lead.
- Holders of the Project Manager role see every task of the projects they are on,
  and the Digital Marketing Head and DM Coordinators every task of the content
  calendar and Digital projects; seeing them gives no extra powers.
- Other members (developers, consultants, support engineers, content people) see
  the projects they are listed on, and only their own tasks there: assigned to
  them, given out by them, or created by them (see docs/workspace-pages.md).

Role permissions on the doctypes decide *what* a role may do; these hooks only
narrow *which* records. Frappe hooks can deny but never grant, so every hook
returns False to deny or None to defer to role permissions.
"""

import json

import frappe
from frappe import _

from helpdesk.content_team import DM_COORDINATOR_ROLE, DM_HEAD_ROLE, is_erp_only

ADMIN_ROLES = ("System Manager", "Agent Manager")
# the digital marketing team's department (by name, see departments.md)
CONTENT_DEPARTMENT = "Digital"
# each team keeps out of the other's department (by department name, see departments.md)
HIDDEN_DEPARTMENTS = {"DM Employee": "ERP", "ERP Employee": CONTENT_DEPARTMENT}
PROJECT_MANAGER_ROLE = "Project Manager"
# Value of Project User.custom_role that makes a member a manager of that project
MANAGER_PROJECT_ROLE = "Project Manager"
# see every task of the content calendar projects and of CONTENT_DEPARTMENT's projects
CONTENT_LEAD_ROLES = (DM_HEAD_ROLE, DM_COORDINATOR_ROLE)


def is_tasky_admin(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return user == "Administrator" or bool(
        set(ADMIN_ROLES) & set(frappe.get_roles(user))
    )


def is_project_manager(user: str | None = None) -> bool:
    """Whether the user may create projects and templates."""
    user = user or frappe.session.user
    return is_tasky_admin(user) or PROJECT_MANAGER_ROLE in frappe.get_roles(user)


def hidden_departments(user: str | None = None) -> list[str]:
    """Departments whose projects and tasks this user never sees: ERP for DM Employees,
    Digital for ERP Employees. System Managers and Agent Managers see every department."""
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return []
    roles = set(frappe.get_roles(user))
    return sorted({dept for role, dept in HIDDEN_DEPARTMENTS.items() if role in roles})


def _departments_sql(departments: list[str]) -> str:
    return ", ".join(frappe.db.escape(d) for d in departments)


def is_hidden_project(project: str | None, user: str | None = None) -> bool:
    hidden = hidden_departments(user)
    if not hidden or not project:
        return False
    return frappe.db.get_value("Project", project, "custom_department") in hidden


def check_can_take_content_task(user: str):
    """ERP Employees never see the content calendar, so they can't be given its tasks,
    whatever the department of the post's project."""
    if is_erp_only(user):
        frappe.throw(
            _("{0} can't be given content calendar tasks.").format(
                frappe.utils.get_fullname(user)
            )
        )


def check_assignment_department(todo, method=None):
    """Refuse giving a task to someone whose team keeps out of its project's department.

    Assigning shares the task with them, which would let them open it even though it's
    hidden from all their lists; so the assignment itself is refused.
    """
    if (
        todo.reference_type != "Task"
        or not todo.allocated_to
        or todo.status == "Cancelled"
    ):
        return
    project, content_post = frappe.db.get_value(
        "Task", todo.reference_name, ["project", "content_post"]
    ) or (None, None)
    if content_post:
        check_can_take_content_task(todo.allocated_to)
    if is_hidden_project(project, todo.allocated_to):
        frappe.throw(
            _("{0} can't be given tasks in the {1} department.").format(
                frappe.utils.get_fullname(todo.allocated_to),
                frappe.db.get_value("Project", project, "custom_department"),
            )
        )


def get_managed_projects(user: str) -> list[str]:
    """Projects the user created or is listed on as the project's manager."""
    owned = frappe.get_all("Project", filters={"owner": user}, pluck="name")
    listed = frappe.get_all(
        "Project User",
        filters={
            "parenttype": "Project",
            "user": user,
            "custom_role": MANAGER_PROJECT_ROLE,
        },
        pluck="parent",
    )
    return list(set(owned) | set(listed))


def get_led_projects(user: str) -> list[str]:
    return frappe.get_all("Project", filters={"project_lead": user}, pluck="name")


def is_project_owner(project: str | None, user: str | None = None) -> bool:
    """Admins and the project's managers: may edit the project and change its lead."""
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return True
    return bool(project) and project in get_managed_projects(user)


def can_manage_project(project: str | None, user: str | None = None) -> bool:
    """Owners plus the project lead: may see all tasks and create/assign them."""
    user = user or frappe.session.user
    if is_project_owner(project, user):
        return True
    return (
        bool(project)
        and frappe.db.get_value("Project", project, "project_lead") == user
    )


def sees_all_tasks(project: str | None, user: str | None = None) -> bool:
    """Sees every task of the project, not only their own: its managers and lead, a
    Project Manager on its team, and for content calendar and Digital projects the
    Digital Marketing Head and DM Coordinators. Agrees with `task_query`."""
    user = user or frappe.session.user
    if not project:
        return False
    if can_manage_project(project, user):
        return True
    roles = set(frappe.get_roles(user))
    if PROJECT_MANAGER_ROLE in roles and is_project_member(project, user):
        return True
    if not roles & set(CONTENT_LEAD_ROLES):
        return False
    from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
        CONTENT_PROJECT_TYPE,
    )

    department, project_type = frappe.db.get_value(
        "Project", project, ["custom_department", "project_type"]
    ) or (None, None)
    return department == CONTENT_DEPARTMENT or project_type == CONTENT_PROJECT_TYPE


def is_own_task(doc, user: str) -> bool:
    """Assigned to the user, given out by them, or created by them: the tasks a member
    sees in a project they don't run. Agrees with `_own_tasks_subquery`."""
    if doc.get("owner") == user:
        return True
    todo = frappe.qb.DocType("ToDo")
    return bool(
        frappe.qb.from_(todo)
        .select(todo.name)
        .where(
            (todo.reference_type == "Task")
            & (todo.reference_name == doc.name)
            & (todo.status != "Cancelled")
            & ((todo.allocated_to == user) | (todo.assigned_by == user))
        )
        .limit(1)
        .run()
    )


def can_add_tasks(project: str | None, user: str | None = None) -> bool:
    """Anyone on the project (owner, lead, member, or with a task in it) may add
    tasks; approving, editing others' tasks and deleting stay with managers."""
    user = user or frappe.session.user
    if not project:
        return False
    return (
        is_tasky_admin(user)
        or can_manage_project(project, user)
        or is_project_member(project, user)
        or has_assigned_task(project, user)
    )


def is_project_member(project: str, user: str) -> bool:
    return bool(
        frappe.db.exists(
            "Project User", {"parenttype": "Project", "parent": project, "user": user}
        )
    )


def get_project_team(project: str) -> list[str]:
    """The project's members plus its lead, in member order."""
    members = frappe.get_all(
        "Project User",
        filters={"parenttype": "Project", "parent": project},
        pluck="user",
        order_by="idx asc",
    )
    lead = frappe.db.get_value("Project", project, "project_lead")
    team = list(dict.fromkeys(members + ([lead] if lead else [])))
    return [u for u in team if u not in ("Administrator", "Guest")]


def has_assigned_task(project: str, user: str) -> bool:
    """A developer given a task in a project sees that project, member or not."""
    return bool(
        frappe.db.exists(
            "Task", {"project": project, "_assign": ("like", f'%"{user}"%')}
        )
    )


def is_assigned(doc, user: str) -> bool:
    try:
        return user in json.loads(doc.get("_assign") or "[]")
    except (json.JSONDecodeError, TypeError):
        return False


def get_assigners(assignees: dict[str, str]) -> dict[str, str]:
    """Who gave each task to its assignee: {task: assignee} in, {task: assigner} out.

    The assignee's latest ToDo that wasn't cancelled names who assigned it; when
    it doesn't (an assignment made outside assign_to), whoever created the task
    did. Two queries for any number of tasks.
    """
    if not assignees:
        return {}
    todo = frappe.qb.DocType("ToDo")
    rows = (
        frappe.qb.from_(todo)
        .select(todo.reference_name, todo.allocated_to, todo.assigned_by)
        .where(
            (todo.reference_type == "Task")
            & todo.reference_name.isin(list(assignees))
            & (todo.status != "Cancelled")
        )
        .orderby(todo.creation)
        .run(as_dict=True)
    )
    found = {}
    for row in rows:
        # oldest first, so the latest assignment wins
        if row.assigned_by and row.allocated_to == assignees.get(row.reference_name):
            found[row.reference_name] = row.assigned_by
    missing = [name for name in assignees if name not in found]
    if missing:
        task = frappe.qb.DocType("Task")
        found.update(
            frappe.qb.from_(task)
            .select(task.name, task.owner)
            .where(task.name.isin(missing))
            .run()
        )
    return found


def is_assigner(assigner: str | None, assignees: list[str], user: str) -> bool:
    """`user` gave the task to someone else. Someone who took the task themselves
    is its assignee, not its assigner."""
    return bool(assigner) and assigner == user and user not in assignees


def can_move_task(
    project: str | None,
    assigner: str | None,
    assignees: list[str],
    user: str | None = None,
) -> bool:
    """Who may move a task to another project: admins, the project's managers and
    lead, and whoever assigned it. Never the assignee on their own say."""
    user = user or frappe.session.user
    return can_manage_project(project, user) or is_assigner(assigner, assignees, user)


def _managed_projects_subquery(user: str) -> str:
    u = frappe.db.escape(user)
    role = frappe.db.escape(MANAGER_PROJECT_ROLE)
    return (
        f"select `name` from `tabProject` where `owner` = {u} "
        f"union select `parent` from `tabProject User` "
        f"where `parenttype` = 'Project' and `user` = {u} and `custom_role` = {role}"
        f" union select `name` from `tabProject` where `project_lead` = {u}"
    )


def _all_tasks_projects_subquery(user: str) -> str:
    """Projects in which `user` sees every task (`sees_all_tasks`)."""
    query = _managed_projects_subquery(user)
    roles = set(frappe.get_roles(user))
    if PROJECT_MANAGER_ROLE in roles:
        query += (
            " union select `parent` from `tabProject User` "
            f"where `parenttype` = 'Project' and `user` = {frappe.db.escape(user)}"
        )
    if roles & set(CONTENT_LEAD_ROLES):
        from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
            CONTENT_PROJECT_TYPE,
        )

        query += (
            " union select `name` from `tabProject` where "
            f"`custom_department` = {frappe.db.escape(CONTENT_DEPARTMENT)} "
            f"or `project_type` = {frappe.db.escape(CONTENT_PROJECT_TYPE)}"
        )
    return query


def _own_tasks_subquery(user: str) -> str:
    """Tasks assigned to `user` or given out by them, from the ToDos. Matching the ToDo
    columns exactly, since a LIKE on `_assign` reads `_` in a user ID as a wildcard;
    a finished assignment (Closed) still counts, a withdrawn one (Cancelled) doesn't."""
    u = frappe.db.escape(user)
    return (
        "select `reference_name` from `tabToDo` where `reference_type` = 'Task' "
        f"and `status` != 'Cancelled' and (`allocated_to` = {u} or `assigned_by` = {u})"
    )


# --- permission_query_conditions ---


def project_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    u = frappe.db.escape(user)
    assigned = frappe.db.escape(f'%"{user}"%')
    condition = (
        f"(`tabProject`.`owner` = {u} or `tabProject`.`project_lead` = {u} or `tabProject`.`name` in "
        f"(select `parent` from `tabProject User` where `parenttype` = 'Project' and `user` = {u}) "
        f"or `tabProject`.`name` in (select `project` from `tabTask` where `_assign` like {assigned}))"
    )
    hidden = hidden_departments(user)
    if hidden:
        condition += f" and ifnull(`tabProject`.`custom_department`, '') not in ({_departments_sql(hidden)})"
    return condition


def task_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    # a task someone added for a teammate stays visible to them
    owner = frappe.db.escape(user)
    condition = (
        f"(`tabTask`.`project` in ({_all_tasks_projects_subquery(user)}) "
        f"or `tabTask`.`name` in ({_own_tasks_subquery(user)}) "
        f"or `tabTask`.`owner` = {owner})"
    )
    hidden = hidden_departments(user)
    if hidden:
        condition += (
            f" and ifnull(`tabTask`.`project`, '') not in (select `name` from `tabProject` "
            f"where `custom_department` in ({_departments_sql(hidden)}))"
        )
    if is_erp_only(user):
        # the content calendar is the Digital team's, whatever its project's department
        condition += " and ifnull(`tabTask`.`content_post`, '') = ''"
    return condition


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


def project_has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    user = user or frappe.session.user
    if ptype == "create" or is_tasky_admin(user):
        return None
    if doc.get("custom_department") in hidden_departments(user):
        return False
    if is_project_owner(doc.name, user):
        return None
    if ptype in ("read", "print", "email", "report") and (
        doc.get("project_lead") == user
        or is_project_member(doc.name, user)
        or has_assigned_task(doc.name, user)
    ):
        return None
    return False


def task_has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    if is_hidden_project(doc.project, user):
        return False
    if doc.get("content_post") and is_erp_only(user):
        return False
    if can_manage_project(doc.project, user):
        return None
    if ptype == "create":
        return None if can_add_tasks(doc.project, user) else False
    if ptype == "delete":
        return False
    if ptype in ("read", "print", "email", "report") and (
        sees_all_tasks(doc.project, user) or is_own_task(doc, user)
    ):
        return None
    return None if is_assigned(doc, user) else False


def timesheet_has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    user = user or frappe.session.user
    if ptype == "create" or is_tasky_admin(user) or doc.owner == user:
        return None
    managed = set(get_managed_projects(user))
    if ptype == "read" and any(
        log.project in managed for log in doc.get("time_logs", [])
    ):
        return None
    return False


# --- HD Pull Request: visible to whoever can read the task it's linked to ---


def pull_request_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    condition = task_query(user)
    if condition is None:
        return None
    return f"`tabHD Pull Request`.`task` in (select `name` from `tabTask` where {condition})"


def pull_request_has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    user = user or frappe.session.user
    if is_tasky_admin(user):
        return None
    if ptype not in ("read", "print", "report", "export"):
        return False
    if not doc.task:
        return False
    return (
        None
        if frappe.has_permission("Task", "read", doc=doc.task, user=user)
        else False
    )
