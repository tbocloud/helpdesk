import json

import frappe

from helpdesk.tasky.task_events import ASSIGNED_EMPLOYEE_FIELD, set_assigned_employee


def execute():
    """Link helpdesk-created tasks to their assignee's Employee, as new ones now are."""
    meta = frappe.get_meta("Task")
    if not meta.has_field(ASSIGNED_EMPLOYEE_FIELD):
        return
    link_fields = [f for f in ("content_post", "hd_ticket") if meta.has_field(f)]
    if not link_fields:
        return
    Task = frappe.qb.DocType("Task")
    condition = None
    for field in link_fields:
        clause = Task[field].isnotnull() & (Task[field] != "")
        condition = clause if condition is None else condition | clause
    tasks = (
        frappe.qb.from_(Task)
        .select(Task.name, Task._assign)
        .where(condition)
        .where(
            Task[ASSIGNED_EMPLOYEE_FIELD].isnull()
            | (Task[ASSIGNED_EMPLOYEE_FIELD] == "")
        )
        .run(as_dict=True)
    )
    for task in tasks:
        assignees = json.loads(task._assign or "[]")
        if assignees:
            set_assigned_employee(task.name, assignees[0], replace=False)
