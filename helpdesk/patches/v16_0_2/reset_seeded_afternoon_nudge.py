import frappe

SETTINGS = "HD Follow Up Settings"


def execute():
    """Put the afternoon nudge back to 14:00 where seed_follow_up_settings stored the time
    it ran: Frappe gives a new document's Time fields the current time (with
    microseconds) instead of their default, and the settings page only ever saves HH:MM."""
    # nothing stored yet: the seed patch stores every default, now with 14:00
    if not frappe.db.get_singles_dict(SETTINGS):
        return
    value = str(frappe.db.get_single_value(SETTINGS, "afternoon_nudge_at") or "")
    if not value or "." in value:
        frappe.db.set_single_value(SETTINGS, "afternoon_nudge_at", "14:00")
