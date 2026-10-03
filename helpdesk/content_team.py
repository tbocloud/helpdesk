"""The Content Team role: writers, designers and marketers who work only on content.

They are agents (so the app opens for them) with the extra Content Team role,
and see the Content Calendar, their projects, My Work, the Calendar and
Timesheets. Tickets stay hidden from them. Anyone who also manages (Agent
Manager, Project Manager, System Manager) keeps full access.
"""

import frappe

CONTENT_TEAM_ROLE = "Content Team"
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


def ensure_role():
    """Created on migrate, so it can be given to people from the user's Roles."""
    if frappe.db.exists("Role", CONTENT_TEAM_ROLE):
        return
    frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": CONTENT_TEAM_ROLE,
            "desk_access": 1,
            "home_page": "/helpdesk/content",
        }
    ).insert(ignore_permissions=True)
