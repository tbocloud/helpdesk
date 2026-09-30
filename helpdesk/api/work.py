"""Task and ticket control: one view of important work and its deadlines.

Tasks are due on `exp_end_date`; tickets on their SLA `resolution_by`. Key work
is a task flagged `is_key` or a ticket with Urgent/High priority. Lists go
through `frappe.get_list`, so everyone only sees what their permissions allow.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime, nowdate

from helpdesk.tasky.permissions import can_manage_project, is_project_manager
from helpdesk.utils import agent_only

KEY_TICKET_PRIORITIES = ("Urgent", "High")
OPEN_TASK_FILTER = ("not in", ["Completed", "Cancelled", "Template"])
DUE_SOON_DAYS = 3
LIST_LIMIT = 300
WAITING_ON_TASK = "Waiting on Task"

TASK_FIELDS = [
    "name",
    "subject",
    "project",
    "status",
    "priority",
    "exp_end_date",
    "is_key",
    "hd_ticket",
    "_assign",
]
TICKET_FIELDS = [
    "name",
    "subject",
    "customer",
    "status",
    "status_category",
    "priority",
    "resolution_by",
    "_assign",
]


def _assignees(raw) -> list[str]:
    try:
        return json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []


def _project_names(tasks) -> dict:
    names = list({t.project for t in tasks if t.project})
    if not names:
        return {}
    return dict(
        frappe.get_all(
            "Project",
            filters={"name": ("in", names)},
            fields=["name", "project_name"],
            as_list=True,
        )
    )


def _task_item(task, project_names: dict) -> dict:
    deadline = getdate(task.exp_end_date) if task.exp_end_date else None
    return {
        "kind": "task",
        "name": task.name,
        "title": task.subject,
        "project": task.project,
        "project_name": project_names.get(task.project),
        "status": task.status,
        "priority": task.priority,
        "deadline": str(deadline) if deadline else None,
        "is_key": bool(task.is_key),
        "is_overdue": bool(deadline and deadline < getdate(nowdate())),
        "hd_ticket": task.hd_ticket,
        "assignees": _assignees(task._assign),
    }


def _ticket_item(ticket) -> dict:
    deadline = get_datetime(ticket.resolution_by) if ticket.resolution_by else None
    return {
        "kind": "ticket",
        "name": str(ticket.name),
        "title": ticket.subject,
        "customer": ticket.customer,
        "status": ticket.status,
        "priority": ticket.priority,
        "deadline": str(deadline) if deadline else None,
        "is_key": ticket.priority in KEY_TICKET_PRIORITIES,
        # SLA only runs while the ticket is open; paused tickets aren't overdue
        "is_overdue": bool(
            deadline and ticket.status_category == "Open" and deadline < now_datetime()
        ),
        "assignees": _assignees(ticket._assign),
    }


def _sort_key(item: dict):
    deadline = item["deadline"] or "9999-12-31"
    return (not item["is_overdue"], not item["is_key"], deadline)


def _assigned_to(user: str):
    # _assign stores a JSON list, so match the quoted email
    return ("like", f'%"{user}"%')


@frappe.whitelist()
@agent_only
def get_my_work() -> dict:
    """The current user's open tasks and tickets, overdue first, then by deadline."""
    user = frappe.session.user
    tasks = frappe.get_list(
        "Task",
        filters={"_assign": _assigned_to(user), "status": OPEN_TASK_FILTER},
        fields=TASK_FIELDS,
        limit_page_length=LIST_LIMIT,
    )
    tickets = frappe.get_list(
        "HD Ticket",
        filters={
            "_assign": _assigned_to(user),
            "status_category": ("in", ["Open", "Paused"]),
        },
        fields=TICKET_FIELDS,
        limit_page_length=LIST_LIMIT,
    )
    names = _project_names(tasks)
    items = [_task_item(t, names) for t in tasks] + [_ticket_item(t) for t in tickets]
    items.sort(key=_sort_key)
    return {
        "items": items,
        "counts": {
            "total": len(items),
            "overdue": sum(i["is_overdue"] for i in items),
            "key": sum(i["is_key"] for i in items),
        },
    }


@frappe.whitelist()
@agent_only
def get_overview(
    project: str | None = None,
    customer: str | None = None,
    assignee: str | None = None,
) -> dict:
    """Overdue, due-soon, key and waiting work across the projects and tickets the user can see."""
    today = getdate(nowdate())
    soon = add_days(today, DUE_SOON_DAYS)

    task_filters = {"status": OPEN_TASK_FILTER}
    ticket_filters = {"status_category": ("in", ["Open", "Paused"])}
    if project:
        task_filters["project"] = project
    if customer:
        ticket_filters["customer"] = customer
        task_filters["project"] = (
            "in",
            frappe.get_all("Project", filters={"hd_customer": customer}, pluck="name")
            or [""],
        )
    if assignee:
        task_filters["_assign"] = _assigned_to(assignee)
        ticket_filters["_assign"] = _assigned_to(assignee)

    tasks = frappe.get_list(
        "Task", filters=task_filters, fields=TASK_FIELDS, limit_page_length=LIST_LIMIT
    )
    tickets = (
        []
        if project  # a project filter narrows to project work only
        else frappe.get_list(
            "HD Ticket",
            filters=ticket_filters,
            fields=TICKET_FIELDS,
            limit_page_length=LIST_LIMIT,
        )
    )
    names = _project_names(tasks)
    items = [_task_item(t, names) for t in tasks] + [_ticket_item(t) for t in tickets]
    items.sort(key=_sort_key)

    def due_soon(item):
        if item["is_overdue"] or not item["deadline"]:
            return False
        return getdate(item["deadline"]) <= soon

    buckets = {
        "overdue": [i for i in items if i["is_overdue"]],
        "due_soon": [i for i in items if due_soon(i)],
        "key": [i for i in items if i["is_key"]],
        "waiting_on_task": [
            i for i in items if i["kind"] == "ticket" and i["status"] == WAITING_ON_TASK
        ],
    }
    return {
        "buckets": buckets,
        "counts": {k: len(v) for k, v in buckets.items()},
    }


@frappe.whitelist()
@agent_only
def get_ticket_task_context(ticket: str | int) -> dict:
    """Projects a task for this ticket can go into, and tasks already linked to it."""
    ticket = str(ticket)
    frappe.has_permission("HD Ticket", "read", ticket, throw=True)
    customer = frappe.db.get_value("HD Ticket", ticket, "customer")

    filters = {"status": ("not in", ["Completed", "Cancelled"])}
    # the customer's projects are open to support agents; others only to their managers
    candidates = frappe.get_all(
        "Project",
        filters=filters,
        fields=["name", "project_name", "hd_customer as customer"],
        order_by="modified desc",
        limit_page_length=LIST_LIMIT,
    )
    projects = [
        p
        for p in candidates
        if (customer and p.customer == customer) or can_manage_project(p.name)
    ]
    projects.sort(key=lambda p: p.customer != customer)
    # sent here because support agents who aren't members can't open the project
    members = {}
    for row in frappe.get_all(
        "Project User",
        filters={
            "parenttype": "Project",
            "parent": ("in", [p.name for p in projects] or [""]),
        },
        fields=["parent", "user", "full_name"],
        order_by="idx asc",
    ):
        members.setdefault(row.parent, []).append(
            {"user": row.user, "full_name": row.full_name}
        )
    for p in projects:
        p["members"] = members.get(p.name, [])

    linked = frappe.get_all(
        "Task",
        filters={"hd_ticket": ticket},
        fields=["name", "subject", "status", "project", "exp_end_date"],
        order_by="creation desc",
    )
    return {"customer": customer, "projects": projects, "linked_tasks": linked}


@frappe.whitelist()
@agent_only
def create_task_from_ticket(
    ticket: str | int,
    project: str,
    task_name: str = "",
    description: str = "",
    assigned_to: str = "",
    due_date: str | None = None,
    is_key: bool = False,
) -> dict:
    """Turn a ticket that needs project work into a task; the ticket waits until it's done."""
    from helpdesk.tasky.api import (
        _assign_user,
        _format_task,
        _is_project_member,
        _task_dict,
    )

    ticket = str(ticket)
    frappe.has_permission("HD Ticket", "write", ticket, throw=True)
    ticket_doc = frappe.get_doc("HD Ticket", ticket)

    if not frappe.db.exists("Project", project):
        frappe.throw(_("Project not found: {0}").format(project))
    project_customer = frappe.db.get_value("Project", project, "hd_customer")
    same_customer = (
        bool(ticket_doc.customer) and project_customer == ticket_doc.customer
    )
    if not (same_customer or can_manage_project(project)):
        frappe.throw(
            _("You can only create tasks in this customer's projects."),
            frappe.PermissionError,
        )
    assigned_to = (assigned_to or "").strip()
    if assigned_to and not _is_project_member(project, assigned_to):
        frappe.throw(_("{0} is not a member of this project.").format(assigned_to))

    task = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": (task_name or ticket_doc.subject or "").strip()
            or _("Ticket {0}").format(ticket),
            "description": description or "",
            "project": project,
            "priority": "High"
            if ticket_doc.priority in KEY_TICKET_PRIORITIES
            else "Medium",
            "status": "Open",
            "exp_end_date": due_date or None,
            "is_key": 1 if is_key else 0,
            "hd_ticket": ticket,
        }
    )
    # support agents may raise work in the customer's project without managing it;
    # the permission rule above already decided who may do this
    task.insert(ignore_permissions=True)
    if assigned_to:
        _assign_user(task, assigned_to, ignore_permissions=True)
    task.reload()

    if frappe.db.exists("HD Ticket Status", WAITING_ON_TASK):
        ticket_doc.status = WAITING_ON_TASK
        ticket_doc.save()
    frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": ticket,
            "content": _("Task {0} created in {1}: {2}").format(
                frappe.bold(task.name),
                frappe.utils.escape_html(
                    frappe.db.get_value("Project", project, "project_name") or project
                ),
                frappe.utils.escape_html(task.subject),
            ),
            "commented_by": frappe.session.user,
        }
    ).insert(ignore_permissions=True)
    return {"task": _format_task(_task_dict(task)), "ticket_status": ticket_doc.status}


def can_see_overview(user: str | None = None) -> bool:
    """PMs, admins and anyone leading a project get the cross-project overview."""
    user = user or frappe.session.user
    return is_project_manager(user) or bool(
        frappe.db.exists("Project", {"project_lead": user})
    )
