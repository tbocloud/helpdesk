import frappe


def execute():
    """Turn the automated-email filter on for existing sites; a new Check field's
    default only applies to new documents."""
    frappe.db.set_single_value("HD Settings", "ignore_automated_emails", 1)
