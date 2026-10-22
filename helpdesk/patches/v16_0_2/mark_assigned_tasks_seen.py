import frappe
from frappe.utils import now_datetime

from helpdesk.tasky.new_assignments import SEEN


def execute():
    """Tasks people already had before the New mark existed count as seen, so My Work
    doesn't open with every task marked New. Safe to run again: it skips pairs that
    already have a row."""
    todo = frappe.qb.DocType("ToDo")
    pairs = (
        frappe.qb.from_(todo)
        .select(todo.allocated_to, todo.reference_name)
        .distinct()
        .where(
            (todo.reference_type == "Task")
            & (todo.status == "Open")
            & todo.allocated_to.isnotnull()
        )
        .run()
    )
    existing = set(frappe.get_all(SEEN, fields=["user", "task"], as_list=True))
    now = now_datetime()
    rows = [
        (frappe.generate_hash(length=10), user, task, now, now, now, "Administrator")
        for user, task in pairs
        if (user, task) not in existing
    ]
    frappe.db.bulk_insert(
        SEEN,
        ["name", "user", "task", "seen_on", "creation", "modified", "owner"],
        rows,
    )
    print(f"Marked {len(rows)} existing task assignment(s) as seen")
