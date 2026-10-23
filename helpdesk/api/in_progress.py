"""In progress: every started task and every content post in production, in one view.

Lanes by project (the default), person or department. Tasks come through
`frappe.get_list`, so the #94 rule decides whose tasks each viewer gets (the people
who run a project see its tasks, everyone else only their own), with the department
walls and the content team rule on top. Posts come through `frappe.get_list` on HD
Content Post, so only the content team sees them; outside the content leads, only
the posts the viewer is on. See docs/workspace-pages.md "In progress".
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime, sbool

from helpdesk.api.content_board import role_tasks, task_for_role, user_full_names
from helpdesk.api.work import (
    IN_PROGRESS_STATUSES,
    ON_HOLD,
    PENDING_REVIEW,
    TASK_FIELDS,
    WORKING,
    _assignees,
    _open_dependencies,
    _task_item,
    can_see_overview,
    scoped_task_filters,
    status_since,
)
from helpdesk.content_team import in_content_team
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    DONE_TASK_STATUSES,
    NEXT_PERSON,
    READY_STATUSES,
    REMINDER_WINDOW_HOURS,
    TASK_ROLES,
    _is_content_lead,
    role_teams_of,
)
from helpdesk.tasky.api import hold_by_names
from helpdesk.tasky.permissions import (
    CONTENT_DEPARTMENT,
    CONTENT_LEAD_ROLES,
    PROJECT_MANAGER_ROLE,
    get_coordinated_projects,
)
from helpdesk.utils import agent_only

# a post between its first draft and going out; Idea hasn't started, Scheduled is done
PRODUCTION_STATUSES = (
    "Drafting",
    "Design",
    "Internal Review",
    "Client Review",
    "Changes Requested",
    "Head Review",
    "Approved",
)
# the post's parts come back on Changes Requested, even ones already finished once
REOPENS_PARTS = "Changes Requested"
GROUPS = ("project", "person", "department")
TASK_LIMIT = 1000
POST_LIMIT = 500
CONTENT_LANE = "content"
NO_KEY = "__none__"
POST_FIELDS = [
    "name",
    "title",
    "customer",
    "status",
    "publish_on",
    "channel",
    "platforms",
    "format",
    "task_mode",
    "owner",
]
# row order inside a lane: being worked on, then waiting for review, then paused
STATUS_ORDER = {WORKING: 0, PENDING_REVIEW: 1, ON_HOLD: 2}


@frappe.whitelist()
@agent_only
def get_in_progress(
    group_by: str = "project",
    department: str | None = None,
    customer: str | None = None,
    person: str | None = None,
    only_overdue: bool | int | str = False,
    hide_on_hold: bool | int | str = False,
) -> dict:
    """Started tasks and posts in production, in lanes, with a summary of the whole view.

    The summary counts everything under department, customer and person; "only
    overdue / escalated" and "hide on hold" only narrow the lanes, so the summary
    still says how much is on hold or late.
    """
    if group_by not in GROUPS:
        frappe.throw(_("Unknown grouping: {0}").format(group_by))
    user = frappe.session.user
    tasks, truncated = _tasks(department, customer, person)
    posts, posts_truncated = _posts(user, department, customer, person)

    summary = _counts(tasks, posts)
    if sbool(hide_on_hold):
        tasks = [t for t in tasks if t["status"] != ON_HOLD]
    if sbool(only_overdue):
        tasks = [t for t in tasks if t["is_overdue"] or t["escalation_level"]]
        posts = [p for p in posts if p["is_missed"]]

    return {
        "scope": "team" if _sees_team(user) else "own",
        "group_by": group_by,
        "summary": summary,
        "lanes": _lanes(group_by, tasks, posts),
        "truncated": truncated or posts_truncated,
    }


def _sees_team(user: str) -> bool:
    """Runs some work beyond their own: admins, project managers, leads, coordinators
    and the content leads. Only words the page; the lists decide what each one sees."""
    roles = set(frappe.get_roles(user))
    return (
        can_see_overview(user)
        or PROJECT_MANAGER_ROLE in roles
        or bool(roles & set(CONTENT_LEAD_ROLES))
        or bool(get_coordinated_projects(user))
    )


# --- tasks ---


def _tasks(department, customer, person) -> tuple[list[dict], bool]:
    filters = scoped_task_filters(
        ("in", IN_PROGRESS_STATUSES), None, customer, person, department
    )
    rows = frappe.get_list(
        "Task",
        filters=filters,
        fields=TASK_FIELDS,
        order_by="exp_end_date asc",
        limit_page_length=TASK_LIMIT + 1,
    )
    truncated = len(rows) > TASK_LIMIT
    rows = rows[:TASK_LIMIT]
    projects = _projects({t.project for t in rows if t.project})
    names = {p: info.project_name for p, info in projects.items()}
    waiting = _open_dependencies(rows)
    holders = hold_by_names(rows)
    people = user_full_names({u for t in rows for u in _assignees(t._assign)})
    since = status_since(rows)
    items = []
    for task in rows:
        item = _task_item(task, names, waiting, holders)
        project = projects.get(task.project) or frappe._dict()
        item.update(
            {
                "customer": project.customer,
                "department": project.custom_department,
                "assignee_names": {u: people.get(u, u) for u in item["assignees"]},
                "status_since": since.get(task.name),
                "estimated_hours": task.custom_estimated_hours or 0,
                # the board timer (docs/workspace-pages.md "The board timer")
                "custom_timer_start": (
                    str(task.custom_timer_start) if task.custom_timer_start else None
                ),
                "custom_timer_elapsed": task.custom_timer_elapsed or 0,
            }
        )
        items.append(item)
    return items, truncated


def _projects(names: set[str]) -> dict:
    """Name, customer and department of each project, in one query."""
    if not names:
        return {}
    return {
        p.name: p
        for p in frappe.get_all(
            "Project",
            filters={"name": ("in", list(names))},
            fields=["name", "project_name", "customer", "custom_department"],
        )
    }


# --- content posts ---


def _posts(user, department, customer, person) -> tuple[list[dict], bool]:
    """Posts in production the viewer may see; none outside the content team, and
    none under another department's filter (the content calendar is the Digital team's)."""
    if not in_content_team(user):
        return [], False
    if department and department != CONTENT_DEPARTMENT:
        return [], False
    filters = {"status": ("in", PRODUCTION_STATUSES)}
    if customer:
        filters["customer"] = customer
    # narrowed in the query, so the cap counts only posts the viewer gets
    wanted_names = None
    if not _is_content_lead(user):
        # outside the content leads, only the posts they're on: their own items
        wanted_names = _posts_with(user, include_owned=True)
    if person:
        theirs = _posts_with(person)
        wanted_names = theirs if wanted_names is None else wanted_names & theirs
    if wanted_names is not None:
        filters["name"] = ("in", list(wanted_names) or [""])
    rows = frappe.get_list(
        "HD Content Post",
        filters=filters,
        fields=POST_FIELDS,
        order_by="publish_on asc",
        limit_page_length=POST_LIMIT + 1,
    )
    truncated = len(rows) > POST_LIMIT
    wanted = rows[:POST_LIMIT]
    teams = role_teams_of([p.name for p in wanted])
    tasks = role_tasks([p.name for p in wanted])
    full_names = user_full_names(
        {u for p in wanted for users in teams.get(p.name, {}).values() for u in users}
    )
    now = now_datetime()
    return [
        _post_item(p, teams.get(p.name, {}), tasks, full_names, now) for p in wanted
    ], truncated


def _posts_with(user: str, include_owned: bool = False) -> set[str]:
    """Posts with `user` on any part (main person or extra team), and the ones they
    created when `include_owned`; two queries for any number of posts."""
    fields = [*TASK_ROLES, "owner"] if include_owned else list(TASK_ROLES)
    main = frappe.get_all(
        "HD Content Post",
        or_filters={field: user for field in fields},
        pluck="name",
    )
    extra = frappe.get_all(
        "HD Content Post Member",
        filters={"parenttype": "HD Content Post", "user": user},
        pluck="parent",
    )
    return set(main) | set(extra)


def _post_item(post, team: dict, tasks: dict, full_names: dict, now) -> dict:
    publish_on = get_datetime(post.publish_on) if post.publish_on else None
    return {
        "kind": "post",
        "name": post.name,
        "title": post.title,
        "customer": post.customer,
        "status": post.status,
        "publish_on": str(publish_on) if publish_on else None,
        "platforms": _platforms(post),
        "format": post.format,
        "pending": _pending_parts(post, team, tasks, full_names),
        "waiting_on": _review_stage(post.status),
        "is_missed": bool(publish_on and publish_on < now),
        "at_risk": bool(
            publish_on
            and post.status not in READY_STATUSES
            and now <= publish_on <= add_to_date(now, hours=REMINDER_WINDOW_HOURS)
        ),
    }


def _review_stage(status: str) -> str | None:
    """Who a post waits on in a review stage, rather than on someone's part."""
    return {
        "Internal Review": _("Internal review"),
        "Client Review": _("Client approval"),
        "Head Review": _("Head approval"),
    }.get(status)


def _role_label(field: str) -> str:
    """A part's name as the content calendar shows it (TEAM_ROLES in constants.ts)."""
    return {
        "writer": _("Writer"),
        "designer": _("Designer"),
        "video_editor": _("Video editor"),
        "marketer": _("Digital marketer"),
    }[field]


def _platforms(post) -> list[str]:
    raw = post.platforms or post.channel or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def _pending_parts(post, team: dict, tasks: dict, full_names: dict) -> list[dict]:
    """The parts the post waits on in its stage, and who has each: the writer while
    drafting, the designer and video editor in design, the marketer once approved.
    A part whose task is done no longer waits, unless changes were asked for."""
    parts = []
    for field in NEXT_PERSON.get(post.status, ()):
        people = team.get(field) or []
        task = task_for_role(tasks, post, field)
        if not people:
            continue
        if (
            task
            and task["status"] in DONE_TASK_STATUSES
            and post.status != REOPENS_PARTS
        ):
            continue
        parts.append(part_item(field, people, task, full_names))
    return parts


def part_item(field: str, people: list[str], task: dict | None, full_names: dict):
    """One part of a post: its role, who has it and how far their task is."""
    return {
        "role": field,
        "label": _role_label(field),
        "people": [{"user": u, "full_name": full_names.get(u, u)} for u in people],
        "task": task["task"] if task else None,
        "task_status": task["status"] if task else None,
        "due": task["due"] if task else None,
    }


# --- summary and lanes ---


def _counts(tasks: list[dict], posts: list[dict]) -> dict:
    """The summary line's numbers, for the whole view or one lane. A task shared by
    two people sits in both their lanes but counts once in the summary."""
    return {
        "in_progress": sum(t["status"] == WORKING for t in tasks),
        "review": sum(t["status"] == PENDING_REVIEW for t in tasks),
        "on_hold": sum(t["status"] == ON_HOLD for t in tasks),
        "overdue": sum(t["is_overdue"] for t in tasks),
        "escalated": sum(bool(t["escalation_level"]) for t in tasks),
        "posts": len(posts),
        "missed": sum(p["is_missed"] for p in posts),
        "at_risk": sum(p["at_risk"] for p in posts),
    }


def _lanes(group_by: str, tasks: list[dict], posts: list[dict]) -> list[dict]:
    lanes = {}

    def lane(key, kind, title, subtitle=None):
        return lanes.setdefault(
            (kind, key),
            {
                "key": key,
                "kind": kind,
                "title": title,
                "subtitle": subtitle,
                "tasks": [],
                "posts": [],
            },
        )

    for task in tasks:
        for key, kind, title, subtitle in _task_lanes(group_by, task):
            lane(key, kind, title, subtitle)["tasks"].append(task)
    for post in posts:
        for key, kind, title in _post_lanes(group_by, post):
            lane(key, kind, title)["posts"].append(post)

    out = list(lanes.values())
    for item in out:
        item["tasks"].sort(key=_task_order)
        item["posts"].sort(key=_post_order)
        item["counts"] = _counts(item["tasks"], item["posts"])
    out.sort(
        key=lambda row: (
            -(row["counts"]["overdue"] + row["counts"]["missed"]),
            -(len(row["tasks"]) + len(row["posts"])),
            (row["title"] or "").lower(),
        )
    )
    return out


def _task_lanes(group_by: str, task: dict) -> list[tuple]:
    if group_by == "person":
        if not task["assignees"]:
            return [(NO_KEY, "person", _("Unassigned"), None)]
        return [
            (user, "person", task["assignee_names"].get(user, user), None)
            for user in task["assignees"]
        ]
    if group_by == "department":
        department = task["department"]
        return [
            (department or NO_KEY, "department", department or _("No department"), None)
        ]
    return [
        (
            task["project"] or NO_KEY,
            "project",
            task["project_name"] or task["project"] or _("No project"),
            task["customer"],
        )
    ]


def _post_lanes(group_by: str, post: dict) -> list[tuple]:
    if group_by == "person":
        people = {
            p["user"]: p["full_name"]
            for part in post["pending"]
            for p in part["people"]
        }
        if people:
            return [(user, "person", name) for user, name in people.items()]
        # waiting on a reviewer or the client, or nobody on the part yet
        return [(CONTENT_LANE, "content", _("Content calendar"))]
    if group_by == "department":
        return [(CONTENT_DEPARTMENT, "department", CONTENT_DEPARTMENT)]
    return [(CONTENT_LANE, "content", _("Content calendar"))]


def _task_order(task: dict):
    return (
        not task["is_overdue"],
        -task["escalation_level"],
        STATUS_ORDER.get(task["status"], 3),
        not task["is_key"],
        task["deadline"] or "9999-12-31",
    )


def _post_order(post: dict):
    return (not post["is_missed"], not post["at_risk"], post["publish_on"] or "9999")
