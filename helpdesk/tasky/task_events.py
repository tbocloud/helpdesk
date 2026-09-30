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


ASSIGNED_EMPLOYEE_FIELD = "custom_assigned_employee"


def on_todo_insert(todo, method=None):
    """Fill a task's Assigned Employee when someone is assigned and it is still empty.

    Sites that limit people to their own Employee record (strict user permissions)
    only let them open tasks linked to that record.
    """
    if todo.reference_type != "Task" or not todo.allocated_to:
        return
    set_assigned_employee(todo.reference_name, todo.allocated_to, replace=False)


def set_assigned_employee(task: str, user: str | None, replace: bool = True):
    if not frappe.get_meta("Task").has_field(ASSIGNED_EMPLOYEE_FIELD):
        return
    current = frappe.db.get_value("Task", task, ASSIGNED_EMPLOYEE_FIELD)
    if current and not replace:
        return
    employee = (
        frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
        if user
        else None
    )
    if employee != current and (employee or replace):
        frappe.db.set_value(
            "Task", task, ASSIGNED_EMPLOYEE_FIELD, employee, update_modified=False
        )
