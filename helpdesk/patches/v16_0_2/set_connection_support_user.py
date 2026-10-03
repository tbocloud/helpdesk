import frappe


def execute():
    """Connections registered before the support user was configurable all used the original one."""
    for name in frappe.get_all(
        "HDS Support Connection",
        filters={"connection_status": "Connected", "support_user": ("is", "not set")},
        pluck="name",
    ):
        frappe.db.set_value(
            "HDS Support Connection", name, "support_user", "support@quarkcs.com"
        )
