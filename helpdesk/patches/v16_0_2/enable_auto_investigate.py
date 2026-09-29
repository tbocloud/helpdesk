import frappe


def execute():
    """Turn on Auto Investigate for existing hubs; new fields on a Single have no stored value."""
    if frappe.db.get_single_value("HDS Hub Settings", "auto_investigate") in (None, ""):
        frappe.db.set_single_value("HDS Hub Settings", "auto_investigate", 1)
