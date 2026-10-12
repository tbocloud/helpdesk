import frappe

SETTINGS = "HD Follow Up Settings"


def execute():
    """Store HD Follow Up Settings' defaults on existing sites, so the follow-ups run
    and every field has its value (a new Single has nothing stored)."""
    if frappe.db.get_singles_dict(SETTINGS):
        return
    frappe.new_doc(SETTINGS).save(ignore_permissions=True)
