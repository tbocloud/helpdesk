# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Messages section's actions for agents (TBO Copilot phase 32, docs/messages.md)."""

import frappe
from frappe import _

from helpdesk import chat_messages
from helpdesk.utils import agent_only


@frappe.whitelist(methods=["POST"])
@agent_only
def move_to_support(ticket: str) -> dict:
    """A Messages chat that is really a customer's ERP problem goes to Support."""
    ticket = str(ticket or "").strip()
    if not ticket or not frappe.db.exists("HD Ticket", ticket):
        frappe.throw(_("Ticket {0} was not found.").format(ticket))
    if not frappe.has_permission("HD Ticket", "write", doc=ticket):
        frappe.throw(
            _("You may not change ticket {0}.").format(ticket), frappe.PermissionError
        )
    return {
        "ticket": chat_messages.move_to_support(ticket),
        "section": chat_messages.SUPPORT,
    }
