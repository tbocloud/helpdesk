"""The sales team a Sales Head manages (docs/sales-team.md).

The team is every enabled user with a sales team role: Sales User, Presales Executive or
Sales Employee. A Sales Head adds an agent to it, changes which of those roles they hold,
or removes them, which takes those roles away and leaves the account as it is.
"""

import frappe
from frappe import _

from helpdesk.api.departments import WALL_ROLES
from helpdesk.content_team import (
    FULL_ACCESS_ROLES,
    PRESALES_EXECUTIVE_ROLE,
    SALES_EMPLOYEE_ROLE,
    ensure_role,
)
from helpdesk.sales_targets import NOT_PEOPLE, SALES_USER_ROLE, can_assign_targets

# what a Sales Head gives and takes away, in the order the page shows them
TEAM_ROLES = (SALES_USER_ROLE, PRESALES_EXECUTIVE_ROLE, SALES_EMPLOYEE_ROLE)


class SalesTeamForbiddenError(frappe.PermissionError):
    pass


def require_sales_head():
    if not can_assign_targets():
        frappe.throw(
            _("Only a Sales Head can manage the sales team."), SalesTeamForbiddenError
        )


def team_members() -> list[dict]:
    """Enabled users with a team role, by name, each with the team roles they hold."""
    has_role = frappe.qb.DocType("Has Role")
    user = frappe.qb.DocType("User")
    rows = (
        frappe.qb.from_(has_role)
        .join(user)
        .on(user.name == has_role.parent)
        .select(user.name, user.full_name, user.user_image, has_role.role)
        .where(
            (has_role.parenttype == "User")
            & has_role.role.isin(TEAM_ROLES)
            & (user.enabled == 1)
            & user.name.notin(NOT_PEOPLE)
        )
        .run(as_dict=True)
    )
    members: dict[str, dict] = {}
    for row in rows:
        member = members.setdefault(
            row.name,
            {
                "user": row.name,
                "full_name": row.full_name or row.name,
                "user_image": row.user_image,
                "roles": [],
            },
        )
        member["roles"].append(row.role)
    for member in members.values():
        member["roles"].sort(key=TEAM_ROLES.index)
    return sorted(members.values(), key=lambda m: m["full_name"].lower())


def candidates(members: list[dict]) -> list[dict]:
    """Active agents with an enabled account who are not on the team yet: who can be added."""
    on_team = {m["user"] for m in members} | set(NOT_PEOPLE)
    agent = frappe.qb.DocType("HD Agent")
    user = frappe.qb.DocType("User")
    rows = (
        frappe.qb.from_(agent)
        .join(user)
        .on(user.name == agent.user)
        .select(user.name, user.full_name)
        .where((agent.is_active == 1) & (user.enabled == 1))
        .run(as_dict=True)
    )
    return sorted(
        (
            {"user": r.name, "full_name": r.full_name or r.name}
            for r in rows
            if r.name not in on_team
        ),
        key=lambda c: c["full_name"].lower(),
    )


def set_team_roles(user: str, roles: list[str]) -> list[str]:
    """Gives `user` exactly these team roles; none takes them off the team. Their other
    roles stay, except that Sales Employee, a department wall, replaces the ERP or Digital
    wall, as Settings → Agents does (one wall at a time)."""
    if set(roles) - set(TEAM_ROLES):
        frappe.throw(_("Pick Sales User, Presales Executive or Sales Employee."))
    roles = [r for r in TEAM_ROLES if r in set(roles)]
    doc = get_manageable_user(user, adding=bool(roles))
    ensure_role()
    drop = set(TEAM_ROLES) - set(roles)
    if SALES_EMPLOYEE_ROLE in roles:
        drop |= set(WALL_ROLES) - {SALES_EMPLOYEE_ROLE}
    doc.set("roles", [r for r in doc.roles if r.role not in drop])
    held = {r.role for r in doc.roles}
    for role in roles:
        if role not in held:
            doc.append("roles", {"role": role})
    # a Sales Head has no write access on User; require_sales_head decided
    doc.save(ignore_permissions=True)
    return roles


def get_manageable_user(user: str, adding: bool):
    """The User a Sales Head may change: never a built-in account or an admin (unless a
    System Manager asks), and only an active agent may be put on the team."""
    if user in NOT_PEOPLE or not frappe.db.exists("User", user):
        frappe.throw(_("{0} is not a user.").format(user), frappe.DoesNotExistError)
    if adding and not (
        frappe.db.get_value("User", user, "enabled")
        and frappe.db.get_value("HD Agent", {"user": user, "is_active": 1})
    ):
        frappe.throw(_("{0} is not an active agent.").format(user))
    if "System Manager" not in frappe.get_roles() and set(frappe.get_roles(user)) & set(
        FULL_ACCESS_ROLES
    ):
        frappe.throw(
            _("Only a System Manager can change an admin's roles."),
            SalesTeamForbiddenError,
        )
    return frappe.get_doc("User", user)
