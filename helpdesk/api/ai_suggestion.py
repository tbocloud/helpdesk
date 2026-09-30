import frappe
from frappe import _

from helpdesk.ai_suggestion import (
    MAX_INSTRUCTIONS_CHARS,
    get_suggestion_info,
    is_ai_configured,
    is_open_ticket,
    queue_suggestion,
)
from helpdesk.api.ticket_ai import truncate
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def get_suggestion(ticket: str | int) -> dict:
    """The AI suggested reply waiting on `ticket`, with its status, note and sources."""
    ticket = str(ticket)
    frappe.has_permission("HD Ticket", "read", ticket, throw=True)
    return get_suggestion_info(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def regenerate_suggestion(ticket: str | int, instructions: str = "") -> dict:
    """Draft the suggested reply again in the background, optionally following `instructions`.

    Returns the suggestion as Pending; the card polls until it is Ready or Failed.
    """
    ticket = str(ticket)
    frappe.has_permission("HD Ticket", "write", ticket, throw=True)
    if not is_ai_configured():
        frappe.throw(_("AI isn't set up yet. Add an AI provider in HDS Hub Settings."))
    if not is_open_ticket(ticket):
        frappe.throw(_("This ticket is closed, so there is no reply to draft."))
    instructions = truncate((instructions or "").strip(), MAX_INSTRUCTIONS_CHARS)
    if not queue_suggestion(ticket, instructions):
        frappe.throw(_("Couldn't start drafting a reply. Try again."))
    return get_suggestion_info(ticket)
