"""Team dashboard: who delivered what in a period, and who the champion is.

The numbers come from the hub's own records: Tasks (completion date, due date,
key/milestone, estimate, priority, who made it, slips, the close rating,
send-backs on review, comebacks), Timesheets (hours) and the content calendar
(posts published on time). `task_weight()` and `task_quality()` say what one
task is worth; `score()` is the one place a person's score is worked out; the
dashboard, the champions and the AI analysis all use them. See
docs/team-dashboard.md for the formulas and their reasons.

Who may see which part of it is decided in helpdesk.api.team_dashboard.
"""

import json
import re
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import quote

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, flt, get_last_day, getdate, now_datetime, nowdate

from helpdesk.ai_engine import call_haiku, fact_numbers, invents_numbers
from helpdesk.api.content_performance import members, scored_posts
from helpdesk.api.ticket_ai import truncate
from helpdesk.work_reminders import SKIP, notify_users

# period key -> (HD Team Champion period type, least weighted work delivered to be
# champion: the tasks' weights plus posts published)
PERIODS = {
    "today": ("Day", 2),
    "week": ("Week", 3),
    "month": ("Month", 5),
    "quarter": ("Quarter", 8),
    "half": ("Half year", 12),
    "year": ("Year", 20),
}
# and at least this many tasks and posts, so one big task alone never wins
MIN_DELIVERED = 2
# no AI analysis for a day (cost): not at close, and no refresh on the page
QUIET_PERIODS = ("today",)

WEIGHTS = {
    # half of a task's worth (its weight times its quality) is for doing it, half
    # for doing it by its due date
    "done_share": 0.5,
    "post_on_time": 1.0,
    "post_late": 0.5,
    "post_missed": -1.0,
    "overdue": -1.0,
    "slip": -0.5,
    # hours count lightly, and never for more than a tenth of what was delivered
    "hour": 0.05,
    "hours_cap_share": 0.1,
}

# A task's weight (task_weight), worked out by the system: nobody types it. From
# 0.5 (a task the doer made and took themselves) to 4.5 (a key task, 16 hours or
# more estimated, Urgent). Logged hours never count: that would be time tracking.
TASK_WEIGHT = {
    "base": 1.0,
    # made and taken by the doer: nobody else asked for it, so it counts half, and
    # what the doer alone sets (key, priority, a long estimate) adds nothing more
    "self_made_base": 0.5,
    "key": 1.0,
    "size_per_hour": 0.125,
    "size_cap": 2.0,
    "self_made_size_cap": 0.5,
    "priority": {"High": 0.25, "Urgent": 0.5},
}

# A task's quality (task_quality): the close rating, less what happened to the
# work afterwards. Between 0.25 and 1.25; unrated work is 1 (no penalty, no
# bonus). Slips aren't here: they already cost points of their own (WEIGHTS).
QUALITY = {
    "rating": {"Excellent": 1.25, "Good": 1.0, "Needs rework": 0.5},
    "unrated": 1.0,
    "sent_back": -0.15,
    "came_back": -0.25,
    "floor": 0.25,
    "ceiling": 1.25,
}
RATINGS = tuple(QUALITY["rating"])

OPEN_STATUSES = ("Open", "Working", "Overdue")
SENT_BACK = "Sent back:%"
CACHE_PREFIX = "team_dashboard"
# bumped when a cached task row changes shape, so a deploy never reads old rows
CACHE_VERSION = 2
CACHE_SECONDS = 300
# a closed period's numbers (later edits to old tasks show within the hour)
CLOSED_CACHE_SECONDS = 60 * 60
ANALYSIS_SECONDS = 12 * 60 * 60
AI_PEOPLE_CAP = 15
AI_TEXT_CHARS = 400
AI_ITEM_CAP = 5
JOB_TIMEOUT = 900

SYSTEM_PROMPT = """You write a short performance analysis of one team for its manager.
Use only the facts in the JSON you are given. Never invent people, tasks, numbers, dates, causes
or plans. Every number you write must appear in the facts. The champion was chosen by a fixed
formula; explain the choice with the champion's reasons, don't choose another one.
- summary: two or three sentences: how the period went and who the champion is and why.
- risks: overdue work, slips, missed posts or send-backs worth acting on, most serious first.
- needs_help: people whose numbers suggest they need support (overdue work, late or missed
  deliveries), with the fact that shows it. Be kind and specific; never judge hours worked.
Each list item is one short plain-text sentence (no HTML, no markdown), at most 5 per list.
Reply with JSON only: {"summary": "...", "risks": ["..."], "needs_help": ["..."]}"""


# --- periods -----------------------------------------------------------------


def period_bounds(period: str, day=None) -> tuple[date, date]:
    """First and last day of the period that `day` (today by default) falls in.

    Weeks run Monday to Sunday; halves are January-June and July-December.
    """
    day = getdate(day or nowdate())
    if period == "today":
        return day, day
    if period == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        return day.replace(day=1), get_last_day(day)
    if period in ("quarter", "half"):
        months = 3 if period == "quarter" else 6
        first = (day.month - 1) // months * months + 1
        start = date(day.year, first, 1)
        return start, get_last_day(date(day.year, first + months - 1, 1))
    if period == "year":
        return date(day.year, 1, 1), date(day.year, 12, 31)
    frappe.throw(_("Unknown period: {0}").format(period))


def comparison_bounds(period: str, start, end, day=None) -> tuple[date, date]:
    """The previous period up to the same point: a week in progress on Wednesday is
    compared with Monday to Wednesday of the week before, not the whole week."""
    day = getdate(day or nowdate())
    prev_start, prev_end = period_bounds(period, add_days(start, -1))
    elapsed = (min(day, getdate(end)) - getdate(start)).days
    return prev_start, min(prev_start + timedelta(days=max(elapsed, 0)), prev_end)


def recent_periods(period: str, count: int, day=None) -> list[tuple[date, date]]:
    """The `count` periods up to the one `day` (today) falls in, oldest first."""
    found = [period_bounds(period, day)]
    while len(found) < count:
        found.insert(0, period_bounds(period, add_days(found[0][0], -1)))
    return found


# --- the numbers -------------------------------------------------------------


def collect(start, end, with_overdue: bool = True, today=None) -> dict:
    """Every row the dashboard counts in the period, for everyone; cached briefly.

    `with_overdue` adds the open tasks overdue today, which only mean something for
    the period in progress or one that just closed.
    """
    today = getdate(today or nowdate())
    # a closed period without today's overdue no longer depends on the day: keep it
    # longer, so 8-period trends don't recount years every few minutes
    closed = not with_overdue and getdate(end) < today
    key = (
        f"{CACHE_PREFIX}:{CACHE_VERSION}:{start}:{end}:{int(with_overdue)}:"
        f"{'' if closed else today}"
    )
    cached = frappe.cache.get_value(key, expires=True)
    if cached is not None:
        return cached
    data = {
        "tasks": completed_tasks(start, end),
        "overdue": overdue_tasks(today) if with_overdue else [],
        "hours": logged_hours(start, end),
        "posts": delivered_posts(start, end),
    }
    frappe.cache.set_value(
        key, data, expires_in_sec=CLOSED_CACHE_SECONDS if closed else CACHE_SECONDS
    )
    return data


def clear_cache():
    """Drops the cached numbers (not the analyses), e.g. after a test changed the records."""
    frappe.cache.delete_keys(f"{CACHE_PREFIX}:")


def assignees(raw) -> list[str]:
    """The people a task is assigned to; Administrator and Guest never count."""
    try:
        return [u for u in json.loads(raw or "[]") if u and u not in SKIP]
    except (TypeError, ValueError):
        return []


def completed_tasks(start, end) -> list[dict]:
    """Tasks completed in the period, each with its weight and quality."""
    task = frappe.qb.DocType("Task")
    return scored_tasks(
        (task.status == "Completed") & task.completed_on.between(start, end)
    )


def scored_tasks(condition) -> list[dict]:
    """The tasks `condition` picks, as the Scoreboard counts them: department,
    assignees, dates, weight (task_weight) and quality (task_quality). A few
    grouped queries for any number of tasks."""
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(task)
        .left_join(project)
        .on(project.name == task.project)
        .select(
            task.name,
            task.project,
            task.owner,
            task["_assign"],
            task.exp_end_date,
            task.completed_on,
            task.is_key,
            task.is_milestone,
            task.priority,
            task.custom_estimated_hours,
            task.slip_count,
            task.quality_rating,
            task.reopen_count,
            project.custom_department.as_("department"),
        )
        .where(condition)
        .run(as_dict=True)
    )
    names = [r.name for r in rows]
    sent_back = send_backs(names)
    self_made = self_made_tasks(rows)
    out = []
    for r in rows:
        row = {
            "name": r.name,
            "project": r.project,
            "department": r.department,
            "users": assignees(r._assign),
            "completed_on": getdate(r.completed_on) if r.completed_on else None,
            "dated": bool(r.exp_end_date),
            "on_time": bool(
                r.completed_on
                and r.exp_end_date
                and getdate(r.completed_on) <= getdate(r.exp_end_date)
            ),
            "key": bool(r.is_key or r.is_milestone),
            "priority": r.priority,
            "estimate": flt(r.custom_estimated_hours),
            "self_made": r.name in self_made,
            "slips": r.slip_count or 0,
            "rating": r.quality_rating or None,
            "sent_back": sent_back.get(r.name, 0),
            "came_back": r.reopen_count or 0,
        }
        row["weight"] = task_weight(row)["weight"]
        row["quality"] = task_quality(row)["quality"]
        out.append(row)
    return out


def send_backs(names: list[str]) -> dict[str, int]:
    """How often each task was sent back on review
    (helpdesk.tasky.api.send_back_task leaves a "Sent back: ..." comment)."""
    if not names:
        return {}
    comment = frappe.qb.DocType("Comment")
    return dict(
        frappe.qb.from_(comment)
        .select(comment.reference_name, Count("*"))
        .where(
            (comment.reference_doctype == "Task")
            & comment.reference_name.isin(names)
            & (comment.comment_type == "Info")
            & comment.content.like(SENT_BACK)
        )
        .groupby(comment.reference_name)
        .run()
    )


def self_made_tasks(rows) -> set[str]:
    """Tasks the doer made and took themselves: whoever created the task is one of
    its assignees, and nobody else gave it to them (tasky.permissions.get_assigners
    names the creator when no one assigned it)."""
    from helpdesk.tasky.permissions import get_assigners

    own = {r.name: r.owner for r in rows if r.owner in assignees(r._assign)}
    return {name for name, by in get_assigners(own).items() if by == own[name]}


def overdue_tasks(today) -> list[dict]:
    """Open tasks past their due date today. Held tasks and tasks waiting for
    review are left out: they wait on someone else."""
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(task)
        .left_join(project)
        .on(project.name == task.project)
        .select(
            task.name,
            task.project,
            task["_assign"],
            project.custom_department.as_("department"),
        )
        .where(task.status.isin(OPEN_STATUSES) & (task.exp_end_date < today))
        .run(as_dict=True)
    )
    return [
        {
            "name": r.name,
            "project": r.project,
            "department": r.department,
            "users": assignees(r._assign),
        }
        for r in rows
    ]


def logged_hours(start, end) -> list[dict]:
    """Hours in draft and submitted time logs of the period, per person and project."""
    log = frappe.qb.DocType("Timesheet Detail")
    sheet = frappe.qb.DocType("Timesheet")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(log)
        .join(sheet)
        .on(sheet.name == log.parent)
        .left_join(project)
        .on(project.name == log.project)
        .select(
            sheet.owner.as_("user"),
            log.project,
            project.custom_department.as_("department"),
            Sum(log.hours).as_("hours"),
        )
        .where(
            (log.parenttype == "Timesheet")
            & (sheet.docstatus < 2)
            & log.from_time.between(f"{start} 00:00:00", f"{end} 23:59:59")
        )
        .groupby(sheet.owner, log.project, project.custom_department)
        .run(as_dict=True)
    )
    return [
        {
            "user": r.user,
            "project": r.project,
            "department": r.department,
            "hours": flt(r.hours),
        }
        for r in rows
    ]


def delivered_posts(start, end) -> list[dict]:
    """Content posts due in the period that are published or missed (not upcoming),
    with everyone on them and the department of their tasks' project."""
    posts = [p for p in scored_posts(start, end) if p["timing"] != "Upcoming"]
    departments = post_departments([p["name"] for p in posts])
    return [
        {
            "name": p["name"],
            "project": None,
            "department": departments.get(p["name"]),
            "users": sorted(members(p) - SKIP),
            "timing": p["timing"],
        }
        for p in posts
    ]


def post_departments(names: list[str]) -> dict[str, str]:
    if not names:
        return {}
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(task)
        .join(project)
        .on(project.name == task.project)
        .select(task.content_post, project.custom_department)
        .where(task.content_post.isin(names) & project.custom_department.isnotnull())
        .run()
    )
    return dict(rows)


# --- per person --------------------------------------------------------------


def blank() -> dict:
    return {
        "tasks": 0,
        "dated": 0,
        "on_time": 0,
        "key": 0,
        # weighted work: the tasks' weights added up (task_weight)
        "weight": 0.0,
        "weight_on_time": 0.0,
        # the same, each task's weight times its quality (task_quality)
        "value": 0.0,
        "value_on_time": 0.0,
        "self_made": 0,
        "excellent": 0,
        "good": 0,
        "rework": 0,
        "sent_back": 0,
        "came_back": 0,
        "slips": 0,
        "overdue": 0,
        "hours": 0.0,
        "posts_on_time": 0,
        "posts_late": 0,
        "posts_missed": 0,
    }


def task_weight(task: dict) -> dict:
    """How much one task counts, worked out from the task itself (nobody types a
    weight), and why: {"weight": 0.5 to 4.5, "reasons": ["key", "8h estimate"]}.

    `task` has `key` (key task or milestone), `estimate` (estimated hours),
    `priority` and `self_made` (the doer made it and took it themselves). A
    self-made task counts half, and its key flag, priority and estimate beyond
    4 hours are ignored: the doer alone set them, so many small tasks of one's
    own can't outweigh a few real ones. Logged hours are never part of it.
    """
    w = TASK_WEIGHT
    self_made = bool(task.get("self_made"))
    weight = w["self_made_base"] if self_made else w["base"]
    reasons = [_("self-assigned, counts half")] if self_made else []
    if task.get("key") and not self_made:
        weight += w["key"]
        reasons.append(_("key"))
    hours = flt(task.get("estimate"))
    cap = w["self_made_size_cap"] if self_made else w["size_cap"]
    size = min(hours * w["size_per_hour"], cap)
    if size:
        weight += size
        reasons.append(
            _("{0}h estimate").format(f"{hours:g}")
            if size < cap
            else _("{0}h estimate (counts up to {1}h)").format(
                f"{hours:g}", f"{cap / w['size_per_hour']:g}"
            )
        )
    bonus = 0 if self_made else w["priority"].get(task.get("priority"), 0)
    if bonus:
        weight += bonus
        reasons.append(_("{0} priority").format(_(task["priority"])))
    return {"weight": round(weight, 3), "reasons": reasons}


def task_quality(task: dict) -> dict:
    """How well one task was done, as a factor on its weight, and why:
    {"quality": 0.25 to 1.25, "reasons": [...]}.

    The close rating (`rating`: Excellent 1.25, Good 1, Needs rework 0.5; unrated
    is 1, no penalty and no bonus), less 0.15 per send-back on review
    (`sent_back`) and 0.25 each time the task or its ticket came back after it
    was done (`came_back`).
    """
    q = QUALITY
    rating = task.get("rating")
    quality = q["rating"].get(rating, q["unrated"])
    reasons = [_("rated {0}").format(_(rating))] if rating in q["rating"] else []
    if task.get("sent_back"):
        quality += task["sent_back"] * q["sent_back"]
        reasons.append(_("sent back {0}×").format(task["sent_back"]))
    if task.get("came_back"):
        quality += task["came_back"] * q["came_back"]
        reasons.append(_("came back {0}×").format(task["came_back"]))
    quality = min(max(quality, q["floor"]), q["ceiling"])
    return {"quality": round(quality, 3), "reasons": reasons or [_("not rated")]}


def score_rules(period: str) -> dict:
    """The numbers behind weight, quality and the score, for the page's "How
    weight works": the page shows these, so it can't drift from the formula."""
    w = TASK_WEIGHT
    return {
        "weight": {
            **w,
            "min": w["self_made_base"],
            "max": w["base"] + w["key"] + w["size_cap"] + max(w["priority"].values()),
        },
        "quality": QUALITY,
        "score": WEIGHTS,
        "champion_minimum": PERIODS[period][1],
        "min_delivered": MIN_DELIVERED,
    }


def tally(data: dict, group) -> dict:
    """Each person's numbers per group: `group(row)` names the group a row counts
    in (e.g. its department), or None to leave it out. A task shared by several
    people counts in full for each of them."""
    out = defaultdict(lambda: defaultdict(blank))
    rating_field = {"Excellent": "excellent", "Good": "good", "Needs rework": "rework"}
    for t in data["tasks"]:
        g = group(t)
        if g is None:
            continue
        weight, value = t["weight"], t["weight"] * t["quality"]
        for user in t["users"]:
            s = out[g][user]
            s["tasks"] += 1
            s["dated"] += t["dated"]
            s["on_time"] += t["on_time"]
            s["key"] += t["key"]
            s["weight"] += weight
            s["value"] += value
            if t["on_time"]:
                s["weight_on_time"] += weight
                s["value_on_time"] += value
            s["self_made"] += t["self_made"]
            if t["rating"] in rating_field:
                s[rating_field[t["rating"]]] += 1
            s["sent_back"] += t["sent_back"]
            s["came_back"] += t["came_back"]
            s["slips"] += t["slips"]
    for t in data["overdue"]:
        g = group(t)
        if g is None:
            continue
        for user in t["users"]:
            out[g][user]["overdue"] += 1
    for row in data["hours"]:
        g = group(row)
        if g is not None and row["user"] not in SKIP:
            out[g][row["user"]]["hours"] += row["hours"]
    for post in data["posts"]:
        g = group(post)
        if g is None:
            continue
        field = {"On time": "posts_on_time", "Late": "posts_late"}.get(
            post["timing"], "posts_missed"
        )
        for user in post["users"]:
            out[g][user][field] += 1
    return out


def pct(part, whole) -> int | None:
    return round(part / whole * 100) if whole else None


def delivered(stats: dict) -> int:
    """How many tasks were completed and posts published."""
    return stats["tasks"] + stats["posts_on_time"] + stats["posts_late"]


def eligible(stats: dict, period: str, total: float) -> bool:
    """Did enough to be champion: weighted work (task weights plus posts
    published) of at least the period's minimum, from at least MIN_DELIVERED
    tasks and posts, and a positive score. Weighted, so a pile of tiny tasks of
    one's own doesn't qualify sooner than a few real ones."""
    weighted = stats["weight"] + stats["posts_on_time"] + stats["posts_late"]
    return (
        weighted >= PERIODS[period][1]
        and delivered(stats) >= MIN_DELIVERED
        and total > 0
    )


def score(stats: dict, period: str) -> dict:
    """A person's score for the period, with each part of it and the reasons.

    The single source of truth for the champion. Each task is worth its weight
    times its quality: half for finishing it, half for finishing it by its due
    date. `tasks` and `on_time` are the weights alone; `quality` is what the
    ratings, send-backs and comebacks add or take away. Hours are added last and
    capped at a tenth of the points earned by delivering, so long hours never
    beat delivering on time, and hours alone score nothing.
    """
    w = WEIGHTS
    done, on_time = w["done_share"], 1 - w["done_share"]
    parts = {
        "tasks": stats["weight"] * done,
        "on_time": stats["weight_on_time"] * on_time,
        "quality": (stats["value"] - stats["weight"]) * done
        + (stats["value_on_time"] - stats["weight_on_time"]) * on_time,
        "posts": stats["posts_on_time"] * w["post_on_time"]
        + stats["posts_late"] * w["post_late"],
        "missed_posts": stats["posts_missed"] * w["post_missed"],
        "overdue": stats["overdue"] * w["overdue"],
        "slips": stats["slips"] * w["slip"],
    }
    earned = sum(v for v in parts.values() if v > 0)
    parts["hours"] = min(stats["hours"] * w["hour"], earned * w["hours_cap_share"])
    total = round(sum(parts.values()), 1)
    breakdown = [
        {"key": k, "points": round(v, 1), "detail": part_detail(k, stats)}
        for k, v in parts.items()
        if round(v, 1)
    ]
    reasons = [
        b["detail"]
        for b in sorted(breakdown, key=lambda b: -b["points"])
        if b["points"] > 0 and b["key"] != "hours"
    ][:3]
    return {
        "score": total,
        "eligible": eligible(stats, period, total),
        "breakdown": breakdown,
        "reasons": reasons,
    }


def part_detail(key: str, s: dict) -> str:
    """What one part of the score stands for, in words."""
    if key == "tasks":
        text = _("Tasks done: {0}, weighted work {1}").format(
            s["tasks"], round(s["weight"], 1)
        )
        extra = []
        if s["key"]:
            extra.append(_("{0} key or milestones").format(s["key"]))
        if s["self_made"]:
            extra.append(_("{0} self-assigned at half weight").format(s["self_made"]))
        return f"{text} ({', '.join(extra)})" if extra else text
    if key == "on_time":
        return _("On time: {0}% ({1} of {2} with a due date)").format(
            pct(s["on_time"], s["dated"]), s["on_time"], s["dated"]
        )
    if key == "quality":
        return _("Quality: {0}").format(", ".join(quality_words(s)))
    if key == "posts":
        return _("Posts published: {0} on time, {1} late").format(
            s["posts_on_time"], s["posts_late"]
        )
    if key == "missed_posts":
        return _("Posts missed: {0}").format(s["posts_missed"])
    if key == "overdue":
        return _("Overdue now: {0}").format(s["overdue"])
    if key == "slips":
        return _("Due dates moved: {0}").format(s["slips"])
    return _("Hours logged: {0} (count lightly, capped)").format(round(s["hours"], 1))


def quality_words(s: dict) -> list[str]:
    """The ratings and signals behind a person's quality points."""
    words = [
        text.format(s[field])
        for field, text in (
            ("excellent", _("{0} rated excellent")),
            ("good", _("{0} rated good")),
            ("rework", _("{0} rated needs rework")),
            ("sent_back", _("sent back {0}×")),
            ("came_back", _("came back {0}×")),
        )
        if s[field]
    ]
    return words or [_("nothing rated")]


def rank(people: dict, period: str) -> list[dict]:
    """Everyone scored, best first. Ties go to the better on-time rate, then more
    tasks done, then fewer overdue."""
    rows = []
    for user, stats in people.items():
        rows.append({"user": user, "stats": stats, **score(stats, period)})
    rows.sort(
        key=lambda r: (
            -r["score"],
            -(pct(r["stats"]["on_time"], r["stats"]["dated"]) or 0),
            -r["stats"]["tasks"],
            r["stats"]["overdue"],
            r["user"],
        )
    )
    return rows


def champion_of(ranked: list[dict]) -> dict | None:
    """The best-scoring person who did enough in the period, if anyone did."""
    return next((r for r in ranked if r["eligible"]), None)


def totals(data: dict, keep) -> dict:
    """The team's figures for the rows `keep(row)` accepts. Unlike the per-person
    numbers, a task shared by several people counts once."""
    tasks = [t for t in data["tasks"] if keep(t)]
    dated = [t for t in tasks if t["dated"]]
    posts = [p for p in data["posts"] if keep(p)]
    return {
        "tasks": len(tasks),
        "weight": round(sum(t["weight"] for t in tasks), 1),
        "key": sum(t["key"] for t in tasks),
        "on_time_pct": pct(sum(t["on_time"] for t in dated), len(dated)),
        "hours": round(sum(r["hours"] for r in data["hours"] if keep(r)), 1),
        "overdue": sum(1 for t in data["overdue"] if keep(t)),
        "posts": sum(p["timing"] != "Missed" for p in posts),
        "posts_missed": sum(p["timing"] == "Missed" for p in posts),
    }


def trend(data: dict, keep, start, end, period: str) -> dict | None:
    """Tasks completed per day (week, month), per week (quarter, half) or per
    month (year); None for a single day."""
    if period == "today":
        return None
    start, end = getdate(start), getdate(end)
    if period in ("week", "month"):
        bucket = "day"
        dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    elif period == "year":
        bucket = "month"
        dates = [date(start.year, m, 1) for m in range(1, 13)]
    else:
        bucket = "week"
        first = start - timedelta(days=start.weekday())
        dates = [first + timedelta(weeks=i) for i in range((end - first).days // 7 + 1)]

    def bucket_of(day):
        if bucket == "day":
            return day
        if bucket == "month":
            return day.replace(day=1)
        return day - timedelta(days=day.weekday())

    counts = defaultdict(int)
    for t in data["tasks"]:
        if keep(t):
            counts[bucket_of(t["completed_on"])] += 1
    return {
        "bucket": bucket,
        "dates": [str(d) for d in dates],
        "values": [counts.get(d, 0) for d in dates],
    }


# --- AI analysis -------------------------------------------------------------


def analysis_facts(title: str, period_label: str, ranked: list, team: dict) -> dict:
    """The numbers the AI may use, and nothing else."""
    info = people_info([r["user"] for r in ranked])
    names = {u: i["name"] for u, i in info.items()}
    champion = champion_of(ranked)
    shown = [r for r in ranked if r["score"] or r["stats"]["overdue"]][:AI_PEOPLE_CAP]
    return {
        "team": title,
        "period": period_label,
        "totals": team,
        "champion": champion
        and {
            "name": names.get(champion["user"]),
            "score": champion["score"],
            "reasons": champion["reasons"],
        },
        "people": [
            {
                "name": names.get(r["user"]),
                "score": r["score"],
                "tasks_done": r["stats"]["tasks"],
                "key_tasks_done": r["stats"]["key"],
                "weighted_work": round(r["stats"]["weight"], 1),
                "on_time_pct": pct(r["stats"]["on_time"], r["stats"]["dated"]),
                "overdue_now": r["stats"]["overdue"],
                "due_date_moves": r["stats"]["slips"],
                "posts_on_time": r["stats"]["posts_on_time"],
                "posts_late": r["stats"]["posts_late"],
                "posts_missed": r["stats"]["posts_missed"],
                "sent_back": r["stats"]["sent_back"],
                "came_back": r["stats"]["came_back"],
                "rated_excellent": r["stats"]["excellent"],
                "rated_needs_rework": r["stats"]["rework"],
            }
            for r in shown
        ],
    }


def write_analysis(facts: dict) -> dict:
    """The AI's reading of the facts, or why there is none. Never raises: the
    dashboard and the champion work without it."""
    from helpdesk.ai_suggestion import is_ai_configured

    if not is_ai_configured():
        return {"status": "unavailable", "reason": _("AI isn't set up on this hub.")}
    try:
        result = call_haiku(SYSTEM_PROMPT, json.dumps(facts, indent=1, default=str))
    except Exception:  # noqa: BLE001 - provider errors vary; the dashboard still works
        frappe.log_error(
            title="Team dashboard analysis failed", message=frappe.get_traceback()
        )
        return {"status": "unavailable", "reason": _("The AI couldn't be reached.")}
    response = result.get("response") if isinstance(result, dict) else None
    analysis = clean_analysis(response, facts)
    if not analysis:
        frappe.log_error(
            title="Team dashboard: AI answer not usable", message=str(response)[:3000]
        )
        return {
            "status": "unavailable",
            "reason": _("The AI's answer couldn't be used."),
        }
    return {
        "status": "ready",
        **analysis,
        "generated_at": str(now_datetime()),
    }


def clean_analysis(response, facts: dict) -> dict | None:
    """Plain-text summary, risks and needs_help, keeping only sentences whose
    numbers all appear in the facts."""
    if not isinstance(response, dict):
        return None
    known = fact_numbers(facts)

    def honest(text) -> str:
        if not isinstance(text, str):
            return ""
        text = truncate(re.sub(r"<[^>]+>", "", text).strip(), AI_TEXT_CHARS)
        return "" if invents_numbers(text, known) else text

    def items(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [t for t in (honest(v) for v in value[:AI_ITEM_CAP]) if t]

    summary = " ".join(
        s
        for s in (
            honest(s)
            for s in re.split(r"(?<=[.!?])\s+", str(response.get("summary") or ""))
        )
        if s
    )
    if not summary:
        return None
    return {
        "summary": summary,
        "risks": items(response.get("risks")),
        "needs_help": items(response.get("needs_help")),
    }


def analysis_cache_key(
    period: str, start, department: str | None, is_group: bool = False
) -> str:
    scope = f"group:{department}" if is_group else department or ""
    return f"{CACHE_PREFIX}_analysis:{period}:{start}:{scope}"


# --- closing a period --------------------------------------------------------


def close_periods():
    """Scheduler, just after midnight: every period that ended yesterday gets its
    champions, one background job per period; then the repeat issues are worked out."""
    yesterday = add_days(getdate(nowdate()), -1)
    for period in PERIODS:
        start, end = period_bounds(period, yesterday)
        if end != yesterday:
            continue
        frappe.enqueue(
            "helpdesk.team_dashboard.close_period",
            queue="long",
            timeout=JOB_TIMEOUT,
            job_id=f"team-champions-{period}-{start}",
            deduplicate=True,
            now=frappe.flags.in_test,
            period=period,
            start=str(start),
            end=str(end),
        )
    # the Scoreboard's repeat issues, ready with their AI titles for the first visit
    frappe.enqueue(
        "helpdesk.repeat_issues.precompute",
        queue="long",
        timeout=JOB_TIMEOUT,
        job_id=f"repeat-issues-{yesterday}",
        deduplicate=True,
        now=frappe.flags.in_test,
    )


def close_period(period: str, start: str, end: str):
    """Champions of a closed period: the whole team, each department group (a
    main department with its sub-departments) and each active department.

    A period already closed is left as it was, so a re-run sends nobody a second
    notification and the history never changes. The badges earned in the period
    are awarded after the champions (helpdesk.competition), just as idempotently.
    """
    from helpdesk.competition import award_badges

    data = collect(start, end, with_overdue=True, today=add_days(end, 1))
    label = period_label(period, start, end)
    save_champion(period, start, end, None, data, label)
    for group, in_group in department_groups().items():
        save_champion(period, start, end, group, data, label, in_group)
    for department in active_departments():
        save_champion(period, start, end, department, data, label)
    award_badges(period, start, end, data)


def save_champion(
    period: str,
    start,
    end,
    department: str | None,
    data,
    label,
    in_group: list[str] | None = None,
):
    """Stores one scope's champion: the whole team (no department), a department,
    or, with `in_group` (its departments), the group that `department` heads."""
    from helpdesk.helpdesk.doctype.hd_team_champion.hd_team_champion import (
        HDTeamChampion,
    )

    period_type = PERIODS[period][0]
    is_group = in_group is not None
    if frappe.db.exists(
        "HD Team Champion",
        HDTeamChampion.record_name(period_type, start, department, is_group),
    ):
        return None
    keep = scope_filter(None if department is None else in_group or [department])
    ranked = rank(tally(data, lambda r: "scope" if keep(r) else None)["scope"], period)
    champion = champion_of(ranked)
    analysis = None
    if period not in QUIET_PERIODS and ranked:
        facts = analysis_facts(
            scope_title(department, is_group), label, ranked, totals(data, keep)
        )
        analysis = write_analysis(facts)
    doc = frappe.get_doc(
        {
            "doctype": "HD Team Champion",
            "period_type": period_type,
            "period_start": start,
            "period_end": end,
            "department": department,
            "is_group": int(is_group),
            "user": champion and champion["user"],
            "score": champion["score"] if champion else 0,
            "breakdown": json.dumps(champion["breakdown"], indent=1)
            if champion
            else None,
            "analysis": json.dumps(analysis, indent=1) if analysis else None,
            "generated_by_ai": int(bool(analysis and analysis["status"] == "ready")),
        }
    ).insert(ignore_permissions=True)
    if champion:
        announce(doc, label)
    return doc


def scope_filter(departments: list[str] | None):
    """Rows of these departments; every row when None (the whole team)."""
    if departments is None:
        return lambda r: True
    wanted = set(departments)
    return lambda r: r["department"] in wanted


def scope_title(department: str | None, is_group: bool = False) -> str:
    """How a scope is named: "Whole team", "ERP", or "ERP group"."""
    if not department:
        return _("Whole team")
    return _("{0} group").format(department) if is_group else department


def announce(doc, label: str):
    """Tells the champion, and the department's heads (a group's: its main
    department's heads; Agent Managers for the whole team), once."""
    from helpdesk.tasky.permissions import department_heads

    team = scope_title(doc.department, doc.is_group) if doc.department else None
    team = team or _("whole team")
    link = "/team-dashboard"
    if doc.department:
        link += f"?{'group' if doc.is_group else 'department'}={quote(doc.department)}"
    notify_users(
        [doc.user],
        "HD Team Champion",
        doc.name,
        _("You're the {0} champion for {1}").format(team, label),
        link=link,
    )
    notify_users(
        [u for u in department_heads(doc.department) if u != doc.user],
        "HD Team Champion",
        doc.name,
        _("{0} is the {1} champion for {2}").format(
            frappe.utils.get_fullname(doc.user), team, label
        ),
        link=link,
    )


def period_label(period: str, start, end) -> str:
    """How a closed period reads in a notification: "week of 5 Oct 2026"."""
    start = getdate(start)
    if period == "today":
        return frappe.utils.formatdate(start, "d MMM yyyy")
    if period == "week":
        return _("the week of {0}").format(frappe.utils.formatdate(start, "d MMM yyyy"))
    if period == "month":
        return frappe.utils.formatdate(start, "MMMM yyyy")
    if period == "quarter":
        return _("Q{0} {1}").format((start.month - 1) // 3 + 1, start.year)
    if period == "half":
        return _("H{0} {1}").format(1 if start.month <= 6 else 2, start.year)
    return str(start.year)


# --- shared lookups ----------------------------------------------------------


def active_departments() -> list[str]:
    department = frappe.qb.DocType("HD Department")
    return (
        frappe.qb.from_(department)
        .select(department.name)
        .where(department.is_active == 1)
        .orderby(department.sort_order)
        .run(pluck=True)
    )


def department_groups() -> dict[str, list[str]]:
    """The main departments that have active sub-departments, in display order:
    {"ERP": ["ERP", "GrowthX", "Internal / R&D"]}, the main department first. A
    sub-department of an inactive department isn't in any group."""
    department = frappe.qb.DocType("HD Department")
    rows = (
        frappe.qb.from_(department)
        .select(department.name, department.parent_department)
        .where(department.is_active == 1)
        .orderby(department.sort_order)
        .run()
    )
    active = {name for name, _parent in rows}
    groups: dict[str, list[str]] = {}
    for name, parent in rows:
        if parent in active:
            groups.setdefault(parent, [parent]).append(name)
    return {name: groups[name] for name, _parent in rows if name in groups}


def task_score(name: str) -> dict:
    """One task's weight and quality with their reasons, for the task dialog."""
    task = frappe.qb.DocType("Task")
    row = next(iter(scored_tasks(task.name == name)), None)
    if not row:
        return {}
    weight, quality = task_weight(row), task_quality(row)
    return {
        "weight": round(weight["weight"], 2),
        "weight_reasons": weight["reasons"],
        "quality": round(quality["quality"], 2),
        "quality_reasons": quality["reasons"],
        "self_made": row["self_made"],
    }


def people_info(users) -> dict[str, dict]:
    """Name, photo and whether the account is enabled, per user."""
    users = sorted({u for u in users if u})
    if not users:
        return {}
    user = frappe.qb.DocType("User")
    return {
        r.name: {
            "name": r.full_name or r.name,
            "image": r.user_image,
            "enabled": bool(r.enabled),
        }
        for r in frappe.qb.from_(user)
        .select(user.name, user.full_name, user.user_image, user.enabled)
        .where(user.name.isin(users))
        .run(as_dict=True)
    }
