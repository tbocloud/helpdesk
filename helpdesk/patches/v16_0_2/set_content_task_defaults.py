import frappe

# New fields on an existing single doctype start empty, not at their defaults
DEFAULTS = {
    "create_tasks_on_assign": 1,
    "writer_hours": 2,
    "designer_hours": 3,
    "marketer_hours": 1,
}


def execute():
    Singles = frappe.qb.DocType("Singles")
    saved = set(
        frappe.qb.from_(Singles)
        .select(Singles.field)
        .where(Singles.doctype == "HD Content Settings")
        .where(Singles.field.isin(list(DEFAULTS)))
        .run(pluck=True)
    )
    for field, value in DEFAULTS.items():
        if field not in saved:
            frappe.db.set_single_value("HD Content Settings", field, value)
