import frappe

from helpdesk.api.customization import ensure_ticket_type


def execute():
    """The Customization ticket type, and the default development hours per day."""
    ensure_ticket_type()
    if not frappe.db.get_single_value("HD Work Settings", "dev_hours_per_day"):
        frappe.db.set_single_value("HD Work Settings", "dev_hours_per_day", 6)
