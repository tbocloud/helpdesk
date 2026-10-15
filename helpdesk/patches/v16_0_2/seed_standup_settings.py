import frappe

SETTINGS = "HD Standup Settings"


def execute():
    """Store HD Standup Settings' defaults (off, 09:00 / 10:00 / 10:30, hours shown,
    every team view on), since a new Single has nothing stored until it is saved."""
    if frappe.db.get_singles_dict(SETTINGS):
        return
    frappe.new_doc(SETTINGS).save(ignore_permissions=True)
