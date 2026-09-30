import frappe
from frappe import _

WAITING_ON_TASK = "Waiting on Task"


def on_update(doc, method=None):
    if doc.status == "Completed" and doc.has_value_changed("status"):
        notify_ticket_task_completed(doc)


def notify_ticket_task_completed(task):
    """Hand the linked support ticket back to the agent once the work is done."""
    if not task.get("hd_ticket") or not frappe.db.exists("HD Ticket", task.hd_ticket):
        return
    ticket = frappe.get_doc("HD Ticket", task.hd_ticket)
    if ticket.status == WAITING_ON_TASK:
        ticket.status = "Open"
        ticket.save(ignore_permissions=True)
    done_by = (
        frappe.db.get_value("User", frappe.session.user, "full_name")
        or frappe.session.user
    )
    frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": ticket.name,
            "content": _(
                "Task {0} ({1}) was completed by {2}. Reply to the customer."
            ).format(
                frappe.bold(task.name),
                frappe.utils.escape_html(task.subject or ""),
                done_by,
            ),
            "commented_by": frappe.session.user,
        }
    ).insert(ignore_permissions=True)
