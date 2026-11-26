# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Copilot board's API (Phase 10): read-only, for agents, each seeing what their permissions
allow (helpdesk.copilot.board)."""

import frappe
from frappe.utils import sbool

from helpdesk.copilot import board
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def summary() -> dict:
    """The top strip: the worker and the month's AI spend (Agent Managers), runs waiting."""
    return board.summary()


@frappe.whitelist()
@agent_only
def work(
    customer: str | None = None,
    mine: str | int | None = None,
    source: str | None = None,
) -> dict:
    """Copilot's runs by column; `mine`: the person is assigned, approves or took it over."""
    return board.work(customer or None, sbool(mine), source or None)


@frappe.whitelist()
@agent_only
def approvals() -> list[dict]:
    return board.approvals()


@frappe.whitelist()
@agent_only
def releases(days: int = 7) -> dict:
    return board.releases(int(days or 7))


@frappe.whitelist()
@agent_only
def sites(customer: str | None = None) -> list[dict]:
    return board.sites(customer or None)


@frappe.whitelist()
@agent_only
def known_issues(status: str | None = None) -> list[dict]:
    if status and status not in ("Open", "Fixed", "Not a bug"):
        frappe.throw(frappe._("Unknown status {0}").format(status))
    return board.known_issues(status or None)
