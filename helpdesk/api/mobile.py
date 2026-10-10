"""The TBO Smart app's API (v1): a thin layer over the hub's own functions.

Every method calls the function the web pages use (My Work, Home, tasky, tickets,
project files, follow-ups, the team views and the Scoreboard) and reshapes its
answer into the stable shapes in docs/tbo-smart-api.md; no rule is decided here
that the web decides elsewhere, so the app and the web never disagree. The same
permission checks apply: lists go through `frappe.get_list` (or the reused
function), single records are checked, and writes are POST only.

Responses are {"v": 1, "data": …}; lists add `next_cursor` and `has_more`
(pass `cursor` back for the next page). A breaking change gets a new module and
a new `v`, never a changed shape here.
"""

import html

import frappe
from frappe import _
from frappe.permissions import AUTOMATIC_ROLES
from frappe.query_builder.functions import Count
from frappe.rate_limiter import rate_limit
from frappe.utils import (
    cint,
    escape_html,
    flt,
    get_datetime,
    get_fullname,
    getdate,
    now_datetime,
    nowdate,
)

from helpdesk import follow_ups, task_activity
from helpdesk import team_dashboard as td
from helpdesk.api import home, project_files
from helpdesk.api.content_board import user_full_names
from helpdesk.api.doc import remove_assignments
from helpdesk.api.follow_ups import check_admin
from helpdesk.api.team_dashboard import get_team_dashboard
from helpdesk.api.ticket import assign_ticket_to_agent
from helpdesk.api.work import (
    ON_HOLD,
    OPEN_TASK_FILTER,
    PENDING_REVIEW,
    TIMER_FIELDS,
    _assignees,
    can_see_overview,
    get_my_work,
    get_project_portfolio,
    get_team_workload,
    is_task_overdue,
    sla_due_soon,
)
from helpdesk.helpdesk.doctype.hd_notification.utils import clear
from helpdesk.helpdesk.doctype.hd_project_file.hd_project_file import SUPERSEDED
from helpdesk.helpdesk.doctype.hd_ticket.api import get_comments, get_communications
from helpdesk.tasky import api as tasky
from helpdesk.tasky.permissions import (
    can_coordinate_project,
    can_manage_project,
    get_coordinated_projects,
    get_led_projects,
    get_managed_projects,
    get_project_team,
    is_tasky_admin,
)
from helpdesk.utils import (
    agent_only,
    assigned_names_query,
    assigned_to_filter,
    get_agents_team,
)
from helpdesk.work_calendar import leave_today
from helpdesk.work_reminders import notify_users

API_VERSION = 1
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEVICE = "HD Mobile Device"
PLATFORMS = ("ios", "android")
MAX_TOKEN_LENGTH = 255
MAX_NUDGE_LENGTH = 500
OPEN_TICKET_CATEGORIES = ["Open", "Paused"]
TICKET_VIEWS = ("mine", "unassigned", "team", "all-open")
NUDGE_DOCTYPES = ("Task", "HD Ticket")
# per IP address (an office shares one), per minute
REPLY_RATE_LIMIT = 60
DEVICE_RATE_LIMIT = 30
RATE_WINDOW_SECONDS = 60
TICKET_FIELDS = [
    "name",
    "subject",
    "customer",
    "contact",
    "raised_by",
    "priority",
    "status",
    "status_category",
    "agent_group",
    "response_by",
    "first_responded_on",
    "resolution_by",
    "creation",
    "_assign",
    "custom_escalation_level",
]
# the hub's task activity kinds, grouped into the app's five
ACTIVITY_KINDS = {
    "created": "status",
    "status": "status",
    "due": "status",
    "estimate": "status",
    "assigned": "assign",
    "unassigned": "assign",
    "note": "comment",
    "comment": "comment",
    "time": "time",
}
# where the app opens a document
APP_ROUTES = {
    "Task": "/task/{0}",
    "HD Ticket": "/ticket/{0}",
    "Project": "/project/{0}",
}


# --- envelope and paging -----------------------------------------------------


def _one(data) -> dict:
    return {"v": API_VERSION, "data": data}


def _page_args(cursor, limit) -> tuple[int, int]:
    start = max(cint(cursor), 0)
    limit = min(max(cint(limit) or DEFAULT_LIMIT, 1), MAX_LIMIT)
    return start, limit


def _paged(items: list, cursor, limit) -> dict:
    """One page of an already ordered list."""
    start, limit = _page_args(cursor, limit)
    has_more = len(items) > start + limit
    return {
        "v": API_VERSION,
        "data": items[start : start + limit],
        "next_cursor": start + limit if has_more else None,
        "has_more": has_more,
    }


def app_route(doctype: str | None, name) -> str | None:
    """The app screen that shows a document, or None when the app has none."""
    pattern = APP_ROUTES.get(doctype or "")
    return pattern.format(name) if pattern and name else None


def _person(user: str | None, names: dict | None = None) -> dict | None:
    if not user:
        return None
    full_name = (names or {}).get(user) if names is not None else get_fullname(user)
    return {"user": user, "full_name": full_name or user}


# --- me and home ---------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_me() -> dict:
    """Who is signed in and which parts of the app they may open."""
    return _one(_me())


@frappe.whitelist()
@agent_only
def get_home() -> dict:
    """The home screen's counts (HomeCounts)."""
    items = get_my_work()["items"]
    return _one(_counts(items, home.build_day(items)))


@frappe.whitelist()
@agent_only
def get_home_bundle() -> dict:
    """Everything the app shows at launch in one request: me, the home counts and the
    first page of the user's tasks. The action plan follows as its own request
    (get_action_plan), because writing it may take the AI a few seconds."""
    items = get_my_work()["items"]
    tasks = _task_rows([i for i in items if i["kind"] == "task"])
    return _one(
        {
            "me": _me(),
            "counts": _counts(items, home.build_day(items)),
            "tasks": _paged(tasks, 0, DEFAULT_LIMIT),
        }
    )


@frappe.whitelist(methods=["POST"])
@agent_only
def get_action_plan(refresh: bool = False) -> dict:
    """Today's plan (helpdesk.api.home.get_action_plan), each step with the app
    screen it opens. POST like the web call, since it may ask the AI."""
    plan = home.get_action_plan(refresh=refresh)
    return _one(
        {
            "steps": [
                {
                    "id": f"s{index}",
                    "text": step["text"],
                    "detail": "",
                    "route": app_route("Task", step.get("task")),
                }
                for index, step in enumerate(plan["steps"], start=1)
            ],
            "generated_at": plan.get("generated_at"),
            "source": plan.get("source"),
            "stale": bool(plan.get("stale")),
            "reason": plan.get("reason"),
        }
    )


def _me() -> dict:
    user = frappe.session.user
    info = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    manager = can_see_overview(user)
    return {
        "user": user,
        "full_name": (info and info.full_name) or user,
        "image": info and info.user_image,
        "roles": sorted(set(frappe.get_roles(user)) - set(AUTOMATIC_ROLES)),
        "is_agent": True,
        "is_manager": manager,
        "can": {
            "team": manager,
            "projects_health": manager,
            "sla_summary": manager,
            "escalations": is_tasky_admin(user),
            "approvals": bool(_review_projects(user)),
        },
        "departments": _departments(user),
        "teams": sorted(t.team_name for t in get_agents_team()),
    }


def _review_projects(user: str) -> set[str]:
    """Projects whose tasks the user signs off (home._approvals reads the same)."""
    return (
        set(get_managed_projects(user))
        | set(get_led_projects(user))
        | set(get_coordinated_projects(user))
    )


def _departments(user: str) -> list[str]:
    """The departments of the open projects the user is on or leads."""
    project = frappe.qb.DocType("Project")
    member = frappe.qb.DocType("Project User")
    return sorted(
        frappe.qb.from_(project)
        .left_join(member)
        .on((member.parent == project.name) & (member.parenttype == "Project"))
        .select(project.custom_department)
        .distinct()
        .where(
            (project.status == "Open")
            & project.custom_department.isnotnull()
            & ((member.user == user) | (project.project_lead == user))
        )
        .run(pluck=True)
    )


def _counts(items: list[dict], day: dict) -> dict:
    tasks = [i for i in items if i["kind"] == "task"]
    return {
        "open_tickets": sum(i["kind"] == "ticket" for i in items),
        "awaiting_reply": day["replies"]["count"],
        "tasks_open": len(tasks),
        "tasks_due_today": day["summary"]["due_today"],
        "tasks_overdue": sum(t["is_overdue"] for t in tasks),
        "tasks_on_hold": day["summary"]["on_hold"],
        "tasks_in_review": day["summary"]["in_review"],
        "escalated_to_head": sum(t["escalation_level"] >= 2 for t in tasks),
        "approvals": day["approvals"]["count"],
        "unread_notifications": _unread_count(),
    }


# --- tasks ---------------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_tasks(
    group: str | None = None, cursor: int | str | None = None, limit: int | str = 20
) -> dict:
    """The user's open tasks (My Work), overdue first; `group` keeps one of overdue,
    today, upcoming, on_hold or in_review."""
    tasks = _task_rows([i for i in get_my_work()["items"] if i["kind"] == "task"])
    if group:
        tasks = [t for t in tasks if t["group"] == group]
    return _paged(tasks, cursor, limit)


@frappe.whitelist()
@agent_only
def get_task(task: str) -> dict:
    """One task with its description and activity, for anyone who may read it."""
    return _one(_task_detail(task))


@frappe.whitelist(methods=["POST"])
@agent_only
def start_task(task: str) -> dict:
    """Start the task, or resume its paused timer when it's already in progress."""
    frappe.has_permission("Task", "write", str(task), throw=True)
    if frappe.db.get_value("Task", str(task), "status") == "Working":
        tasky.start_timer(task)
    else:
        tasky.move_task(task, "Working")
    return _one(_task_detail(task))


@frappe.whitelist(methods=["POST"])
@agent_only
def pause_task(task: str) -> dict:
    """Pause the timer; the task stays in progress with its time banked."""
    frappe.has_permission("Task", "write", str(task), throw=True)
    tasky.stop_timer(task)
    return _one(_task_detail(task))


@frappe.whitelist(methods=["POST"])
@agent_only
def complete_task(task: str, hours_worked: float | str, notes: str) -> dict:
    """Complete with the hours and a note, logged to the user's timesheet."""
    frappe.has_permission("Task", "write", str(task), throw=True)
    tasky.complete_task(task, hours_worked=hours_worked, notes=notes)
    return _one(_task_detail(task))


@frappe.whitelist(methods=["POST"])
@agent_only
def hold_task(task: str, reason: str, note: str = "") -> dict:
    frappe.has_permission("Task", "write", str(task), throw=True)
    tasky.hold_task(task, reason, note)
    return _one(_task_detail(task))


@frappe.whitelist(methods=["POST"])
@agent_only
def resume_task(task: str, extend_due_date: bool = True) -> dict:
    frappe.has_permission("Task", "write", str(task), throw=True)
    tasky.resume_task(task, extend_due_date=extend_due_date)
    return _one(_task_detail(task))


@frappe.whitelist(methods=["POST"])
@agent_only
def hand_over_task(task: str, teammate: str, reason: str) -> dict:
    """Pass the task to a teammate. The task may leave the user's view, so only its
    name and the new assignee come back."""
    frappe.has_permission("Task", "read", str(task), throw=True)
    tasky.hand_over_task(task, teammate, reason)
    return _one({"task": str(task), "handed_to": _person(teammate)})


@frappe.whitelist(methods=["POST"])
@agent_only
def request_help(
    task: str,
    teammate: str,
    task_name: str,
    description: str = "",
    due_date: str | None = None,
) -> dict:
    """Ask a teammate for something the task needs: they get a new task and this one
    waits on it."""
    frappe.has_permission("Task", "read", str(task), throw=True)
    result = tasky.request_help(task, teammate, task_name, description, due_date)
    return _one({"task": _task_detail(task), "help_task": result["help_task"]["name"]})


@frappe.whitelist(methods=["POST"])
@agent_only
def review_task(task: str, approve: bool, note: str = "") -> dict:
    """Sign off a task waiting for review, or send it back with what still needs doing."""
    frappe.has_permission("Task", "read", str(task), throw=True)
    if approve:
        tasky.approve_task(task)
    else:
        tasky.send_back_task(task, note)
    return _one(_task_detail(task))


@frappe.whitelist(methods=["POST"])
@agent_only
def add_task_comment(task: str, content: str) -> dict:
    """Comment on a task anyone who can see it may comment on."""
    frappe.has_permission("Task", "read", str(task), throw=True)
    item = task_activity.add_comment(task, content)
    return _one(_activity_item(item, 0))


@frappe.whitelist()
@agent_only
def get_teammates(task: str | None = None) -> dict:
    """Active agents to hand over to or ask for help; for a task, its project's team
    unless the user may give it to anyone (its manager or lead)."""
    users = tasky.get_users()
    if task:
        doc = frappe.get_doc("Task", str(task))
        doc.check_permission("read")
        if doc.project and not can_manage_project(doc.project):
            team = set(get_project_team(doc.project))
            users = [u for u in users if u.name in team]
    away = leave_today()
    return _one(
        [
            {
                "user": u.name,
                "full_name": u.full_name or u.name,
                "image": u.user_image,
                "on_leave": u.name in away,
            }
            for u in users
            if u.name != frappe.session.user
        ]
    )


def _task_rows(items: list[dict]) -> list[dict]:
    """My Work's task items in the app's shape, with timers and customers in two queries."""
    names = [i["name"] for i in items]
    timers = (
        {
            row.name: row
            for row in frappe.get_list(
                "Task",
                filters={"name": ("in", names)},
                fields=["name", *TIMER_FIELDS, "custom_actual_hours"],
                limit_page_length=len(names),
            )
        }
        if names
        else {}
    )
    customers = _project_customers({i["project"] for i in items})
    today = str(getdate(nowdate()))
    rows = []
    for item in items:
        row = timers.get(item["name"]) or frappe._dict()
        rows.append(
            _task_shape(
                {
                    **item,
                    "subject": item["title"],
                    "customer": customers.get(item["project"]),
                    "timer_start": row.custom_timer_start,
                    "timer_elapsed": row.custom_timer_elapsed,
                    "actual_hours": row.custom_actual_hours,
                    "estimated_hours": row.custom_estimated_hours,
                },
                today,
            )
        )
    return rows


def _task_detail(task: str) -> dict:
    """tasky.get_task_detail (which checks read permission) in the app's shape, with
    the description and the task's activity."""
    detail = frappe._dict(tasky.get_task_detail(task))
    today = getdate(nowdate())
    deadline = getdate(detail.exp_end_date) if detail.exp_end_date else None
    project = (
        frappe.db.get_value(
            "Project", detail.project, ["project_name", "customer"], as_dict=True
        )
        if detail.project
        else None
    ) or frappe._dict()
    on_hold = detail.status == ON_HOLD
    row = _task_shape(
        {
            **detail,
            "project_name": project.project_name,
            "customer": project.customer,
            "deadline": str(deadline) if deadline else None,
            "is_overdue": is_task_overdue(detail, deadline, today),
            "hold_days": (
                (today - getdate(detail.hold_since)).days
                if on_hold and detail.hold_since
                else None
            ),
            "waiting_on": detail.depends_on_subject if detail.blocked else None,
            "risks": [],
            "can_approve": detail.status == PENDING_REVIEW
            and can_coordinate_project(detail.project),
            "timer_start": detail.custom_timer_start,
            "timer_elapsed": detail.custom_timer_elapsed,
            "actual_hours": detail.actual_hours,
            "estimated_hours": detail.estimated_hours,
        },
        str(today),
    )
    activity = task_activity.get_activity(task)["items"]
    return {
        **row,
        "description": detail.description or "",
        "activity": [_activity_item(item, i) for i, item in enumerate(activity)],
        "pull_requests": detail.pull_requests or [],
    }


def _task_shape(t: dict, today: str) -> dict:
    """The app's Task, from a My Work item or a task detail merged with timer fields."""
    status = t["status"]
    on_hold = status == ON_HOLD
    level = t.get("escalation_level") or 0
    assigned_by = t.get("assigned_by")
    return {
        "name": t["name"],
        "subject": t["subject"],
        "project": t.get("project"),
        "project_name": t.get("project_name"),
        "customer": t.get("customer"),
        "status": status,
        "group": _task_group(status, t.get("is_overdue"), t.get("deadline"), today),
        "exp_end_date": t.get("deadline"),
        "is_overdue": bool(t.get("is_overdue")),
        "is_key": bool(t.get("is_key")),
        "is_milestone": bool(t.get("is_milestone")),
        "priority": t.get("priority"),
        "assignees": t.get("assignees") or [],
        "assigned_by": (
            {"user": assigned_by, "full_name": t.get("assigned_by_name") or assigned_by}
            if assigned_by
            else None
        ),
        "hold_reason": t.get("hold_reason") if on_hold else None,
        "hold_note": t.get("hold_note") if on_hold else None,
        "hold_days": t.get("hold_days"),
        "escalation": (
            {"level": level, "label": follow_ups.level_labels().get(level)}
            if level
            else None
        ),
        "timer": _timer(status, t),
        "expected_hours": flt(t.get("estimated_hours")) or None,
        "waiting_on": t.get("waiting_on"),
        "risks": t.get("risks") or [],
        "can_approve": bool(t.get("can_approve")),
    }


def _task_group(status: str, is_overdue, deadline: str | None, today: str) -> str:
    if status == ON_HOLD:
        return "on_hold"
    if status == PENDING_REVIEW:
        return "in_review"
    if is_overdue:
        return "overdue"
    if deadline == today:
        return "today"
    return "upcoming"


def _timer(status: str, t: dict) -> dict:
    """Running while Working with a start time; paused while Working without one."""
    running = status == "Working" and bool(t.get("timer_start"))
    state = "running" if running else "paused" if status == "Working" else "idle"
    return {
        "state": state,
        "started_at": str(t["timer_start"]) if running else None,
        "logged_hours": round(flt(t.get("actual_hours")), 2),
    }


def _activity_item(item: dict, index: int) -> dict:
    """A task activity item (helpdesk.task_activity) with the app's kind; the hub's
    own kind and values stay in `type` and `data`, for the app to word."""
    data = {
        k: v
        for k, v in item.items()
        if k not in ("kind", "at", "by", "by_name", "text")
    }
    return {
        "id": item.get("name") or f"{item['kind']}-{index}",
        "at": item["at"],
        "who": item.get("by_name") or item.get("by"),
        "kind": ACTIVITY_KINDS.get(item["kind"], "status"),
        "type": item["kind"],
        "text": item.get("text"),
        "data": data,
    }


def _project_customers(projects: set) -> dict:
    projects = [p for p in projects if p]
    if not projects:
        return {}
    return dict(
        frappe.get_all(
            "Project",
            filters={"name": ("in", projects)},
            fields=["name", "customer"],
            as_list=True,
        )
    )


# --- tickets -------------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_tickets(
    view: str = "mine",
    search: str | None = None,
    cursor: int | str | None = None,
    limit: int | str = 20,
) -> dict:
    """Open and paused tickets the user can see: `mine`, `unassigned`, `team` (their
    HD Teams) or `all-open`, the soonest SLA deadline first."""
    if view not in TICKET_VIEWS:
        frappe.throw(_("Unknown ticket view: {0}").format(view))
    user = frappe.session.user
    filters = {"status_category": ("in", OPEN_TICKET_CATEGORIES)}
    if view == "mine":
        filters["name"] = assigned_to_filter("HD Ticket", user, finished=False)
    elif view == "team":
        filters["agent_group"] = (
            "in",
            [t.team_name for t in get_agents_team()] or [""],
        )
    search = (search or "").strip()
    if search.isdigit():
        names = filters.get("name", ("in", [search]))[1]
        filters["name"] = ("in", [n for n in names if str(n) == search] or [""])
    elif search:
        filters["subject"] = ("like", f"%{search}%")
    rows = _ticket_rows(filters)
    if view == "unassigned":
        rows = [r for r in rows if not r["assignees"]]
    rows.sort(key=lambda r: (r["sla_due"] is None, r["sla_due"] or ""))
    return _paged(rows, cursor, limit)


@frappe.whitelist()
@agent_only
def get_ticket(ticket: str | int) -> dict:
    """One ticket with its conversation: the emails and the agents' internal notes."""
    return _one(_ticket_detail(ticket))


@frappe.whitelist(methods=["POST"])
@agent_only
@rate_limit(limit=REPLY_RATE_LIMIT, seconds=RATE_WINDOW_SECONDS)
def reply_ticket(
    ticket: str | int, message: str, attachments: list[str] | None = None
) -> dict:
    """Reply to the customer, as the agent page does (HD Ticket.reply_via_agent).
    `message` is plain text; `attachments` are File names the user uploaded."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("write")
    files = _own_files(attachments)
    doc.reply_via_agent(_text_to_html(message), to=doc.raised_by, attachments=files)
    return _one(_ticket_detail(ticket))


@frappe.whitelist(methods=["POST"])
@agent_only
@rate_limit(limit=REPLY_RATE_LIMIT, seconds=RATE_WINDOW_SECONDS)
def comment_ticket(ticket: str | int, message: str) -> dict:
    """An internal note on the ticket (HD Ticket.new_comment); customers never see it."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("write")
    doc.new_comment(_text_to_html(message))
    return _one(_ticket_detail(ticket))


@frappe.whitelist(methods=["POST"])
@agent_only
def set_ticket_status(ticket: str | int, status: str) -> dict:
    """Move the ticket to one of the enabled HD Ticket Statuses."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("write")
    if status not in _ticket_statuses():
        frappe.throw(_("Unknown ticket status: {0}").format(status))
    doc.status = status
    doc.save()
    return _one(_ticket_detail(ticket))


@frappe.whitelist(methods=["POST"])
@agent_only
def assign_ticket(ticket: str | int, agent: str) -> dict:
    """Give the ticket to one agent: they are assigned, anyone else is taken off."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("write")
    others = [u for u in _assignees(doc.get("_assign")) if u != agent]
    assign_ticket_to_agent(doc.name, agent)
    if others:
        remove_assignments("HD Ticket", doc.name, others)
    return _one(_ticket_detail(ticket))


def _ticket_rows(filters: dict) -> list[dict]:
    tickets = frappe.get_list(
        "HD Ticket", filters=filters, fields=TICKET_FIELDS, limit_page_length=0
    )
    names = user_full_names(
        {u for t in tickets for u in _assignees(t._assign)} - {None}
    )
    now = now_datetime()
    return [_ticket_row(t, names, now) for t in tickets]


def _ticket_row(t, names: dict, now) -> dict:
    """The SLA due is the first response deadline until the first reply, then the
    resolution deadline; the clock only runs while the ticket is in an Open status."""
    responding = bool(t.response_by and not t.first_responded_on)
    due = _when(t.response_by if responding else t.resolution_by)
    running = t.status_category == "Open"
    assignees = _assignees(t._assign)
    return {
        "name": str(t.name),
        "subject": t.subject,
        "customer": t.customer,
        "contact": t.contact or t.raised_by,
        "raised_by": t.raised_by,
        "priority": t.priority,
        "status": t.status,
        "status_category": t.status_category,
        "sla_due": str(due) if due else None,
        "sla_kind": ("first_response" if responding else "resolution") if due else None,
        "sla_breached": bool(due and running and due < now),
        "sla_due_soon": bool(running and sla_due_soon(due, now)),
        "assigned_to": assignees[0] if assignees else None,
        "assignees": [_person(u, names) for u in assignees],
        "team": t.agent_group,
        "opened_at": str(t.creation),
        # an Open-category status waits on the agent, a Paused one on someone else
        "awaiting_reply": running,
        "escalation_level": t.get("custom_escalation_level") or 0,
    }


def _when(value):
    # get_datetime(None) is now, so an empty deadline must stay None
    return get_datetime(value) if value else None


def _ticket_detail(ticket) -> dict:
    name = str(ticket)
    frappe.has_permission("HD Ticket", "read", name, throw=True)
    rows = _ticket_rows({"name": name})
    if not rows:
        frappe.throw(_("Ticket not found"), frappe.DoesNotExistError)
    conversation = [
        _message(
            c.name,
            "agent" if c.sent_or_received == "Sent" else "customer",
            c.user,
            c.communication_date or c.creation,
            c.content,
            c.attachments,
        )
        for c in get_communications(name)
    ] + [
        _message(c.name, "note", c.user, c.creation, c.content, c.attachments)
        for c in get_comments(name)
    ]
    conversation.sort(key=lambda m: m["at"])
    return {**rows[0], "conversation": conversation, "statuses": _ticket_statuses()}


def _message(name, kind: str, user: dict, at, content, attachments) -> dict:
    return {
        "id": name,
        "kind": kind,
        "author": (user or {}).get("name") or (user or {}).get("email"),
        "author_email": (user or {}).get("email"),
        "at": str(get_datetime(at)),
        "body": task_activity.plain_text(content),
        "body_html": content or "",
        "attachments": [
            {"name": f.name, "file_name": f.file_name, "file_url": f.file_url}
            for f in attachments or []
        ],
    }


def _ticket_statuses() -> list[str]:
    return frappe.get_all(
        "HD Ticket Status", filters={"enabled": 1}, pluck="name", order_by="`order` asc"
    )


def _own_files(files: list[str] | None) -> list[str]:
    """Files the user uploaded themselves: the only ones they may send with a reply."""
    files = [str(f) for f in frappe.parse_json(files or []) if f]
    if not files:
        return []
    own = set(
        frappe.get_all(
            "File",
            filters={"name": ("in", files), "owner": frappe.session.user},
            pluck="name",
        )
    )
    if missing := [f for f in files if f not in own]:
        frappe.throw(
            _("Attach only files you uploaded: {0}").format(", ".join(missing)),
            frappe.PermissionError,
        )
    return files


def _text_to_html(text: str) -> str:
    text = (text or "").strip()
    if not text:
        frappe.throw(_("Write a message first."))
    return escape_html(text).replace("\n", "<br>")


# --- projects and files --------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_projects(
    status: str = "Open", cursor: int | str | None = None, limit: int | str = 20
) -> dict:
    """Projects the user can see (tasky.get_projects), with their role, their own open
    tasks and the files marked for them."""
    projects = [p for p in tasky.get_projects() if not status or p.status == status]
    names = [p.name for p in projects]
    roles = _my_project_roles(names)
    open_tasks = _my_open_tasks_by_project(names)
    for_you = _files_for_me_by_project(names)
    return _paged(
        [
            {
                "name": p.name,
                "project_name": p.project_name or p.name,
                "customer": p.customer,
                "department": p.department,
                "status": p.status,
                "my_role": roles.get(p.name)
                or (
                    _("Project Lead") if p.project_lead == frappe.session.user else None
                ),
                "lead": _person(p.project_lead, {p.project_lead: p.project_lead_name})
                if p.project_lead
                else None,
                "open_tasks": open_tasks.get(p.name, 0),
                "files": p.file_count,
                "for_you": for_you.get(p.name, 0),
                "expected_end_date": str(p.expected_end_date)
                if p.expected_end_date
                else None,
            }
            for p in projects
        ],
        cursor,
        limit,
    )


@frappe.whitelist()
@agent_only
def get_project_files(
    project: str, folder: str | None = None, for_me: bool = False
) -> dict:
    """One folder of a project's files (the top level by default) and its subfolders,
    as the Files page lists them; `for_me` lists the files for the user from every
    folder."""
    data = project_files.list_project_files(project, folder=folder, for_me=for_me)
    current = data["folder"]
    hiding = data["hiding_superseded"]
    return _one(
        {
            "project": project,
            "folder": (
                {
                    "name": current["name"],
                    "folder_name": current["folder_name"],
                    "path": _folder_path(current["path"]),
                }
                if current
                else None
            ),
            "folders": [
                {
                    "name": f["name"],
                    "folder_name": f["folder_name"],
                    "file_count": f["file_count"],
                    "folder_count": f["folder_count"],
                    "for_you": f["is_for_me"] or f["for_me_via_parent"],
                    "status": f["status"],
                }
                for f in data["folders"]
                if not for_me
                and f["parent_folder"] == (folder or None)
                and not (
                    hiding and (f["status"] == SUPERSEDED or f["superseded_via_parent"])
                )
            ],
            "files": [_project_file(f) for f in data["files"]],
            "superseded_hidden": data["superseded_hidden"],
            "can_upload": data["can_upload"],
        }
    )


@frappe.whitelist()
@agent_only
def get_file(project: str, file: str) -> dict:
    """A project file to open: Markdown and text come with their content; anything else
    with its (private, permission-checked) URL to download with the bearer token."""
    # the user may read the project, and the file is attached to it
    project = project_files._check_read(project)
    file_doc = project_files._get_project_file(project, file)
    is_text = (file_doc.file_name or "").lower().endswith(project_files.TEXT_EXTENSIONS)
    text = (
        project_files.get_project_file_text(project, file_doc.name)["content"]
        if is_text
        else None
    )
    return _one(
        {
            "name": file_doc.name,
            "file_name": file_doc.file_name,
            "file_url": file_doc.file_url,
            "size": file_doc.file_size,
            "kind": _extension(file_doc.file_name),
            "text": text,
        }
    )


def _project_file(f: dict) -> dict:
    return {
        "name": f["name"],
        "file_name": f["file_name"],
        "file_url": f["file_url"],
        "folder": _folder_path(f["folder_path"]),
        "folder_id": f["folder"],
        "kind": _extension(f["file_name"]),
        "size": f["file_size"],
        "modified": str(f["creation"]),
        "uploaded_by": f["uploaded_by_name"],
        "for_you": bool(f["is_for_me"] or f["shared_via_folder"]),
        "status": f["status"],
        "status_note": f["status_note"],
        "can_preview": (f["file_name"] or "")
        .lower()
        .endswith(project_files.TEXT_EXTENSIONS),
    }


def _folder_path(path: list[dict]) -> str:
    return "/".join(p["folder_name"] for p in path or [])


def _extension(file_name: str | None) -> str:
    name = (file_name or "").lower()
    return name.rsplit(".", 1)[-1] if "." in name else ""


def _my_project_roles(projects: list[str]) -> dict:
    if not projects:
        return {}
    return dict(
        frappe.get_all(
            "Project User",
            filters={
                "parenttype": "Project",
                "parent": ("in", projects),
                "user": frappe.session.user,
            },
            fields=["parent", "custom_role"],
            as_list=True,
        )
    )


def _my_open_tasks_by_project(projects: list[str]) -> dict:
    if not projects:
        return {}
    task = frappe.qb.DocType("Task")
    return dict(
        frappe.qb.from_(task)
        .select(task.project, Count(task.name))
        .where(
            task.project.isin(projects)
            & task.status.notin(OPEN_TASK_FILTER[1])
            & task.name.isin(assigned_names_query("Task", frappe.session.user))
        )
        .groupby(task.project)
        .run()
    )


def _files_for_me_by_project(projects: list[str]) -> dict:
    """Current files marked for the user, per project (a folder's "For" not counted)."""
    if not projects:
        return {}
    record = frappe.qb.DocType(project_files.PROJECT_FILE)
    row = frappe.qb.DocType(project_files.PROJECT_FILE_USER)
    return dict(
        frappe.qb.from_(row)
        .join(record)
        .on(
            (record.name == row.parent) & (row.parenttype == project_files.PROJECT_FILE)
        )
        .select(record.project, Count(row.name))
        .where(
            (row.user == frappe.session.user)
            & (record.status != SUPERSEDED)
            & record.project.isin(projects)
        )
        .groupby(record.project)
        .run()
    )


# --- notifications -------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_notifications(
    cursor: int | str | None = None,
    limit: int | str = 20,
    unread_only: bool = False,
) -> dict:
    """The user's own notifications (the web's bell), newest first."""
    start, limit = _page_args(cursor, limit)
    filters = {"user_to": frappe.session.user}
    if frappe.utils.sbool(unread_only):
        filters["read"] = 0
    rows = frappe.qb.get_query(
        "HD Notification",
        fields=[
            "name",
            "creation",
            "read",
            "user_from",
            "user_to",
            "notification_type",
            "reference_ticket",
            "reference_comment",
            "reference_doctype",
            "reference_name",
            "link",
            "message",
        ],
        filters=filters,
        order_by="creation desc",
        limit=limit + 1,
        offset=start,
    ).run(as_dict=True)
    items = [
        notification_item(frappe.get_doc({"doctype": "HD Notification", **row}))
        for row in rows[:limit]
    ]
    has_more = len(rows) > limit
    return {
        "v": API_VERSION,
        "data": items,
        "next_cursor": start + limit if has_more else None,
        "has_more": has_more,
        "unread": _unread_count(),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def mark_notifications_read(names: list[str] | str) -> dict:
    """Mark the user's own notifications read: a list of names, or "all"."""
    if names == "all":
        clear()
    else:
        names = [str(n) for n in frappe.parse_json(names) or [] if n]
        if names:
            notice = frappe.qb.DocType("HD Notification")
            (
                frappe.qb.update(notice)
                .set(notice.read, 1)
                .where(
                    (notice.user_to == frappe.session.user)
                    & notice.name.isin(names)
                    & (notice.read == 0)
                )
            ).run()
    return _one({"unread": _unread_count()})


def notification_item(doc) -> dict:
    """An HD Notification as the app lists it and pushes it: the same words chat
    uses (first line the title, the rest the body) and where it opens."""
    text = html.unescape(doc.chat_text() or "").strip()
    title, _sep, body = text.partition("\n")
    doctype = doc.reference_doctype or ("HD Ticket" if doc.reference_ticket else None)
    reference = doc.reference_name or doc.reference_ticket
    return {
        "name": doc.name,
        "site": "hub",
        "type": doc.notification_type,
        "title": title or _(doc.notification_type),
        "body": body.strip(),
        "at": str(doc.creation) if doc.creation else None,
        "read": bool(cint(doc.read)),
        "doctype": doctype,
        "reference": str(reference) if reference else None,
        "route": doc.chat_path(),
        "app_route": app_route(doctype, reference),
        "from": _person(doc.user_from),
    }


def _unread_count() -> int:
    return frappe.db.count(
        "HD Notification", {"user_to": frappe.session.user, "read": 0}
    )


# --- devices -------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@agent_only
@rate_limit(limit=DEVICE_RATE_LIMIT, seconds=RATE_WINDOW_SECONDS)
def register_device(token: str, platform: str, app_version: str | None = None) -> dict:
    """Register (or refresh) this phone's push token for the signed-in user. Call it
    at every launch; a token signed in by someone else before moves to this user."""
    token = (token or "").strip()
    if not token or len(token) > MAX_TOKEN_LENGTH:
        frappe.throw(_("Send the push token from the device."))
    platform = (platform or "").strip().lower()
    if platform not in PLATFORMS:
        frappe.throw(_("Platform must be ios or android."))
    user = frappe.session.user
    existing = frappe.db.get_value(
        DEVICE, {"token": token}, ["name", "user"], as_dict=True
    )
    if existing and existing.user != user:
        # the phone changed hands: its token now belongs to whoever signed in on it
        frappe.delete_doc(DEVICE, existing.name, ignore_permissions=True)
        existing = None
    values = {
        "platform": platform,
        "app_version": (app_version or "").strip()[:140] or None,
        "last_seen": now_datetime(),
    }
    if existing:
        doc = frappe.get_doc(DEVICE, existing.name)
        doc.update(values)
        # the user's own device row, found by its user above
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc(
            {"doctype": DEVICE, "user": user, "token": token, **values}
        ).insert(ignore_permissions=True)
    return _one(
        {
            "name": doc.name,
            "platform": doc.platform,
            "token_type": doc.token_type,
            "app_version": doc.app_version,
            "last_seen": str(doc.last_seen),
        }
    )


@frappe.whitelist(methods=["POST"])
@agent_only
@rate_limit(limit=DEVICE_RATE_LIMIT, seconds=RATE_WINDOW_SECONDS)
def unregister_device(token: str) -> dict:
    """Stop pushes to this phone (sign-out). Only the user's own token is removed."""
    name = frappe.db.get_value(
        DEVICE, {"token": (token or "").strip(), "user": frappe.session.user}
    )
    if name:
        frappe.delete_doc(DEVICE, name, ignore_permissions=True)
    return _one({"removed": bool(name)})


# --- managers ------------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_team() -> dict:
    """Each person's open work and leave today (helpdesk.api.work.get_team_workload,
    for project managers, leads and admins)."""
    workload = get_team_workload()
    away = leave_today()
    users = [p["user"] for p in workload["people"]]
    images = (
        dict(
            frappe.get_all(
                "User",
                filters={"name": ("in", users)},
                fields=["name", "user_image"],
                as_list=True,
            )
        )
        if users
        else {}
    )
    return _one(
        {
            "people": [
                {
                    "user": p["user"],
                    "full_name": p["full_name"],
                    "image": images.get(p["user"]),
                    "on_leave": p["on_leave"],
                    "leave": away.get(p["user"]),
                    "open_tasks": p["open"],
                    "working": p["working"],
                    "in_review": p["review"],
                    "on_hold": p["on_hold"],
                    "overdue": p["overdue"],
                    "due_this_week": p["due_this_week"],
                    "done_this_week": p["done_this_week"],
                    "tickets": p["tickets"],
                    "sla_breached": p["sla_breached"],
                    "working_on": p["working_on"],
                    "next_due": p["next_due"],
                }
                for p in workload["people"]
            ],
            "totals": workload["totals"],
        }
    )


@frappe.whitelist()
@agent_only
def get_team_member(
    user: str, cursor: int | str | None = None, limit: int | str = 20
) -> dict:
    """One person's open tasks, for the people who may see their work (get_my_work)."""
    tasks = _task_rows(
        [i for i in get_my_work(user=user)["items"] if i["kind"] == "task"]
    )
    return _paged(tasks, cursor, limit)


@frappe.whitelist()
@agent_only
def get_escalations(cursor: int | str | None = None, limit: int | str = 20) -> dict:
    """Work escalated to L2 or above (helpdesk.follow_ups), for System and Agent
    Managers, like Overview → Follow-ups."""
    check_admin()
    rows = []
    for f in follow_ups.escalations():
        row = follow_ups._row(f)
        rows.append(
            {
                "id": f"{f.doctype}:{f.name}",
                "kind": "task" if f.doctype == "Task" else "ticket",
                "doctype": f.doctype,
                "ref": str(f.name),
                "title": row["title"],
                "owners": row["owners"],
                "level": row["level"],
                "level_label": row["level_label"],
                "days": row["days"],
                "severity": row["severity"],
                "reason": row["text"],
                "route": row["link"],
                "app_route": app_route(f.doctype, f.name),
            }
        )
    return _paged(rows, cursor, limit)


@frappe.whitelist(methods=["POST"])
@agent_only
def nudge(doctype: str, name: str | int, message: str) -> dict:
    """Ping whoever owns a task or ticket (the bell, plus chat or email), and note it on
    the item. Admins may nudge anything; a project's manager, lead or coordinator its
    tasks."""
    if doctype not in NUDGE_DOCTYPES:
        frappe.throw(_("Only tasks and tickets can be nudged."))
    doc = frappe.get_doc(doctype, str(name))
    doc.check_permission("read")
    if not (
        is_tasky_admin() or (doctype == "Task" and can_coordinate_project(doc.project))
    ):
        frappe.throw(
            _("Only managers and the project's lead or coordinator can nudge."),
            frappe.PermissionError,
        )
    message = (message or "").strip()
    if not message:
        frappe.throw(_("Write what you need from them."))
    if len(message) > MAX_NUDGE_LENGTH:
        frappe.throw(_("Keep it under {0} characters.").format(MAX_NUDGE_LENGTH))
    owners = _assignees(frappe.db.get_value(doctype, doc.name, "_assign"))
    if not owners:
        frappe.throw(_("Nobody is assigned to it yet. Reassign it instead."))
    me = frappe.session.user
    title = doc.get("subject")
    notify_users(
        owners,
        doctype,
        doc.name,
        _("{0} nudged you on {1}: {2}").format(get_fullname(me), title, message),
        user_from=me,
        once=False,
    )
    doc.add_comment(
        "Info",
        escape_html(_("Nudged by {0}: {1}").format(get_fullname(me), message)),
    )
    return _one({"notified": [_person(u) for u in owners]})


@frappe.whitelist(methods=["POST"])
@agent_only
def reassign(doctype: str, name: str | int, to: str, reason: str = "") -> dict:
    """Give an escalated task to someone else (tasky.hand_over_task, with the reason)
    or a ticket to another agent (assign_ticket)."""
    if doctype == "Task":
        return hand_over_task(str(name), to, reason)
    if doctype == "HD Ticket":
        return assign_ticket(name, to)
    frappe.throw(_("Only tasks and tickets can be reassigned."))


@frappe.whitelist()
@agent_only
def get_approvals() -> dict:
    """Tasks waiting for the user's review (Home's Approvals), for the managers, leads
    and coordinators of their projects."""
    user = frappe.session.user
    if not _review_projects(user):
        frappe.throw(
            _("Only a project's manager, lead or coordinator reviews its tasks."),
            frappe.PermissionError,
        )
    items = home._approvals(user)
    names = user_full_names({a for i in items for a in i["assignees"]})
    return _one(
        [
            {
                "id": i["name"],
                "kind": "review",
                "ref": i["name"],
                "title": i["title"],
                "who": ", ".join(names.get(a, a) for a in i["assignees"]),
                "detail": i["project_name"],
                "project": i["project"],
                "due": i["deadline"],
                "is_overdue": i["is_overdue"],
            }
            for i in items
        ]
    )


@frappe.whitelist()
@agent_only
def get_projects_health() -> dict:
    """The open projects the user runs (helpdesk.api.work.get_project_portfolio):
    progress, open and overdue work and the next milestone."""
    portfolio = get_project_portfolio("Open")
    return _one(
        [
            {
                "name": c["name"],
                "project_name": c["project_name"],
                "customer": c["customer"],
                "lead": _person(c["lead"], {c["lead"]: c.get("lead_name")})
                if c["lead"]
                else None,
                "progress": c["progress"],
                "counts": c["counts"],
                "overdue": c["counts"]["overdue"],
                "expected_end_date": c["expected_end_date"],
                "next_milestone": (
                    {
                        "title": c["next_milestone"]["subject"],
                        "due": c["next_milestone"]["due"],
                        "is_overdue": c["next_milestone"]["is_overdue"],
                    }
                    if c["next_milestone"]
                    else None
                ),
            }
            for c in portfolio["projects"]
        ]
    )


@frappe.whitelist()
@agent_only
def get_sla_summary() -> dict:
    """Open tickets against their SLA (Home's company tickets), for the people who see
    the overview."""
    if not can_see_overview():
        frappe.throw(
            _("Only project managers, leads and admins see the ticket summary."),
            frappe.PermissionError,
        )
    tickets = home._open_tickets()
    summary = home._ticket_summary(tickets)
    now = now_datetime()
    unassigned = [t for t in tickets if not _assignees(t._assign)]
    oldest = min(unassigned, key=lambda t: cint(t.name), default=None)
    return _one(
        {
            "open": summary["open"],
            "new_today": summary["new_today"],
            "breached": summary["sla_breached"],
            "first_reply_overdue": summary["first_reply_overdue"],
            "breaching_soon": sum(
                1
                for t in tickets
                if t.status_category == "Open"
                and sla_due_soon(_when(t.resolution_by), now)
            ),
            "unassigned": summary["unassigned"],
            "waiting_on_customer": summary["waiting_on_customer"],
            "oldest_unassigned": (
                _ticket_rows({"name": oldest.name})[0] if oldest else None
            ),
        }
    )


@frappe.whitelist()
@agent_only
def get_scoreboard(period: str = "week", department: str | None = None) -> dict:
    """The Scoreboard (helpdesk.api.team_dashboard), which every agent sees: the
    champion, the user's own line, the leaders and the departments."""
    board = get_team_dashboard(period, department)
    user = frappe.session.user
    people = board["people"]
    mine = next((p for p in people if p["user"] == user), None)
    start, end = board["period"]["start"], board["period"]["end"]
    return _one(
        {
            "period": period,
            "period_label": td.period_label(period, start, end),
            "range": {"start": start, "end": end},
            "champion": board["champion"],
            "me": (
                {**_score_line(mine), "of": len(people), "breakdown": mine["breakdown"]}
                if mine
                else None
            ),
            "leaders": [_score_line(p) for p in people[:10]],
            "departments": [
                {
                    "department": d["department"],
                    "people": d["people"],
                    "done": d["tasks"],
                    "on_time_pct": d["on_time_pct"],
                    "overdue": d["overdue"],
                    "hours": d["hours"],
                    "champion": (d["champion"] or {}).get("name"),
                }
                for d in board["departments"]
            ],
        }
    )


def _score_line(p: dict) -> dict:
    return {
        "user": p["user"],
        "full_name": p["name"],
        "image": p["image"],
        "department": p["department"],
        "rank": p["rank"],
        "score": p["score"],
        "tasks_done": p["tasks"],
        "key_tasks": p["key"],
        "on_time_pct": p["on_time_pct"],
        "hours": p["hours"],
        "overdue": p["overdue"],
    }
