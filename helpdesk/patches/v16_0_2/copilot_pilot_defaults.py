import frappe

SETTINGS = "HDS Copilot Settings"
DEFAULTS = {
    "monthly_ai_budget_usd": 100,
    "max_diagnosis_usd": 1,
    "pilot_report_enabled": 1,
}


def execute():
    """Phase 4 (the pilot): a new Single field's default only reaches new sites. The budget,
    the diagnosis cap and the weekly email get their defaults where never saved, and the
    default Copilot level keeps each site doing what it did: Diagnose only in shadow mode,
    Correct (everything, as before the levels) where Copilot already runs live."""
    saved = {
        row[0]
        for row in frappe.db.sql(
            "select field from `tabSingles` where doctype = %s", (SETTINGS,)
        )
    }
    for field, value in DEFAULTS.items():
        if field not in saved:
            frappe.db.set_single_value(SETTINGS, field, value)
    if "default_copilot_level" not in saved:
        live = not frappe.db.get_single_value(SETTINGS, "shadow_mode")
        frappe.db.set_single_value(
            SETTINGS, "default_copilot_level", "Correct" if live else "Diagnose only"
        )
