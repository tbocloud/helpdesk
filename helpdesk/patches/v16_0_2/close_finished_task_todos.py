import frappe

from helpdesk.helpdesk.doctype.task.task import DONE


def execute():
    """Close the open ToDos of tasks completed or cancelled before Task.close_assignments
    did it on the status change. Safe to run again: it only finds what is still open."""
    todo = frappe.qb.DocType("ToDo")
    task = frappe.qb.DocType("Task")
    names = (
        frappe.qb.from_(todo)
        .join(task)
        .on(task.name == todo.reference_name)
        .select(task.name)
        .distinct()
        .where(
            (todo.reference_type == "Task")
            & (todo.status == "Open")
            & task.status.isin(list(DONE))
        )
        .run(pluck=True)
    )
    closed = sum(frappe.get_doc("Task", name).close_assignments() for name in names)
    message = (
        f"Closed {closed} open ToDo(s) of {len(names)} completed or cancelled task(s)"
    )
    frappe.logger("helpdesk").info(message)
    print(message)
