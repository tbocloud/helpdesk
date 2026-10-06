"""Board actions for the Content Calendar: add entries, postpone, cancel."""

import json

import frappe
from frappe import _
from frappe.utils import date_diff

from helpdesk.helpdesk.doctype.hd_content_occasion.hd_content_occasion import (
    occasions_between,
)
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    DONE_TASK_STATUSES,
    ONE_TASK,
    SHARED_ROLE,
    TASK_ROLES,
    role_teams_of,
    team_of,
)

TEAM_FIELDS = ("writer", "designer", "marketer", "video_editor")
# fields the Add entry dialog may set on every post it creates
ENTRY_FIELDS = (
    "title",
    "customer",
    "campaign",
    "format",
    "status",
    "publish_on",
    "caption",
    "hashtags",
    "brief",
    "task_mode",
    *TEAM_FIELDS,
)


@frappe.whitelist(methods=["POST"])
def add_entries(
    values: str | dict,
    channels: str | list,
    separate: bool | int | str = True,
    team: str | dict | None = None,
) -> list[str]:
    """Create the entry for the chosen platforms, all together or not at all.

    `separate` makes one post per platform (each can be scheduled, approved and
    published on its own); otherwise one post covers every platform. `team`
    ({role: [users]}) puts several people on a role; the first is its main person.
    """
    frappe.has_permission("HD Content Post", "create", throw=True)
    values = json.loads(values) if isinstance(values, str) else values
    channels = json.loads(channels) if isinstance(channels, str) else channels
    channels = list(dict.fromkeys(c for c in channels or [] if c))
    if not channels:
        frappe.throw(_("Pick at least one platform"))
    separate = frappe.utils.sbool(separate)
    if not values.get("publish_on"):
        frappe.throw(_("Pick the posting date and time"))

    team = json.loads(team) if isinstance(team, str) else team or {}
    common = {k: values.get(k) for k in ENTRY_FIELDS if values.get(k) not in (None, "")}
    groups = [[c] for c in channels] if separate else [channels]
    names = []
    for platforms in groups:
        post = frappe.get_doc(
            {
                "doctype": "HD Content Post",
                **common,
                "channel": platforms[0],
                "platforms": ", ".join(platforms),
            }
        )
        for role in TEAM_FIELDS:
            if role in team:
                post.set_people(role, team[role] or [])
        post.insert()
        names.append(post.name)
    return names


@frappe.whitelist()
def get_team_defaults(customer: str) -> dict:
    """Everyone on this customer's most recent post, by role, to pre-fill a new entry."""
    latest = frappe.get_list(
        "HD Content Post",
        filters={"customer": customer},
        pluck="name",
        order_by="creation desc",
        limit=1,
    )
    if not latest:
        return {role: [] for role in TEAM_FIELDS}
    return team_of(frappe.get_doc("HD Content Post", latest[0]))


@frappe.whitelist(methods=["POST"])
def assign(post: str, role: str, users: str | list | None = None) -> list[str]:
    """Put these people on one role of a post; the first is its main person.

    Their tasks follow the post's task mode: in one-task-per-person mode
    everyone on the role shares that role's task.
    """
    if role not in TEAM_FIELDS:
        frappe.throw(_("Unknown role {0}").format(role))
    users = json.loads(users) if isinstance(users, str) else users or []
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    doc.set_people(role, users)
    doc.save()
    return doc.people(role)


@frappe.whitelist()
def get_team_task_status(posts: str | list) -> dict:
    """Each post's people by role, with how far each is with their task.

    {post: {role: [{user, full_name, task, status, due}]}}. Only posts the viewer
    can see are answered, and only what the board shows of each task, so people
    with narrower Task access still see how their teammates are getting on.
    """
    posts = json.loads(posts) if isinstance(posts, str) else posts or []
    if not posts:
        return {}
    visible = frappe.get_list(
        "HD Content Post",
        filters={"name": ("in", posts)},
        fields=["name", "task_mode"],
    )
    if not visible:
        return {}
    names = [p.name for p in visible]
    teams = role_teams_of(names)
    tasks = role_tasks(names)
    full_names = user_full_names(
        {u for team in teams.values() for users in team.values() for u in users}
    )
    out = {}
    for post in visible:
        out[post.name] = {}
        for role, users in teams[post.name].items():
            task = task_for_role(tasks, post, role)
            out[post.name][role] = [
                {"user": u, "full_name": full_names.get(u, u), **(task or {})}
                for u in users
            ]
    return out


def task_for_role(tasks: dict, post, role: str) -> dict | None:
    """The task that stands for a role's part.

    The kind the post's task mode makes comes first, unless only the other kind is
    still open; switching the mode cancels the old kind's tasks.
    """
    own = tasks.get((post.name, TASK_ROLES[role]))
    shared = tasks.get((post.name, SHARED_ROLE))
    candidates = [t for t in (own, shared) if t]
    if post.task_mode == ONE_TASK:
        candidates.reverse()
    for task in candidates:
        if task["status"] not in DONE_TASK_STATUSES:
            return task
    return candidates[0] if candidates else None


def role_tasks(posts: list[str]) -> dict[tuple[str, str], dict]:
    """The newest task per (post, content role), as the board shows it."""
    out = {}
    for task in frappe.get_all(
        "Task",
        filters={"content_post": ("in", posts), "content_role": ("is", "set")},
        fields=["name", "content_post", "content_role", "status", "exp_end_date"],
        order_by="creation asc",
    ):
        out[(task.content_post, task.content_role)] = {
            "task": task.name,
            "status": task.status,
            "due": str(task.exp_end_date) if task.exp_end_date else None,
        }
    return out


def user_full_names(users: set[str]) -> dict[str, str]:
    if not users:
        return {}
    return {
        u.name: u.full_name or u.name
        for u in frappe.get_all(
            "User", filters={"name": ("in", list(users))}, fields=["name", "full_name"]
        )
    }


@frappe.whitelist()
def get_occasions(start: str, end: str, customer: str | None = None) -> list[dict]:
    """Occasions between two dates; for one customer, only its package's regions."""
    frappe.has_permission("HD Content Post", "read", throw=True)
    if date_diff(end, start) > 400:
        frappe.throw(_("Pick a range of at most a year."))
    regions = None
    if customer and frappe.db.exists("HD Content Package", customer):
        regions = frappe.get_cached_doc(
            "HD Content Package", customer
        ).occasion_regions()
    return [
        {
            "date": str(o.date),
            "occasion": o.occasion_name,
            "region": o.region,
            "idea": o.idea,
        }
        for o in occasions_between(start, end, regions)
    ]


@frappe.whitelist(methods=["POST"])
def postpone(post: str, publish_on: str, reason: str):
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    doc.postpone(publish_on, reason)
    return {"publish_on": doc.publish_on, "times_postponed": doc.times_postponed}


@frappe.whitelist(methods=["POST"])
def cancel(post: str, reason: str | None = None):
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    doc.cancel(reason)
    return {"status": doc.status}
