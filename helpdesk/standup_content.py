"""The content calendar in the daily stand-up, for the content team (Digital).

docs/standup.md "Content calendar". Writers, designers, video editors and digital
marketers work on content posts, so their stand-up shows each part with its post:
- yesterday: the parts they finished ("Designer · Global Handwashing Day (Avera IoT)"),
  and the posts they published or moved on;
- today: their open parts (due today, else the next one due), the posts they're on
  going live today and tomorrow; heads and coordinators also every post going live
  today;
- blockers: missed posts, posts going live within 24 hours that aren't approved,
  changes requested, posts waiting on the client too long, and parts waiting on
  someone else's part (the Tasks view's "waiting on Writer (Ajmal)").
A role task that is also on the person's My Work shows once, as its part.

Everything is read as the person (`frappe.get_list`), so the calendar's walls apply:
outside the content team (ERP Employees included) nothing is added. The department
summary and team view get a "Content today" block (`content_today`).
"""

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_to_date,
    cint,
    format_datetime,
    get_datetime,
    getdate,
    now_datetime,
    strip_html,
)

from helpdesk.api.content_board import role_tasks, user_full_names
from helpdesk.api.content_tasks import NOT_STARTED, ROLE_FIELDS, WORKING, post_progress
from helpdesk.api.in_progress import REOPENS_PARTS, _platforms, _role_label
from helpdesk.content_team import in_content_team
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    CLIENT_REVIEW,
    CLOSED_STATUSES,
    CONTENT_PROJECT_TYPE,
    READY_STATUSES,
    role_teams_of,
)
from helpdesk.standup import item, md_link, plain, short_date, task_item
from helpdesk.tasky.permissions import CONTENT_DEPARTMENT, CONTENT_LEAD_ROLES

POST = "HD Content Post"
PUBLISHED = "Published"
# a missed post stays on the stand-up for a week; older ones are the board's to chase
MISSED_DAYS = 7
# going live this soon without the client's and the head's approval blocks the post
AT_RISK_HOURS = 24
# Client Review this long is a blocker: HD Content Settings' client reminder, else this
CLIENT_WAIT_DAYS = 2
POST_LIMIT = 500
# posts in the Teams summary's Content today block
SUMMARY_POSTS = 8
POST_FIELDS = [
    "name",
    "title",
    "customer",
    "status",
    "publish_on",
    "channel",
    "platforms",
    "task_mode",
    "client_review_since",
    "sent_for_approval_on",
    "head_feedback",
    "client_feedback",
]
# the content team sorts on the post's own column (a person filter may join its team)
ORDER = "`tabHD Content Post`.`publish_on` asc"


# --- settings ----------------------------------------------------------------------


def content_departments() -> set[str]:
    """Departments with content work: Digital, and the departments of Content Calendar
    projects and of projects with post tasks. Settings → Stand-up lists these."""
    project = frappe.qb.DocType("Project")
    task = frappe.qb.DocType("Task")
    with_posts = (
        frappe.qb.from_(task)
        .select(task.project)
        .distinct()
        .where(task.content_post.isnotnull() & (task.content_post != ""))
    )
    found = (
        frappe.qb.from_(project)
        .select(project.custom_department)
        .distinct()
        .where(
            project.custom_department.isnotnull()
            & (project.custom_department != "")
            & (
                (project.project_type == CONTENT_PROJECT_TYPE)
                | project.name.isin(with_posts)
            )
        )
        .run(pluck=True)
    )
    return {CONTENT_DEPARTMENT, *found}


def client_wait_days() -> int:
    return (
        cint(frappe.get_cached_doc("HD Content Settings").client_reminder_days)
        or CLIENT_WAIT_DAYS
    )


# --- words -------------------------------------------------------------------------


def post_title(post) -> str:
    """ "Global Handwashing Day (Avera IoT)"."""
    return f"{post.title} ({post.customer})" if post.customer else post.title


def part_title(post, field: str | None) -> str:
    """ "Designer · Global Handwashing Day (Avera IoT)"."""
    label = _role_label(field) if field else _("Whole post")
    return f"{label} · {post_title(post)}"


def when(value) -> str:
    return format_datetime(value, "EEE d MMM, HH:mm")


def first_name(name: str) -> str:
    return (name or "").strip().split(" ")[0] or name


def content_fields(post, field: str | None = None) -> dict:
    """What a stand-up row keeps about its post (HD Standup Item's content fields)."""
    return {
        "content_post": post.name,
        "content_role": field,
        "customer": post.customer,
        "go_live": str(post.publish_on) if post.publish_on else None,
        "stage": post.status,
    }


def content_shape(row) -> dict | None:
    """A row's post, part, client, go-live and stage, for the page and the app."""
    if not row.get("content_post"):
        return None
    field = row.get("content_role")
    return {
        "post": row.get("content_post"),
        "part": field,
        "part_label": _role_label(field) if field in ROLE_FIELDS.values() else None,
        "client": row.get("customer"),
        "go_live": str(row.get("go_live")) if row.get("go_live") else None,
        "stage": row.get("stage"),
    }


# --- one person's stand-up -----------------------------------------------------------


def content_day(user: str, day, work: list[dict], yesterday: list[dict]):
    """The person's ContentDay, read as them; None outside the content team (an ERP
    Employee's stand-up never shows content)."""
    if not in_content_team(user):
        return None
    return ContentDay(user, day, work, yesterday)


def is_content_lead(user: str) -> bool:
    """The Digital Marketing Head and DM Coordinators: they hear about every post
    going live today, not only their own."""
    return bool(set(frappe.get_roles(user)) & set(CONTENT_LEAD_ROLES))


class ContentDay:
    """One person's content work for a stand-up. Build it as the person (the stand-up's
    `as_user`), then `merge` it into the generic sections."""

    def __init__(self, user: str, day, work: list[dict], yesterday: list[dict]):
        self.user = user
        self.day = getdate(day)
        self.now = now_datetime()
        self.lead = is_content_lead(user)
        self.work = {i["name"]: i for i in work if i["kind"] == "task"}
        done = [
            r["reference_name"] for r in yesterday if r["reference_doctype"] == "Task"
        ]
        self.parts = role_parts([*self.work, *done])
        moved = {
            r["reference_name"] for r in yesterday if r["reference_doctype"] == POST
        }
        self.posts = load_posts(self.day, {p for p, _f in self.parts.values()} | moved)
        self.teams = role_teams_of(list(self.posts))
        self.names = user_full_names(
            {
                u
                for team in self.teams.values()
                for users in team.values()
                for u in users
            }
        )
        self.tasks = role_tasks(list(self.posts)) if self.posts else {}
        self.blocked = self.waiting_parts()

    def on(self, post: str) -> bool:
        return any(self.user in users for users in self.teams.get(post, {}).values())

    def waiting_parts(self) -> dict[str, str]:
        """{task: "Waiting on Writer (Ajmal)"}: their parts not started while the post
        waits on someone else's part first (the Tasks view's rule, `post_progress`)."""
        found = {}
        for task, (name, field) in self.parts.items():
            row, post = self.work.get(task), self.posts.get(name)
            if not row or not post or row["status"] not in NOT_STARTED:
                continue
            waiting = post_progress(
                post, self.teams.get(name, {}), self.tasks, self.names
            )["waiting_on"]
            if not waiting or waiting["kind"] != "part" or waiting["role"] == field:
                continue
            people = [p for p in waiting["people"] if p["user"] != self.user]
            if len(people) < len(waiting["people"]):
                continue
            who = ", ".join(first_name(p["full_name"]) for p in people)
            label = f"{waiting['label']} ({who})" if who else waiting["label"]
            found[task] = _("Waiting on {0}").format(label)
        return found

    def merge(self, yesterday: list, today: list, blockers: list) -> tuple:
        """The sections with each role task shown once, as its part, and the content
        rows added."""
        yesterday = [self.as_part(r, _("Done")) for r in yesterday]
        # a finished part moves its post on: the move isn't listed again
        finished = {
            r.get("content_post")
            for r in yesterday
            if r["kind"] == "task" and r.get("content_post")
        }
        yesterday = [
            self.as_moved(r)
            for r in yesterday
            if not (r["reference_doctype"] == POST and r["reference_name"] in finished)
        ]
        today = [self.as_part(r) for r in today]
        listed = {r["reference_name"] for r in today if r.get("content_post")}
        going_live, held = self.post_rows()
        blockers = [
            *(self.as_part(r) for r in blockers),
            *(
                self.as_part(task_item(self.work[task], why))
                for task, why in self.blocked.items()
            ),
            *held,
        ]
        return yesterday, [*today, *self.next_part(listed), *going_live], blockers

    def as_part(self, row: dict, done: str | None = None) -> dict:
        """A generic task row as its part, with the post around it."""
        part = self.parts.get(row["reference_name"]) if row["kind"] == "task" else None
        post = self.posts.get(part[0]) if part else None
        if not post:
            return row
        return {
            **row,
            "title": part_title(post, part[1]),
            "detail": done or row["detail"],
            **content_fields(post, part[1]),
        }

    def as_moved(self, row: dict) -> dict:
        post = self.posts.get(row["reference_name"]) if row["kind"] == "post" else None
        if not post:
            return row
        detail = _("Published") if post.status == PUBLISHED else row["detail"]
        return {
            **row,
            "title": post_title(post),
            "detail": detail,
            **content_fields(post),
        }

    def next_part(self, listed: set) -> list[dict]:
        """When none of their parts is on today's list, the next one due."""
        if listed:
            return []
        upcoming = [
            row
            for task, row in self.work.items()
            if task in self.parts
            and task not in self.blocked
            and row["deadline"]
            and row["status"] in (*NOT_STARTED, WORKING)
            and not row.get("waiting_on")
            and self.parts[task][0] in self.posts
        ]
        if not upcoming:
            return []
        row = min(upcoming, key=lambda r: r["deadline"])
        due = _("Next: due {0}").format(short_date(row["deadline"]))
        return [self.as_part(task_item(row, due))]

    def post_rows(self) -> tuple[list, list]:
        """(today, blockers): each open post they're on going live today or tomorrow,
        or blocked, in one of them; for leads every post going live today too."""
        today, blockers = [], []
        tomorrow = add_days(self.day, 1)
        for post in self.posts.values():
            if post.status in CLOSED_STATUSES or not post.publish_on:
                continue
            mine = self.on(post.name)
            why = self.post_blocker(post) if mine else None
            if why:
                blockers.append(self.post_row(post, why))
                continue
            live = getdate(post.publish_on)
            if mine and live in (self.day, tomorrow):
                today.append(self.post_row(post, self.going_live(post)))
            elif self.lead and live == self.day:
                # a team post of today's that already passed its time is still theirs
                # to chase, said as missed
                today.append(self.post_row(post, self.lead_detail(post)))
        return today, blockers

    def lead_detail(self, post) -> str:
        publish_on = get_datetime(post.publish_on)
        if publish_on < self.now:
            return _("Missed · was due {0}").format(when(publish_on))
        return self.going_live(post)

    def post_blocker(self, post) -> str | None:
        """Why a post they're on is stuck, the most pressing reason only."""
        publish_on = get_datetime(post.publish_on)
        if publish_on < self.now:
            return _("Missed · was due {0}").format(when(publish_on))
        if post.status not in READY_STATUSES and publish_on <= add_to_date(
            self.now, hours=AT_RISK_HOURS
        ):
            return _("Goes live {0}, not approved yet ({1})").format(
                when(publish_on), _(post.status)
            )
        if post.status == REOPENS_PARTS:
            feedback = strip_html(post.head_feedback or post.client_feedback or "")
            feedback = feedback.strip()[:120]
            return (
                _("Changes requested: {0}").format(feedback)
                if feedback
                else _("Changes requested")
            )
        since = post.client_review_since or post.sent_for_approval_on
        if post.status == CLIENT_REVIEW and since:
            days = (self.now - get_datetime(since)).days
            if days >= client_wait_days():
                return _("Waiting on the client's approval for {0} days").format(days)
        return None

    def going_live(self, post) -> str:
        """ "Goes live today, 10:00 · Instagram, LinkedIn · Approved"."""
        live = get_datetime(post.publish_on)
        if live.date() == self.day:
            text = _("Goes live today, {0}").format(format_datetime(live, "HH:mm"))
        else:
            text = _("Goes live tomorrow, {0}").format(format_datetime(live, "HH:mm"))
        return " · ".join(
            p for p in (text, ", ".join(_platforms(post)), _(post.status)) if p
        )

    @staticmethod
    def post_row(post, detail: str) -> dict:
        return {
            **item("post", post_title(post), detail, POST, post.name),
            **content_fields(post),
        }


def role_parts(tasks: list[str]) -> dict[str, tuple[str, str | None]]:
    """{task: (post, part field)} for the role tasks among `tasks`; a task shared by
    the whole post has no field."""
    if not tasks:
        return {}
    return {
        row.name: (row.content_post, ROLE_FIELDS.get(row.content_role))
        for row in frappe.get_list(
            "Task",
            filters={
                "name": ("in", tasks),
                "content_post": ("is", "set"),
                "content_role": ("is", "set"),
            },
            fields=["name", "content_post", "content_role"],
            limit_page_length=0,
        )
    }


def load_posts(day, names: set) -> dict:
    """The posts the stand-up looks at, as the person may read them: going live from a
    week ago to tomorrow, waiting on the client or on changes, and `names` (their
    parts' posts and the ones they moved). Cancelled posts are left out."""
    or_filters = [
        [
            "publish_on",
            "between",
            [f"{add_days(day, -MISSED_DAYS)} 00:00:00", f"{add_days(day, 1)} 23:59:59"],
        ],
        ["status", "in", [CLIENT_REVIEW, REOPENS_PARTS]],
    ]
    if names:
        or_filters.append(["name", "in", list(names)])
    rows = frappe.get_list(
        POST,
        filters=[["status", "!=", "Cancelled"]],
        or_filters=or_filters,
        fields=POST_FIELDS,
        order_by=ORDER,
        limit_page_length=POST_LIMIT,
    )
    return {p.name: p for p in rows}


# --- the team's Content today --------------------------------------------------------


def content_today(day, users, as_viewer: bool) -> list[dict]:
    """The posts going live on `day` that the department's people are on, and their
    posts missed in the week before; missed and not-approved first. Read as the viewer
    (the team view), or whole for the Teams summary, which goes to the department's own
    channel."""
    day = getdate(day)
    now = now_datetime()
    users = set(users)
    read = frappe.get_list if as_viewer else frappe.get_all
    rows = read(
        POST,
        filters=[
            ["status", "!=", "Cancelled"],
            [
                "publish_on",
                "between",
                [f"{add_days(day, -MISSED_DAYS)} 00:00:00", f"{day} 23:59:59"],
            ],
        ],
        fields=POST_FIELDS,
        order_by=ORDER,
        # eight days of posts, filtered by people below: a cap could drop theirs
        limit_page_length=0,
    )
    teams = role_teams_of([r.name for r in rows])
    found = []
    for post in rows:
        people = list(
            dict.fromkeys(u for us in teams.get(post.name, {}).values() for u in us)
        )
        live = get_datetime(post.publish_on)
        missed = live < now and post.status not in CLOSED_STATUSES
        if not users & set(people) or (live.date() != day and not missed):
            continue
        found.append((post, people, post_state(post, missed)))
    names = user_full_names({u for _p, people, _s in found for u in people})
    out = [
        {
            "post": post.name,
            "title": post.title,
            "client": post.customer,
            "go_live": str(post.publish_on),
            "channels": _platforms(post),
            "stage": post.status,
            "state": state,
            "people": [{"user": u, "full_name": names.get(u, u)} for u in people],
            "route": f"/content?post={post.name}",
        }
        for post, people, state in found
    ]
    out.sort(
        key=lambda p: (p["state"] != "missed", p["state"] != "at_risk", p["go_live"])
    )
    return out


def post_state(post, missed: bool) -> str:
    """missed, at_risk (not approved yet), published or ready."""
    if missed:
        return "missed"
    if post.status == PUBLISHED:
        return "published"
    if post.status not in READY_STATUSES:
        return "at_risk"
    return "ready"


def summary_lines(posts: list[dict]) -> list[str]:
    """The Teams summary's block: "**Content today (3)**", then one line per post."""
    from helpdesk.chat_notifications import helpdesk_url

    if not posts:
        return []
    lines = [f"**{_('Content today')} ({len(posts)})**"]
    for post in posts[:SUMMARY_POSTS]:
        live = get_datetime(post["go_live"])
        names = ", ".join(first_name(p["full_name"]) for p in post["people"])
        title = md_link(post["title"], helpdesk_url(post["route"]))
        if post["state"] == "missed":
            parts = [
                f"{_('Missed')}: {title}",
                post["client"],
                _("was due {0}").format(when(live)),
                names,
            ]
        else:
            lead = f"{_('Not approved')}: " if post["state"] == "at_risk" else ""
            parts = [
                f"{lead}{format_datetime(live, 'HH:mm')} {title}",
                post["client"],
                ", ".join(post["channels"]),
                _(post["stage"]),
                names if post["state"] == "at_risk" else None,
            ]
        lines.append(
            "- " + " · ".join(plain(p) if i else p for i, p in enumerate(parts) if p)
        )
    if len(posts) > SUMMARY_POSTS:
        lines.append("- " + _("and {0} more").format(len(posts) - SUMMARY_POSTS))
    return lines
