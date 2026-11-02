"""The Adoption page: who is using the system and what is stuck (docs/adoption.md).
The findings and the people table are built in helpdesk.adoption."""

import frappe
from frappe import _

from helpdesk.adoption import PERIODS, build, can_see_adoption
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def get_adoption(period: str = "this_week", fresh: int | str = 0) -> dict:
    """Ranked findings and the people table for `period` (this_week, last_week, last_30).
    For System Managers, Agent Managers, TBO Management and project coordinators."""
    if not can_see_adoption():
        frappe.throw(
            _("Only managers and project coordinators can open Adoption."),
            frappe.PermissionError,
        )
    if period not in PERIODS:
        frappe.throw(_("Unknown period: {0}").format(period))
    return build(period, fresh)
