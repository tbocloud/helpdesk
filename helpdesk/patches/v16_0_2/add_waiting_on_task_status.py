import frappe


def execute():
    """Ticket status used while a linked project task is being worked on (pauses SLA)."""
    if frappe.db.exists("HD Ticket Status", "Waiting on Task"):
        return
    frappe.get_doc(
        {
            "doctype": "HD Ticket Status",
            "label_agent": "Waiting on Task",
            "color": "Orange",
            "enabled": 1,
            "category": "Paused",
            "different_view": 1,
            "label_customer": "In progress",
            "order": 5,
        }
    ).insert(ignore_permissions=True)
