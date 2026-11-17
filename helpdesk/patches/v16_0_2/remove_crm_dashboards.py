import frappe

# the CRM dashboards and their organisation were removed; the ERP sites (HD CRM Source) and
# their leads' reporting copy stay for the divisions (docs/divisions.md, "ERP sites")
DOCTYPES = (
    "HD CRM Dashboard KPI",
    "HD CRM Dashboard Chart",
    "HD CRM Dashboard Filter",
    "HD CRM Dashboard Role",
    "HD CRM Dashboard Unit",
    "HD CRM Dashboard",
    "HD CRM Org Unit",
)


def execute():
    for doctype in DOCTYPES:
        frappe.delete_doc("DocType", doctype, ignore_missing=True, force=True)
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
