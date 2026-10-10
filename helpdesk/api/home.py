"""Home: what to do now and whether anything is on fire.

Everyone gets "your day": all of their own open tasks in the order to tackle
them (close first, in progress, waiting, coming up, no due date), the tasks they
gave out that are late or in review, their projects, tickets waiting for their
reply, tasks waiting for their review and files shared with them lately, plus an
action plan for the day (helpdesk.home_plan) fetched as its own request. People
who can see the overview (project managers, project leads, admins) also get the company pulse, what needs attention grouped by reason,
projects ending soon and team load; admins also get the health of the systems
the hub depends on. The Overview page does the analysis. See docs/home.md.

Lists go through `frappe.get_list`, so nobody sees records they couldn't open.
"""

from collections import Counter

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, nowdate

from helpdesk import home_plan
from helpdesk.api.content_board import user_full_names
from helpdesk.api.work import (
    ON_HOLD,
    OPEN_TASK_FILTER,
    PENDING_REVIEW,
    TASK_FIELDS,
    WAITING_ON_TASK,
    _assignees,
    _project_names,
    _sort_key,
    _task_item,
    _ticket_item,
    can_see_overview,
    get_my_work,
    get_overview,
    get_project_portfolio,
)
from helpdesk.customer_health import (
    AT_RISK,
    WATCH,
    all_health,
    brief,
    readable,
    sort_key,
)
from helpdesk.follow_ups import summary_for
from helpdesk.helpdesk.doctype.hd_project_folder.hd_project_folder import FolderTree
from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import LOW_RATING_STARS
from helpdesk.tasky.permissions import (
    get_coordinated_projects,
    get_led_projects,
    get_managed_projects,
    is_tasky_admin,
)
from helpdesk.utils import agent_only
from helpdesk.work_calendar import leave_today, next_holiday

LIST_LIMIT = 8
CUSTOMER_LIMIT = 6
PEOPLE_LIMIT = 10
OPEN_TICKET_CATEGORIES = ("in", ["Open", "Paused"])
OPEN_CHAT_STATUSES = ("in", ["Open", "Pending"])
RATING_DAYS = 30
DAY_LIMIT = 6
GROUP_LIMIT = 5
# replied this long ago with no answer: the ticket needs a nudge or closing
WAITING_ON_CUSTOMER_DAYS = 3
FILES_DAYS = 7
ENDING_DAYS = 14
ENDING_LIMIT = 6
HEALTH_LIMIT = 5
APPROVAL_LIMIT = 50
FILE_LIMIT = 50
GIVEN_OUT_LIMIT = 50
PROJECT_LIMIT = 6
COMING_UP_DAYS = 7
# held tasks don't run late and reviewed ones wait on the reviewer
WAITING_STATUSES = (ON_HOLD, PENDING_REVIEW)
# the day's task sections, most urgent first
DAY_TASK_SECTIONS = ("close_first", "in_progress", "waiting", "coming_up", "no_date")
PROJECT_FILE = "HD Project File"
OPEN_TICKET_FIELDS = [
    "name",
    "subject",
    "customer",
    "status",
    "status_category",
    "priority",
    "response_by",
    "first_responded_on",
    "resolution_by",
    "last_agent_response",
    "modified",
    "_assign",
]


@frappe.whitelist()
@agent_only
def get_home() -> dict:
    mine = get_my_work()
    company = can_see_overview()
    portfolio = get_project_portfolio("Open") if company else None
    day = build_day(mine["items"], portfolio["projects"] if portfolio else None)
    return {
        "mine": {"counts": mine["counts"], "items": mine["items"][:LIST_LIMIT]},
        "day": day,
        "follow_ups": summary_for(frappe.session.user),
        "calendar": _calendar(company),
        "company": _company(portfolio) if company else None,
        "systems": _systems() if is_tasky_admin() else None,
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def get_action_plan(refresh: bool = False) -> dict:
    """The user's numbered plan for today: written by the AI from their own work,
    or built from the same priority order when the AI is off or fails."""
    user = frappe.session.user
    if refresh:
        home_plan.check_refresh_allowed(user)
    # a refresh reads the work afresh; a page load reuses the day get_home just built
    day = (
        None
        if refresh
        else frappe.cache.get_value(home_plan.day_cache_key(user), expires=True)
    )
    if day is None:
        day = _day(get_my_work()["items"])
    return home_plan.action_plan(user, day, refresh=bool(refresh))


def build_day(items: list[dict], cards: list[dict] | None = None) -> dict:
    """The user's day (see _day), kept for the action plan request that follows
    (get_action_plan); the web Home and the mobile app both start here."""
    day = _day(items, cards)
    frappe.cache.set_value(
        home_plan.day_cache_key(frappe.session.user),
        day,
        expires_in_sec=home_plan.DAY_CACHE_SECONDS,
    )
    return day


def _calendar(company: bool) -> dict:
    """The next holiday, and for people who run work who is on leave today."""
    holiday = next_holiday()
    away = leave_today() if company else {}
    names = user_full_names(set(away))
    return {
        "next_holiday": {**holiday, "date": str(holiday["date"])} if holiday else None,
        "on_leave_today": sorted(
            (
                {"user": user, "full_name": names.get(user) or user, **leave}
                for user, leave in away.items()
            ),
            key=lambda row: row["full_name"],
        )
        if company
        else None,
    }


# --- your day ---


def _day(items: list[dict], cards: list[dict] | None = None) -> dict:
    """The user's own open work in the order to tackle it, each task in one section.

    `cards` are the portfolio's project cards (for people who run projects), which
    add each project's totals next to the user's own numbers.
    """
    user = frappe.session.user
    today = getdate(nowdate())
    # tickets in an "Open" category status wait on the agent, "Paused" ones on someone else
    reply_statuses = set(
        frappe.get_all("HD Ticket Status", filters={"category": "Open"}, pluck="name")
    )
    tasks = [i for i in items if i["kind"] == "task"]
    _add_timers(tasks)
    groups = _task_groups(tasks, today)
    replies = [
        i for i in items if i["kind"] == "ticket" and i["status"] in reply_statuses
    ]
    approvals = _approvals(user)
    projects = _my_projects(user, tasks, cards)
    return {
        "summary": _summary(items, tasks, str(today)),
        **{key: _section(group) for key, group in groups.items()},
        "given_out": _section(_given_out(user, {a["name"] for a in approvals})),
        "projects": {"count": len(projects), "items": projects[:PROJECT_LIMIT]},
        "replies": _section(replies),
        "approvals": _section(approvals),
        "files": _section(_files_for(user)),
    }


def _section(items: list) -> dict:
    return {"count": len(items), "items": items[:DAY_LIMIT]}


def _summary(items: list[dict], tasks: list[dict], today: str) -> dict:
    """The header's facts: all of the user's open work, not only what is due."""
    return {
        "open": len(items),
        "overdue": sum(i["is_overdue"] for i in items),
        "due_today": sum(
            1
            for t in tasks
            if t["deadline"] == today
            and not t["is_overdue"]
            and t["status"] not in WAITING_STATUSES
        ),
        "on_hold": sum(t["status"] == ON_HOLD for t in tasks),
        "in_review": sum(t["status"] == PENDING_REVIEW for t in tasks),
        "in_progress": sum(t["status"] == "Working" for t in tasks),
        "projects": len({t["project"] for t in tasks if t["project"]}),
    }


def _task_groups(tasks: list[dict], today) -> dict[str, list[dict]]:
    """Each open task under the first section it fits, most urgent section first.

    Held and in-review tasks wait on someone else, so they are never due. Tasks
    due after the coming week are only counted, in the summary.
    """
    soon = str(add_days(today, COMING_UP_DAYS))
    today = str(today)
    groups = {key: [] for key in DAY_TASK_SECTIONS}
    for task in tasks:
        if task["status"] in WAITING_STATUSES:
            key = "waiting"
        elif (
            task["is_overdue"]
            or task["deadline"] == today
            or (task["is_key"] and task["status"] == "Working")
        ):
            key = "close_first"
        elif task["status"] == "Working":
            key = "in_progress"
        elif not task["deadline"]:
            key = "no_date"
        elif task["deadline"] <= soon:
            key = "coming_up"
        else:
            continue
        groups[key].append(task)
    # overdue, then due today, then key work in progress
    groups["close_first"].sort(
        key=lambda t: (
            not t["is_overdue"],
            t["deadline"] != today,
            t["deadline"] or "9999-12-31",
        )
    )
    groups["coming_up"].sort(key=lambda t: t["deadline"])
    # the longest wait first: it most needs a nudge
    groups["waiting"].sort(key=lambda t: -(t.get("hold_days") or 0))
    return groups


def _add_timers(tasks: list[dict]) -> None:
    """Say whether each task in progress has its timer running or paused, in one query."""
    working = [t["name"] for t in tasks if t["status"] == "Working"]
    if not working:
        return
    running = set(
        frappe.get_all(
            "Task",
            filters={"name": ("in", working), "custom_timer_start": ("is", "set")},
            pluck="name",
        )
    )
    for task in tasks:
        if task["status"] == "Working":
            task["timer"] = "running" if task["name"] in running else "paused"


def _given_out(user: str, skip: set[str]) -> list[dict]:
    """Tasks the user gave someone else that are overdue or waiting for review,
    overdue first. `skip` holds tasks already in the user's approvals."""
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
            & (todo.assigned_by == user)
            & (todo.allocated_to != user)
            # due today is overdue only past its estimate; is_task_overdue decides below
            & (
                (task.status == PENDING_REVIEW)
                | (task.exp_end_date <= getdate(nowdate()))
            )
            & task.status.notin(["Completed", "Cancelled", "Template", ON_HOLD])
        )
        .limit(GIVEN_OUT_LIMIT)
        .run(pluck=True)
    )
    names = [n for n in names if n not in skip]
    if not names:
        return []
    # through get_list, so the department walls still apply
    tasks = frappe.get_list(
        "Task",
        filters={"name": ("in", names)},
        fields=TASK_FIELDS,
        limit_page_length=GIVEN_OUT_LIMIT,
    )
    project_names = _project_names(tasks)
    items = [
        i
        for i in (_task_item(t, project_names) for t in tasks)
        if user not in i["assignees"]
        and (i["is_overdue"] or i["status"] == PENDING_REVIEW)
    ]
    full_names = user_full_names({a for i in items for a in i["assignees"]})
    for item in items:
        item["assignee_names"] = [full_names.get(a, a) for a in item["assignees"]]
    items.sort(key=_sort_key)
    return items


def _my_projects(user: str, tasks: list[dict], cards: list[dict] | None) -> list[dict]:
    """Open projects the user is on, with their own open and overdue tasks and the
    next milestone they can see. People who run a project also get its totals
    (from the portfolio `cards`); everyone else sees only their own numbers."""
    member_of = frappe.get_all(
        "Project User",
        filters={"parenttype": "Project", "user": user},
        pluck="parent",
    )
    ids = (
        set(member_of)
        | set(get_led_projects(user))
        | {t["project"] for t in tasks if t["project"]}
    )
    if not ids:
        return []
    projects = frappe.get_list(
        "Project",
        filters={"name": ("in", list(ids)), "status": "Open"},
        fields=["name", "project_name", "customer"],
        limit_page_length=0,
    )
    milestones = _next_milestones([p.name for p in projects])
    team = {c["name"]: c["counts"] for c in cards or []}
    rows = []
    for project in projects:
        mine = [t for t in tasks if t["project"] == project.name]
        counts = team.get(project.name)
        rows.append(
            {
                "name": project.name,
                "project_name": project.project_name or project.name,
                "customer": project.customer,
                "open": len(mine),
                "overdue": sum(t["is_overdue"] for t in mine),
                "team_open": counts["open"] if counts else None,
                "team_overdue": counts["overdue"] if counts else None,
                "next_milestone": milestones.get(project.name),
            }
        )
    rows.sort(key=lambda r: (-r["overdue"], -r["open"], r["project_name"].lower()))
    return rows


def _next_milestones(projects: list[str]) -> dict[str, dict]:
    """Each project's earliest open milestone the user may see, dated ones first."""
    if not projects:
        return {}
    rows = frappe.get_list(
        "Task",
        filters={
            "project": ("in", projects),
            "is_milestone": 1,
            "status": OPEN_TASK_FILTER,
        },
        fields=["name", "subject", "project", "exp_end_date"],
        order_by="exp_end_date asc",
        limit_page_length=0,
    )
    milestones = {}
    # undated milestones sort first in SQL; a dated one wins over them
    for row in sorted(rows, key=lambda r: r.exp_end_date is None):
        milestones.setdefault(
            row.project,
            {
                "name": row.name,
                "subject": row.subject,
                "due": str(row.exp_end_date) if row.exp_end_date else None,
            },
        )
    return milestones


def _approvals(user: str) -> list[dict]:
    """Tasks waiting for review in the projects the user manages, leads or coordinates."""
    projects = list(
        set(get_managed_projects(user))
        | set(get_led_projects(user))
        | set(get_coordinated_projects(user))
    )
    if not projects:
        return []
    tasks = frappe.get_list(
        "Task",
        filters={"status": PENDING_REVIEW, "project": ("in", projects)},
        fields=TASK_FIELDS,
        order_by="exp_end_date asc",
        limit_page_length=APPROVAL_LIMIT,
    )
    names = _project_names(tasks)
    return [{**_task_item(t, names), "can_approve": True} for t in tasks]


def _files_for(user: str) -> list[dict]:
    """Current (not superseded) files marked for the user in the last FILES_DAYS by
    someone else, from projects they can read."""
    record = frappe.qb.DocType(PROJECT_FILE)
    row = frappe.qb.DocType("HD Project File User")
    file = frappe.qb.DocType("File")
    uploader = frappe.qb.DocType("User")
    rows = (
        frappe.qb.from_(row)
        .join(record)
        .on((record.name == row.parent) & (row.parenttype == PROJECT_FILE))
        .join(file)
        .on(file.name == record.file)
        .left_join(uploader)
        .on(uploader.name == file.owner)
        .select(
            file.name,
            file.file_name,
            file.creation,
            file.owner,
            record.project,
            record.folder,
            uploader.full_name.as_("uploaded_by_name"),
        )
        .where(
            (row.user == user)
            & (record.status != "Superseded")
            & (file.owner != user)
            & (file.creation >= add_days(now_datetime(), -FILES_DAYS))
        )
        .orderby(file.creation, order=frappe.qb.desc)
        .limit(FILE_LIMIT)
        .run(as_dict=True)
    )
    projects = list({r.project for r in rows if r.project})
    readable = (
        dict(
            frappe.get_list(
                "Project",
                filters={"name": ("in", projects)},
                fields=["name", "project_name"],
                as_list=True,
            )
        )
        if projects
        else {}
    )
    # a file keeps its own status inside a superseded folder; "For me" hides it too
    trees = {p: FolderTree(p) for p in readable}
    return [
        {
            "name": r.name,
            "file_name": r.file_name,
            "project": r.project,
            "project_name": readable[r.project] or r.project,
            "uploaded_by_name": r.uploaded_by_name or r.owner,
            "creation": str(r.creation),
        }
        for r in rows
        if r.project in readable and not trees[r.project].is_superseded(r.folder)
    ]


# --- company ---


def _company(portfolio: dict) -> dict:
    overview = get_overview()
    projects = sorted(portfolio["projects"], key=_project_order)
    open_tickets = _open_tickets()
    return {
        "tickets": _ticket_summary(open_tickets),
        "work": overview["counts"],
        "attention": overview["attention"][:LIST_LIMIT],
        "attention_groups": _attention_groups(overview["buckets"], open_tickets),
        "projects": [_project(card) for card in projects[:LIST_LIMIT]],
        "project_count": len(projects),
        "ending_soon": _ending_soon(portfolio["projects"]),
        "customer_health": _customer_health(),
        "people": [_person(p) for p in portfolio["people"] if not p["is_free"]][
            :PEOPLE_LIMIT
        ],
        "people_busy": portfolio["totals"]["people_active"],
        "people_free": portfolio["totals"]["people_free"],
        "free_people": [p["full_name"] for p in portfolio["people"] if p["is_free"]][
            :PEOPLE_LIMIT
        ],
    }


def _open_tickets() -> list:
    return frappe.get_list(
        "HD Ticket",
        filters={"status_category": OPEN_TICKET_CATEGORIES},
        fields=OPEN_TICKET_FIELDS,
        limit_page_length=0,
    )


def _ticket_summary(open_tickets: list) -> dict:
    now = now_datetime()
    by_customer = Counter(t.customer or "" for t in open_tickets)
    return {
        "open": len(open_tickets),
        "new_today": len(
            frappe.get_list(
                "HD Ticket",
                filters={"creation": (">=", getdate(nowdate()))},
                pluck="name",
                limit_page_length=0,
            )
        ),
        "unassigned": sum(1 for t in open_tickets if not _assignees(t._assign)),
        # paused tickets (waiting on the customer or a task) don't run the SLA clock
        "sla_breached": sum(
            1
            for t in open_tickets
            if t.status_category == "Open"
            and t.resolution_by
            and get_datetime(t.resolution_by) < now
        ),
        "first_reply_overdue": sum(
            1
            for t in open_tickets
            if t.status_category == "Open"
            and not t.first_responded_on
            and t.response_by
            and get_datetime(t.response_by) < now
        ),
        "waiting_on_customer": len(_waiting_on_customer(open_tickets)),
        "rating": _rating(),
        "by_customer": [
            {"customer": customer or None, "open": count}
            for customer, count in by_customer.most_common(CUSTOMER_LIMIT)
        ],
    }


def _waiting_on_customer(open_tickets: list) -> list:
    """Tickets we answered over WAITING_ON_CUSTOMER_DAYS ago that the customer hasn't, oldest first."""
    cutoff = add_days(now_datetime(), -WAITING_ON_CUSTOMER_DAYS)
    waiting = [
        t
        for t in open_tickets
        if t.status_category == "Paused"
        and t.status != WAITING_ON_TASK
        and get_datetime(t.last_agent_response or t.modified) < cutoff
    ]
    waiting.sort(key=lambda t: get_datetime(t.last_agent_response or t.modified))
    return waiting


def _attention_groups(buckets: dict, open_tickets: list) -> list[dict]:
    """What needs a manager now, by reason; each item only under its first reason, empty reasons left out."""
    now = now_datetime()
    unassigned = sorted(
        (_ticket_item(t) for t in open_tickets if not _assignees(t._assign)),
        key=_sort_key,
    )
    waiting = []
    for ticket in _waiting_on_customer(open_tickets):
        since = get_datetime(ticket.last_agent_response or ticket.modified)
        waiting.append({**_ticket_item(ticket), "waiting_days": (now - since).days})

    seen = set()
    groups = []
    for key, items in (
        ("overdue", buckets["overdue"]),
        ("at_risk", buckets["at_risk"]),
        ("unassigned_tickets", unassigned),
        ("waiting_on_customer", waiting),
    ):
        fresh = [i for i in items if (i["kind"], i["name"]) not in seen]
        seen.update((i["kind"], i["name"]) for i in fresh)
        if fresh:
            groups.append(
                {"key": key, "count": len(fresh), "items": fresh[:GROUP_LIMIT]}
            )
    _add_customers([i for g in groups for i in g["items"]])
    return groups


def _add_customers(items: list[dict]) -> None:
    """Fill in the customer of task items from their project, in one query."""
    projects = list({i["project"] for i in items if i.get("project")})
    customers = (
        dict(
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
    for item in items:
        item["customer"] = item.get("customer") or customers.get(item.get("project"))


def _ending_soon(cards: list[dict]) -> list[dict]:
    """Open projects due to end within ENDING_DAYS, or already past their end date, soonest first."""
    today = getdate(nowdate())
    horizon = str(add_days(today, ENDING_DAYS))
    ending = sorted(
        (
            c
            for c in cards
            if c["expected_end_date"] and c["expected_end_date"] <= horizon
        ),
        key=lambda c: c["expected_end_date"],
    )
    return [
        {
            **_project(card),
            "days_left": (getdate(card["expected_end_date"]) - today).days,
        }
        for card in ending[:ENDING_LIMIT]
    ]


def _customer_health() -> dict:
    """The customers at risk or to watch that the user may read, worst first, at most HEALTH_LIMIT."""
    healths = all_health()
    flagged = [c for c, h in healths.items() if h["status"] in (AT_RISK, WATCH)]
    names = sorted(readable(flagged), key=lambda c: (sort_key(healths[c]), c))
    return {
        "count": len(names),
        "at_risk": sum(1 for c in names if healths[c]["status"] == AT_RISK),
        "items": [{"customer": c, **brief(healths[c])} for c in names[:HEALTH_LIMIT]],
    }


def _rating() -> dict:
    """Customers' ratings on tickets updated in the last RATING_DAYS, out of 5."""
    ratings = frappe.get_list(
        "HD Ticket",
        filters={
            "feedback_rating": (">", 0),
            "modified": (">=", add_days(now_datetime(), -RATING_DAYS)),
        },
        pluck="feedback_rating",
        limit_page_length=0,
    )
    return {
        "average": round(sum(ratings) / len(ratings) * 5, 1) if ratings else None,
        "count": len(ratings),
        # ratings are stored as 0-1
        "low": sum(1 for r in ratings if r * 5 <= LOW_RATING_STARS),
    }


def _project_order(card: dict):
    # projects in trouble first, then the ones that end soonest
    return (
        -card["counts"]["overdue"],
        card["expected_end_date"] or "9999-12-31",
        card["project_name"].lower(),
    )


def _project(card: dict) -> dict:
    return {
        "name": card["name"],
        "project_name": card["project_name"],
        "customer": card["customer"],
        "lead": card["lead"],
        "lead_name": card["lead_name"],
        "progress": card["progress"],
        "open": card["counts"]["open"],
        "overdue": card["counts"]["overdue"],
        "expected_end_date": card["expected_end_date"],
        "next_milestone": card["next_milestone"],
    }


def _person(person: dict) -> dict:
    return {
        "user": person["user"],
        "full_name": person["full_name"],
        "open": person["open"],
        "working": person["working"],
        "projects": [p["project_name"] for p in person["projects"][:3]],
    }


def _systems() -> dict:
    """What the hub depends on: customer ERPs, mailboxes, Teams, TBO Chat and the AI."""
    today = getdate(nowdate())
    return {
        "connections": frappe.get_all(
            "HDS Support Connection",
            fields=[
                "name",
                "customer_name",
                "site_url",
                "connection_status",
                "last_error",
                "last_health_check",
            ],
            order_by="customer_name asc",
        ),
        "mailboxes": frappe.get_all(
            "Email Account",
            filters={"email_server": ("is", "set")},
            fields=["name", "email_id", "enable_incoming", "no_failed"],
            order_by="email_id asc",
        ),
        "teams": {
            "enabled": bool(frappe.db.get_single_value("HD Chat Settings", "enabled")),
            "platform": frappe.db.get_single_value("HD Chat Settings", "platform"),
        },
        "chat": {
            "enabled": bool(
                frappe.db.get_single_value("HD Chatwoot Settings", "enabled")
            ),
            "open": frappe.db.count(
                "HD Chat Conversation", {"status": OPEN_CHAT_STATUSES}
            ),
        },
        "ai": {
            "calls_today": frappe.db.count(
                "HDS AI Usage Log", {"creation": (">=", today)}
            ),
            "triage_failed": frappe.db.count(
                "HD Ticket",
                {
                    "status_category": OPEN_TICKET_CATEGORIES,
                    "custom_triage_status": "Failed",
                },
            ),
        },
    }
