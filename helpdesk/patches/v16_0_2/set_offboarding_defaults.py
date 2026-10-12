import frappe


def execute():
    """A Single's defaults only reach new sites: existing ones start offboarding in dry
    run with a limit of 5, like a new site (it stays switched off)."""
    frappe.db.set_single_value(
        "HD Settings", {"offboarding_dry_run": 1, "offboarding_max_disables": 5}
    )
