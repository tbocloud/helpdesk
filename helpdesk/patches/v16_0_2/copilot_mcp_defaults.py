import frappe

from helpdesk.copilot.settings import DEFAULT_MCP_CALLS_PER_MINUTE


def execute():
    """Switch the MCP server on for existing sites with the default limit; a new
    field's default only applies to new documents."""
    frappe.db.set_single_value("HDS Copilot Settings", "mcp_enabled", 1)
    if not frappe.db.get_single_value("HDS Copilot Settings", "mcp_calls_per_minute"):
        frappe.db.set_single_value(
            "HDS Copilot Settings", "mcp_calls_per_minute", DEFAULT_MCP_CALLS_PER_MINUTE
        )
