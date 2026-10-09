"""Team dashboard: who delivered what in a period, and who the champion is.

The numbers come from the hub's own records: Tasks (completion date, due date,
key/milestone, estimate, slips, send-backs on review), Timesheets (hours) and
the content calendar (posts published on time). `score()` is the one place a
person's score is worked out; the dashboard, the champions and the AI analysis
all use it. See docs/team-dashboard.md for the formula and its reasons.

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

from helpdesk.ai_engine import call_haiku
from helpdesk.api.content_performance import members, scored_posts
from helpdesk.api.ticket_ai import truncate
from helpdesk.work_reminders import SKIP, notify_users

# period key -> (HD Team Champion period type, least work delivered to be champion)
PERIODS = {
    "today": ("Day", 2),
    "week": ("Week", 3),
    "month": ("Month", 5),
    "quarter": ("Quarter", 8),
    "half": ("Half year", 12),
    "year": ("Year", 20),
}
# a day's champion is kept for the history but nobody is notified, and no AI runs
QUIET_PERIODS = ("today",)

WEIGHTS = {
    # every completed task is worth 1, a key task or milestone 1 more, and a
    # bigger task (by its estimate) up to 2 more
    "task": 1.0,
    "key": 1.0,
    "size_per_hour": 0.125,
    "size_cap": 2.0,
    # half of a task's worth is for doing it, half for doing it by its due date
    "done_share": 0.5,
    # approved on review without being sent back
    "first_time": 0.5,
    "post_on_time": 1.0,
    "post_late": 0.5,
    "post_missed": -1.0,
    "overdue": -1.0,
    "slip": -0.5,
    # hours count lightly, and never for more than a tenth of what was delivered
    "hour": 0.05,
    "hours_cap_share": 0.1,
}

OPEN_STATUSES = ("Open", "Working", "Overdue")
SENT_BACK = "Sent back:%"
CACHE_PREFIX = "team_dashboard"
CACHE_SECONDS = 300
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


# --- the numbers -------------------------------------------------------------


def collect(start, end, with_overdue: bool = True, today=None) -> dict:
    """Every row the dashboard counts in the period, for everyone; cached briefly.

    `with_overdue` adds the open tasks overdue today, which only mean something for
    the period in progress or one that just closed.
    """
    today = getdate(today or nowdate())
    key = f"{CACHE_PREFIX}:{start}:{end}:{int(with_overdue)}:{today}"
    cached = frappe.cache.get_value(key, expires=True)
    if cached is not None:
        return cached
    data = {
        "tasks": completed_tasks(start, end),
        "overdue": overdue_tasks(today) if with_overdue else [],
        "hours": logged_hours(start, end),
        "posts": delivered_posts(start, end),
    }
    frappe.cache.set_value(key, data, expires_in_sec=CACHE_SECONDS)
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
    """Tasks completed in the period, with their project's department and send-backs."""
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
            task.exp_end_date,
            task.completed_on,
            task.is_key,
            task.is_milestone,
            task.custom_estimated_hours,
            task.slip_count,
            project.custom_department.as_("department"),
            project.review_before_done,
        )
        .where((task.status == "Completed") & task.completed_on.between(start, end))
        .run(as_dict=True)
    )
    sent_back = send_backs(start, end)
    return [
        {
            "name": r.name,
            "project": r.project,
            "department": r.department,
            "users": assignees(r._assign),
            "completed_on": getdate(r.completed_on),
            "dated": bool(r.exp_end_date),
            "on_time": bool(
                r.exp_end_date and getdate(r.completed_on) <= getdate(r.exp_end_date)
            ),
            "key": bool(r.is_key or r.is_milestone),
            "estimate": flt(r.custom_estimated_hours),
            "slips": r.slip_count or 0,
            "reviewed": bool(r.review_before_done),
            "sent_back": sent_back.get(r.name, 0),
        }
        for r in rows
    ]


def send_backs(start, end) -> dict[str, int]:
    """How often each task completed in the period was sent back on review
    (helpdesk.tasky.api.send_back_task leaves a "Sent back: ..." comment)."""
    task = frappe.qb.DocType("Task")
    comment = frappe.qb.DocType("Comment")
    return dict(
        frappe.qb.from_(comment)
        .join(task)
        .on(task.name == comment.reference_name)
        .select(comment.reference_name, Count("*"))
        .where(
            (comment.reference_doctype == "Task")
            & (comment.comment_type == "Info")
            & comment.content.like(SENT_BACK)
            & (task.status == "Completed")
            & task.completed_on.between(start, end)
        )
        .groupby(comment.reference_name)
        .run()
    )


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
        "weight": 0.0,
        "weight_on_time": 0.0,
        "reviewed": 0,
        "first_time": 0,
        "slips": 0,
        "overdue": 0,
        "hours": 0.0,
        "posts_on_time": 0,
        "posts_late": 0,
        "posts_missed": 0,
    }


def task_weight(task: dict) -> float:
    """What one completed task is worth before the on-time share."""
    size = min(task["estimate"] * WEIGHTS["size_per_hour"], WEIGHTS["size_cap"])
    return WEIGHTS["task"] + (WEIGHTS["key"] if task["key"] else 0) + size


def tally(data: dict, group) -> dict:
    """Each person's numbers per group: `group(row)` names the group a row counts
    in (e.g. its department), or None to leave it out. A task shared by several
    people counts in full for each of them."""
    out = defaultdict(lambda: defaultdict(blank))
    for t in data["tasks"]:
        g = group(t)
        if g is None:
            continue
        weight = task_weight(t)
        for user in t["users"]:
            s = out[g][user]
            s["tasks"] += 1
            s["dated"] += t["dated"]
            s["on_time"] += t["on_time"]
            s["key"] += t["key"]
            s["weight"] += weight
            s["weight_on_time"] += weight if t["on_time"] else 0
            s["slips"] += t["slips"]
            if t["reviewed"]:
                s["reviewed"] += 1
                s["first_time"] += not t["sent_back"]
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
    """Tasks completed and posts published: what the minimum activity counts."""
    return stats["tasks"] + stats["posts_on_time"] + stats["posts_late"]


def score(stats: dict, period: str) -> dict:
    """A person's score for the period, with each part of it and the reasons.

    The single source of truth for the champion. Hours are added last and capped
    at a tenth of the points earned by delivering, so long hours never beat
    delivering on time, and hours alone score nothing.
    """
    w = WEIGHTS
    parts = {
        "tasks": stats["weight"] * w["done_share"],
        "on_time": stats["weight_on_time"] * (1 - w["done_share"]),
        "first_time": stats["first_time"] * w["first_time"],
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
        "eligible": delivered(stats) >= PERIODS[period][1] and total > 0,
        "breakdown": breakdown,
        "reasons": reasons,
    }


def part_detail(key: str, s: dict) -> str:
    """What one part of the score stands for, in words."""
    if key == "tasks":
        text = _("Tasks done: {0}").format(s["tasks"])
        if s["key"]:
            text += " " + _("({0} key or milestones)").format(s["key"])
        return text
    if key == "on_time":
        return _("On time: {0}% ({1} of {2} with a due date)").format(
            pct(s["on_time"], s["dated"]), s["on_time"], s["dated"]
        )
    if key == "first_time":
        return _("Approved without a send-back: {0} of {1}").format(
            s["first_time"], s["reviewed"]
        )
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
                "on_time_pct": pct(r["stats"]["on_time"], r["stats"]["dated"]),
                "overdue_now": r["stats"]["overdue"],
                "due_date_moves": r["stats"]["slips"],
                "posts_on_time": r["stats"]["posts_on_time"],
                "posts_late": r["stats"]["posts_late"],
                "posts_missed": r["stats"]["posts_missed"],
                "sent_back": r["stats"]["reviewed"] - r["stats"]["first_time"],
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
    known = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(facts, default=str)))

    def honest(text) -> str:
        if not isinstance(text, str):
            return ""
        text = truncate(re.sub(r"<[^>]+>", "", text).strip(), AI_TEXT_CHARS)
        return "" if set(re.findall(r"\d+(?:\.\d+)?", text)) - known else text

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


def analysis_cache_key(period: str, start, department: str | None) -> str:
    return f"{CACHE_PREFIX}_analysis:{period}:{start}:{department or ''}"


# --- closing a period --------------------------------------------------------


def close_periods():
    """Scheduler, just after midnight: every period that ended yesterday gets its
    champions, one background job per period."""
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


def close_period(period: str, start: str, end: str):
    """Champions of a closed period: the whole team and each active department.

    A period already closed is left as it was, so a re-run sends nobody a second
    notification and the history never changes.
    """
    data = collect(start, end, with_overdue=True, today=add_days(end, 1))
    label = period_label(period, start, end)
    for department in [None, *active_departments()]:
        save_champion(period, start, end, department, data, label)


def save_champion(period: str, start, end, department: str | None, data, label):
    from helpdesk.helpdesk.doctype.hd_team_champion.hd_team_champion import (
        HDTeamChampion,
    )

    period_type = PERIODS[period][0]
    if frappe.db.exists(
        "HD Team Champion", HDTeamChampion.record_name(period_type, start, department)
    ):
        return None
    keep = (
        (lambda r: True)
        if department is None
        else (lambda r: r["department"] == department)
    )
    ranked = rank(tally(data, lambda r: "scope" if keep(r) else None)["scope"], period)
    champion = champion_of(ranked)
    analysis = None
    if period not in QUIET_PERIODS and ranked:
        facts = analysis_facts(
            department or _("Whole team"), label, ranked, totals(data, keep)
        )
        analysis = write_analysis(facts)
    doc = frappe.get_doc(
        {
            "doctype": "HD Team Champion",
            "period_type": period_type,
            "period_start": start,
            "period_end": end,
            "department": department,
            "user": champion and champion["user"],
            "score": champion["score"] if champion else 0,
            "breakdown": json.dumps(champion["breakdown"], indent=1)
            if champion
            else None,
            "analysis": json.dumps(analysis, indent=1) if analysis else None,
            "generated_by_ai": int(bool(analysis and analysis["status"] == "ready")),
        }
    ).insert(ignore_permissions=True)
    if champion and period not in QUIET_PERIODS:
        announce(doc, label)
    return doc


def announce(doc, label: str):
    """Tells the champion, and the department's heads (Agent Managers for the
    whole team), once."""
    from helpdesk.tasky.permissions import department_heads

    team = doc.department or _("whole team")
    link = (
        f"/team-dashboard?department={quote(doc.department)}"
        if doc.department
        else "/team-dashboard"
    )
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
