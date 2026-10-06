"""Task and ticket control: one view of important work and its deadlines.

Tasks are due on `exp_end_date`; tickets on their SLA `resolution_by`. Key work
is a task flagged `is_key` or a ticket with Urgent/High priority. Lists go
through `frappe.get_list`, so everyone only sees what their permissions allow.
"""

import json

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_to_date,
    get_datetime,
    getdate,
    now_datetime,
    nowdate,
)

from helpdesk.github_sync import OPEN_STATES as PR_OPEN_STATES
from helpdesk.github_sync import get_pull_requests
from helpdesk.tasky.permissions import (
    can_add_tasks,
    can_manage_project,
    get_led_projects,
    get_managed_projects,
    is_project_manager,
    is_tasky_admin,
)
from helpdesk.utils import agent_only

KEY_TICKET_PRIORITIES = ("Urgent", "High")
OPEN_TASK_FILTER = ("not in", ["Completed", "Cancelled", "Template"])
DUE_SOON_DAYS = 3
# at risk: not started this close to the deadline, or pushed out this often
NOT_STARTED_RISK_DAYS = 2
RESCHEDULE_RISK_COUNT = 2
SLA_RISK_HOURS = 4
# how far back My Work's Completed tab looks
DONE_DAYS = 30
PRS_PER_ITEM = 3
LIST_LIMIT = 300
WAITING_ON_TASK = "Waiting on Task"
ON_HOLD = "On Hold"
PENDING_REVIEW = "Pending Review"
# the Overview's donut counts each item once, under the first of these it falls in
URGENCY_ORDER = ("overdue", "at_risk", "due_soon", "key")
TOP_PROJECTS = 7
ATTENTION_LIMIT = 8

TASK_FIELDS = [
    "name",
    "subject",
    "project",
    "status",
    "priority",
    "exp_end_date",
    "is_key",
    "hd_ticket",
    "hold_reason",
    "hold_since",
    "is_milestone",
    "slip_count",
    "depends_on_task",
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


def _open_dependencies(tasks) -> dict:
    """Subjects of the tasks these depend on that aren't done yet."""
    names = list({t.depends_on_task for t in tasks if t.depends_on_task})
    if not names:
        return {}
    return dict(
        frappe.get_all(
            "Task",
            filters={
                "name": ("in", names),
                "status": ("not in", ["Completed", "Cancelled"]),
            },
            fields=["name", "subject"],
            as_list=True,
        )
    )


def _task_risks(task, deadline, today, waiting_on: str | None) -> list[str]:
    if task.status in (ON_HOLD, "Pending Review") or not deadline or deadline < today:
        return []
    days_left = (deadline - today).days
    risks = []
    if task.status == "Open" and days_left <= NOT_STARTED_RISK_DAYS:
        risks.append(_("Not started, due in {0} day(s)").format(days_left))
    if (task.slip_count or 0) >= RESCHEDULE_RISK_COUNT:
        risks.append(_("Rescheduled {0} times").format(task.slip_count))
    if waiting_on and days_left <= DUE_SOON_DAYS:
        risks.append(_("Still waiting on {0}").format(waiting_on))
    return risks


def _task_item(
    task, project_names: dict, open_dependencies: dict | None = None
) -> dict:
    deadline = getdate(task.exp_end_date) if task.exp_end_date else None
    on_hold = task.status == ON_HOLD
    today = getdate(nowdate())
    waiting_on = (open_dependencies or {}).get(task.depends_on_task)
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
        # the due date moves out by the days on hold, so a paused task isn't late
        "is_overdue": bool(deadline and deadline < today and not on_hold),
        "hd_ticket": task.hd_ticket,
        "hold_reason": task.hold_reason if on_hold else None,
        "hold_days": (
            (today - getdate(task.hold_since)).days
            if on_hold and task.hold_since
            else None
        ),
        "is_milestone": bool(task.is_milestone),
        "slip_count": task.slip_count or 0,
        "waiting_on": waiting_on,
        "risks": _task_risks(task, deadline, today, waiting_on),
        "assignees": _assignees(task._assign),
    }


def _ticket_risks(ticket, deadline) -> list[str]:
    if ticket.status_category != "Open":
        return []
    risks = []
    now = now_datetime()
    if deadline and now <= deadline <= add_to_date(now, hours=SLA_RISK_HOURS):
        hours = max(int((deadline - now).total_seconds() // 3600), 0)
        risks.append(_("SLA due in {0}h").format(hours))
    if ticket.priority in KEY_TICKET_PRIORITIES and not _assignees(ticket._assign):
        risks.append(_("{0} priority and unassigned").format(ticket.priority))
    return risks


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
        "risks": _ticket_risks(ticket, deadline),
        "assignees": _assignees(ticket._assign),
    }


def _items(tasks, tickets) -> list[dict]:
    names = _project_names(tasks)
    waiting = _open_dependencies(tasks)
    task_items = [_task_item(t, names, waiting) for t in tasks]
    # a task's pull requests mark it as Git work: open ones first, then the
    # latest merged or closed, newest activity first within each
    prs = get_pull_requests([t.name for t in tasks])
    for item in task_items:
        task_prs = prs.get(item["name"]) or []
        task_prs.sort(key=lambda pr: pr.state not in PR_OPEN_STATES)
        item["pull_requests"] = task_prs[:PRS_PER_ITEM]
    # who may sign off a task waiting for review: the project's manager or lead
    managed = {}
    for item in task_items:
        if item["status"] == PENDING_REVIEW:
            if item["project"] not in managed:
                managed[item["project"]] = can_manage_project(item["project"])
            item["can_approve"] = managed[item["project"]]
    items = task_items + [_ticket_item(t) for t in tickets]
    items.sort(key=_sort_key)
    return items


def _sort_key(item: dict):
    deadline = item["deadline"] or "9999-12-31"
    return (not item["is_overdue"], not item["is_key"], deadline)


def _assigned_to(user: str):
    # _assign stores a JSON list, so match the quoted email
    return ("like", f'%"{user}"%')


@frappe.whitelist()
@agent_only
def get_my_work(user: str | None = None) -> dict:
    """Open tasks and tickets of the current user (or, for leads and managers, a team member), overdue first."""
    viewer = frappe.session.user
    user = (user or "").strip() or viewer
    if user != viewer:
        allowed = can_see_overview(viewer) and (
            is_tasky_admin(viewer) or user in _team_members(viewer, None)
        )
        if not allowed:
            frappe.throw(
                _("You can only see the work of people on your projects."),
                frappe.PermissionError,
            )
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
    items = _items(tasks, tickets)
    done = _done_items(user)
    return {
        "items": items,
        "done": done,
        "counts": {
            "total": len(items),
            "overdue": sum(i["is_overdue"] for i in items),
            "key": sum(i["is_key"] for i in items),
            "at_risk": sum(bool(i["risks"]) for i in items),
            "done": len(done),
        },
    }


def _done_items(user: str) -> list[dict]:
    """Tasks the person completed and tickets they resolved lately, newest first."""
    since = add_days(getdate(nowdate()), -DONE_DAYS)
    tasks = frappe.get_list(
        "Task",
        filters={
            "_assign": _assigned_to(user),
            "status": "Completed",
            "completed_on": (">=", since),
        },
        fields=["name", "subject", "project", "completed_on", "custom_actual_hours"],
        order_by="completed_on desc",
        limit_page_length=LIST_LIMIT,
    )
    tickets = frappe.get_list(
        "HD Ticket",
        filters={
            "_assign": _assigned_to(user),
            "status_category": "Resolved",
            "resolution_date": (">=", since),
        },
        fields=["name", "subject", "customer", "status", "resolution_date"],
        order_by="resolution_date desc",
        limit_page_length=LIST_LIMIT,
    )
    project_names = _project_names(tasks)
    done = [
        {
            "kind": "task",
            "name": t.name,
            "title": t.subject,
            "project": t.project,
            "project_name": project_names.get(t.project),
            "status": "Completed",
            "done_on": str(t.completed_on) if t.completed_on else None,
            "hours": t.custom_actual_hours or 0,
        }
        for t in tasks
    ] + [
        {
            "kind": "ticket",
            "name": str(t.name),
            "title": t.subject,
            "customer": t.customer,
            "status": t.status,
            "done_on": str(getdate(t.resolution_date)) if t.resolution_date else None,
            "hours": None,
        }
        for t in tickets
    ]
    done.sort(key=lambda i: i["done_on"] or "", reverse=True)
    return done


@frappe.whitelist()
@agent_only
def get_overview(
    project: str | None = None,
    customer: str | None = None,
    assignee: str | None = None,
) -> dict:
    """Overdue, due-soon, key and waiting work across the projects and tickets the user can see.

    Also the Overview's charts: active work split by urgency, open tasks of the
    busiest projects, and the items that need attention first.
    """
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
            frappe.get_all("Project", filters={"customer": customer}, pluck="name")
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
    items = _items(tasks, tickets)

    def due_soon(item):
        if item["is_overdue"] or not item["deadline"] or item["status"] == ON_HOLD:
            return False
        return getdate(item["deadline"]) <= soon

    buckets = {
        "overdue": [i for i in items if i["is_overdue"]],
        "due_soon": [i for i in items if due_soon(i)],
        "key": [i for i in items if i["is_key"]],
        "waiting_on_task": [
            i for i in items if i["kind"] == "ticket" and i["status"] == WAITING_ON_TASK
        ],
        "on_hold": [i for i in items if i["kind"] == "task" and i["status"] == ON_HOLD],
        "at_risk": [i for i in items if i["risks"]],
        "review": [
            i for i in items if i["kind"] == "task" and i["status"] == "Pending Review"
        ],
    }
    return {
        "buckets": buckets,
        "counts": {k: len(v) for k, v in buckets.items()},
        "active": _urgency_split(items, buckets),
        "projects": _tasks_by_project(task_filters),
        "attention": _attention(buckets),
    }


def _urgency_split(items: list[dict], buckets: dict) -> dict:
    """Active work counted once, under its most urgent bucket, so the parts add up to the total."""
    members = {b: {(i["kind"], i["name"]) for i in buckets[b]} for b in URGENCY_ORDER}
    split = dict.fromkeys((*URGENCY_ORDER, "other"), 0)
    for item in items:
        key = (item["kind"], item["name"])
        split[next((b for b in URGENCY_ORDER if key in members[b]), "other")] += 1
    return {"total": len(items), **split}


def _tasks_by_project(task_filters: dict) -> list[dict]:
    """Open tasks per project under the overview's filters, busiest projects first."""
    filters = {**task_filters}
    filters.setdefault("project", ("is", "set"))
    rows = frappe.get_list(
        "Task",
        filters=filters,
        fields=["project", "count(*) as count"],
        group_by="project",
        order_by="count desc, project asc",
        limit_page_length=TOP_PROJECTS,
    )
    names = _project_names(rows)
    return [
        {
            "project": r.project,
            "project_name": names.get(r.project) or r.project,
            "count": r.count,
        }
        for r in rows
    ]


def _attention(buckets: dict) -> list[dict]:
    """Overdue work first, then work likely to slip; each item once, with its customer's latest summary."""
    seen = set()
    items = []
    for item in buckets["overdue"] + buckets["at_risk"]:
        key = (item["kind"], item["name"])
        if key not in seen:
            seen.add(key)
            items.append(item)
    items = items[:ATTENTION_LIMIT]

    projects = list({i["project"] for i in items if i.get("project")})
    project_customers = (
        dict(
            # only projects the user may read add their customer
            frappe.get_list(
                "Project",
                filters={"name": ("in", projects)},
                fields=["name", "customer"],
                as_list=True,
            )
        )
        if projects
        else {}
    )
    attention = [
        {
            **i,
            "customer": i.get("customer") or project_customers.get(i.get("project")),
        }
        for i in items
    ]
    summaries = _latest_summaries({i["customer"] for i in attention if i["customer"]})
    for item in attention:
        item["summary"] = summaries.get(item["customer"])
    return attention


def _latest_summaries(customers: set[str]) -> dict:
    """Each customer's newest work summary that the user may read."""
    if not customers:
        return {}
    latest = frappe.get_list(
        "HD Work Summary",
        filters={"customer": ("in", list(customers))},
        fields=["customer", "max(period_end) as period_end"],
        group_by="customer",
        order_by="customer asc",
    )
    wanted = {(r.customer, str(r.period_end)) for r in latest if r.period_end}
    if not wanted:
        return {}
    # several summaries can share the newest period; the latest generated wins
    rows = frappe.get_list(
        "HD Work Summary",
        filters={
            "customer": ("in", list({customer for customer, _end in wanted})),
            "period_end": ("in", list({end for _customer, end in wanted})),
        },
        fields=["name", "customer", "period_end"],
        order_by="creation desc",
    )
    summaries = {}
    for r in rows:
        if (r.customer, str(r.period_end)) in wanted:
            summaries.setdefault(
                r.customer, {"name": r.name, "period_end": str(r.period_end)}
            )
    return summaries


@frappe.whitelist()
@agent_only
def get_ticket_task_context(ticket: str | int) -> dict:
    """Projects a task for this ticket can go into, and tasks already linked to it."""
    ticket = str(ticket)
    frappe.has_permission("HD Ticket", "read", ticket, throw=True)
    customer = frappe.db.get_value("HD Ticket", ticket, "customer")

    filters = {"status": ("not in", ["Completed", "Cancelled"])}
    # the customer's projects are open to support agents; others to the people on them
    candidates = frappe.get_all(
        "Project",
        filters=filters,
        fields=["name", "project_name", "customer"],
        order_by="modified desc",
        limit_page_length=LIST_LIMIT,
    )
    projects = [
        p
        for p in candidates
        if (customer and p.customer == customer) or can_add_tasks(p.name)
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
    estimated_hours: float | str | None = None,
) -> dict:
    """Turn a ticket that needs project work into a task; the ticket waits until it's done.

    An approved customization estimate fills in the due date and hours when they aren't given.
    """
    from helpdesk.tasky.api import (
        _assign_user,
        _estimate_if_undated,
        _format_task,
        _is_project_member,
        _task_dict,
    )

    ticket = str(ticket)
    frappe.has_permission("HD Ticket", "write", ticket, throw=True)
    ticket_doc = frappe.get_doc("HD Ticket", ticket)

    if not frappe.db.exists("Project", project):
        frappe.throw(_("Project not found: {0}").format(project))
    project_customer = frappe.db.get_value("Project", project, "customer")
    same_customer = (
        bool(ticket_doc.customer) and project_customer == ticket_doc.customer
    )
    if not (same_customer or can_add_tasks(project)):
        frappe.throw(
            _(
                "You can only create tasks in this customer's projects or in projects you are on."
            ),
            frappe.PermissionError,
        )
    assigned_to = (assigned_to or "").strip()
    if assigned_to and not _is_project_member(project, assigned_to):
        frappe.throw(_("{0} is not a member of this project.").format(assigned_to))

    if ticket_doc.get("custom_estimate_status") == "Approved":
        due_date = due_date or ticket_doc.get("custom_agreed_delivery")
        estimated_hours = estimated_hours or ticket_doc.get("custom_estimate_hours")
    task = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": (task_name or ticket_doc.subject or "").strip()
            or _("Ticket {0}").format(ticket),
            "description": description or "",
            "project": project,
            "priority": (
                "High" if ticket_doc.priority in KEY_TICKET_PRIORITIES else "Medium"
            ),
            "status": "Open",
            "exp_end_date": due_date or None,
            "is_key": 1 if is_key else 0,
            "hd_ticket": ticket,
            # Task's existing "Estimated Hours" custom field (setup/install.py)
            "custom_estimated_hours": frappe.utils.flt(estimated_hours) or 0,
        }
    )
    # support agents may raise work in the customer's project without managing it;
    # the permission rule above already decided who may do this
    task.insert(ignore_permissions=True)
    if assigned_to:
        _assign_user(task, assigned_to, ignore_permissions=True)
    _estimate_if_undated(task)
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


def _team_members(user: str, projects: list[str] | None) -> set[str]:
    """Whose workload the viewer sees: every active agent for admins, else their projects' people."""
    if projects is None and is_tasky_admin(user):
        from helpdesk.tasky.api import get_users

        return {u.name for u in get_users()}
    projects = projects or list(
        set(get_managed_projects(user)) | set(get_led_projects(user))
    )
    if not projects:
        return set()
    members = set(
        frappe.get_all(
            "Project User",
            filters={"parenttype": "Project", "parent": ("in", projects)},
            pluck="user",
        )
    )
    leads = frappe.get_all(
        "Project", filters={"name": ("in", projects)}, pluck="project_lead"
    )
    # people given a task directly (never added to the team) still work on the project
    assignees = set()
    for raw in frappe.get_all(
        "Task",
        filters={"project": ("in", projects), "status": OPEN_TASK_FILTER},
        pluck="_assign",
    ):
        assignees.update(_assignees(raw))
    return {u for u in members | set(leads) | assignees if u}


@frappe.whitelist()
@agent_only
def get_team_workload(project: str | None = None, customer: str | None = None) -> dict:
    """Per person: their open tasks, what they're working on, counts, done this week."""
    user = frappe.session.user
    if not can_see_overview(user):
        frappe.throw(
            _("Only project managers and leads can see the team."),
            frappe.PermissionError,
        )

    projects = None
    if project:
        projects = [project]
    elif customer:
        projects = frappe.get_all(
            "Project", filters={"customer": customer}, pluck="name"
        )
    people = _team_members(user, projects)
    if projects is not None and not projects:
        people = set()

    today = getdate(nowdate())
    week_ago = add_days(today, -7)
    week_ahead = add_days(today, 7)
    task_filters = {"status": ("not in", ["Cancelled", "Template"])}
    if projects is not None:
        task_filters["project"] = ("in", projects or [""])
    tasks = frappe.get_list(
        "Task",
        filters=task_filters,
        or_filters={"status": ("!=", "Completed"), "completed_on": (">=", week_ago)},
        fields=[*TASK_FIELDS, "completed_on", "custom_estimated_hours"],
        limit_page_length=0,
    )
    ticket_filters = {"status_category": ("in", ["Open", "Paused"])}
    if customer:
        ticket_filters["customer"] = customer
    tickets = (
        []
        if project
        else frappe.get_list(
            "HD Ticket",
            filters=ticket_filters,
            fields=TICKET_FIELDS,
            limit_page_length=0,
        )
    )
    names = _project_names(tasks)

    rows = {
        person: {
            "user": person,
            "working_on": [],
            "tasks": [],
            "next_due": None,
            "open": 0,
            "working": 0,
            "review": 0,
            "on_hold": 0,
            "overdue": 0,
            "due_this_week": 0,
            "done_this_week": 0,
            "tickets": 0,
            "sla_breached": 0,
            "estimated_hours": 0,
        }
        for person in people
    }
    for task in tasks:
        item = _task_item(task, names)
        for person in item["assignees"]:
            row = rows.get(person)
            if not row:
                continue
            if task.status == "Completed":
                row["done_this_week"] += 1
                continue
            row["open"] += 1
            row["estimated_hours"] += task.custom_estimated_hours or 0
            row["tasks"].append(item)
            if task.status == "Working":
                row["working"] += 1
                row["working_on"].append(
                    {
                        "name": task.name,
                        "title": task.subject,
                        "project_name": item["project_name"],
                    }
                )
            elif task.status == "Pending Review":
                row["review"] += 1
            elif task.status == ON_HOLD:
                row["on_hold"] += 1
            if item["is_overdue"]:
                row["overdue"] += 1
            deadline = getdate(task.exp_end_date) if task.exp_end_date else None
            if deadline and today <= deadline <= week_ahead and task.status != ON_HOLD:
                row["due_this_week"] += 1
            if (
                deadline
                and task.status != ON_HOLD
                and (not row["next_due"] or str(deadline) < row["next_due"]["deadline"])
            ):
                row["next_due"] = {
                    "name": task.name,
                    "title": task.subject,
                    "deadline": str(deadline),
                }
    for ticket in tickets:
        item = _ticket_item(ticket)
        for person in item["assignees"]:
            row = rows.get(person)
            if row:
                row["tickets"] += 1
                row["sla_breached"] += item["is_overdue"]

    full_names = dict(
        frappe.get_all(
            "User",
            filters={"name": ("in", list(rows) or [""])},
            fields=["name", "full_name"],
            as_list=True,
        )
    )
    team = []
    for row in rows.values():
        row["full_name"] = full_names.get(row["user"]) or row["user"]
        row["tasks"].sort(key=_sort_key)
        row["estimated_hours"] = round(row["estimated_hours"], 1)
        team.append(row)
    team.sort(key=lambda r: (-r["overdue"], -r["open"], r["full_name"]))
    return {
        "people": team,
        "totals": {
            "people": len(team),
            "working_now": sum(1 for r in team if r["working"]),
            "free": sum(1 for r in team if not r["open"] and not r["tickets"]),
            "open": sum(r["open"] for r in team),
            "overdue": sum(r["overdue"] for r in team),
            "review": sum(r["review"] for r in team),
            "done_this_week": sum(r["done_this_week"] for r in team),
        },
    }


PROJECT_STATUSES = ("Open", "On hold", "Completed", "Cancelled")
ALL_PROJECTS = "All"
PORTFOLIO_TASK_FIELDS = [
    "name",
    "subject",
    "project",
    "status",
    "exp_end_date",
    "is_milestone",
    "_assign",
]
PROJECT_FIELDS = [
    "name",
    "project_name",
    "customer",
    "project_type",
    "status",
    "priority",
    "project_lead",
    "expected_start_date",
    "expected_end_date",
]


@frappe.whitelist()
@agent_only
def get_project_portfolio(status: str = "Open", customer: str | None = None) -> dict:
    """Which projects exist and who works on each: progress, members and what they're doing now."""
    user = frappe.session.user
    if not can_see_overview(user):
        frappe.throw(
            _("Only project managers and leads can see the team."),
            frappe.PermissionError,
        )
    status = status or "Open"
    if status != ALL_PROJECTS and status not in PROJECT_STATUSES:
        frappe.throw(_("Unknown project status: {0}").format(status))

    admin = is_tasky_admin(user)
    projects = _portfolio_projects(user, admin, status, customer)
    names = [p.name for p in projects]
    tasks = (
        frappe.get_list(
            "Task",
            filters={"project": ("in", names), "status": ("!=", "Template")},
            fields=PORTFOLIO_TASK_FIELDS,
            order_by="exp_end_date asc",
            limit_page_length=0,
        )
        if names
        else []
    )
    tasks_by_project = {}
    for task in tasks:
        tasks_by_project.setdefault(task.project, []).append(task)

    roles = _project_roles(names)
    today = getdate(nowdate())
    cards = [
        _portfolio_card(p, tasks_by_project.get(p.name, []), roles, today)
        for p in projects
    ]
    people = _people_matrix(cards)
    free = _free_people() if admin else None

    users = {m["user"] for c in cards for m in c["members"]}
    users |= {c["lead"] for c in cards if c["lead"]}
    users |= {p["user"] for p in people + (free or [])}
    full_names = _full_names(users)
    for card in cards:
        card["lead_name"] = full_names.get(card["lead"]) or card["lead"]
        for member in card["members"]:
            member["full_name"] = full_names.get(member["user"]) or member["user"]
        card["members"].sort(
            key=lambda m: (not m["working_now"], -m["open"], m["full_name"].lower())
        )
    for person in people + (free or []):
        person["full_name"] = full_names.get(person["user"]) or person["user"]
    people.sort(key=lambda p: (-p["open"], p["full_name"].lower()))
    for person in sorted(free or [], key=lambda p: p["full_name"].lower()):
        people.append(person)

    return {
        "projects": cards,
        "people": people,
        "totals": {
            "projects": len(cards),
            "people_active": sum(1 for p in people if not p["is_free"]),
            # only admins see every agent, so only they can tell who is free
            "people_free": len(free) if free is not None else None,
            "overdue": sum(c["counts"]["overdue"] for c in cards),
        },
    }


def _portfolio_projects(user: str, admin: bool, status: str, customer: str | None):
    filters = {}
    if status != ALL_PROJECTS:
        filters["status"] = status
    if customer:
        filters["customer"] = customer
    if not admin:
        # members see more projects than they run; the portfolio is only the ones they run
        filters["name"] = (
            "in",
            list(set(get_managed_projects(user)) | set(get_led_projects(user))) or [""],
        )
    return frappe.get_list(
        "Project",
        filters=filters,
        fields=PROJECT_FIELDS,
        order_by="project_name asc",
        limit_page_length=0,
    )


def _project_roles(projects: list[str]) -> dict:
    """{project: {user: project role}} from the projects' member tables."""
    if not projects:
        return {}
    member = frappe.qb.DocType("Project User")
    rows = (
        frappe.qb.from_(member)
        .select(member.parent, member.user, member.custom_role)
        .where((member.parenttype == "Project") & member.parent.isin(projects))
        .orderby(member.idx)
        .run(as_dict=True)
    )
    roles = {}
    for row in rows:
        if row.user:
            roles.setdefault(row.parent, {})[row.user] = row.custom_role
    return roles


def _full_names(users: set[str]) -> dict:
    if not users:
        return {}
    user = frappe.qb.DocType("User")
    return dict(
        frappe.qb.from_(user)
        .select(user.name, user.full_name)
        .where(user.name.isin(list(users)))
        .run()
    )


def _portfolio_card(project, tasks: list, roles: dict, today) -> dict:
    counts = {
        "total": 0,
        "done": 0,
        "open": 0,
        "working": 0,
        "review": 0,
        "on_hold": 0,
        "overdue": 0,
    }
    members = {u: _member(u, role) for u, role in roles.get(project.name, {}).items()}
    if project.project_lead:
        members.setdefault(project.project_lead, _member(project.project_lead))
        members[project.project_lead]["is_lead"] = True
    milestone = None

    for task in tasks:
        if task.status == "Cancelled":
            continue
        counts["total"] += 1
        if task.status == "Completed":
            counts["done"] += 1
            continue
        counts["open"] += 1
        deadline = getdate(task.exp_end_date) if task.exp_end_date else None
        is_overdue = bool(deadline and deadline < today and task.status != ON_HOLD)
        counts["overdue"] += is_overdue
        if task.status == "Working":
            counts["working"] += 1
        elif task.status == "Pending Review":
            counts["review"] += 1
        elif task.status == ON_HOLD:
            counts["on_hold"] += 1
        if task.is_milestone and (
            not milestone
            or (deadline and (not milestone["due"] or str(deadline) < milestone["due"]))
        ):
            milestone = {
                "name": task.name,
                "subject": task.subject,
                "due": str(deadline) if deadline else None,
                "is_overdue": is_overdue,
            }
        for person in _assignees(task._assign):
            member = members.setdefault(person, _member(person))
            member["open"] += 1
            if task.status == "Working":
                member["working"] += 1
                member["working_now"] = True
                member["working_on"] = member["working_on"] or {
                    "name": task.name,
                    "subject": task.subject,
                }

    return {
        "name": project.name,
        "project_name": project.project_name or project.name,
        "customer": project.customer,
        "project_type": project.project_type,
        "status": project.status,
        "priority": project.priority,
        "lead": project.project_lead,
        "expected_start_date": (
            str(project.expected_start_date) if project.expected_start_date else None
        ),
        "expected_end_date": (
            str(project.expected_end_date) if project.expected_end_date else None
        ),
        # cancelled work was never going to be done, so it doesn't hold progress back
        "progress": (
            round(counts["done"] / counts["total"] * 100) if counts["total"] else 0
        ),
        "counts": counts,
        "next_milestone": milestone,
        "members": list(members.values()),
    }


def _member(user: str, role: str | None = None) -> dict:
    return {
        "user": user,
        "role": role,
        "is_lead": False,
        "open": 0,
        "working": 0,
        "working_now": False,
        "working_on": None,
    }


def _people_matrix(cards: list[dict]) -> list[dict]:
    """Per person, the projects they have open work in, busiest project first."""
    people = {}
    for card in cards:
        for member in card["members"]:
            if not member["open"]:
                continue
            person = people.setdefault(
                member["user"],
                {
                    "user": member["user"],
                    "open": 0,
                    "working": 0,
                    "is_free": False,
                    "projects": [],
                },
            )
            person["open"] += member["open"]
            person["working"] += member["working"]
            person["projects"].append(
                {
                    "project": card["name"],
                    "project_name": card["project_name"],
                    "open": member["open"],
                    "working_now": member["working_now"],
                }
            )
    for person in people.values():
        person["projects"].sort(key=lambda p: (-p["open"], p["project_name"].lower()))
    return list(people.values())


def _free_people() -> list[dict]:
    """Active agents with no open task in any project, not just the ones shown."""
    from helpdesk.tasky.api import get_users

    task = frappe.qb.DocType("Task")
    busy = set()
    for raw in (
        frappe.qb.from_(task)
        .select(task["_assign"])
        .where(
            task.status.notin(["Completed", "Cancelled", "Template"])
            & task["_assign"].isnotnull()
        )
        .run(pluck=True)
    ):
        busy.update(_assignees(raw))
    return [
        {"user": u.name, "open": 0, "working": 0, "is_free": True, "projects": []}
        for u in get_users()
        if u.name not in busy
    ]


def can_see_overview(user: str | None = None) -> bool:
    """PMs, admins and anyone leading a project get the cross-project overview."""
    user = user or frappe.session.user
    return is_project_manager(user) or bool(
        frappe.db.exists("Project", {"project_lead": user})
    )
