import frappe

from helpdesk.utils import agent_only


@frappe.whitelist()
@agent_only
def get_nav_counts() -> dict[str, int]:
    """Counts of work waiting on the current agent, for the sidebar."""
    # _assign stores a JSON list, so match the quoted email to avoid partial matches
    assigned = ("like", f'%"{frappe.session.user}"%')
    counts = {
        "tickets": frappe.db.count(
            "HD Ticket", {"_assign": assigned, "status_category": "Open"}
        ),
        "my_tasks": 0,
    }
    if frappe.db.table_exists("Task"):
        counts["my_tasks"] = frappe.db.count(
            "Task",
            {"_assign": assigned, "status": ("not in", ["Completed", "Cancelled"])},
        )
    counts["my_work"] = counts["my_tasks"] + frappe.db.count(
        "HD Ticket",
        {"_assign": assigned, "status_category": ("in", ["Open", "Paused"])},
    )
    return counts
