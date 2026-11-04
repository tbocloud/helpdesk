import frappe

SETTINGS = "HD Follow Up Settings"


def execute():
    """Switch the weekly adoption digest on where the settings were stored before it
    existed (a stored Single gives a field added later 0, not its default); a site with
    nothing stored gets the default."""
    if frappe.db.get_singles_dict(SETTINGS):
        frappe.db.set_single_value(SETTINGS, "adoption_digest", 1)
