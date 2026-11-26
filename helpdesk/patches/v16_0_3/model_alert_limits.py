import frappe

SETTINGS = "HDS Hub Settings"
LIMITS = {"model_alert_error_rate": 20, "model_alert_fallback_rate": 30}


def execute():
    """AI models (Phase 31): a site that already has its hub settings gets the two alert limits.
    A new field of a single document has no value until someone saves one, and the first save
    would write 0, which means "no alert"."""
    for field, limit in LIMITS.items():
        if not frappe.db.exists("Singles", {"doctype": SETTINGS, "field": field}):
            frappe.db.set_single_value(SETTINGS, field, limit)
