"""Who the Performance page shows, and to whom.

The team is the active helpdesk agents. Where the site keeps Employee records
with a department, designation or photo (an HR / ERPNext site), those are
added; the hub keeps only a slim Employee, so the page works without them.

Every report reads across doctypes the viewer may not have permission on, so
access is decided once, in `visible_employees`:

- System Managers, Agent Managers and HR see everyone
- Project Managers see the members of the projects they manage, and themselves
- everyone else sees only themselves
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate

from helpdesk.tasky.permissions import get_managed_projects, is_tasky_admin

TEAM_ROLES = ("System Manager", "Agent Manager", "HR Manager", "HR User")
MAX_RANGE_DAYS = 366
# Employee fields the page shows when the site has them
EMPLOYEE_EXTRAS = ("department", "designation", "image")


def sees_everyone(user: str) -> bool:
    return is_tasky_admin(user) or bool(set(TEAM_ROLES) & set(frappe.get_roles(user)))


def visible_employees(user: str | None = None) -> list[dict]:
    """The active agents this user may see, with their Employee details if any.

    `employee` identifies the person on the page: their Employee record when
    they have one, else their user.
    """
    user = user or frappe.session.user
    filters = {"is_active": 1}
    if not sees_everyone(user):
        filters["user"] = ("in", list(team_users(user)))
    agents = frappe.get_all(
        "HD Agent",
        filters=filters,
        fields=["user", "agent_name", "user_image"],
        order_by="agent_name asc",
    )
    employees = employee_details([a.user for a in agents])
    people = []
    for agent in agents:
        record = employees.get(agent.user, {})
        people.append(
            frappe._dict(
                employee=record.get("name") or agent.user,
                employee_name=agent.agent_name or agent.user,
                user_id=agent.user,
                department=record.get("department"),
                designation=record.get("designation"),
                image=record.get("image") or agent.user_image,
            )
        )
    return people


def team_users(user: str) -> set[str]:
    """The user and, for a project manager, the members of their projects."""
    users = {user}
    projects = get_managed_projects(user)
    if projects:
        users |= set(
            frappe.get_all(
                "Project User",
                filters={"parenttype": "Project", "parent": ("in", projects)},
                pluck="user",
            )
        )
    return users


def employee_details(users: list[str]) -> dict[str, dict]:
    """Each user's active Employee record, with whichever extras the site has."""
    if not users or not frappe.db.exists("DocType", "Employee"):
        return {}
    meta = frappe.get_meta("Employee")
    fields = ["name", "user_id"] + [f for f in EMPLOYEE_EXTRAS if meta.has_field(f)]
    rows = frappe.get_all(
        "Employee",
        filters={"user_id": ("in", users), "status": "Active"},
        fields=fields,
    )
    return {row.user_id: row for row in rows}


def resolve_scope(employee: str | None, department: str | None) -> list[dict]:
    people = visible_employees()
    if employee:
        people = [p for p in people if p.employee == employee]
        if not people:
            frappe.throw(
                _("You can't view this employee's performance."), frappe.PermissionError
            )
    elif department:
        people = [p for p in people if p.department == department]
    return people


def check_range(from_date: str, to_date: str):
    start, end = getdate(from_date), getdate(to_date)
    if end < start:
        frappe.throw(_("The end date is before the start date."))
    if date_diff(end, start) > MAX_RANGE_DAYS:
        frappe.throw(_("Pick a period of up to a year."))
    return start, end


@frappe.whitelist()
def get_scope() -> dict:
    """Who the viewer can see, for the page's pickers."""
    people = visible_employees()
    me = next((p.employee for p in people if p.user_id == frappe.session.user), None)
    return {
        "sees_team": len(people) > 1 or sees_everyone(frappe.session.user),
        "me": me,
        "employees": people,
        "departments": sorted({p.department for p in people if p.department}),
    }
