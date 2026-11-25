import frappe

SETTINGS = "HDS Copilot Settings"
OLD, NEW = "Correct", "Fix and data"


def execute():
    """Phase 30: the fourth Copilot level, "Correct", is called "Fix and data" (a code fix and a
    senior-approved change to the customer's settings and data). Customers and the default level
    keep the level they had under its new name."""
    if frappe.db.has_column("HD Customer", "custom_copilot_level"):
        frappe.db.sql(
            "update `tabHD Customer` set custom_copilot_level = %s where custom_copilot_level = %s",
            (NEW, OLD),
        )
    if frappe.db.get_single_value(SETTINGS, "default_copilot_level") == OLD:
        frappe.db.set_single_value(SETTINGS, "default_copilot_level", NEW)
