import frappe


def execute():
    """Copilot starts in shadow mode on existing sites: its findings stay with the team
    until the ratings show it is right often enough. A new field's default only
    applies to new documents."""
    frappe.db.set_single_value("HDS Copilot Settings", "shadow_mode", 1)
