import frappe


def before_insert(doc, method=None):
    """Frappe's assignment notice (and its email) opens the item in /helpdesk,
    not in /app, which agents can't use."""
    from helpdesk.work_reminders import helpdesk_path

    if (
        doc.type == "Assignment"
        and doc.document_type in ("HD Ticket", "Task")
        and doc.document_name
    ):
        doc.link = frappe.utils.get_url(
            "/helpdesk" + helpdesk_path(doc.document_type, doc.document_name)
        )
