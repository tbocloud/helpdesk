import frappe

from helpdesk.helpdesk.doctype.hd_content_occasion.hd_content_occasion import (
    ensure_default_occasions,
)


def execute():
    """Defaults for monthly plans and client follow-up, and the fixed-date occasions."""
    values = {"plan_day": 20, "client_reminder_days": 2, "client_escalate_days": 4}
    for field, value in values.items():
        if frappe.db.get_single_value("HD Content Settings", field) is None:
            frappe.db.set_single_value("HD Content Settings", field, value)
    ensure_default_occasions()
