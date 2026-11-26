"""Sales → Sales team: a Sales Head sees the sales team and adds, changes or removes its
people (docs/sales-team.md)."""

import frappe

from helpdesk.sales_team import (
    TEAM_ROLES,
    candidates,
    require_sales_head,
    set_team_roles,
    team_members,
)


@frappe.whitelist()
def get_team() -> dict:
    """The team, the roles a Sales Head gives, and the agents who can be added."""
    require_sales_head()
    members = team_members()
    return {
        "roles": list(TEAM_ROLES),
        "members": members,
        "candidates": candidates(members),
    }


@frappe.whitelist(methods=["POST"])
def set_member_roles(user: str, roles) -> list[str]:
    """Gives `user` exactly these team roles (adding them to the team); an empty list
    removes them from it. Returns the team roles they now hold."""
    require_sales_head()
    return set_team_roles(user, frappe.parse_json(roles) or [])
