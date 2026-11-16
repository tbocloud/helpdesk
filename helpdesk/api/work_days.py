"""Working days for the desk: a task is never due on a day off and never goes overdue over
one (helpdesk.work_calendar, "days off and task due dates"). The date pickers warn with
check_due_date before a task is saved, and the task screens count overdue against
get_overdue_cutoff, as the server does."""

import frappe
from frappe.utils import cint

from helpdesk.utils import agent_only
from helpdesk.work_calendar import due_on_working_day, overdue_cutoff


@frappe.whitelist()
@agent_only
def get_overdue_cutoff() -> dict:
    """{cutoff}: a task due before this date is overdue (today, or the first of the days
    off right before it)."""
    return {"cutoff": str(overdue_cutoff())}


@frappe.whitelist()
@agent_only
def check_due_date(date: str, content: int | str = 0) -> dict | None:
    """Where a due date on a day off will be saved: {was, due, reason}; None on a working
    day. `content`: a content task, which moves to the working day before instead."""
    if not date:
        return None
    moved = due_on_working_day(date, content=bool(cint(content)))
    if not moved:
        return None
    return {key: str(value) for key, value in moved.items()}
