"""The async daily stand-up: yesterday, today and blockers, without the meeting room.

docs/standup.md has the flow. Every 15 minutes `run()`, on working days only:
- at the open time, fills in a draft HD Standup for everyone with work (`autofill`,
  from the queries My Work, Home and the Scoreboard already use) and tells them in
  the app and in Teams ("Your stand-up is ready…"); people on leave and people with
  no open work and nothing done the day before are skipped;
- at the reminder time, reminds once whoever hasn't submitted;
- at the post time, posts each department's summary to its Teams channel (the
  escalation channel when it has none): an AI headline when the AI answers, the
  blockers and who needs help first, then each person's yesterday and today; drafts
  go out as filled in, marked "(auto)".

Task control, not time tracking: hours appear as a fact (when the setting is on),
never in the AI's facts and never as a judgement.
"""

import json
import re
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import (
    cint,
    flt,
    formatdate,
    get_fullname,
    get_time,
    getdate,
    now_datetime,
    strip_html,
)

from helpdesk import home_plan
from helpdesk import team_dashboard as td
from helpdesk.ai_engine import call_haiku
from helpdesk.api.work import ON_HOLD, PENDING_REVIEW, WAITING_ON_TASK
from helpdesk.follow_ups import WorkCalendar, open_work_owners
from helpdesk.tasky.permissions import (
    PROJECT_MANAGER_ROLE,
    department_heads,
    departments_headed,
    get_coordinated_projects,
    get_led_projects,
    get_managed_projects,
    hidden_departments,
    is_tasky_admin,
)
from helpdesk.utils import assigned_to_filter
from helpdesk.work_calendar import leave_today, on_leave
from helpdesk.work_reminders import enabled_users, notify_users

SETTINGS = "HD Standup Settings"
STANDUP = "HD Standup"
ITEM = "HD Standup Item"
DRAFT = "Draft"
SUBMITTED = "Submitted"
AUTO_POSTED = "Auto-posted"
SECTIONS = ("yesterday", "today", "blockers")
# free text under yesterday and today; a blocker is always its own row, so it can be acted on
NOTE_FIELDS = {"yesterday": "yesterday_note", "today": "today_note"}
PATH = "/standup"
# Settings → Stand-up's times, when a site never saved them
DEFAULT_TIMES = {"open_at": "09:00", "remind_at": "10:00", "post_at": "10:30"}
# admins open the people who are in no department with this team name
NO_DEPARTMENT = "__none__"
LIST_LIMIT = 200
MAX_ITEMS = 30
MAX_TEXT = 300
MAX_NOTE = 1000
# per person and section in the Teams summary
SUMMARY_ITEMS = 4
HISTORY_LIMIT = 30
TEXT_KINDS = ("plan", "note")

HEADLINE_PROMPT = """You write the first lines of one team's daily stand-up summary at TBO, a company that implements ERPNext, builds apps and websites and runs digital marketing.
Use only the facts in the JSON you are given. Never invent people, tasks, numbers or causes. Every number you write must appear in the facts.
Write 2 or 3 short plain sentences: what the team finished on the last working day, what it works on today, and what is blocked or who needs help, by name. Be kind and factual; never judge people or hours. No HTML, no markdown, no numbering.
Reply with JSON only: {"lines": ["...", "..."]}"""


def get_settings():
    return frappe.get_cached_doc(SETTINGS)


def is_enabled() -> bool:
    return bool(cint(get_settings().enabled))


def setting_time(settings, field: str) -> str:
    """"09:00": the stored time, or its default on a site that never saved them."""
    return (settings.get(field) or DEFAULT_TIMES[field]).strip()


def flag(settings, field: str) -> bool:
    """A switch that is on until someone turns it off (team views, hours)."""
    value = settings.get(field)
    return True if value is None else bool(cint(value))


def standup_name(user: str, day) -> str:
    return f"SU-{getdate(day)}-{user}"


@contextmanager
def as_user(user: str):
    """Read someone's work as them, so only what they may open is listed."""
    previous = frappe.session.user
    if previous == user:
        yield
        return
    frappe.set_user(user)  # their own work, as Home builds it - nosemgrep
    try:
        yield
    finally:
        frappe.set_user(previous)  # back to whoever ran the job - nosemgrep


# --- auto-fill ---------------------------------------------------------------


def item(
    kind: str,
    title: str,
    detail: str | None = None,
    doctype: str | None = None,
    name=None,
    project: str | None = None,
) -> dict:
    return {
        "kind": kind,
        "title": title,
        "detail": detail,
        "reference_doctype": doctype,
        "reference_name": str(name) if name else None,
        "project": project,
        "auto": 1,
    }


def task_item(task: dict, detail: str) -> dict:
    return item("task", task["title"], detail, "Task", task["name"], task["project"])


def autofill(
    user: str, day, calendar: WorkCalendar | None = None, hours: dict | None = None
) -> dict:
    """What `user`'s stand-up for `day` starts with, from their own work. Writes
    nothing. `hours` ({user: hours} on the previous working day) saves a query per
    person when a run fills everyone's; leave it out to read it here."""
    from helpdesk.api.home import _add_timers
    from helpdesk.api.work import get_my_work

    day = getdate(day)
    calendar = calendar or WorkCalendar(day)
    previous = calendar.previous_working_day()
    with as_user(user):
        try:
            work = get_my_work()["items"]
        except frappe.PermissionError:
            work = []
        yesterday = done_on(user, previous)
        tasks = [i for i in work if i["kind"] == "task"]
        _add_timers(tasks)
    today, blockers = plan_and_blockers(work, day, calendar.next_working_day())
    today += [item("plan", step) for step in stored_plan(user, day)]
    if hours is None:
        hours = hours_by_user(previous)
    return {
        "previous_day": str(previous),
        "yesterday": yesterday,
        "today": today,
        "blockers": blockers,
        "hours": round(flt(hours.get(user)), 1),
    }


def done_on(user: str, day) -> list[dict]:
    """What the person finished or moved on `day`: tasks completed, tickets resolved
    or replied to, content posts moved on. Only what they may open."""
    start, end = f"{day} 00:00:00", f"{day} 23:59:59"
    tasks = frappe.get_list(
        "Task",
        filters={
            "name": assigned_to_filter("Task", user),
            "status": "Completed",
            "completed_on": getdate(day),
        },
        fields=["name", "subject", "project"],
        order_by="modified asc",
        limit_page_length=LIST_LIMIT,
    )
    resolved = frappe.get_list(
        "HD Ticket",
        filters={
            "name": assigned_to_filter("HD Ticket", user),
            "status_category": "Resolved",
            "resolution_date": ("between", [start, end]),
        },
        fields=["name", "subject"],
        limit_page_length=LIST_LIMIT,
    )
    resolved_names = {str(t.name) for t in resolved}
    replied = [
        name for name in replied_tickets(user, start, end) if name not in resolved_names
    ]
    replied_rows = (
        frappe.get_list(
            "HD Ticket",
            filters={"name": ("in", replied)},
            fields=["name", "subject"],
            limit_page_length=LIST_LIMIT,
        )
        if replied
        else []
    )
    moved = moved_posts(user, start, end)
    posts = (
        frappe.get_list(
            "HD Content Post",
            filters={"name": ("in", moved)},
            fields=["name", "title", "status"],
            limit_page_length=LIST_LIMIT,
        )
        if moved
        else []
    )
    return [
        *(
            item("task", t.subject, _("Completed"), "Task", t.name, t.project)
            for t in tasks
        ),
        *(
            item("ticket", t.subject, _("Resolved"), "HD Ticket", t.name)
            for t in resolved
        ),
        *(
            item("ticket", t.subject, _("Replied"), "HD Ticket", t.name)
            for t in replied_rows
        ),
        *(
            item(
                "post",
                p.title,
                _("Moved to {0}").format(_(p.status)),
                "HD Content Post",
                p.name,
            )
            for p in posts
        ),
    ]


def replied_tickets(user: str, start: str, end: str) -> list[str]:
    """Tickets the person sent a reply on between `start` and `end`."""
    communication = frappe.qb.DocType("Communication")
    return [
        str(name)
        for name in frappe.qb.from_(communication)
        .select(communication.reference_name)
        .distinct()
        .where(
            (communication.reference_doctype == "HD Ticket")
            & (communication.owner == user)
            & (communication.sent_or_received == "Sent")
            & (communication.communication_type == "Communication")
            & communication.creation.between(start, end)
        )
        .run(pluck=True)
    ]


def moved_posts(user: str, start: str, end: str) -> list[str]:
    """Content posts whose stage the person changed between `start` and `end`, from
    the posts' history."""
    version = frappe.qb.DocType("Version")
    return (
        frappe.qb.from_(version)
        .select(version.docname)
        .distinct()
        .where(
            (version.ref_doctype == "HD Content Post")
            & (version.owner == user)
            & version.creation.between(start, end)
            & version.data.like('%"status"%')
        )
        .run(pluck=True)
    )


def plan_and_blockers(work: list[dict], day, next_day) -> tuple[list, list]:
    """Today: overdue, due today, in progress, due on the next working day. Blockers:
    held work, work waiting on another task, overdue key tasks and tickets waiting on
    a task. Each task lands in one of them at most."""
    today, tomorrow = str(getdate(day)), str(getdate(next_day))
    planned, blockers = [], []
    for task in (i for i in work if i["kind"] == "task"):
        blocker = task_blocker(task)
        if blocker:
            blockers.append(task_item(task, blocker))
            continue
        rank_detail = task_plan(task, today, tomorrow)
        if rank_detail:
            planned.append((rank_detail[0], task_item(task, rank_detail[1])))
    for ticket in work:
        if ticket["kind"] == "ticket" and ticket["status"] == WAITING_ON_TASK:
            blockers.append(
                item(
                    "ticket",
                    ticket["title"],
                    _("Waiting on a task"),
                    "HD Ticket",
                    ticket["name"],
                )
            )
    planned.sort(key=lambda pair: pair[0])
    return [entry for _rank, entry in planned], blockers


def task_blocker(task: dict) -> str | None:
    """Why the task is blocked, or None."""
    if task["status"] == ON_HOLD:
        days = task.get("hold_days") or 0
        text = _("On hold {0} day(s): {1}").format(
            days, task.get("hold_reason") or _("no reason")
        )
        note = (task.get("hold_note") or "").strip()
        return f"{text} · {note}" if note else text
    if task.get("waiting_on"):
        return _("Waiting on {0}").format(task["waiting_on"])
    if task["is_overdue"] and task["is_key"]:
        return _("Key task, overdue since {0}").format(short_date(task["deadline"]))
    return None


def task_plan(task: dict, today: str, tomorrow: str) -> tuple[int, str] | None:
    """(order, why) for a task on today's list, or None."""
    if task["status"] == PENDING_REVIEW:
        return None
    if task["is_overdue"]:
        return 0, _("Overdue since {0}").format(short_date(task["deadline"]))
    if task["deadline"] == today:
        return 1, _("Due today")
    if task["status"] == "Working":
        if task.get("timer") == "running":
            return 2, _("In progress, timer running")
        return 2, _("In progress")
    if task["deadline"] == tomorrow:
        return 3, _("Due {0}").format(short_date(tomorrow))
    return None


def short_date(value) -> str:
    return formatdate(value, "EEE d MMM") if value else ""


def stored_plan(user: str, day) -> list[str]:
    """Today's Home plan when Home already wrote one: the stand-up never calls the AI
    for it (the follow-up digest reads the same cache)."""
    if getdate(day) != getdate(now_datetime()):
        return []
    cached = frappe.cache.get_value(home_plan.plan_cache_key(user), expires=True)
    return [s["text"] for s in (cached or {}).get("steps") or []]


def hours_by_user(day) -> dict[str, float]:
    """{user: hours logged on `day`}, the Scoreboard's timesheet query."""
    totals = {}
    for row in td.logged_hours(day, day):
        totals[row["user"]] = totals.get(row["user"], 0) + row["hours"]
    return totals


# --- departments ---------------------------------------------------------------


def home_departments(users) -> dict[str, str | None]:
    """{user: their department}: one they head, else the department with most of their
    open tasks, else one whose open projects they are on (in Settings → Departments'
    order), else None."""
    from helpdesk.api.team_dashboard import department_members

    users = set(users)
    order = td.active_departments()
    found = {}
    for department in order:
        for head in department_heads(department):
            if head in users:
                found.setdefault(head, department)
    counts = open_task_departments(users - set(found), order)
    for user, by_department in counts.items():
        found[user] = max(by_department, key=lambda d: (by_department[d], -order.index(d)))
    members = department_members(order) if users - set(found) else {}
    for department in order:
        for user in members.get(department, set()) & (users - set(found)):
            found[user] = department
    return {user: found.get(user) for user in users}


def open_task_departments(users: set, departments: list[str]) -> dict[str, dict]:
    """{user: {department: open tasks assigned to them there}}, in one query."""
    if not users or not departments:
        return {}
    todo = frappe.qb.DocType("ToDo")
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(todo)
        .join(task)
        .on(task.name == todo.reference_name)
        .join(project)
        .on(project.name == task.project)
        .select(todo.allocated_to, project.custom_department, Count(task.name))
        .where(
            (todo.reference_type == "Task")
            & (todo.status == "Open")
            & todo.allocated_to.isin(list(users))
            & task.status.notin(["Completed", "Cancelled", "Template"])
            & project.custom_department.isin(departments)
        )
        .groupby(todo.allocated_to, project.custom_department)
        .run()
    )
    found = {}
    for user, department, count in rows:
        found.setdefault(user, {})[department] = count
    return found


def included_departments(settings) -> list[str]:
    return [row.department for row in settings.get("departments") or []]


# --- the run ---------------------------------------------------------------------


def run():
    """Every 15 minutes (hooks.py): open drafts, remind, post, each once a working day."""
    settings = get_settings()
    if not cint(settings.enabled):
        return
    now = now_datetime()
    calendar = WorkCalendar(now.date())
    if not calendar.is_working_day(now.date()):
        return
    process(settings, now, calendar)


def process(settings, now: datetime, calendar: WorkCalendar) -> None:
    today = now.date()
    opened = False
    if is_due(settings, "open_at", "opened_on", now):
        record(settings, "opened_on", today)
        open_drafts(settings, today, calendar)
        opened = True
    if is_due(settings, "remind_at", "reminded_on", now):
        record(settings, "reminded_on", today)
        # drafts that only just opened (the server was down) aren't reminded at once
        if not opened:
            send_reminders(settings, today)
    if is_due(settings, "post_at", "posted_on", now):
        record(settings, "posted_on", today)
        post_summaries(settings, today, calendar)


def is_due(settings, time_field: str, done_field: str, now: datetime) -> bool:
    """The step's time has come today and it hasn't run today."""
    at = datetime.combine(now.date(), get_time(setting_time(settings, time_field)))
    done = settings.get(done_field)
    return now >= at and (not done or getdate(done) < now.date())


def record(settings, field: str, day) -> None:
    """Recorded and committed before anything goes out: chat posts can't be rolled
    back, so a job that dies halfway must not send them twice."""
    frappe.db.set_single_value(SETTINGS, field, day)
    settings.set(field, day)
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    frappe.db.commit()  # nosemgrep


def candidates(settings, day) -> tuple[list[str], dict]:
    """Active agents not on leave `day`, in the stand-up's departments, with each
    one's department."""
    agents = frappe.get_all("HD Agent", filters={"is_active": 1}, pluck="user")
    away = on_leave(day)
    users = [u for u in enabled_users(agents) if u not in away]
    departments = home_departments(users)
    included = set(included_departments(settings))
    if included:
        users = [u for u in users if departments.get(u) in included]
    return users, departments


def open_drafts(settings, day, calendar: WorkCalendar) -> list[str]:
    """Everyone's draft for `day`, once (a person who has one keeps it), and the
    message that it is ready. Returns the drafts created."""
    users, departments = candidates(settings, day)
    busy = open_work_owners()
    hours = hours_by_user(calendar.previous_working_day())
    created = []
    for user in users:
        if frappe.db.exists(STANDUP, standup_name(user, day)):
            continue
        try:
            filled = autofill(user, day, calendar, hours)
            # nothing open and nothing done: no stand-up to write
            if user not in busy and not filled["yesterday"]:
                continue
            doc = new_standup(user, day, departments.get(user), filled)
            notify_users(
                [user],
                STANDUP,
                doc.name,
                _("Your stand-up is ready, check it and submit (1 min)"),
                link=PATH,
            )
            created.append(doc.name)
        except Exception:  # noqa: BLE001 - one person's draft must not stop the rest
            frappe.log_error(title=f"Stand-up draft failed for {user}")
    return created


def new_standup(user: str, day, department: str | None, filled: dict):
    """A draft HD Standup from `filled` (autofill's answer); the one already there
    when two requests race."""
    doc = frappe.get_doc(
        {
            "doctype": STANDUP,
            "user": user,
            "date": getdate(day),
            "department": department,
            "status": DRAFT,
            "hours": filled["hours"],
            **{section: filled[section] for section in SECTIONS},
        }
    )
    try:
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        return frappe.get_doc(STANDUP, standup_name(user, day))
    return doc


def send_reminders(settings, day) -> None:
    """One reminder to everyone whose stand-up is still a draft."""
    away = on_leave(day)
    text = _("Your stand-up isn't submitted yet. It goes to your team at {0}.").format(
        setting_time(settings, "post_at")
    )
    for draft in frappe.get_all(
        STANDUP,
        filters={"date": getdate(day), "status": DRAFT},
        fields=["name", "user"],
        limit_page_length=0,
    ):
        if draft.user not in away:
            notify_users([draft.user], STANDUP, draft.name, text, link=PATH)


def post_summaries(settings, day, calendar: WorkCalendar | None = None) -> dict:
    """Drafts become Auto-posted, then each department's summary goes to its channel.
    Returns {department: text} of what was composed."""
    from helpdesk.chat_notifications import ChatError
    from helpdesk.chat_notifications import is_enabled as chat_enabled

    table = frappe.qb.DocType(STANDUP)
    (
        frappe.qb.update(table)
        .set(table.status, AUTO_POSTED)
        .where((table.date == getdate(day)) & (table.status == DRAFT))
        .run()
    )
    channels = {
        row.department: row.get_password("channel_webhook", raise_exception=False)
        for row in settings.get("departments") or []
    }
    posted = {}
    for department, docs in by_department(load_standups(day)).items():
        text = compose_summary(department, docs, day, settings)
        posted[department] = text
        if not chat_enabled():
            continue
        try:
            post_summary(text, channels.get(department), team_path(department, day))
        except (ChatError, requests.RequestException):
            frappe.log_error(title=f"Stand-up summary not posted for {department}")
    return posted


def post_summary(text: str, webhook: str | None, path: str) -> None:
    """To the department's own Teams channel, else the escalation channel."""
    from helpdesk.chat_notifications import (
        TEAMS,
        helpdesk_url,
        post_to_channel,
        teams_message,
        teams_post_url,
    )
    from helpdesk.chat_notifications import get_settings as chat_settings

    url = helpdesk_url(path)
    if webhook and chat_settings().platform == TEAMS:
        teams_post_url(webhook, teams_message(text, url))
    else:
        post_to_channel(text, url)


def team_path(department: str | None, day) -> str:
    query = urlencode({"team": department or NO_DEPARTMENT, "date": str(getdate(day))})
    return f"{PATH}?{query}"


def load_standups(day, department: str | None = False, users=None) -> list:
    """The day's stand-ups (all of them, one department's, or `users`'), each with its
    rows, in two queries."""
    filters = {"date": getdate(day)}
    if department is not False:
        filters["department"] = department or ("is", "not set")
    if users is not None:
        filters["user"] = ("in", list(users) or [""])
    docs = frappe.get_all(
        STANDUP,
        filters=filters,
        fields=[
            "name",
            "user",
            "full_name",
            "date",
            "department",
            "status",
            "submitted_on",
            "needs_help",
            "hours",
            *NOTE_FIELDS.values(),
        ],
        order_by="full_name asc",
        limit_page_length=0,
    )
    rows = frappe.get_all(
        ITEM,
        filters={"parenttype": STANDUP, "parent": ("in", [d.name for d in docs] or [""])},
        fields=[
            "name",
            "parent",
            "parentfield",
            "kind",
            "title",
            "detail",
            "reference_doctype",
            "reference_name",
            "project",
            "auto",
            "helper",
            "help_task",
        ],
        order_by="idx asc",
        limit_page_length=0,
    )
    for doc in docs:
        for section in SECTIONS:
            doc[section] = []
    by_name = {d.name: d for d in docs}
    for row in rows:
        by_name[row.parent][row.parentfield].append(row)
    return docs


def by_department(docs: list) -> dict:
    groups = {}
    for doc in docs:
        groups.setdefault(doc.department or "", []).append(doc)
    return groups


# --- the Teams summary -----------------------------------------------------------


def compose_summary(department: str | None, docs: list, day, settings) -> str:
    """The department's summary as Teams Markdown: the headline, blockers and help
    first (with names), then each person's yesterday and today."""
    from helpdesk.chat_notifications import helpdesk_url

    label = department or _("No department")
    lines = [f"**{_('Stand-up')} · {label} · {formatdate(day, 'EEE d MMM')}**"]
    headline = write_headline(label, docs, day)
    if headline:
        lines += ["", *headline]
    flagged = blocker_lines(docs)
    if flagged:
        lines += ["", f"**{_('Blockers and help needed')} ({len(flagged)})**", *flagged]
    hours = flag(settings, "include_hours")
    for doc in docs:
        name = doc.full_name or doc.user
        if doc.status == AUTO_POSTED:
            name = _("{0} (auto)").format(name)
        done = compact(doc.yesterday, doc.yesterday_note)
        if hours and flt(doc.hours):
            done += " · " + _("{0}h logged").format(f"{flt(doc.hours):g}")
        lines += [
            "",
            f"**{name}**",
            _("Yesterday: {0}").format(done),
            _("Today: {0}").format(compact(doc.today, doc.today_note)),
        ]
    lines += [
        "",
        md_link(_("Open the stand-up"), helpdesk_url(team_path(department, day))),
    ]
    return "\n".join(lines)


def blocker_lines(docs: list) -> list[str]:
    """One line per blocker, then the people who asked for help without one."""
    from helpdesk.chat_notifications import helpdesk_url

    lines = []
    for doc in docs:
        name = doc.full_name or doc.user
        who = _("{0} (needs help)").format(name) if doc.needs_help else name
        for row in doc.blockers:
            title = (
                md_link(row.title, helpdesk_url(item_path(row)))
                if item_path(row)
                else plain(row.title)
            )
            detail = f": {plain(row.detail)}" if row.detail else ""
            lines.append(f"- {who}: {title}{detail}")
        if doc.needs_help and not doc.blockers:
            lines.append(f"- {who}")
    return lines


def compact(rows: list, note: str | None) -> str:
    """"Fix GST report (Completed); Bank reconciliation (Resolved) and 2 more · note"."""
    from helpdesk.chat_notifications import helpdesk_url

    parts = []
    for row in rows[:SUMMARY_ITEMS]:
        path = item_path(row)
        title = md_link(row.title, helpdesk_url(path)) if path else plain(row.title)
        parts.append(f"{title} ({plain(row.detail)})" if row.detail else title)
    text = "; ".join(parts)
    if len(rows) > SUMMARY_ITEMS:
        text += " " + _("and {0} more").format(len(rows) - SUMMARY_ITEMS)
    note = clean_text(note, MAX_TEXT)
    if note:
        text = f"{text} · {plain(note)}" if text else plain(note)
    return text or _("nothing listed")


def plain(text: str | None) -> str:
    """Text that can't break the Markdown around it."""
    return re.sub(r"[\[\]*_`]", "", str(text or "")).strip()


def md_link(text: str, url: str) -> str:
    return f"[{plain(text)}]({url})"


def item_path(row) -> str | None:
    """Where an item opens in /helpdesk."""
    from helpdesk.work_reminders import helpdesk_path

    doctype, name = row.get("reference_doctype"), row.get("reference_name")
    if not doctype or not name:
        return None
    if doctype == "Task":
        project = row.get("project")
        return f"/projects/{project}" if project else "/my-work"
    if doctype == "HD Content Post":
        return "/content"
    return helpdesk_path(doctype, name)


def headline_facts(label: str, docs: list, day) -> dict:
    """What the AI may use: counts and titles, never hours."""
    return {
        "team": label,
        "date": f"{getdate(day)} ({getdate(day).strftime('%A')})",
        "people": len(docs),
        "submitted": sum(d.status == SUBMITTED for d in docs),
        "finished_last_working_day": [
            {"person": d.full_name, "items": [r.title for r in d.yesterday[:5]]}
            for d in docs
            if d.yesterday
        ],
        "planned_today": [
            {"person": d.full_name, "items": [r.title for r in d.today[:5]]}
            for d in docs
            if d.today
        ],
        "blockers": [
            {"person": d.full_name, "blocker": r.title, "why": r.detail}
            for d in docs
            for r in d.blockers
        ],
        "needs_help": [d.full_name for d in docs if d.needs_help],
    }


def write_headline(label: str, docs: list, day) -> list[str]:
    """Two or three lines from the AI, or none when it is off, fails or answers with
    a number that isn't in the facts. The summary goes out either way."""
    from helpdesk.ai_suggestion import is_ai_configured

    if not docs or not is_ai_configured():
        return []
    facts = headline_facts(label, docs, day)
    try:
        result = call_haiku(HEADLINE_PROMPT, json.dumps(facts, indent=1, default=str))
    except Exception:  # noqa: BLE001 - provider errors vary; the summary still posts
        frappe.log_error(title="Stand-up headline failed")
        return []
    response = result.get("response") if isinstance(result, dict) else None
    lines = home_plan.clean_steps(
        {"steps": response.get("lines")} if isinstance(response, dict) else None,
        facts,
    )
    return lines[:3] if len(lines) >= 2 else []


# --- who sees what ---------------------------------------------------------------


def team_departments(user: str) -> list[str]:
    """The departments whose team view (nudge, blocker actions, plan against done) the
    user gets: every one for admins; for others, per Settings → Stand-up, the ones they
    head and the ones of the projects they lead, coordinate or manage. Never one the
    department walls hide from them."""
    order = td.active_departments()
    if is_tasky_admin(user):
        return [*order, NO_DEPARTMENT]
    settings = get_settings()
    found = set()
    if flag(settings, "team_view_heads"):
        found |= set(departments_headed(user))
    projects = set()
    if flag(settings, "team_view_leads"):
        projects |= set(get_led_projects(user)) | set(get_coordinated_projects(user))
    if flag(settings, "team_view_project_managers") and (
        PROJECT_MANAGER_ROLE in frappe.get_roles(user)
    ):
        projects |= set(get_managed_projects(user))
    if projects:
        found |= set(
            frappe.get_all(
                "Project",
                filters={
                    "name": ("in", list(projects)),
                    "status": "Open",
                    "custom_department": ("is", "set"),
                },
                pluck="custom_department",
            )
        )
    hidden = set(hidden_departments(user))
    return [d for d in order if d in found and d not in hidden]


def own_department(user: str, day) -> str | None:
    stored = frappe.db.get_value(STANDUP, standup_name(user, day), "department")
    return stored or home_departments([user]).get(user)


def check_team(user: str, team: str, day) -> bool:
    """True when the user gets the team view of `team`; False for a plain member's own
    department (the channel's content, read-only); refused otherwise."""
    if team in team_departments(user):
        return True
    own = own_department(user, day) or NO_DEPARTMENT
    if team == own and team not in hidden_departments(user):
        return False
    frappe.throw(
        _("You see your own department's stand-up only."), frappe.PermissionError
    )


def visible(rows: list, hidden_projects: set) -> list:
    return [r for r in rows if not (r.project and r.project in hidden_projects)]


def walled_projects(user: str, docs: list) -> set:
    """The projects among the stand-ups' rows that the department walls hide from
    `user`."""
    hidden = hidden_departments(user)
    projects = {r.project for d in docs for s in SECTIONS for r in d[s] if r.project}
    if not hidden or not projects:
        return set()
    return set(
        frappe.get_all(
            "Project",
            filters={"name": ("in", list(projects)), "custom_department": ("in", hidden)},
            pluck="name",
        )
    )


# --- shapes for the page and the app -------------------------------------------


def item_shape(row, names: dict | None = None) -> dict:
    helper = row.get("helper")
    return {
        "id": row.get("name"),
        "kind": row.get("kind"),
        "title": row.get("title"),
        "detail": row.get("detail"),
        "reference_doctype": row.get("reference_doctype"),
        "reference_name": row.get("reference_name"),
        "project": row.get("project"),
        "auto": bool(cint(row.get("auto"))),
        "route": item_path(row),
        "helper": helper,
        "helper_name": (names or {}).get(helper) or (get_fullname(helper) if helper else None),
        "help_task": row.get("help_task"),
    }


def standup_shape(doc, include_hours: bool, hidden_projects: set | None = None) -> dict:
    hidden_projects = hidden_projects or set()
    return {
        "name": doc.get("name"),
        "user": doc.user,
        "full_name": doc.get("full_name") or get_fullname(doc.user),
        "date": str(getdate(doc.date)),
        "department": doc.get("department"),
        "status": doc.get("status") or DRAFT,
        "submitted_on": str(doc.submitted_on) if doc.get("submitted_on") else None,
        "needs_help": bool(cint(doc.get("needs_help"))),
        "hours": round(flt(doc.get("hours")), 1) if include_hours else None,
        **{
            section: [
                item_shape(r) for r in visible(doc.get(section) or [], hidden_projects)
            ]
            for section in SECTIONS
        },
        "notes": {
            section: doc.get(field) or "" for section, field in NOTE_FIELDS.items()
        },
    }


def my_standup(user: str, date: str | None = None) -> dict:
    """The person's stand-up for `date` (today): the stored one, else for today a
    fresh draft from their work that isn't saved until they save it."""
    settings = get_settings()
    today = getdate(now_datetime())
    day = getdate(date) if date else today
    if day > today:
        frappe.throw(_("There's no stand-up for a day that hasn't come yet."))
    enabled = bool(cint(settings.enabled))
    name = standup_name(user, day)
    doc = frappe.get_doc(STANDUP, name) if frappe.db.exists(STANDUP, name) else None
    include_hours = flag(settings, "include_hours")
    calendar = WorkCalendar(day)
    previous = calendar.previous_working_day()
    shape = None
    if doc:
        shape = standup_shape(doc, include_hours)
    elif day == today and enabled:
        filled = autofill(user, day, calendar)
        shape = standup_shape(
            frappe._dict(
                user=user,
                date=day,
                department=own_department(user, day),
                status=DRAFT,
                hours=filled["hours"],
                **{s: [frappe._dict(r) for r in filled[s]] for s in SECTIONS},
            ),
            include_hours,
        )
    teams = team_departments(user)
    return {
        "enabled": enabled,
        "date": str(day),
        "previous_day": str(previous),
        "is_working_day": bool(calendar.is_working_day(day)),
        "editable": enabled and day == today,
        "post_at": setting_time(settings, "post_at"),
        "posted": bool(settings.posted_on) and getdate(settings.posted_on) == day,
        "standup": shape,
        "teams": teams,
        "department": (shape or {}).get("department") or own_department(user, day),
    }


def save(user: str, values: dict, submit: bool = False) -> dict:
    """Today's stand-up as the person edited it. Linked items can only be kept or
    removed (so nobody can link work they don't have); text items and notes are theirs."""
    if not is_enabled():
        frappe.throw(_("The daily stand-up isn't switched on."))
    today = getdate(now_datetime())
    name = standup_name(user, today)
    if frappe.db.exists(STANDUP, name):
        doc = frappe.get_doc(STANDUP, name)
    else:
        doc = new_standup(user, today, own_department(user, today), autofill(user, today))
    for section in SECTIONS:
        if section in values:
            doc.set(section, edited_rows(doc, section, values.get(section) or []))
    for section, field in NOTE_FIELDS.items():
        if field in values or section in (values.get("notes") or {}):
            raw = (values.get("notes") or {}).get(section, values.get(field))
            doc.set(field, clean_text(raw, MAX_NOTE))
    if "needs_help" in values:
        doc.needs_help = cint(values.get("needs_help"))
    if submit:
        doc.status = SUBMITTED
        doc.submitted_on = now_datetime()
    doc.save(ignore_permissions=True)
    return my_standup(user)


def edited_rows(doc, section: str, rows: list) -> list[dict]:
    """The section's rows as sent: linked ones only if the section already had them
    (taken from the stored row, helper and help task included), text ones as typed."""
    stored = {
        (r.reference_doctype, str(r.reference_name)): r
        for r in doc.get(section)
        if r.reference_name
    }
    kept = []
    for raw in rows[:MAX_ITEMS]:
        raw = frappe._dict(raw if isinstance(raw, dict) else {"title": raw})
        if raw.reference_name:
            row = stored.pop((raw.reference_doctype, str(raw.reference_name)), None)
            if row:
                kept.append(
                    {
                        f: row.get(f)
                        for f in (
                            "kind",
                            "title",
                            "detail",
                            "reference_doctype",
                            "reference_name",
                            "project",
                            "auto",
                            "helper",
                            "help_task",
                        )
                    }
                )
            continue
        title = clean_text(raw.title, MAX_TEXT)
        if title:
            kind = raw.kind if raw.kind in TEXT_KINDS else "note"
            kept.append({"kind": kind, "title": title, "auto": cint(raw.auto) if kind == "plan" else 0})
    return kept


def clean_text(value, limit: int) -> str:
    return strip_html(str(value or "")).strip()[:limit]


def team_standup(viewer: str, team: str | None = None, date: str | None = None) -> dict:
    """One department's stand-ups for a day. Leads (see team_departments) get who is
    pending, the blockers with actions and plan against done; a plain member gets their
    own department's summary, the channel's content."""
    settings = get_settings()
    today = getdate(now_datetime())
    day = getdate(date) if date else today
    teams = team_departments(viewer)
    team = team or (teams[0] if teams else own_department(viewer, day) or NO_DEPARTMENT)
    lead = check_team(viewer, team, day)
    department = None if team == NO_DEPARTMENT else team
    docs = load_standups(day, department)
    hidden = walled_projects(viewer, docs)
    include_hours = flag(settings, "include_hours")
    calendar = WorkCalendar(day)
    previous = calendar.previous_working_day()
    planned = (
        plan_against_done(docs, previous) if lead else {}
    )
    people = []
    for doc in docs:
        shape = standup_shape(doc, include_hours, hidden)
        if lead:
            shape["plan_vs_done"] = planned.get(doc.user)
        people.append(shape)
    blockers = [
        {"standup": p["name"], "user": p["user"], "full_name": p["full_name"], "needs_help": p["needs_help"], **b}
        for p in people
        for b in p["blockers"]
    ]
    return {
        "team": team,
        "teams": teams,
        "can_lead": lead,
        "date": str(day),
        "previous_day": str(previous),
        "editable": lead and day == today,
        "post_at": setting_time(settings, "post_at"),
        "posted": bool(settings.posted_on) and getdate(settings.posted_on) == day,
        "people": people,
        "blockers": blockers,
        "needs_help": [p["full_name"] for p in people if p["needs_help"]],
        "counts": {
            "people": len(people),
            "submitted": sum(p["status"] == SUBMITTED for p in people),
            "pending": sum(p["status"] == DRAFT for p in people),
            "auto": sum(p["status"] == AUTO_POSTED for p in people),
            "blockers": len(blockers),
        },
        "on_leave": team_on_leave(department, day) if lead else [],
    }


def plan_against_done(docs: list, previous) -> dict:
    """{user: {"planned", "done", "unplanned"}}: the linked work their stand-up on the
    previous working day planned, how much of it is in today's "yesterday", and what
    else they did. A count, not a score."""
    before = {d.user: d for d in load_standups(previous, users=[d.user for d in docs])}
    found = {}
    for doc in docs:
        earlier = before.get(doc.user)
        if not earlier:
            continue
        plan = {refs(r) for r in earlier.today if r.reference_name}
        done = {refs(r) for r in doc.yesterday if r.reference_name}
        found[doc.user] = {
            "planned": len(plan),
            "done": len(plan & done),
            "unplanned": len(done - plan),
        }
    return found


def refs(row) -> tuple[str, str]:
    return row.reference_doctype, str(row.reference_name)


def team_on_leave(department: str | None, day) -> list[dict]:
    """The department's people on leave `day`, by name (no leave type)."""
    away = leave_today(day)
    if not away:
        return []
    homes = home_departments(away)
    return sorted(
        (
            {"user": u, "full_name": get_fullname(u), **away[u]}
            for u in away
            if homes.get(u) == department
        ),
        key=lambda row: row["full_name"],
    )


def history(viewer: str, user: str | None = None, limit: int = HISTORY_LIMIT) -> dict:
    """A person's past stand-ups, newest first: the viewer's own, or a teammate's for
    someone with that department's team view."""
    user = user or viewer
    rows = frappe.get_all(
        STANDUP,
        filters={"user": user},
        fields=["name", "date", "department", "status", "needs_help", "submitted_on"],
        order_by="date desc",
        limit_page_length=min(max(cint(limit), 1), HISTORY_LIMIT),
    )
    if user != viewer:
        allowed = set(team_departments(viewer))
        rows = [r for r in rows if (r.department or NO_DEPARTMENT) in allowed]
        if not rows and not allowed:
            frappe.throw(
                _("You see your own stand-ups only."), frappe.PermissionError
            )
    counts = item_counts([r.name for r in rows])
    return {
        "user": user,
        "full_name": get_fullname(user),
        "items": [
            {
                "name": r.name,
                "date": str(r.date),
                "department": r.department,
                "status": r.status,
                "needs_help": bool(r.needs_help),
                "submitted_on": str(r.submitted_on) if r.submitted_on else None,
                **counts.get(r.name, dict.fromkeys(SECTIONS, 0)),
            }
            for r in rows
        ],
    }


def item_counts(names: list[str]) -> dict:
    if not names:
        return {}
    row = frappe.qb.DocType(ITEM)
    found = {}
    for parent, field, count in (
        frappe.qb.from_(row)
        .select(row.parent, row.parentfield, Count(row.name))
        .where((row.parenttype == STANDUP) & row.parent.isin(names))
        .groupby(row.parent, row.parentfield)
        .run()
    ):
        found.setdefault(parent, dict.fromkeys(SECTIONS, 0))[field] = count
    return found


# --- the team's actions ------------------------------------------------------------


def team_doc(viewer: str, standup: str):
    """A stand-up the viewer leads the department of; refused otherwise."""
    doc = frappe.get_doc(STANDUP, standup)
    if (doc.department or NO_DEPARTMENT) not in team_departments(viewer):
        frappe.throw(
            _("Only the team's heads, leads and managers can do this."),
            frappe.PermissionError,
        )
    return doc


def blocker_row(doc, row: str):
    found = next((r for r in doc.blockers if r.name == row), None)
    if not found:
        frappe.throw(_("That blocker isn't on this stand-up any more."))
    return found


def nudge(viewer: str, standup: str) -> dict:
    """Ask a person whose stand-up is still a draft to submit it, every time asked."""
    doc = team_doc(viewer, standup)
    if doc.status != DRAFT or getdate(doc.date) != getdate(now_datetime()):
        frappe.throw(_("Only today's unsubmitted stand-ups can be nudged."))
    notify_users(
        [doc.user],
        STANDUP,
        doc.name,
        _("{0} is waiting for your stand-up: check it and submit (1 min)").format(
            get_fullname(viewer)
        ),
        link=PATH,
        user_from=viewer,
        once=False,
    )
    return {"nudged": doc.user}


def assign_help(viewer: str, standup: str, row: str, helper: str) -> dict:
    """Ask `helper` to help with a blocker: they are told, and when the blocker is a
    task the viewer may change, they also join its assignees."""
    doc = team_doc(viewer, standup)
    blocker = blocker_row(doc, row)
    helper = (helper or "").strip()
    if not frappe.db.exists("HD Agent", {"user": helper, "is_active": 1}) or not enabled_users([helper]):
        frappe.throw(_("{0} is not an active agent.").format(helper))
    if helper == doc.user:
        frappe.throw(_("Pick someone other than the person who is blocked."))
    if blocker.reference_doctype == "Task" and frappe.has_permission(
        "Task", "write", blocker.reference_name, user=viewer
    ):
        join_task(blocker.reference_name, helper)
    blocker.helper = helper
    doc.save(ignore_permissions=True)
    notify_users(
        [helper],
        blocker.reference_doctype or STANDUP,
        blocker.reference_name or doc.name,
        _("{0} asked you to help {1}: {2}").format(
            get_fullname(viewer), doc.full_name or doc.user, blocker.title
        ),
        link=item_path(blocker) or PATH,
        user_from=viewer,
        once=False,
    )
    return item_shape(blocker)


def join_task(task: str, helper: str) -> None:
    """Add `helper` to the task's assignees unless they already are (the ToDo hooks
    still refuse someone across a department wall)."""
    from helpdesk.utils import add_assignment

    assigned = frappe.db.exists(
        "ToDo",
        {
            "reference_type": "Task",
            "reference_name": task,
            "allocated_to": helper,
            "status": "Open",
        },
    )
    if not assigned:
        add_assignment(
            {"doctype": "Task", "name": task, "assign_to": [helper]},
            ignore_permissions=True,
        )


def create_task_from_blocker(
    viewer: str,
    standup: str,
    row: str,
    project: str,
    subject: str,
    assigned_to: str | None = None,
    due_date: str | None = None,
) -> dict:
    """A task for what unblocks the person, in a project the viewer may add tasks to
    (tasky's own checks); the blocker remembers it."""
    from helpdesk.tasky.api import add_task

    doc = team_doc(viewer, standup)
    blocker = blocker_row(doc, row)
    task = add_task(
        project=project,
        task_name=subject,
        assigned_to=assigned_to or "",
        due_date=due_date or None,
        description=_("From {0}'s stand-up on {1}: {2}").format(
            doc.full_name or doc.user, formatdate(doc.date, "d MMM"), blocker.title
        ),
    )
    blocker.help_task = task["name"]
    doc.save(ignore_permissions=True)
    return {"task": task["name"], "blocker": item_shape(blocker)}


# --- Home ---------------------------------------------------------------------------


def home_card(user: str) -> dict | None:
    """Home's morning card: today's stand-up while it is still a draft."""
    if not is_enabled():
        return None
    row = frappe.db.get_value(
        STANDUP,
        standup_name(user, getdate(now_datetime())),
        ["name", "status", "date"],
        as_dict=True,
    )
    if not row or row.status != DRAFT:
        return None
    return {
        "name": row.name,
        "date": str(row.date),
        "post_at": setting_time(get_settings(), "post_at"),
    }
