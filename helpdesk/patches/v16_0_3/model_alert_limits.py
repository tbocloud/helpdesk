import frappe

SETTINGS = "HDS Hub Settings"
LIMITS = {"model_alert_error_rate": 20, "model_alert_fallback_rate": 30}


def execute():
    """AI models (Phase 31): a site that already has its hub settings gets the two alert limits.
    A new field of a single document has no value until someone saves one, and the first save
    would write 0, which means "no alert"."""
    for field, limit in LIMITS.items():
        if not saved(field):
            frappe.db.set_single_value(SETTINGS, field, limit)


def saved(field: str) -> bool:
    """The field has a stored value, 0 too. frappe.db.exists can't tell: it asks tabSingles for
    a name column it doesn't have and swallows the error, so it always answers None."""
    singles = frappe.qb.DocType("Singles")
    # singles.field would be pypika's own field() method, not the column
    column = singles["field"]
    return bool(
        frappe.qb.from_(singles)
        .select(column)
        .where(singles.doctype == SETTINGS)
        .where(column == field)
        .run()
    )
