import frappe


def execute():
    """Defaults for the new task settings; a Single's field defaults only apply to new sites."""
    values = {
        "default_task_mode": "One task per person",
        "writer_days_before": 3,
        "designer_days_before": 1,
    }
    for field, value in values.items():
        if not frappe.db.get_single_value("HD Content Settings", field):
            frappe.db.set_single_value("HD Content Settings", field, value)
