import frappe

# Helpdesk once shipped its own copies of these ERPNext doctypes, which replaced
# ERPNext's on migrate. Put ERPNext's definitions back before the schema sync,
# so they are never treated as orphans of the helpdesk module.
ERPNEXT_DOCTYPES = (
    ("projects", "project_user"),
    ("projects", "project"),
    ("projects", "task"),
    ("projects", "timesheet_detail"),
    ("projects", "timesheet"),
    ("setup", "employee"),
)


def execute():
    if "erpnext" not in frappe.get_installed_apps():
        return
    for module, name in ERPNEXT_DOCTYPES:
        frappe.reload_doc(module, "doctype", name, force=True)
    frappe.clear_cache()
