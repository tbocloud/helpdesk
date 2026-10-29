import frappe

SETTINGS = "HD Follow Up Settings"


def execute():
    """Switch the stale-lead rule on where the settings were stored before it existed (a
    stored Single gives a field added later 0, not its default); a site with nothing stored
    gets the default from seed_follow_up_settings."""
    if frappe.db.get_singles_dict(SETTINGS):
        frappe.db.set_single_value(SETTINGS, "stale_leads", 1)
