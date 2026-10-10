import frappe
from frappe.query_builder.functions import Count

from helpdesk.utils import agent_only, assigned_names_query


@frappe.whitelist()
@agent_only
def get_nav_counts() -> dict[str, int]:
    """Counts of work waiting on the current agent, for the sidebar."""
    user = frappe.session.user
    ticket = frappe.qb.DocType("HD Ticket")
    counts = {
        "tickets": _count_assigned("HD Ticket", user, ticket.status_category == "Open"),
        "my_tasks": 0,
    }
    if frappe.db.table_exists("Task"):
        task = frappe.qb.DocType("Task")
        counts["my_tasks"] = _count_assigned(
            "Task", user, task.status.notin(["Completed", "Cancelled"])
        )
    counts["my_work"] = counts["my_tasks"] + _count_assigned(
        "HD Ticket", user, ticket.status_category.isin(["Open", "Paused"])
    )
    return counts


def _count_assigned(doctype: str, user: str, condition) -> int:
    """How many `doctype` records assigned to `user` match `condition`, in one query,
    the assignment matched exactly through its ToDos. A ticket counts only while its
    assignment is open, as in `_assign` (see `assigned_names_query`)."""
    table = frappe.qb.DocType(doctype)
    assigned = assigned_names_query(doctype, user, finished=doctype != "HD Ticket")
    return (
        frappe.qb.from_(table)
        .select(Count(table.name))
        .where(table.name.isin(assigned) & condition)
        .run()[0][0]
    )
