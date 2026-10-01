import frappe

from helpdesk.duplicates import find_duplicates
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def get_possible_duplicates(ticket: str | int) -> list[dict]:
    """Open tickets that look like the same request as `ticket`, for the agent to merge."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    return find_duplicates(doc)
