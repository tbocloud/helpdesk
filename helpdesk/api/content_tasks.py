"""The content calendar's Tasks view: the role tasks of the posts on screen, as a work queue.

One call answers the Tasks view, the "Your tasks" strip, the role boxes' Start / Pause /
Complete and each board card's "3 of 4 parts done · waiting on …" line. Posts come
through `frappe.get_list` on HD Content Post (only the content team gets any), tasks
through `frappe.get_list` on Task, so the #94 rule decides whose tasks each viewer gets:
writers, designers and marketers their own, the content leads every content task. The
parts summary reads each visible post's role tasks the way the board's role boxes do
(`get_team_task_status`), so a member still sees how their teammates' parts stand.
See docs/content-calendar.md "Tasks view".
"""

import frappe
from frappe import _
from frappe.utils import date_diff, get_datetime, getdate, now_datetime, nowdate

from helpdesk.api.content_board import (
    HOURS_FIELDS,
    TEAM_FIELDS,
    role_tasks,
    task_for_role,
    user_full_names,
)
from helpdesk.api.in_progress import _pending_parts, _role_label, part_item
from helpdesk.api.work import (
    ON_HOLD,
    PENDING_REVIEW,
    TASK_FIELDS,
    _assignees,
    _open_dependencies,
    _project_names,
    is_task_overdue,
)
from helpdesk.content_team import can_edit_content, in_content_team
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    CLOSED_STATUSES,
    DONE_TASK_STATUSES,
    SHARED_ROLE,
    TASK_ROLES,
    _is_content_lead,
    role_teams_of,
)
from helpdesk.tasky.api import hold_by_name, hold_by_names
from helpdesk.tasky.permissions import can_coordinate_project
from helpdesk.utils import agent_only, assigned_to_filter

# the queue's columns, in order
STAGES = ("todo", "in_progress", "review", "on_hold", "done")
# not started: Overdue is the old status for an Open task past its date
NOT_STARTED = ("Open", "Overdue")
WORKING = "Working"
COMPLETED = "Completed"
# a calendar month grid shows up to six weeks
MAX_RANGE_DAYS = 62
POST_LIMIT = 1000
TASK_LIMIT = 1000
POST_FIELDS = [
    "name",
    "title",
    "customer",
    "status",
    "publish_on",
    "channel",
    "platforms",
    "format",
    "special_day",
    "task_mode",
    *TEAM_FIELDS,
    *HOURS_FIELDS,
]
# content_role on the task → the post's field for that part
ROLE_FIELDS = {label: field for field, label in TASK_ROLES.items()}


@frappe.whitelist()
@agent_only
def get_content_tasks(
    start: str,
    end: str,
    customer: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    person: str | None = None,
) -> dict:
    """The role tasks of the posts going live between `start` and `end` (dates), under
    the calendar's filters; `person` keeps the tasks assigned to them. Cancelled posts
    are left out unless `status` asks for them, as on the calendar.

    {sees_all, can_edit, tasks: [...], counts: {stage: n}, posts: {name: post},
    truncated}. Each post carries `progress` ({parts, done, waiting_on}) whatever
    `person` is, so the board can show it on every card.
    """
    user = frappe.session.user
    if not in_content_team(user):
        frappe.throw(
            _("Only the content team sees the content calendar's tasks."),
            frappe.PermissionError,
        )
    if date_diff(end, start) < 0 or date_diff(end, start) > MAX_RANGE_DAYS:
        frappe.throw(_("Pick a range of at most two months."))

    posts, posts_truncated = _posts(start, end, customer, channel, status)
    names = list(posts)
    teams = role_teams_of(names)
    parts = role_tasks(names) if names else {}
    rows, tasks_truncated = _task_rows(names, person)
    full_names = user_full_names(
        {u for team in teams.values() for users in team.values() for u in users}
        | {u for row in rows for u in _assignees(row._assign)}
    )
    now = now_datetime()
    out_posts = {
        name: _post_item(post, teams.get(name, {}), parts, full_names, now)
        for name, post in posts.items()
    }
    tasks = _task_items(rows, posts, full_names, user)
    return {
        "sees_all": _is_content_lead(user),
        "can_edit": can_edit_content(user),
        "tasks": tasks,
        "counts": {stage: sum(t["stage"] == stage for t in tasks) for stage in STAGES},
        "posts": out_posts,
        "truncated": posts_truncated or tasks_truncated,
    }


# --- posts ---


def _posts(start, end, customer, channel, status) -> tuple[dict, bool]:
    filters = {
        "publish_on": (
            "between",
            [f"{getdate(start)} 00:00:00", f"{getdate(end)} 23:59:59"],
        ),
        "status": status or ("!=", "Cancelled"),
    }
    if customer:
        filters["customer"] = customer
    if channel:
        # a post can go out on several platforms; `channel` is only the first
        filters["platforms"] = ("like", f"%{channel}%")
    rows = frappe.get_list(
        "HD Content Post",
        filters=filters,
        fields=POST_FIELDS,
        order_by="publish_on asc",
        limit_page_length=POST_LIMIT + 1,
    )
    return {p.name: p for p in rows[:POST_LIMIT]}, len(rows) > POST_LIMIT


def _post_item(post, team: dict, parts: dict, full_names: dict, now) -> dict:
    publish_on = get_datetime(post.publish_on) if post.publish_on else None
    return {
        **{field: post.get(field) for field in POST_FIELDS if field != "task_mode"},
        "publish_on": str(publish_on) if publish_on else None,
        "is_missed": bool(
            publish_on and publish_on < now and post.status not in CLOSED_STATUSES
        ),
        "progress": post_progress(post, team, parts, full_names),
    }


def post_progress(post, team: dict, tasks: dict, full_names: dict) -> dict:
    """How far the post's parts are and who it waits on now.

    `parts` counts the roles with someone on them, `done` those whose task is
    Completed. `waiting_on` is the review stage it sits in ("Client approval"), else
    the part its stage waits on (the writer while drafting, the designer in design,
    the marketer once approved), else the first part not finished yet; None once it
    is published or cancelled, or when every part is done outside a review stage.
    """
    staffed = [field for field in TASK_ROLES if team.get(field)]
    done = sum(
        1
        for field in staffed
        if (task := task_for_role(tasks, post, field)) and task["status"] == COMPLETED
    )
    return {
        "parts": len(staffed),
        "done": done,
        "waiting_on": _waiting_on(post, team, tasks, full_names, staffed),
    }


def _waiting_on(post, team, tasks, full_names, staffed) -> dict | None:
    if post.status in CLOSED_STATUSES:
        return None
    if review := waiting_review(post.status):
        return {"kind": "review", "label": review}
    pending = _pending_parts(post, team, tasks, full_names)
    if pending:
        return {"kind": "part", **pending[0]}
    for field in staffed:
        task = task_for_role(tasks, post, field)
        if task and task["status"] in DONE_TASK_STATUSES:
            continue
        return {"kind": "part", **part_item(field, team[field], task, full_names)}
    return None


# --- tasks ---


def _task_rows(posts: list[str], person: str | None) -> tuple[list, bool]:
    """The posts' role tasks the viewer may read, the newest per post and part."""
    if not posts:
        return [], False
    filters = {
        "content_post": ("in", posts),
        "content_role": ("is", "set"),
        "status": ("not in", ["Cancelled", "Template"]),
    }
    if person:
        filters["name"] = assigned_to_filter("Task", person)
    rows = frappe.get_list(
        "Task",
        filters=filters,
        fields=[*TASK_FIELDS, "content_post", "content_role"],
        order_by="creation asc",
        limit_page_length=TASK_LIMIT + 1,
    )
    newest = {(row.content_post, row.content_role): row for row in rows[:TASK_LIMIT]}
    return list(newest.values()), len(rows) > TASK_LIMIT


def _task_items(rows, posts: dict, full_names: dict, user: str) -> list[dict]:
    waiting = _open_dependencies(rows)
    holders = hold_by_names(rows)
    projects = _project_names(rows)
    coordinates = {
        project: can_coordinate_project(project, user)
        for project in {row.project for row in rows if row.project}
    }
    can_edit = can_edit_content(user)
    today = getdate(nowdate())
    items = [
        _task_item(
            row,
            posts[row.content_post],
            full_names,
            {
                "waiting": waiting,
                "holders": holders,
                "projects": projects,
                "coordinates": coordinates,
                "can_edit": can_edit,
                "today": today,
                "user": user,
            },
        )
        for row in rows
    ]
    items.sort(key=_task_order)
    return items


def _task_item(task, post, full_names: dict, ctx: dict) -> dict:
    assignees = _assignees(task._assign)
    deadline = getdate(task.exp_end_date) if task.exp_end_date else None
    running = task.status == WORKING and bool(task.custom_timer_start)
    on_hold = task.status == ON_HOLD
    waiting_on = ctx["waiting"].get(task.depends_on_task)
    field = ROLE_FIELDS.get(task.content_role)
    stage = task_stage(task.status, post.status, running)
    mine = ctx["user"] in assignees
    return {
        "name": task.name,
        "subject": task.subject,
        "status": task.status,
        "stage": stage,
        "review_label": _review_label(task.status, post.status, stage),
        "role": field,
        "role_label": _role_label(field) if field else _("Whole post"),
        "post": post.name,
        "publish_on": str(post.publish_on) if post.publish_on else None,
        "project": task.project,
        "project_name": ctx["projects"].get(task.project),
        "assignees": assignees,
        "assignee_names": {u: full_names.get(u, u) for u in assignees},
        "mine": mine,
        "due": str(deadline) if deadline else None,
        "is_overdue": is_task_overdue(task, deadline, ctx["today"]),
        "hold_reason": task.hold_reason if on_hold else None,
        "hold_note": task.hold_note if on_hold else None,
        "hold_by_name": (
            hold_by_name(task.hold_by, ctx["holders"]) if on_hold else None
        ),
        "hold_days": (
            (ctx["today"] - getdate(task.hold_since)).days
            if on_hold and task.hold_since
            else None
        ),
        "custom_timer_start": (
            str(task.custom_timer_start) if task.custom_timer_start else None
        ),
        "custom_timer_elapsed": task.custom_timer_elapsed or 0,
        "estimated_hours": task.custom_estimated_hours or 0,
        "escalation_level": task.escalation_level or 0,
        "waiting_on": waiting_on,
        "actions": task_actions(
            task.status,
            mine=mine,
            running=running,
            blocked=bool(waiting_on),
            coordinates=ctx["coordinates"].get(task.project, False),
            can_reassign=ctx["can_edit"] and task.content_role != SHARED_ROLE,
        ),
    }


def task_stage(status: str, post_status: str, running: bool = False) -> str:
    """The queue column: done, on hold, in review (the lead's review, or a part not
    started while the post sits with a reviewer, the client or the head), in progress
    (Working, or a timer running), else to do."""
    if status == COMPLETED:
        return "done"
    if status == ON_HOLD:
        return "on_hold"
    if status == PENDING_REVIEW:
        return "review"
    if status == WORKING or running:
        return "in_progress"
    if waiting_review(post_status):
        return "review"
    return "todo"


def waiting_review(post_status: str) -> str | None:
    """Who a post in a review stage waits on, worded to follow "Waiting on"."""
    return {
        "Internal Review": _("internal review"),
        "Client Review": _("the client's approval"),
        "Head Review": _("the Digital Marketing Head's approval"),
    }.get(post_status)


def _review_label(status: str, post_status: str, stage: str) -> str | None:
    if stage != "review":
        return None
    if status == PENDING_REVIEW:
        return _("the lead's review")
    return waiting_review(post_status)


def task_actions(
    status: str,
    mine: bool,
    running: bool,
    blocked: bool,
    coordinates: bool,
    can_reassign: bool,
) -> list[str]:
    """The steps the viewer may take on the task, as the task APIs allow them.

    The assignee starts, pauses and resumes the timer, completes it (not while it
    waits on another task, which the server refuses), and holds or resumes it; whoever
    runs the project's tasks holds, resumes and approves; content editors reassign the
    part (`content_board.assign`).
    """
    actions = []
    workable = status in (*NOT_STARTED, WORKING)
    if mine and status in NOT_STARTED and not blocked:
        actions.append("start")
    if mine and status == WORKING:
        actions.append("pause" if running else "resume_timer")
    if mine and workable and not blocked:
        actions.append("complete")
    if (mine or coordinates) and workable:
        actions.append("hold")
    if (mine or coordinates) and status == ON_HOLD:
        actions.append("resume")
    if coordinates and status == PENDING_REVIEW:
        actions.append("approve")
    if can_reassign and status != COMPLETED:
        actions.append("reassign")
    return actions


def _task_order(task: dict):
    return (
        STAGES.index(task["stage"]),
        not task["is_overdue"],
        task["due"] or "9999-12-31",
        task["publish_on"] or "9999",
    )
