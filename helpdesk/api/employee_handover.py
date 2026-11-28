"""Hand a leaving person's work over (docs/project-access.md): see their open projects,
tasks and the access entries they added, choose who takes each project, then complete
the handover. Admins, Project Managers and department heads only (`can_hand_over`)."""

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import cint, cstr, get_fullname

from helpdesk.helpdesk.doctype.hd_employee_handover.hd_employee_handover import (
    CLOSED_TASK_STATES,
    HDEmployeeHandover,
)
from helpdesk.tasky.permissions import MANAGER_PROJECT_ROLE, can_hand_over

HANDOVER = "HD Employee Handover"
CLOSED_PROJECT_STATES = ("Completed", "Cancelled")


def require_hand_over() -> None:
    if not can_hand_over():
        frappe.throw(
            _("Only managers and department heads can hand over someone's work."),
            frappe.PermissionError,
        )


def open_projects_of(user: str) -> list[dict]:
    """The open projects the person is on, or leads: name, title, their role, lead."""
    project = frappe.qb.DocType("Project")
    member = frappe.qb.DocType("Project User")
    on_team = (
        frappe.qb.from_(member)
        .select(member.parent)
        .where((member.parenttype == "Project") & (member.user == user))
    )
    rows = (
        frappe.qb.from_(project)
        .select(project.name, project.project_name, project.project_lead)
        .where(
            (project.name.isin(on_team) | (project.project_lead == user))
            & project.status.notin(CLOSED_PROJECT_STATES)
        )
        .orderby(project.project_name)
        .run(as_dict=True)
    )
    roles = dict(
        frappe.get_all(
            "Project User",
            filters={
                "parenttype": "Project",
                "user": user,
                "parent": ("in", [r.name for r in rows] or [""]),
            },
            fields=["parent", "custom_role"],
            as_list=True,
        )
    )
    for row in rows:
        row.role = roles.get(row.name) or (
            _("Project lead") if row.project_lead == user else None
        )
    return rows


def suggested_owner(project: str, lead: str | None, leaving: str) -> str | None:
    """The project's lead, else one of its managers, who isn't the person leaving."""
    if lead and lead != leaving:
        return lead
    managers = frappe.get_all(
        "Project User",
        filters={
            "parenttype": "Project",
            "parent": project,
            "custom_role": MANAGER_PROJECT_ROLE,
            "user": ("!=", leaving),
        },
        pluck="user",
        order_by="idx asc",
        limit=1,
    )
    return managers[0] if managers else None


def access_entries_by(user: str, projects: list[str]) -> dict[str, int]:
    """How many access entries the person added on each project."""
    if not projects:
        return {}
    # query builder, not a "count(name)" field string: newer Frappe refuses SQL in fields
    access = frappe.qb.DocType("HD Project Access")
    return dict(
        frappe.qb.from_(access)
        .select(access.project, Count(access.name))
        .where((access.added_by == user) & access.project.isin(projects))
        .groupby(access.project)
        .run()
    )


@frappe.whitelist()
def get_people() -> dict:
    """`people`: everyone who still holds work (an open project or an open task), enabled
    or already disabled, so a handover can be done after the account is closed.
    `takers`: the active agents who can take it over."""
    require_hand_over()
    return {
        "people": people_holding_work(),
        "takers": active_agents(),
    }


def active_agents() -> list[dict]:
    """The active agents, as {name, full_name}."""
    agent = frappe.qb.DocType("HD Agent")
    return (
        frappe.qb.from_(agent)
        .select(agent.user.as_("name"), agent.agent_name.as_("full_name"))
        .where(agent.is_active == 1)
        .orderby(agent.agent_name)
        .run(as_dict=True)
    )


def people_holding_work() -> list[dict]:
    member = frappe.qb.DocType("Project User")
    project = frappe.qb.DocType("Project")
    on_projects = (
        frappe.qb.from_(member)
        .join(project)
        .on(project.name == member.parent)
        .select(member.user)
        .where(
            (member.parenttype == "Project")
            & project.status.notin(CLOSED_PROJECT_STATES)
        )
        .distinct()
        .run(pluck=True)
    )
    todo = frappe.qb.DocType("ToDo")
    task = frappe.qb.DocType("Task")
    with_tasks = (
        frappe.qb.from_(todo)
        .join(task)
        .on(task.name == todo.reference_name)
        .select(todo.allocated_to)
        .where(
            (todo.reference_type == "Task")
            & (todo.status == "Open")
            & task.status.notin(CLOSED_TASK_STATES)
        )
        .distinct()
        .run(pluck=True)
    )
    users = {
        u for u in [*on_projects, *with_tasks] if u not in ("Administrator", "Guest")
    }
    if not users:
        return []
    return frappe.get_all(
        "User",
        filters={"name": ("in", list(users)), "user_type": "System User"},
        fields=["name", "full_name", "enabled"],
        order_by="full_name asc",
    )


@frappe.whitelist()
def get_handover_preview(employee: str) -> dict:
    """What the person holds: each open project with their role, open tasks and the
    access entries they added, a suggested new owner, and their tasks outside projects."""
    require_hand_over()
    if not frappe.db.exists("User", employee):
        frappe.throw(_("User not found: {0}").format(employee))
    projects = open_projects_of(employee)
    entries = access_entries_by(employee, [p.name for p in projects])
    return {
        "employee": employee,
        "full_name": get_fullname(employee),
        "enabled": cint(frappe.db.get_value("User", employee, "enabled")),
        "projects": [
            {
                "project": p.name,
                "project_name": p.project_name,
                "role": p.role,
                "is_lead": p.project_lead == employee,
                "open_tasks": len(HDEmployeeHandover.open_task_names(employee, p.name)),
                "access_entries": cint(entries.get(p.name)),
                "suggested_owner": suggested_owner(p.name, p.project_lead, employee),
            }
            for p in projects
        ],
        "other_tasks": len(HDEmployeeHandover.open_task_names(employee, None)),
        "history": frappe.get_all(
            HANDOVER,
            filters={"employee": employee},
            fields=["name", "status", "completed_on", "completed_by"],
            order_by="creation desc",
        ),
    }


@frappe.whitelist(methods=["POST"])
def complete_handover(
    employee: str,
    projects: list | str,
    default_owner: str | None = None,
    last_day: str | None = None,
    note: str | None = None,
) -> dict:
    """Record the handover and do it: each project's open tasks and place on the team go
    to its new owner, tasks outside projects to `default_owner`."""
    require_hand_over()
    projects = frappe.parse_json(projects) if isinstance(projects, str) else projects
    if not isinstance(projects, list):
        frappe.throw(_("Choose who takes over each project."))
    held = {p.name for p in open_projects_of(employee)}
    rows = []
    for row in projects:
        project, owner = cstr(row.get("project")), cstr(row.get("new_owner"))
        if project not in held:
            frappe.throw(_("{0} isn't one of their open projects.").format(project))
        if not owner:
            frappe.throw(_("Choose who takes over {0}.").format(project))
        rows.append(
            {
                "project": project,
                "new_owner": owner,
                "note": cstr(row.get("note")).strip(),
            }
        )
    if not rows and not default_owner:
        frappe.throw(_("There is nothing to hand over."))
    doc = frappe.get_doc(
        {
            "doctype": HANDOVER,
            "employee": employee,
            "last_day": last_day or None,
            "default_owner": default_owner or None,
            "note": cstr(note).strip() or None,
            "projects": rows,
        }
    )
    doc.insert(ignore_permissions=True)
    doc.complete()
    return {
        "name": doc.name,
        "projects": [
            {
                "project": r.project,
                "new_owner": r.new_owner,
                "tasks_moved": r.tasks_moved,
            }
            for r in doc.projects
        ],
        "other_tasks_moved": cint(doc.other_tasks_moved),
    }
