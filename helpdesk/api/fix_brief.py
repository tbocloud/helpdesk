import frappe

from helpdesk.fix_brief import build_fix_brief
from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def get_fix_brief(ticket: str | int) -> dict:
    """The ticket as a Markdown brief to hand to an AI coding agent or a developer."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    return {
        "markdown": build_fix_brief(doc),
        "filename": f"ticket-{doc.name}-fix-brief.md",
    }
