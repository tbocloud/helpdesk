"""Board actions for the Content Calendar: add entries, postpone, cancel."""

import json

import frappe
from frappe import _

from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import team_of

TEAM_FIELDS = ("writer", "designer", "marketer")
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
    published on its own); otherwise one post covers every platform.
    """
    frappe.has_permission("HD Content Post", "create", throw=True)
    values = json.loads(values) if isinstance(values, str) else values
    channels = json.loads(channels) if isinstance(channels, str) else channels
    channels = list(dict.fromkeys(c for c in channels or [] if c))
    if not channels:
        frappe.throw(_("Pick at least one platform"))
    separate = frappe.utils.sbool(separate)
    team = parse_team(team)
    if not values.get("publish_on"):
        frappe.throw(_("Pick the posting date and time"))

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
        for role, users in team.items():
            post.set_people(role, users)
        post.insert()
        names.append(post.name)
    return names


@frappe.whitelist()
def get_team_defaults(customer: str) -> dict:
    """The team on this customer's most recent post, to pre-fill a new entry.

    Each role's main person as before, plus `team`: everyone on each role.
    """
    latest = frappe.get_list(
        "HD Content Post",
        filters={"customer": customer},
        fields=["name", *TEAM_FIELDS],
        order_by="creation desc",
        limit=1,
    )
    if not latest:
        return frappe._dict(
            {**dict.fromkeys(TEAM_FIELDS), "team": {r: [] for r in TEAM_FIELDS}}
        )
    post = frappe.get_doc("HD Content Post", latest[0].name)
    return frappe._dict(
        {**{r: post.get(r) for r in TEAM_FIELDS}, "team": team_of(post)}
    )


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


@frappe.whitelist(methods=["POST"])
def assign(
    post: str,
    role: str,
    user: str | None = None,
    hours: float | None = None,
    users: str | list | None = None,
):
    """Put people on a post's writer, designer or marketer role.

    `users` sets everyone on the role (the first is the main person); `user`
    alone replaces the role with that one person. New tasks get `hours` if given.
    """
    if role not in TEAM_FIELDS:
        frappe.throw(_("Unknown role {0}").format(role))
    if users is not None:
        people = frappe.parse_json(users) if isinstance(users, str) else users
    else:
        people = [user] if user else []
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    doc.set_people(role, people or [])
    if people and hours:
        doc.flags.task_hours = {role: float(hours)}
    doc.save()
    return {role: doc.get(role), "people": doc.people(role)}


@frappe.whitelist(methods=["POST"])
def set_team(post: str, team: str | dict):
    """Set everyone on several roles at once, saving the post a single time."""
    team = parse_team(team)
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    for role, users in team.items():
        doc.set_people(role, users)
    doc.save()
    return team_of(doc)


def parse_team(team) -> dict[str, list[str]]:
    team = frappe.parse_json(team) if isinstance(team, str) else (team or {})
    unknown = set(team) - set(TEAM_FIELDS)
    if unknown:
        frappe.throw(_("Unknown role {0}").format(", ".join(sorted(unknown))))
    return {role: [u for u in users or [] if u] for role, users in team.items()}


@frappe.whitelist()
def get_role_tasks(post: str) -> list[dict]:
    """The open tasks created for this post's team, for the Assign dialog."""
    frappe.has_permission("HD Content Post", "read", post, throw=True)
    if not frappe.get_meta("Task").has_field("content_post"):
        return []
    return frappe.get_all(
        "Task",
        filters={
            "content_post": post,
            "status": ("not in", ("Completed", "Cancelled")),
        },
        fields=["name", "content_role", "expected_time", "status"],
    )


@frappe.whitelist()
def get_team_task_status(posts: str | list) -> dict:
    """Everyone on each post's roles, with their task and its status, for the posts on screen.

    `{post: {role: [{user, full_name, task, status, due}]}}`, the main person
    first. Only posts the viewer can see are answered; the task details are
    limited to what the board shows, so people whose Task access is narrower
    still see how their teammates are getting on.
    """
    posts = json.loads(posts) if isinstance(posts, str) else posts
    if not posts:
        return {}
    visible = frappe.get_list(
        "HD Content Post",
        filters={"name": ("in", posts[:500])},
        fields=["name", *TEAM_FIELDS],
    )
    if not visible:
        return {}
    extras = {}
    for row in (
        frappe.get_all(
            "HD Content Post Member",
            filters={
                "parenttype": "HD Content Post",
                "parent": ("in", [p.name for p in visible]),
            },
            fields=["parent", "role", "user"],
            order_by="idx asc",
        )
        if frappe.db.exists("DocType", "HD Content Post Member")
        else []
    ):
        extras.setdefault((row.parent, row.role), []).append(row.user)

    tasks = {}
    if frappe.get_meta("Task").has_field("content_post"):
        rows = frappe.get_all(
            "Task",
            filters={
                "content_post": ("in", [p.name for p in visible]),
                "content_role": ("is", "set"),
            },
            fields=[
                "name",
                "content_post",
                "content_role",
                "status",
                "exp_end_date",
                "_assign",
            ],
            order_by="creation asc",
        )
        # ERPNext empties _assign once a task is completed; its ToDo still says whose it was
        unassigned = [t.name for t in rows if not frappe.parse_json(t._assign or "[]")]
        owner_of = {
            todo.reference_name: todo.allocated_to
            for todo in frappe.get_all(
                "ToDo",
                filters={
                    "reference_type": "Task",
                    "reference_name": ("in", unassigned or [""]),
                },
                fields=["reference_name", "allocated_to"],
                order_by="creation asc",
            )
        }
        for task in rows:
            assigned = frappe.parse_json(task._assign or "[]")
            who = assigned[0] if assigned else owner_of.get(task.name)
            # the newest task for a person wins, e.g. after a cancelled one was replaced
            tasks[(task.content_post, task.content_role, who)] = {
                "task": task.name,
                "status": task.status,
                "due": str(task.exp_end_date) if task.exp_end_date else None,
            }

    names = {}
    out: dict[str, dict] = {}
    for post in visible:
        for role in TEAM_FIELDS:
            people = list(
                dict.fromkeys(
                    u for u in [post.get(role), *extras.get((post.name, role), [])] if u
                )
            )
            for user in people:
                if user not in names:
                    names[user] = frappe.utils.get_fullname(user)
                out.setdefault(post.name, {}).setdefault(role, []).append(
                    {
                        "user": user,
                        "full_name": names[user],
                        **(tasks.get((post.name, role, user)) or {}),
                    }
                )
    return out
