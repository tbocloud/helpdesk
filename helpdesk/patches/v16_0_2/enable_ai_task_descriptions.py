import frappe


def execute():
    """Turn on AI task descriptions for existing sites; a Single's field defaults only apply to new sites."""
    Singles = frappe.qb.DocType("Singles")
    saved = (
        frappe.qb.from_(Singles)
        .select(Singles.value)
        .where(Singles.doctype == "HD Work Settings")
        .where(Singles.field == "ai_task_descriptions")
        .run()
    )
    if not saved or saved[0][0] in (None, ""):
        frappe.db.set_single_value("HD Work Settings", "ai_task_descriptions", 1)
