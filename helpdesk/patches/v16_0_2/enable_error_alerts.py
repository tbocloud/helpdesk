import frappe


def execute():
    """Turn error alerts on for existing sites; a new Check field's default only
    applies to new documents. Nothing is posted until chat is enabled."""
    frappe.db.set_single_value("HD Chat Settings", "post_error_alerts", 1)
