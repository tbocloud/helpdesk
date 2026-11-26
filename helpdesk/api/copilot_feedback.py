# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Pilot feedback from the desktop app: "TBO Support: Report a problem" (TBO Copilot Phase 21)."""

import frappe

from helpdesk.copilot import feedback
from helpdesk.utils import agent_only

CHANNELS = ("Desktop", "Web", "Teams")


@frappe.whitelist(methods=["POST"])
@agent_only
def report_problem(text: str, where: str = "Desktop") -> dict:
    """The signed-in person's report as a task for the TBO Copilot team (their own words; their last
    Copilot actions by id only)."""
    return feedback.report(
        frappe.session.user, where if where in CHANNELS else "Desktop", text
    )
