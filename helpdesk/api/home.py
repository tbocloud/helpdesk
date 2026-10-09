"""Home: what to do now and whether anything is on fire.

Everyone gets "your day": their own tasks due today, overdue or at risk, tickets
waiting for their reply, tasks waiting for their review and files shared with
them lately. People who can see the overview (project managers, project leads,
admins) also get the company pulse, what needs attention grouped by reason,
projects ending soon and team load; admins also get the health of the systems
the hub depends on. The Overview page does the analysis. See docs/home.md.

Lists go through `frappe.get_list`, so nobody sees records they couldn't open.
"""

from collections import Counter

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, nowdate

from helpdesk.api.work import (
    ON_HOLD,
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
from helpdesk.helpdesk.doctype.hd_project_folder.hd_project_folder import FolderTree
from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import LOW_RATING_STARS
from helpdesk.tasky.permissions import (
    get_led_projects,
    get_managed_projects,
    is_tasky_admin,
)
from helpdesk.utils import agent_only

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
    return {
        "mine": {"counts": mine["counts"], "items": mine["items"][:LIST_LIMIT]},
        "day": _day(mine["items"]),
        "company": _company() if can_see_overview() else None,
        "systems": _systems() if is_tasky_admin() else None,
    }


# --- your day ---


def _day(items: list[dict]) -> dict:
    user = frappe.session.user
    today = str(getdate(nowdate()))
    # tickets in an "Open" category status wait on the agent, "Paused" ones on someone else
    reply_statuses = set(
        frappe.get_all("HD Ticket Status", filters={"category": "Open"}, pluck="name")
    )
    tasks = [i for i in items if i["kind"] == "task" and _due_for_me(i, today)]
    replies = [
        i for i in items if i["kind"] == "ticket" and i["status"] in reply_statuses
    ]
    return {
        "tasks": _section(tasks),
        "replies": _section(replies),
        "approvals": _section(_approvals(user)),
        "files": _section(_files_for(user)),
    }


def _section(items: list) -> dict:
    return {"count": len(items), "items": items[:DAY_LIMIT]}


def _due_for_me(item: dict, today: str) -> bool:
    # held tasks don't run late and reviewed ones are waiting on the reviewer
    if item["status"] in (ON_HOLD, PENDING_REVIEW):
        return False
    return bool(item["is_overdue"] or item["deadline"] == today or item["risks"])


def _approvals(user: str) -> list[dict]:
    """Tasks waiting for review in the projects the user manages or leads."""
    projects = list(set(get_managed_projects(user)) | set(get_led_projects(user)))
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


def _company() -> dict:
    overview = get_overview()
    portfolio = get_project_portfolio("Open")
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
