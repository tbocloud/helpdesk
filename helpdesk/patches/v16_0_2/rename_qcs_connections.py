import frappe


def execute():
    """QCS-CONN-2026-00001 -> TBO-CONN-2026-00001, for connections not registered yet.

    A connected customer site stores the connection name as its client_id, so
    those keep their name. The TBO series is moved past the renamed numbers so
    new connections don't collide with them.
    """
    highest = {}
    for name in frappe.get_all(
        "HDS Support Connection",
        filters={
            "name": ("like", "QCS-CONN-%"),
            "connection_status": ("!=", "Connected"),
        },
        pluck="name",
    ):
        new_name = "TBO-" + name[len("QCS-") :]
        if frappe.db.exists("HDS Support Connection", new_name):
            continue
        frappe.rename_doc("HDS Support Connection", name, new_name, force=True)
        prefix, _, number = new_name.rpartition("-")
        if number.isdigit():
            highest[prefix + "-"] = max(highest.get(prefix + "-", 0), int(number))

    for prefix, number in highest.items():
        current = frappe.db.get_value("Series", prefix, "current", order_by="name")
        if current is None:
            frappe.db.sql(
                "insert into `tabSeries` (`name`, `current`) values (%s, %s)",
                (prefix, number),
            )
        elif current < number:
            frappe.db.sql(
                "update `tabSeries` set `current` = %s where `name` = %s",
                (number, prefix),
            )
