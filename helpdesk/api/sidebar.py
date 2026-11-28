import frappe
from frappe.query_builder.functions import Count

from helpdesk.follow_ups import summary_for
from helpdesk.utils import agent_only, assigned_names_query


@frappe.whitelist()
@agent_only
def get_nav_counts() -> dict:
    """Counts of work waiting on the current agent, for the sidebar, and the
    follow-ups that need them (the sidebar's strip, docs/follow-ups.md)."""
    user = frappe.session.user
    ticket = frappe.qb.DocType("HD Ticket")
    in_messages = ticket.custom_section == "Messages"
    open_ = ticket.status_category == "Open"
    counts = {
        # Support's Tickets badge leaves Meta's chats out; Messages has its own
        "tickets": _count_assigned(
            "HD Ticket", user, open_ & (ticket.custom_section.isnull() | ~in_messages)
        ),
        "messages": _count_assigned("HD Ticket", user, open_ & in_messages),
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
    counts["follow_ups"] = summary_for(user)
    counts["customer_chats"] = _customer_chats_waiting(user)
    return counts


def _customer_chats_waiting(user: str) -> int:
    """Customers' ERP chats waiting for a person, for the people who work them."""
    from helpdesk.content_team import can_work_tickets

    if not can_work_tickets(user):
        return 0
    chat = frappe.qb.DocType("HDS Conversation")
    return (
        frappe.qb.from_(chat)
        .select(Count(chat.name))
        .where(chat.channel == "ERP")
        .where(
            (chat.state == "Before a person")
            | ((chat.asked_for_person == 1) & (chat.state != "Closed"))
        )
        .run()[0][0]
    )


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
