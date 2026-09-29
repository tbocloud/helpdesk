import frappe

from helpdesk.session_replay import get_session_replay_info
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def get_session_replay(ticket: str | int) -> dict:
    """The customer's recorded session on `ticket`: replay file, diagnostics and timeline.

    The replay file is private and attached to the ticket, so anyone who passes
    the ticket read check below can also download it from `replay_url`.
    """
    ticket = str(ticket)
    frappe.has_permission("HD Ticket", "read", ticket, throw=True)
    return get_session_replay_info(ticket)
