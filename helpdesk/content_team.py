"""The Content Team role: writers, designers and marketers who work only on content.

They are agents (so the app opens for them) with the extra Content Team role,
and see the Content Calendar, their projects, My Work, the Calendar and
Timesheets. Tickets stay hidden from them. Anyone who also manages (Agent
Manager, Project Manager, System Manager) keeps full access.
"""

import frappe

CONTENT_TEAM_ROLE = "Content Team"
# approves every post after the client does, before it can go out
DM_HEAD_ROLE = "Digital Marketing Head"
# adds and changes content entries; everyone else can only attach files to them
DM_COORDINATOR_ROLE = "DM Coordinator"
# a digital marketing team member: sees entries and attaches files, nothing more
DM_EMPLOYEE_ROLE = "DM Employee"
# an ERP team member: never sees the Digital department's projects or the content calendar
ERP_EMPLOYEE_ROLE = "ERP Employee"
CONTENT_EDITOR_ROLES = (
    "System Manager",
    DM_COORDINATOR_ROLE,
    "Agent Manager",
    "Project Manager",
)
# with the editors, the people who are part of the content calendar; nobody else sees it
CONTENT_CALENDAR_ROLES = (
    CONTENT_TEAM_ROLE,
    DM_HEAD_ROLE,
    DM_COORDINATOR_ROLE,
    DM_EMPLOYEE_ROLE,
)
FULL_ACCESS_ROLES = (
    "Administrator",
    "System Manager",
    "Agent Manager",
    "Project Manager",
)


def is_content_only(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if user in ("Administrator", "Guest"):
        return False
    roles = set(frappe.get_roles(user))
    return CONTENT_TEAM_ROLE in roles and not roles & set(FULL_ACCESS_ROLES)


def is_department_employee(user: str | None = None) -> bool:
    """A DM or ERP Employee: tickets, customers, contacts, templates, the knowledge
    base, support hours and the customer report are hidden from them. System Managers
    and Agent Managers keep everything, as with the department walls."""
    from helpdesk.tasky.permissions import is_tasky_admin

    user = user or frappe.session.user
    if is_tasky_admin(user):
        return False
    return bool({DM_EMPLOYEE_ROLE, ERP_EMPLOYEE_ROLE} & set(frappe.get_roles(user)))


def sees_no_tickets(user: str | None = None) -> bool:
    """Writers and designers (Content Team) and DM / ERP Employees work on projects and
    content, not tickets; the tickets they raised stay theirs."""
    return is_content_only(user) or is_department_employee(user)


def is_erp_only(user: str | None = None) -> bool:
    """An ERP Employee who doesn't also edit content: never in the content team, never
    given a content post's task, and the work Calendar is hidden from them too."""
    user = user or frappe.session.user
    if user == "Administrator":
        return False
    return ERP_EMPLOYEE_ROLE in frappe.get_roles(user) and not can_edit_content(user)


def in_content_team(user: str | None = None) -> bool:
    """Part of the content calendar, so it's shown to them: whoever edits content (the
    admins, Project Managers and DM Coordinators) and holders of a content calendar role.
    Everyone else, ERP Employees included, sees only the content tasks that are their
    own (see docs/content-calendar.md)."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return _in_content_team(set(frappe.get_roles(user)))


def content_team_members(users: list[str]) -> list[str]:
    """Which of `users` are in the content team, from one query (Settings → Agents)."""
    if not users:
        return []
    has_role = frappe.qb.DocType("Has Role")
    roles = {user: set() for user in users}
    for user, role in (
        frappe.qb.from_(has_role)
        .select(has_role.parent, has_role.role)
        .where(
            (has_role.parenttype == "User")
            & has_role.parent.isin(users)
            & has_role.role.isin(
                [*CONTENT_EDITOR_ROLES, *CONTENT_CALENDAR_ROLES, ERP_EMPLOYEE_ROLE]
            )
        )
        .run()
    ):
        roles[user].add(role)
    return [u for u in users if u == "Administrator" or _in_content_team(roles[u])]


def _in_content_team(roles: set[str]) -> bool:
    if roles & set(CONTENT_EDITOR_ROLES):
        return True
    # the ERP Employee wall keeps them out whatever else they hold, as `is_erp_only`
    if ERP_EMPLOYEE_ROLE in roles:
        return False
    return bool(roles & set(CONTENT_CALENDAR_ROLES))


def can_edit_content(user: str | None = None) -> bool:
    """May add content entries and change anything on them. Everyone else who can see
    an entry may only attach files to it."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(set(CONTENT_EDITOR_ROLES) & set(frappe.get_roles(user)))


def is_dm_head(user: str | None = None) -> bool:
    """May approve a client-approved post or send it back; System Managers can too,
    so a post never waits on a head nobody has been given."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool({DM_HEAD_ROLE, "System Manager"} & set(frappe.get_roles(user)))


def head_approvers() -> list[str]:
    """Who hears that a post waits on the head: the Digital Marketing Heads, or the
    System Managers (who can act too) while nobody has been given that role."""
    heads = _users_with_role(DM_HEAD_ROLE)
    if heads:
        return heads
    return [u for u in _users_with_role("System Manager") if u != "Administrator"]


def _users_with_role(role: str) -> list[str]:
    has_role = frappe.qb.DocType("Has Role")
    user = frappe.qb.DocType("User")
    return (
        frappe.qb.from_(has_role)
        .join(user)
        .on(user.name == has_role.parent)
        .select(user.name)
        .where(
            (has_role.role == role)
            & (has_role.parenttype == "User")
            & (user.enabled == 1)
        )
        .run(pluck=True)
    )


def ensure_role():
    """Created on migrate, so they can be given to people from the user's Roles."""
    for role in (
        CONTENT_TEAM_ROLE,
        DM_HEAD_ROLE,
        DM_COORDINATOR_ROLE,
        DM_EMPLOYEE_ROLE,
        ERP_EMPLOYEE_ROLE,
    ):
        if frappe.db.exists("Role", role):
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role,
                "desk_access": 1,
                "home_page": "/helpdesk/content",
            }
        ).insert(ignore_permissions=True)
