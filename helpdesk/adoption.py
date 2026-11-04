"""Adoption: who is actually using the system, and what is stuck (docs/adoption.md).

Management reads one ranked list of findings, each saying what it means and what to do,
and a table of people. Everything is read from what the hub already holds (tasks, timer
sessions, stand-ups, content posts, tickets) and, for sales, from the ERP site through
the same proxies the Leads page uses; when the ERP site can't answer, the Sales findings
are left out quietly and the rest still shows.
"""

import re
from collections import Counter, defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from helpdesk import sales_scoreboard as sales
from helpdesk import standup
from helpdesk.api.leads import READ_TTL, cached_read
from helpdesk.api.work import OPEN_TASK_FILTER, is_task_overdue
from helpdesk.content_team import SALES_EMPLOYEE_ROLE, _users_with_role
from helpdesk.integrations.crm.leads import LeadsError, call_if_deployed, leads_on
from helpdesk.recurrence import working_day_checker
from helpdesk.tasky.api import get_users
from helpdesk.tasky.permissions import COORDINATOR_PROJECT_ROLE, is_tasky_admin
from helpdesk.team_dashboard import assignees
from helpdesk.work_calendar import leave_between
from helpdesk.work_reminders import SKIP

PERIODS = ("this_week", "last_week", "last_30")
# the role the ERP site gives management; kept here too so the hub can grant it the page
MANAGEMENT_ROLE = "TBO Management"
SEVERITIES = ("attention", "watch", "good")
AREAS = ("Sales", "Delivery", "Content", "Support", "Accounts")

# how far back "last activity" looks
LOOKBACK_DAYS = 90
# the ERP site is asked for one day of call batches at a time: the latest working days only
SALES_DAYS = 7
BATCH_PART = "adoption_batches"
LOW_OUTCOME_SHARE = 0.5
OVERDUE_ATTENTION = 0.4
OVERDUE_WATCH = 0.2
NO_LEAD_ATTENTION = 0.3
LONG_HOURS = 7
STUCK_DRAFT_DAYS = 7
MANY_STUCK_POSTS = 10
CONCENTRATION = 0.7
MIN_EDITS = 10
NO_REPLY_HOURS = 24
MANY_UNANSWERED = 5
DIGEST_FINDINGS = 5
DIGEST_SUBJECT = "Adoption: what needs attention this week"

PERSONAL_EMAIL = re.compile(
    r"@(gmail|googlemail|yahoo|ymail|hotmail|outlook|live|rediffmail|icloud)\.", re.I
)
TEST_LOOKING = re.compile(r"(^|[^a-z])(test|demo|dummy|sample|temp)([^a-z]|$)", re.I)


# --- who may look -----------------------------------------------------------------


def can_see_adoption(user: str | None = None) -> bool:
    """System Managers and Agent Managers, holders of the TBO Management role (when the hub
    has it), and anyone who coordinates a project."""
    user = user or frappe.session.user
    if user == "Guest":
        return False
    if is_tasky_admin(user) or MANAGEMENT_ROLE in frappe.get_roles(user):
        return True
    return bool(
        frappe.db.exists(
            "Project User",
            {
                "parenttype": "Project",
                "user": user,
                "custom_role": COORDINATOR_PROJECT_ROLE,
            },
        )
    )


def recipients() -> list[str]:
    """Active agents who may open the page: the people the Monday digest goes to."""
    active = {u.name for u in get_users()}
    managers = {
        parent
        for role in ("System Manager", "Agent Manager", MANAGEMENT_ROLE)
        for parent in _users_with_role(role)
    }
    coordinators = set(
        frappe.get_all(
            "Project User",
            filters={
                "parenttype": "Project",
                "custom_role": COORDINATOR_PROJECT_ROLE,
            },
            pluck="user",
        )
    )
    return sorted((managers | coordinators) & active - set(SKIP))


# --- the period -------------------------------------------------------------------


def period_bounds(period: str, today=None) -> tuple:
    """First and last day: Monday to today, the whole week before, or the last 30 days."""
    today = getdate(today or nowdate())
    monday = today - timedelta(days=today.weekday())
    if period == "this_week":
        return monday, today
    if period == "last_week":
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if period == "last_30":
        return add_days(today, -29), today
    frappe.throw(_("Unknown period: {0}").format(period))


def period_words(period: str) -> str:
    return {
        "this_week": _("this week"),
        "last_week": _("last week"),
        "last_30": _("in the last 30 days"),
    }[period]


def context(period: str, fresh) -> frappe._dict:
    start, end = period_bounds(period)
    agents = get_users()
    names = {a.name: a.full_name or a.name for a in agents}
    return frappe._dict(
        period=period,
        words=period_words(period),
        start=start,
        end=min(end, getdate(nowdate())),
        today=getdate(nowdate()),
        fresh=fresh,
        agents=agents,
        names=names,
        sales_team=set(_users_with_role(SALES_EMPLOYEE_ROLE)),
    )


def first_name(ctx, user: str) -> str:
    return (ctx.names.get(user) or user).split()[0]


def named(ctx, users) -> str:
    """ "Shahana", "Shahana and Anil", "Shahana, Anil and 3 others"."""
    users = list(users)
    firsts = [first_name(ctx, u) for u in users[:3]]
    if len(users) <= 1:
        return "".join(firsts)
    if len(users) == 2:
        return _("{0} and {1}").format(*firsts)
    if len(users) == 3:
        return _("{0}, {1} and {2}").format(*firsts)
    return _("{0}, {1} and {2} others").format(*firsts[:2], len(users) - 2)


def day_after(day):
    return add_days(day, 1)


# --- the finding ------------------------------------------------------------------


def finding(
    ctx,
    key: str,
    severity: str,
    area: str,
    title: str,
    detail: str,
    action_hint: str,
    link: str,
    who=(),
) -> dict:
    return {
        "id": key,
        "severity": severity,
        "area": area,
        "title": title,
        "detail": detail,
        "action_hint": action_hint,
        "link": link,
        "who": [{"user": u, "name": ctx.names.get(u) or u} for u in who],
    }


def ranked(findings: list[dict]) -> list[dict]:
    """Attention first, then watch, then good; each in the order of the areas."""
    return sorted(
        findings,
        key=lambda f: (SEVERITIES.index(f["severity"]), AREAS.index(f["area"])),
    )


# --- what people did --------------------------------------------------------------


def work_log(ctx) -> dict:
    """What each person did up to the period's end, looking back far enough for their last
    activity: tasks completed (user, day), timer sessions (user, day, hours) and
    stand-ups (user, day, status)."""
    since = min(ctx.start, add_days(ctx.today, -LOOKBACK_DAYS))
    until = day_after(ctx.end)
    task = frappe.qb.DocType("Task")
    done = []
    for assign, completed in (
        frappe.qb.from_(task)
        .select(task["_assign"], task.completed_on)
        .where(
            (task.status == "Completed")
            & (task.completed_on >= since)
            & (task.completed_on < until)
        )
        .run()
    ):
        done.extend((u, getdate(completed)) for u in assignees(assign))
    session = frappe.qb.DocType("HD Task Time Session")
    sessions = [
        (user, getdate(started), flt(hours))
        for user, started, hours in frappe.qb.from_(session)
        .select(session.user, session.started_at, session.hours)
        .where((session.started_at >= since) & (session.started_at < until))
        .run()
    ]
    stand = frappe.qb.DocType("HD Standup")
    standups = [
        (user, getdate(day), status)
        for user, day, status in frappe.qb.from_(stand)
        .select(stand.user, stand.date, stand.status)
        .where((stand.date >= since) & (stand.date <= ctx.end))
        .run()
    ]
    return {"tasks": done, "sessions": sessions, "standups": standups}


def tally(ctx, log: dict) -> dict:
    """{user: tasks_done, hours, standups_written, last_activity} for the period."""
    stats = defaultdict(
        lambda: {
            "tasks_done": 0,
            "hours": 0.0,
            "standups_written": 0,
            "last_activity": None,
        }
    )

    def seen(user, day, key=None, add=1):
        row = stats[user]
        if key and ctx.start <= day <= ctx.end:
            row[key] += add
        if not row["last_activity"] or day > row["last_activity"]:
            row["last_activity"] = day

    for user, day in log["tasks"]:
        seen(user, day, "tasks_done")
    for user, day, hours in log["sessions"]:
        seen(user, day, "hours", hours)
    for user, day, status in log["standups"]:
        if status == standup.SUBMITTED:
            seen(user, day, "standups_written")
    return stats


# --- sales (through the ERP site) -------------------------------------------------


def read_sales(ctx) -> dict | None:
    """{user: calls, contacted, handed, outcomes, active} for the sales team, or None when
    leads are off or the ERP site can't answer (the Sales findings then stay out)."""
    if not leads_on():
        return None
    activity = sales.activity(ctx.start, ctx.end, with_overdue=False)
    if activity["status"] != sales.OK:
        return None
    people: dict = {}
    for row in activity["rows"]:
        people[row["user"]] = {
            "calls": cint(row["sales_calls"]),
            "contacted": cint(row["sales_contacted"]),
            "handed": 0,
            "outcomes": 0,
            "active": any(row[stat] for stat in sales.FIELDS.values()),
        }
    for user, batch in read_batches(ctx).items():
        person = people.setdefault(
            user,
            {"calls": 0, "contacted": 0, "handed": 0, "outcomes": 0, "active": False},
        )
        person["handed"] = batch["size"]
        person["outcomes"] = batch["called"]
        person["active"] = person["active"] or bool(batch["called"])
    for user in ctx.sales_team:
        people.setdefault(
            user,
            {"calls": 0, "contacted": 0, "handed": 0, "outcomes": 0, "active": False},
        )
    return people


def read_batches(ctx) -> dict:
    """{user: size, called} summed over the period's latest working days, from the ERP
    site's call batches report. Anything the ERP site refuses ends the loop quietly: a
    coordinator isn't a sales manager there, and an older site has no report."""
    first = max(ctx.start, add_days(ctx.end, 1 - SALES_DAYS))
    is_working = working_day_checker(first, ctx.end)
    totals: dict = {}
    day = first
    while day <= ctx.end:
        if is_working(day):
            try:
                report = batch_report(day, ctx.fresh)
            except LeadsError:
                # frappe.throw queued a message for a toast; nobody is waiting on it
                frappe.clear_last_message()
                return totals
            if report is None:
                return totals
            for person in report.get("people") or []:
                row = totals.setdefault(person["user"], {"size": 0, "called": 0})
                row["size"] += cint(person.get("size"))
                row["called"] += cint(person.get("called"))
        day = day_after(day)
    return totals


def batch_report(day, fresh):
    return cached_read(
        BATCH_PART,
        {"date": str(day)},
        READ_TTL,
        fresh,
        lambda: call_if_deployed("get_call_batches_report", date=str(day)),
        keep=lambda answer: answer is not None,
    )


def sales_findings(ctx, sales_people: dict | None) -> list[dict]:
    if sales_people is None:
        return []
    out = []
    idle = [
        u
        for u, p in sales_people.items()
        if u in ctx.sales_team and not p["active"] and not leave_in_period(ctx, u)
    ]
    handed = {u: p for u, p in sales_people.items() if p["handed"]}
    none_recorded = [u for u, p in handed.items() if not p["outcomes"]]
    few_recorded = [
        u
        for u, p in handed.items()
        if p["outcomes"] and p["outcomes"] / p["handed"] < LOW_OUTCOME_SHARE
    ]
    if none_recorded:
        out.append(outcome_finding(ctx, "attention", none_recorded, handed, none=True))
    if few_recorded:
        out.append(outcome_finding(ctx, "watch", few_recorded, handed, none=False))
    if handed and not none_recorded and not few_recorded:
        out.append(
            finding(
                ctx,
                "sales-outcomes",
                "good",
                "Sales",
                _("Call results are being recorded"),
                _(
                    "Everyone with a call batch recorded most of the results {0}."
                ).format(ctx.words),
                _("Nothing to do."),
                "/leads",
            )
        )
    if idle:
        out.append(
            finding(
                ctx,
                "sales-idle",
                "attention",
                "Sales",
                _("{0} did nothing in the system {1}").format(
                    named(ctx, idle), ctx.words
                ),
                _(
                    "No calls, lead updates, meetings, proposals or follow-ups were recorded for them."
                ),
                _(
                    "Ask them how they are tracking their leads. If they are working, they need to record it in Leads."
                ),
                "/leads",
                idle,
            )
        )
    roster = [u for u in sales_people if u in ctx.sales_team]
    if roster:
        out.extend(sales_activity_findings(ctx, sales_people, roster, set(idle)))
    return out


def outcome_finding(ctx, severity, users, handed, none: bool) -> dict:
    count = sum(handed[u]["handed"] for u in users)
    if none:
        title = (
            _("{0} recorded 0 call results {1}").format(named(ctx, users), ctx.words)
            if len(users) == 1
            else _("{0} salespeople recorded 0 call results {1}").format(
                len(users), ctx.words
            )
        )
        detail = _(
            "They were handed {0} calls in call batches and recorded none."
        ).format(count)
    else:
        title = _("{0} recorded few call results {1}").format(
            named(ctx, users), ctx.words
        )
        detail = _("Less than half of the calls handed to them have a result.")
    return finding(
        ctx,
        "sales-outcomes-none" if none else "sales-outcomes-few",
        severity,
        "Sales",
        title,
        detail,
        _("Remind them to tap the result after each call in Today's calls."),
        "/leads",
        users,
    )


def sales_activity_findings(ctx, sales_people, roster, idle) -> list[dict]:
    out = []
    no_calls = [u for u in roster if not sales_people[u]["calls"] and u not in idle]
    if len(no_calls) == len(roster) and not idle:
        out.append(
            finding(
                ctx,
                "sales-calls",
                "attention",
                "Sales",
                _("No calls were logged {0}").format(ctx.words),
                _("Not one call from the sales team shows in the system."),
                _(
                    "Ask them to call from the lead's page, or use Log a call for calls made another way."
                ),
                "/leads",
                roster,
            )
        )
    elif no_calls:
        out.append(
            finding(
                ctx,
                "sales-calls",
                "watch",
                "Sales",
                _("{0} logged no calls {1}").format(named(ctx, no_calls), ctx.words),
                _("Their calls are not showing in the system."),
                _(
                    "Ask them to call from the lead's page, or use Log a call for calls made another way."
                ),
                "/leads",
                no_calls,
            )
        )
    not_moved = [
        u for u in roster if not sales_people[u]["contacted"] and u not in idle
    ]
    if not_moved:
        out.append(
            finding(
                ctx,
                "sales-stages",
                "watch",
                "Sales",
                _("{0} moved no lead out of New Lead {1}").format(
                    named(ctx, not_moved), ctx.words
                ),
                _("Their leads are not changing stage after they speak to them."),
                _("Ask them to update each lead's stage after every conversation."),
                "/leads",
                not_moved,
            )
        )
    return out


def leave_in_period(ctx, user: str) -> bool:
    return user in leave_users(ctx)


def leave_users(ctx) -> set:
    """People with approved leave during the period: never called quiet."""
    if "leave" not in ctx:
        ctx.leave = {row.user for row in leave_between(ctx.start, ctx.end)}
    return ctx.leave


# --- delivery ---------------------------------------------------------------------


def delivery_findings(ctx, stats: dict) -> list[dict]:
    return [
        *overdue_findings(ctx),
        *lead_findings(ctx),
        *quiet_findings(ctx, stats),
        *standup_findings(ctx),
        *hours_findings(ctx),
    ]


def overdue_findings(ctx) -> list[dict]:
    tasks = frappe.get_all(
        "Task",
        filters={"status": OPEN_TASK_FILTER},
        fields=[
            "status",
            "exp_end_date",
            "_assign",
            "custom_estimated_hours",
            "custom_timer_start",
            "custom_timer_elapsed",
        ],
        limit_page_length=0,
    )
    if not tasks:
        return []
    late = [
        t
        for t in tasks
        if is_task_overdue(
            t, getdate(t.exp_end_date) if t.exp_end_date else None, ctx.today
        )
    ]
    share = len(late) / len(tasks)
    holders = Counter(u for t in late for u in assignees(t["_assign"]))
    who = [u for u, _count in holders.most_common()]
    text = _("{0} of {1} open tasks are overdue").format(len(late), len(tasks))
    if share >= OVERDUE_ATTENTION:
        severity = "attention"
    elif share >= OVERDUE_WATCH:
        severity = "watch"
    else:
        return [
            finding(
                ctx,
                "overdue",
                "good",
                "Delivery",
                _("Tasks are mostly on time"),
                text + ".",
                _("Nothing to do."),
                "/overview",
            )
        ]
    return [
        finding(
            ctx,
            "overdue",
            severity,
            "Delivery",
            text,
            _("Work is slipping past its due date, so customers wait longer."),
            _(
                "Open the Overview, sit with the people who hold the most late tasks and agree new dates or help."
            ),
            "/overview",
            who,
        )
    ]


def lead_findings(ctx) -> list[dict]:
    projects = frappe.get_all(
        "Project",
        filters={"status": "Open"},
        fields=["project_lead"],
        limit_page_length=0,
    )
    if not projects:
        return []
    missing = [p for p in projects if not p.project_lead]
    text = _("{0} of {1} open projects have no lead").format(
        len(missing), len(projects)
    )
    if not missing:
        return [
            finding(
                ctx,
                "no-lead",
                "good",
                "Delivery",
                _("Every open project has a lead"),
                _("{0} open projects, each with someone who owns it.").format(
                    len(projects)
                ),
                _("Nothing to do."),
                "/projects",
            )
        ]
    severity = (
        "attention" if len(missing) / len(projects) >= NO_LEAD_ATTENTION else "watch"
    )
    return [
        finding(
            ctx,
            "no-lead",
            severity,
            "Delivery",
            text,
            _(
                "With no lead, nobody owns the project's tasks and its customer updates."
            ),
            _("Open each project and pick its lead."),
            "/projects",
        )
    ]


def quiet_findings(ctx, stats: dict) -> list[dict]:
    quiet = quiet_delivery(ctx, stats)
    if not quiet:
        return []
    everyone = len(delivery_agents(ctx))
    return [
        finding(
            ctx,
            "quiet-people",
            "attention" if len(quiet) * 2 > everyone else "watch",
            "Delivery",
            _("{0} of {1} people did no work in the system {2}").format(
                len(quiet), everyone, ctx.words
            ),
            _(
                "No task completed, no timer started and no stand-up written by them. People on leave are left out."
            ),
            _("Ask each of them what they worked on, and whether tasks are missing."),
            "/team",
            quiet,
        )
    ]


def delivery_agents(ctx) -> list[str]:
    return [a.name for a in ctx.agents if a.name not in ctx.sales_team]


def quiet_delivery(ctx, stats: dict) -> list[str]:
    return [
        u
        for u in delivery_agents(ctx)
        if is_quiet(stats.get(u)) and not leave_in_period(ctx, u)
    ]


def is_quiet(row) -> bool:
    return not row or not (row["tasks_done"] or row["hours"] or row["standups_written"])


def standup_findings(ctx) -> list[dict]:
    if not standup.is_enabled():
        return []
    stand = frappe.qb.DocType("HD Standup")
    rows = (
        frappe.qb.from_(stand)
        .select(stand.status, Count(stand.name))
        .where(
            (stand.date >= ctx.start)
            & (stand.date <= ctx.end)
            & stand.status.isin([standup.SUBMITTED, standup.AUTO_POSTED])
        )
        .groupby(stand.status)
        .run()
    )
    counts = dict(rows)
    written, auto = counts.get(standup.SUBMITTED, 0), counts.get(standup.AUTO_POSTED, 0)
    total = written + auto
    if not total:
        return []
    text = _("{0} of {1} stand-ups were written by people {2}").format(
        written, total, ctx.words
    )
    if written == total:
        return [
            finding(
                ctx,
                "standups",
                "good",
                "Delivery",
                _("People write their own stand-ups"),
                text + ".",
                _("Nothing to do."),
                "/standup",
            )
        ]
    return [
        finding(
            ctx,
            "standups",
            "attention" if written * 2 < total else "watch",
            "Delivery",
            _("Most stand-ups were posted by the system, not written by people")
            if written * 2 < total
            else _("Some stand-ups were posted by the system"),
            text + ". " + _("The rest were filled in and posted automatically."),
            _("Ask the team to open Stand-up each morning and post their own."),
            "/standup",
        )
    ]


def hours_findings(ctx) -> list[dict]:
    longest: dict = {}
    session = frappe.qb.DocType("HD Task Time Session")
    for user, started, hours in (
        frappe.qb.from_(session)
        .select(session.user, session.started_at, session.hours)
        .where(
            (session.started_at >= ctx.start)
            & (session.started_at < day_after(ctx.end))
            & (session.hours >= LONG_HOURS)
        )
        .run()
    ):
        keep_longest(longest, user, flt(hours), getdate(started))
    for user, hours, started in hand_entered_days(ctx):
        keep_longest(longest, user, flt(hours), getdate(started))
    if not longest:
        return []
    lines = [
        _("{0}: {1}h on {2}").format(
            ctx.names.get(u) or u, round(h, 1), frappe.utils.formatdate(d, "dd MMM")
        )
        for u, (h, d) in longest.items()
    ]
    return [
        finding(
            ctx,
            "long-hours",
            "watch",
            "Delivery",
            _("{0} logged a full day in one entry {1}").format(
                named(ctx, longest), ctx.words
            ),
            "; ".join(lines) + ".",
            _(
                "Check whether a timer was left running or the hours were typed in by hand."
            ),
            "/timesheets",
            longest,
        )
    ]


def keep_longest(longest: dict, user: str, hours: float, day) -> None:
    if user not in longest or hours > longest[user][0]:
        longest[user] = (hours, day)


def hand_entered_days(ctx) -> list[tuple]:
    """Time logs of 7 hours or more that no timer session produced: typed in by hand."""
    log = frappe.qb.DocType("Timesheet Detail")
    sheet = frappe.qb.DocType("Timesheet")
    rows = (
        frappe.qb.from_(log)
        .join(sheet)
        .on(sheet.name == log.parent)
        .select(sheet.owner, log.hours, log.from_time, sheet.name)
        .where(
            (log.parenttype == "Timesheet")
            & (sheet.docstatus < 2)
            & (log.hours >= LONG_HOURS)
            & (log.from_time >= ctx.start)
            & (log.from_time < day_after(ctx.end))
        )
        .run()
    )
    if not rows:
        return []
    from_timer = set(
        frappe.get_all(
            "HD Task Time Session",
            filters={"timesheet": ("in", [r[3] for r in rows])},
            pluck="timesheet",
        )
    )
    return [
        (user, hours, day) for user, hours, day, name in rows if name not in from_timer
    ]


# --- content ----------------------------------------------------------------------


def content_findings(ctx) -> list[dict]:
    open_posts = frappe.get_all(
        "HD Content Post",
        filters={"status": ("not in", ["Published", "Cancelled"])},
        fields=["status", "writer", "modified", "sent_for_approval_on"],
        limit_page_length=0,
    )
    if not open_posts:
        return []
    return [*stuck_findings(ctx, open_posts), *edit_findings(ctx)]


def stuck_findings(ctx, posts) -> list[dict]:
    out = []
    cutoff = now_datetime() - timedelta(days=STUCK_DRAFT_DAYS)
    stuck = [p for p in posts if p.status == "Drafting" and p.modified < cutoff]
    if stuck:
        writers = Counter(p.writer for p in stuck if p.writer)
        out.append(
            finding(
                ctx,
                "stuck-drafts",
                "attention" if len(stuck) >= MANY_STUCK_POSTS else "watch",
                "Content",
                _("{0} posts have sat in Drafting for over {1} days").format(
                    len(stuck), STUCK_DRAFT_DAYS
                ),
                _("They have not moved on, so they will miss their posting dates."),
                _(
                    "Go through them with the writers: finish them, or cancel the ones that are not needed."
                ),
                "/content",
                [u for u, _count in writers.most_common()],
            )
        )
    sent = [
        p
        for p in posts
        if p.status == "Client Review"
        or (
            p.sent_for_approval_on
            and ctx.start <= getdate(p.sent_for_approval_on) <= ctx.end
        )
    ]
    if not sent:
        out.append(
            finding(
                ctx,
                "no-client-review",
                "attention",
                "Content",
                _("No post was sent to a client for review {0}").format(ctx.words),
                _(
                    "Clients cannot approve what they never see, so nothing can go live."
                ),
                _("Move finished posts to Client Review so the client gets them."),
                "/content",
            )
        )
    return out


def edit_findings(ctx) -> list[dict]:
    version = frappe.qb.DocType("Version")
    edits = dict(
        frappe.qb.from_(version)
        .select(version.owner, Count(version.name))
        .where(
            (version.ref_doctype == "HD Content Post")
            & (version.creation >= ctx.start)
            & (version.creation < day_after(ctx.end))
        )
        .groupby(version.owner)
        .run()
    )
    total = sum(edits.values())
    if total < MIN_EDITS:
        return []
    top, count = max(edits.items(), key=lambda item: item[1])
    if count / total <= CONCENTRATION:
        return []
    return [
        finding(
            ctx,
            "edit-concentration",
            "watch",
            "Content",
            _("{0} made {1}% of the content calendar edits {2}").format(
                first_name(ctx, top), round(100 * count / total), ctx.words
            ),
            _(
                "{0} of {1} edits are by one person; the rest of the team is not updating posts."
            ).format(count, total),
            _("Ask the other writers and designers to update their own posts."),
            "/content",
            [top],
        )
    ]


# --- support ----------------------------------------------------------------------


def support_findings(ctx) -> list[dict]:
    cutoff = now_datetime() - timedelta(hours=NO_REPLY_HOURS)
    tickets = frappe.get_all(
        "HD Ticket",
        filters={"status_category": "Open"},
        fields=["creation", "first_responded_on", "agreement_status", "_assign"],
        limit_page_length=0,
    )
    unanswered = [
        t for t in tickets if not t.first_responded_on and t.creation < cutoff
    ]
    breached = [t for t in tickets if t.agreement_status == "Failed"]
    out = []
    if unanswered:
        out.append(
            ticket_finding(
                ctx,
                "no-reply",
                "attention" if len(unanswered) >= MANY_UNANSWERED else "watch",
                _("{0} open tickets have had no reply for over a day").format(
                    len(unanswered)
                ),
                _("Customers are waiting without an answer."),
                _(
                    "Open the tickets and make sure each one has an owner who replies today."
                ),
                unanswered,
            )
        )
    if breached:
        out.append(
            ticket_finding(
                ctx,
                "sla-breach",
                "attention",
                _("{0} open tickets have broken their SLA").format(len(breached)),
                _("The time promised to the customer has already passed."),
                _("Reply to these first, and ask the owners why they were late."),
                breached,
            )
        )
    if tickets and not unanswered and not breached:
        out.append(
            finding(
                ctx,
                "support-ok",
                "good",
                "Support",
                _("Open tickets are being answered"),
                _("No open ticket is waiting for a first reply or past its SLA."),
                _("Nothing to do."),
                "/tickets",
            )
        )
    return out


def ticket_finding(ctx, key, severity, title, detail, action, tickets) -> dict:
    holders = Counter(u for t in tickets for u in assignees(t["_assign"]))
    return finding(
        ctx,
        key,
        severity,
        "Support",
        title,
        detail,
        action,
        "/tickets",
        [u for u, _count in holders.most_common()],
    )


# --- accounts ---------------------------------------------------------------------


def account_findings(ctx) -> list[dict]:
    out = []
    odd = [
        a.name
        for a in ctx.agents
        if PERSONAL_EMAIL.search(a.email or a.name)
        or TEST_LOOKING.search((a.email or a.name).split("@")[0])
        or TEST_LOOKING.search(a.full_name or "")
    ]
    if odd:
        out.append(
            finding(
                ctx,
                "odd-accounts",
                "watch",
                "Accounts",
                _("{0} active accounts look like tests or personal emails").format(
                    len(odd)
                ),
                _(
                    "Staff should sign in with their company email so leaving staff lose access."
                ),
                _("Check each one; switch off the accounts that are not real staff."),
                "/agents",
                odd,
            )
        )
    by_name = defaultdict(list)
    for a in ctx.agents:
        if a.full_name:
            by_name[a.full_name.strip().lower()].append(a.name)
    twice = [u for users in by_name.values() if len(users) > 1 for u in users]
    if twice:
        out.append(
            finding(
                ctx,
                "duplicate-names",
                "watch",
                "Accounts",
                _("{0} people appear twice with the same name").format(
                    len([1 for users in by_name.values() if len(users) > 1])
                ),
                _(
                    "Two active accounts share one full name, so one is probably a duplicate."
                ),
                _("Keep the account the person really uses and switch off the other."),
                "/agents",
                twice,
            )
        )
    if not out and ctx.agents:
        out.append(
            finding(
                ctx,
                "accounts-ok",
                "good",
                "Accounts",
                _("Agent accounts look clean"),
                _("No test, personal-email or duplicate accounts among active agents."),
                _("Nothing to do."),
                "/agents",
            )
        )
    return out


# --- the people table -------------------------------------------------------------


def people_rows(ctx, stats: dict, sales_people: dict | None) -> list[dict]:
    rows = []
    for agent in ctx.agents:
        row = stats.get(agent.name) or {}
        sale = (sales_people or {}).get(agent.name)
        is_sales = agent.name in ctx.sales_team
        if is_sales:
            quiet = sale is not None and not sale["active"]
        else:
            quiet = is_quiet(row)
        rows.append(
            {
                "user": agent.name,
                "name": agent.full_name or agent.name,
                "tasks_done": row.get("tasks_done", 0),
                "hours": round(row.get("hours", 0.0), 1),
                "last_activity": str(row["last_activity"])
                if row.get("last_activity")
                else None,
                "standups_written": row.get("standups_written", 0),
                "is_sales": is_sales,
                "calls": sale["calls"] if sale else None,
                "outcomes": sale["outcomes"] if sale else None,
                "on_leave": leave_in_period(ctx, agent.name),
                "quiet": quiet and not leave_in_period(ctx, agent.name),
            }
        )
    return sorted(rows, key=lambda r: (not r["quiet"], r["name"].lower()))


# --- everything -------------------------------------------------------------------


def build(period: str = "this_week", fresh=0) -> dict:
    """The page's answer: ranked findings, the people table, and the counts."""
    ctx = context(period, fresh)
    stats = tally(ctx, work_log(ctx))
    sales_people = read_sales(ctx)
    findings = ranked(
        [
            *sales_findings(ctx, sales_people),
            *delivery_findings(ctx, stats),
            *content_findings(ctx),
            *support_findings(ctx),
            *account_findings(ctx),
        ]
    )
    return {
        "period": period,
        "from_date": str(ctx.start),
        "to_date": str(ctx.end),
        "findings": findings,
        "counts": dict(Counter(f["severity"] for f in findings)),
        "people": people_rows(ctx, stats, sales_people),
        "sales_available": sales_people is not None,
    }


# --- Monday digest ----------------------------------------------------------------


def send_weekly_digest() -> None:
    """Monday 09:00: the top findings of last week to the people who may open the page,
    by chat or email like the follow-up digest. Off with the switch in Settings →
    Follow-ups (or with follow-ups); quiet when there is nothing to say."""
    from helpdesk import follow_ups

    settings = follow_ups.get_settings()
    if not (settings.enabled and settings.adoption_digest):
        return
    for user in recipients():
        try:
            with standup.as_user(user):
                report = build("last_week")
            sections = digest_sections(report)
            if sections:
                follow_ups.deliver_digest(user, _(DIGEST_SUBJECT), sections)
        except Exception:  # noqa: BLE001 - one person's digest must not stop the rest
            frappe.log_error(title=f"Adoption digest failed for {user}")


def digest_sections(report: dict) -> list[tuple]:
    """The five most important findings that are not good news, with the page at the end."""
    top = [f for f in report["findings"] if f["severity"] != "good"][:DIGEST_FINDINGS]
    if not top:
        return []
    rows = [(f"{f['title']}. {f['action_hint']}", f["link"]) for f in top]
    rows.append((_("Open the Adoption page for the people and details"), "/adoption"))
    return [(_("Last week in the system"), rows)]
