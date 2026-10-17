"""Management insights for the TBO Smart app: how a department (or the whole team)
is delivering, where the risk is and how the work is spread. Read-only.

Built from what the hub already counts: the Scoreboard's numbers
(helpdesk.team_dashboard), the follow-up engine's escalations, the tickets' SLA
fields, capacity planning (helpdesk.api.capacity) and the AI with the Scoreboard's
number guard. Admins see every department; department heads the departments they
head (tasky.permissions.departments_headed). docs/tbo-smart-api.md (Insights).
"""

import json
import statistics
from collections import Counter

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from helpdesk import follow_ups
from helpdesk import team_dashboard as td
from helpdesk.ai_engine import call_haiku
from helpdesk.api.work import SLA_RISK_HOURS, _assignees, can_see_overview, sla_due_soon
from helpdesk.home_plan import clean_steps
from helpdesk.tasky.permissions import departments_headed, is_tasky_admin

TREND_PERIODS = 8
RISK_LIMIT = 5
WORKLOAD_LIMIT = 15
MIN_BULLETS = 3
SUMMARY_PREFIX = "insights_summary"
# after a failed AI call, the summary is built without it for this long
SUMMARY_RETRY_SECONDS = 15 * 60
CLOSED_TASK_STATUSES = ["Completed", "Cancelled", "Template"]
# past holds aren't recorded, so work held or in review now is left out of the
# overdue trend, as "Overdue now" leaves it out today
WAITING_STATUSES = ["On Hold", "Pending Review"]

SUMMARY_PROMPT = """You write a short briefing for a manager at TBO about one team's work in a period.
Use only the facts in the JSON you are given. Never invent people, projects, numbers, dates or causes. Every number you write must appear in the facts.
Write 3 to 5 bullets, most important first: how delivery went against the previous period, then the biggest risks (overdue work, slipped milestones, escalations, SLA breaches) and who or what needs attention first.
Be kind and specific about people; never judge hours worked. Each bullet is one short plain-text sentence, no HTML, no markdown, no numbering.
Reply with JSON only: {"bullets": ["...", "..."]}"""


def scope_for(user: str, department: str | None) -> list[str] | None:
    """The departments the insights cover: for admins every one (None) or the one
    asked for; for department heads the ones they head, or one of them. Everyone
    else is refused."""
    if is_tasky_admin(user):
        if department and department not in td.active_departments():
            frappe.throw(_("{0} isn't an active department.").format(department))
        return [department] if department else None
    headed = departments_headed(user)
    if not headed:
        frappe.throw(
            _("Only department heads and managers see the team insights."),
            frappe.PermissionError,
        )
    if department and department not in headed:
        frappe.throw(
            _("You see the insights of the departments you head only."),
            frappe.PermissionError,
        )
    return [department] if department else headed


def in_scope(scope: list[str] | None):
    if scope is None:
        return lambda r: True
    return lambda r: r["department"] in scope


def covers_tickets(scope: list[str] | None) -> bool:
    """Tickets belong to the support department (Settings → Follow-ups); the whole
    team covers them too."""
    if scope is None:
        return True
    return follow_ups.get_settings().ticket_department in scope


def insights(user: str, period: str, department: str | None, today) -> dict:
    scope = scope_for(user, department)
    keep = in_scope(scope)
    tickets = covers_tickets(scope)
    start, end = td.period_bounds(period, today)
    c_start, c_end = td.comparison_bounds(period, start, end, today)
    data = td.collect(start, end, with_overdue=True, today=today)
    prev = td.collect(c_start, c_end, with_overdue=False, today=today)
    escalated = escalations_in(scope, tickets)
    tile_list = tiles(data, prev, keep, tickets, (start, end), (c_start, c_end))
    tile_list.insert(3, tile("escalations_open", _("Escalations open"), len(escalated)))
    risk = risks(data, keep, scope, tickets, escalated, today)
    label = ", ".join(scope) if scope else _("Whole team")
    return {
        "period": period,
        "period_label": td.period_label(period, start, end),
        "range": {"start": str(start), "end": str(end)},
        "compare": {"start": str(c_start), "end": str(c_end)},
        "scope": {"departments": scope, "label": label, "tickets": tickets},
        "tiles": tile_list,
        "trend": trend(period, today, data, keep),
        "risks": risk,
        "workload": workload(user, scope, keep, data),
        "summary": summary(period, start, end, scope, label, tile_list, risk),
    }


# --- tiles -------------------------------------------------------------------------


def tile(key: str, label: str, value, previous=None, better=None, unit=None) -> dict:
    """`better` says which way is good ("up", "down"), for the arrow's colour; None
    for state that has no previous value, or for hours, which aren't judged."""
    delta = (
        round(value - previous, 1)
        if value is not None and previous is not None
        else None
    )
    return {
        "key": key,
        "label": label,
        "value": value,
        "previous": previous,
        "delta": delta,
        "unit": unit,
        "better": better,
    }


def tiles(data, prev, keep, tickets: bool, now_range, before_range) -> list[dict]:
    now, before = td.totals(data, keep), td.totals(prev, keep)
    t_now = ticket_figures(*now_range) if tickets else {}
    t_before = ticket_figures(*before_range) if tickets else {}
    return [
        tile("tasks_done", _("Tasks done"), now["tasks"], before["tasks"], "up"),
        tile(
            "on_time_pct",
            _("On time"),
            now["on_time_pct"],
            before["on_time_pct"],
            "up",
            "%",
        ),
        tile("overdue_now", _("Overdue now"), now["overdue"]),
        tile(
            "sla_breaches",
            _("SLA breaches"),
            t_now.get("breaches"),
            t_before.get("breaches"),
            "down",
        ),
        tile(
            "first_response_median",
            _("First response (median)"),
            t_now.get("first_response_minutes"),
            t_before.get("first_response_minutes"),
            "down",
            "min",
        ),
        tile(
            "hours_logged", _("Hours logged"), now["hours"], before["hours"], None, "h"
        ),
    ]


def ticket_figures(start, end) -> dict:
    """Tickets opened in the period whose SLA failed, and the median first response
    (minutes) of the tickets first answered in it."""
    ticket = frappe.qb.DocType("HD Ticket")
    breaches = (
        frappe.qb.from_(ticket)
        .select(Count("*"))
        .where(
            (ticket.agreement_status == "Failed")
            & ticket.opening_date.between(getdate(start), getdate(end))
        )
        .run()[0][0]
    )
    seconds = (
        frappe.qb.from_(ticket)
        .select(ticket.first_response_time)
        .where(
            ticket.first_responded_on.between(
                f"{getdate(start)} 00:00:00", f"{getdate(end)} 23:59:59"
            )
            & (ticket.first_response_time > 0)
        )
        .run(pluck=True)
    )
    return {
        "breaches": breaches,
        "first_response_minutes": round(statistics.median(seconds) / 60)
        if seconds
        else None,
    }


def escalations_in(scope: list[str] | None, tickets: bool) -> list:
    """Work escalated to L2 or above (follow_ups.escalations) in scope: tasks by their
    project's department, tickets when the scope covers them."""
    found = follow_ups.escalations()
    departments = task_departments([f.name for f in found if f.doctype == "Task"])
    return [
        f
        for f in found
        if (f.doctype == "HD Ticket" and tickets)
        or (f.doctype == "Task" and (scope is None or departments.get(f.name) in scope))
    ]


def task_departments(tasks: list[str]) -> dict[str, str]:
    if not tasks:
        return {}
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    return dict(
        frappe.qb.from_(task)
        .join(project)
        .on(project.name == task.project)
        .select(task.name, project.custom_department)
        .where(task.name.isin(tasks))
        .run()
    )


# --- trend -------------------------------------------------------------------------


def trend(period: str, today, data: dict, keep) -> list[dict]:
    """The last TREND_PERIODS periods, this one included: tasks done, on-time %
    and overdue at each period's end (now, for this one)."""
    periods = td.recent_periods(period, TREND_PERIODS, today)
    overdue = overdue_on([getdate(add_days(e, 1)) for _s, e in periods[:-1]], keep)
    rows = []
    for index, (start, end) in enumerate(periods):
        current = index == len(periods) - 1
        figures = td.totals(
            data
            if current
            else td.collect(start, end, with_overdue=False, today=today),
            keep,
        )
        rows.append(
            {
                "start": str(start),
                "end": str(end),
                "label": td.period_label(period, start, end),
                "throughput": figures["tasks"],
                "on_time_pct": figures["on_time_pct"],
                "overdue": figures["overdue"]
                if current
                else overdue[getdate(add_days(end, 1))],
            }
        )
    return rows


def overdue_on(days: list, keep) -> dict:
    """How many tasks were past their due date on each of `days` and not completed
    before it, in one query."""
    if not days:
        return {}
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(task)
        .left_join(project)
        .on(project.name == task.project)
        .select(
            task.exp_end_date,
            task.status,
            task.completed_on,
            project.custom_department.as_("department"),
        )
        .where(
            (task.exp_end_date < max(days))
            & task.status.notin(["Cancelled", "Template", *WAITING_STATUSES])
            & ((task.status != "Completed") | (task.completed_on >= min(days)))
        )
        .run(as_dict=True)
    )

    def late_on(row, day) -> bool:
        if getdate(row.exp_end_date) >= day:
            return False
        if row.status != "Completed":
            return True
        return bool(row.completed_on) and getdate(row.completed_on) >= day

    return {day: sum(1 for r in rows if keep(r) and late_on(r, day)) for day in days}


# --- risks -------------------------------------------------------------------------


def risks(data, keep, scope, tickets: bool, escalated: list, today) -> dict:
    soon = breaching_tickets() if tickets else []
    return {
        "projects": project_risks(data, keep, scope, today),
        "people": people_risks(data, keep, escalated),
        "tickets_breaching_soon": soon[:RISK_LIMIT],
        "tickets_breaching_count": len(soon),
        "breaching_within_hours": SLA_RISK_HOURS,
    }


def project_risks(data, keep, scope, today) -> list[dict]:
    """Open projects most off track: overdue tasks now, then milestones that moved
    or passed their date."""
    overdue = Counter(t["project"] for t in data["overdue"] if keep(t) and t["project"])
    slipped = slipped_milestones(scope, today)
    names = list(set(overdue) | set(slipped))
    if not names:
        return []
    project = frappe.qb.DocType("Project")
    info = {
        r.name: r
        for r in frappe.qb.from_(project)
        .select(project.name, project.project_name, project.custom_department)
        .where(project.name.isin(names) & (project.status == "Open"))
        .run(as_dict=True)
    }
    rows = [
        {
            "project": name,
            "project_name": info[name].project_name or name,
            "department": info[name].custom_department,
            "overdue": overdue.get(name, 0),
            "slipped_milestones": slipped.get(name, 0),
        }
        for name in names
        if name in info
    ]
    rows.sort(
        key=lambda r: (-r["overdue"], -r["slipped_milestones"], r["project_name"])
    )
    return rows[:RISK_LIMIT]


def slipped_milestones(scope, today) -> dict[str, int]:
    """Open milestones per project whose due date moved or has passed."""
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    query = (
        frappe.qb.from_(task)
        .join(project)
        .on(project.name == task.project)
        .select(task.project, Count("*"))
        .where(
            (task.is_milestone == 1)
            & task.status.notin(CLOSED_TASK_STATUSES)
            & ((task.slip_count > 0) | (task.exp_end_date < getdate(today)))
        )
        .groupby(task.project)
    )
    if scope is not None:
        query = query.where(project.custom_department.isin(scope))
    return dict(query.run())


def people_risks(data, keep, escalated: list) -> list[dict]:
    """The people with the most overdue and escalated work: names and counts only."""
    overdue = Counter(u for t in data["overdue"] if keep(t) for u in t["users"])
    escalations = Counter(u for f in escalated for u in f.owners)
    users = set(overdue) | set(escalations)
    info = td.people_info(users)
    rows = [
        {
            "user": u,
            "full_name": info.get(u, {}).get("name") or u,
            "overdue": overdue.get(u, 0),
            "escalated": escalations.get(u, 0),
        }
        for u in users
    ]
    rows.sort(key=lambda r: (-(r["overdue"] + r["escalated"]), r["full_name"]))
    return rows[:RISK_LIMIT]


def breaching_tickets() -> list[dict]:
    """Open tickets whose SLA runs out within SLA_RISK_HOURS, soonest first: the
    first reply until it is given, then the resolution."""
    from helpdesk.api.home import _open_tickets

    now = now_datetime()
    soon = []
    for t in _open_tickets():
        if t.status_category != "Open":
            continue
        responding = bool(t.response_by and not t.first_responded_on)
        due = t.response_by if responding else t.resolution_by
        due = get_datetime(due) if due else None
        if due and sla_due_soon(due, now):
            soon.append((due, responding, t))
    soon.sort(key=lambda item: item[0])
    names = td.people_info({u for _d, _r, t in soon for u in _assignees(t._assign)})
    return [
        {
            "ticket": str(t.name),
            "subject": t.subject,
            "due": str(due),
            "kind": "first_response" if responding else "resolution",
            "assignees": [
                names.get(u, {}).get("name") or u for u in _assignees(t._assign)
            ],
        }
        for due, responding, t in soon
    ]


# --- workload ----------------------------------------------------------------------


def workload(user: str, scope, keep, data: dict) -> dict:
    """Open tasks per person in scope, busiest first, with overdue now and, for people
    who plan capacity, next week's load (helpdesk.api.capacity)."""
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(task)
        .left_join(project)
        .on(project.name == task.project)
        .select(task["_assign"], project.custom_department.as_("department"))
        .where(task.status.notin(CLOSED_TASK_STATUSES))
        .run(as_dict=True)
    )
    open_tasks = Counter(u for r in rows if keep(r) for u in td.assignees(r._assign))
    overdue = Counter(u for t in data["overdue"] if keep(t) for u in t["users"])
    capacity = capacity_by_person(user, scope)
    info = td.people_info(open_tasks)
    people = [
        {
            "user": u,
            "full_name": info[u]["name"],
            "image": info[u]["image"],
            "open_tasks": n,
            "overdue": overdue.get(u, 0),
            **((capacity or {}).get(u) or {}),
        }
        for u, n in open_tasks.items()
        if info.get(u, {}).get("enabled")
    ]
    people.sort(key=lambda p: (-p["open_tasks"], p["full_name"]))
    return {
        "people": people[:WORKLOAD_LIMIT],
        "average_open": round(statistics.mean(p["open_tasks"] for p in people), 1)
        if people
        else 0,
        "capacity": capacity is not None,
    }


def capacity_by_person(user: str, scope) -> dict | None:
    """Next week's utilisation, load flag and free hours per person, from capacity
    planning; None for someone who doesn't plan capacity (it is for project
    managers, leads and admins)."""
    from helpdesk.api.capacity import get_capacity

    if not can_see_overview(user):
        return None
    department = scope[0] if scope and len(scope) == 1 else None
    try:
        planned = get_capacity(weeks=1, department=department)
    except frappe.PermissionError:
        return None
    return {
        p["user"]: {
            "utilisation": p["utilisation"],
            "load": p["flag"],
            "free_hours": p["free"],
        }
        for p in planned["people"]
    }


# --- the summary ---------------------------------------------------------------------


def summary(period, start, end, scope, label, tile_list, risk) -> dict:
    """3–5 bullets: the AI's, cached per period and scope, or the same facts as plain
    sentences when the AI is off, fails or answers badly, and always for a day (as
    the Scoreboard writes no analysis for a day)."""
    from helpdesk.ai_suggestion import is_ai_configured

    rules = {"source": "rules", "bullets": rule_bullets(tile_list, risk)}
    if period in td.QUIET_PERIODS:
        return {**rules, "reason": None}
    key = f"{SUMMARY_PREFIX}:{period}:{start}:{','.join(sorted(scope or [])) or '*'}"
    cached = frappe.cache.get_value(key, expires=True)
    if cached:
        return cached
    if not is_ai_configured():
        return {**rules, "reason": _("AI isn't set up on this hub.")}
    if frappe.cache.get_value(f"{key}:failed", expires=True):
        return {
            **rules,
            "reason": _("The AI couldn't write a summary a few minutes ago."),
        }
    facts = summary_facts(label, td.period_label(period, start, end), tile_list, risk)
    bullets, reason = write_bullets(facts)
    if not bullets:
        frappe.cache.set_value(f"{key}:failed", 1, expires_in_sec=SUMMARY_RETRY_SECONDS)
        return {**rules, "reason": reason}
    written = {
        "source": "ai",
        "bullets": bullets,
        "reason": None,
        "generated_at": str(now_datetime()),
    }
    frappe.cache.set_value(key, written, expires_in_sec=td.ANALYSIS_SECONDS)
    return written


def summary_facts(label: str, period_label: str, tile_list: list, risk: dict) -> dict:
    """The numbers the AI may use, and nothing else; never hours as a judgement."""
    return {
        "team": label,
        "period": period_label,
        "figures": {
            t["label"]: {"now": t["value"], "previous period": t["previous"]}
            for t in tile_list
            if t["key"] != "hours_logged" and t["value"] is not None
        },
        "projects_at_risk": [
            {
                "project": p["project_name"],
                "overdue_tasks": p["overdue"],
                "slipped_milestones": p["slipped_milestones"],
            }
            for p in risk["projects"]
        ],
        "people_with_most_late_work": [
            {
                "name": p["full_name"],
                "overdue_tasks": p["overdue"],
                "escalated": p["escalated"],
            }
            for p in risk["people"]
        ],
        "tickets_breaching_soon": risk["tickets_breaching_count"],
    }


def write_bullets(facts: dict) -> tuple[list[str], str | None]:
    """The AI's bullets, or none and why. Never raises: the insights work without it.
    Any bullet with a number that isn't in the facts is dropped (home_plan.clean_steps,
    the Scoreboard's guard)."""
    try:
        result = call_haiku(
            SUMMARY_PROMPT, json.dumps(facts, indent=1, default=str), job="summary"
        )
    except Exception:  # noqa: BLE001 - provider errors vary; the insights still work
        frappe.log_error(title="Team insights summary failed")
        return [], _("The AI couldn't be reached.")
    response = result.get("response") if isinstance(result, dict) else None
    bullets = clean_steps(
        {"steps": response.get("bullets")} if isinstance(response, dict) else None,
        facts,
    )
    if len(bullets) < MIN_BULLETS:
        frappe.log_error(
            title="Team insights: AI answer not usable", message=str(response)[:3000]
        )
        return [], _("The AI's answer couldn't be used.")
    return bullets, None


def rule_bullets(tile_list: list, risk: dict) -> list[str]:
    """The same facts as plain sentences."""
    t = {x["key"]: x for x in tile_list}
    bullets = [
        _("{0} tasks done (previous period {1}).").format(
            t["tasks_done"]["value"], t["tasks_done"]["previous"]
        )
    ]
    on_time = t["on_time_pct"]
    if on_time["value"] is not None:
        bullets.append(
            _("{0}% on time (previous period {1}%).").format(
                on_time["value"], on_time["previous"]
            )
            if on_time["previous"] is not None
            else _("{0}% on time.").format(on_time["value"])
        )
    bullets.append(
        _("{0} tasks overdue now; {1} items escalated to a head or above.").format(
            t["overdue_now"]["value"], t["escalations_open"]["value"]
        )
    )
    if risk["projects"]:
        p = risk["projects"][0]
        bullets.append(
            _("Most at risk: {0}, {1} overdue and {2} slipped milestones.").format(
                p["project_name"], p["overdue"], p["slipped_milestones"]
            )
        )
    if t["sla_breaches"]["value"] is not None:
        bullets.append(
            _("{0} SLA breaches; {1} tickets breach within {2} hours.").format(
                t["sla_breaches"]["value"],
                risk["tickets_breaching_count"],
                risk["breaching_within_hours"],
            )
        )
    return bullets[:5]
