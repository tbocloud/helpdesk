# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Adding a customer to Copilot from the helpdesk screens (Phase 30): for agents, each change
checked against the document's own permission (helpdesk.copilot.setup)."""

import frappe

from helpdesk.copilot import setup
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def customers(show: str = "all") -> list[dict]:
    """The Copilot board's Customers tab."""
    return setup.customers(show or "all")


@frappe.whitelist()
@agent_only
def customer(name: str) -> dict:
    """The customer page's Copilot tab."""
    return setup.customer_setup(name)


@frappe.whitelist(methods=["POST"])
@agent_only
def save_switches(name: str, values: dict | str) -> dict:
    """Copilot Enabled, the Copilot level and Watch Errors for one customer."""
    return setup.save_switches(name, setup.parse(values))


@frappe.whitelist(methods=["POST"])
@agent_only
def save_site_card(values: dict | str, name: str | None = None) -> dict:
    """Adds a site card, or changes the one named."""
    return setup.save_site_card(setup.parse(values), name or None)


@frappe.whitelist(methods=["POST"])
@agent_only
def read_apps(name: str, source: str = "site") -> dict:
    """Reads a site card's apps from the site or from Press."""
    return setup.read_apps(name, source)
