"""Capacity planning: can we take this on, and who has room in the coming weeks.

This plans work ahead; it doesn't track or judge the hours people spent. Each
person's available hours come from the work calendar (weekly off, the Saturdays
off rule, the default SLA's holidays) at HD Work Settings' focused hours per day.
Their planned load is the remaining estimated hours of their open tasks, spread
over the working days up to each task's due date (see `task_allocation`).
"""

from bisect import bisect_left, bisect_right

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, cint, flt, getdate, nowdate

from helpdesk.api.customization import hours_per_day
from helpdesk.api.work import (
    WAITING_ON_TASK,
    _assignees,
    _full_names,
    _team_members,
    can_see_overview,
)
from helpdesk.task_estimates import (
    DEFAULT_MAX_DAYS,
    fallback_estimate,
    reference_durations,
    weekly_off_days,
)
from helpdesk.tasky.permissions import (
    get_led_projects,
    get_managed_projects,
    is_tasky_admin,
)
from helpdesk.utils import agent_only
from helpdesk.work_calendar import is_saturday_off, saturday_rule

WEEK_CHOICES = (1, 2, 4)
DEFAULT_WEEKS = 2
# work someone can pick up now; On Hold and Pending Review wait on someone else
PLANNED_STATUSES = ("Open", "Working", "Overdue", WAITING_ON_TASK)
BUSY_FROM = 80
OVERLOADED = "overloaded"
BUSY = "busy"
AVAILABLE = "available"
TOP_TASKS = 5
# how far ahead the calendar is laid out to spread tasks due later
HORIZON_DAYS = 366


@frappe.whitelist()
@agent_only
def get_capacity(
    weeks: int = DEFAULT_WEEKS,
    department: str | None = None,
    project: str | None = None,
) -> dict:
    """Per person: available and planned hours per day and week over the next `weeks` weeks."""
    user = frappe.session.user
    if not can_see_overview(user):
        frappe.throw(
            _("Only project managers and leads can plan the team's capacity."),
            frappe.PermissionError,
        )
    weeks = cint(weeks) if cint(weeks) in WEEK_CHOICES else DEFAULT_WEEKS

    projects = _scoped_projects(user, department, project)
    people = _team_members(user, projects) if projects != [] else set()
    visible = None if is_tasky_admin(user) else _own_projects(user)

    holiday_dates = holidays()
    start, end = planning_window(getdate(nowdate()), weeks, holiday_dates)
    calendar = working_days(start, add_days(start, HORIZON_DAYS), holiday_dates)
    window = calendar[: bisect_right(calendar, end)]
    per_day = hours_per_day()

    tasks = _planned_tasks(people)
    infos = _project_info({t.project for t in tasks if t.project})
    typical = _typical_estimates(tasks, infos)
    loads = {person: {} for person in people}
    shares = []
    for task in tasks:
        assignees = _assignees(task._assign)
        allocation = task_allocation(
            task, typical.get(task.name), calendar, start, per_day
        )
        hours = {
            day: value / len(assignees)
            for day, value in allocation["by_day"].items()
            if day <= end
        }
        total = sum(hours.values())
        if not total:
            continue
        for person in assignees:
            if person not in loads:
                continue
            for day, value in hours.items():
                loads[person][day] = loads[person].get(day, 0) + value
            shares.append((person, task, total, allocation["typical"]))

    names = _full_names(people)
    rows = [
        _person_row(p, names.get(p) or p, loads[p], window, start, end, per_day)
        for p in people
    ]
    _add_contributions(rows, shares, infos, visible)
    rows.sort(key=lambda r: (-(r["utilisation"] or 0), r["full_name"]))
    return {
        # the server's today, so the page doesn't go by the browser's clock
        "today": nowdate(),
        "start": str(start),
        "end": str(end),
        "hours_per_day": per_day,
        "weeks": [
            {"start": str(w_start), "end": str(w_end)}
            for w_start, w_end in week_ranges(start, end)
        ],
        "people": rows,
        "totals": _totals(rows),
        "by_department": _by_department(shares, infos, visible),
        "by_project": _by_project(shares, infos, visible),
    }


def _scoped_projects(
    user: str, department: str | None, project: str | None
) -> list[str] | None:
    """The projects a filter narrows to (None: no filter), only those the viewer runs."""
    if not department and not project:
        return None
    filters = {}
    if project:
        filters["name"] = project
    if department:
        filters["custom_department"] = department
    projects = frappe.get_all("Project", filters=filters, pluck="name")
    if is_tasky_admin(user):
        return projects
    mine = _own_projects(user)
    return [p for p in projects if p in mine]


def _own_projects(user: str) -> set[str]:
    return set(get_managed_projects(user)) | set(get_led_projects(user))


# ---- the work calendar ---------------------------------------------------------------


def planning_window(today, weeks: int, holiday_dates: set) -> tuple:
    """Today to the Sunday `weeks` calendar weeks on. A week with no working day left
    (say it's Sunday) doesn't count, so the window starts next Monday."""
    start = today
    if not working_days(start, _sunday(start), holiday_dates):
        start = add_days(_sunday(start), 1)
    return start, add_days(_sunday(start), 7 * (weeks - 1))


def week_ranges(start, end) -> list[tuple]:
    ranges = []
    day = start
    while day <= end:
        sunday = _sunday(day)
        ranges.append((day, sunday))
        day = add_days(sunday, 1)
    return ranges


def _sunday(day):
    return add_days(day, 6 - getdate(day).weekday())


def holidays() -> set:
    """The default SLA's holiday list: public holidays people entered."""
    holiday_list = frappe.db.get_value(
        "HD Service Level Agreement",
        {"default_sla": 1, "enabled": 1},
        "holiday_list",
    )
    if not holiday_list:
        return set()
    return {
        getdate(day)
        for day in frappe.get_all(
            "HD Holiday",
            filters={"parenttype": "HD Service Holiday List", "parent": holiday_list},
            pluck="holiday_date",
        )
    }


def working_days(start, end, holiday_dates: set) -> list:
    """Working days from start to end (both included): not the weekly off, not a
    Saturday off, not a holiday. Reads the settings once, not once per day."""
    weekly_off = weekly_off_days()
    rule = saturday_rule()
    days = []
    day = getdate(start)
    end = getdate(end)
    while day <= end:
        if (
            day.weekday() not in weekly_off
            and not is_saturday_off(day, rule)
            and day not in holiday_dates
        ):
            days.append(day)
        day = add_days(day, 1)
    return days


# ---- spreading a task's hours ------------------------------------------------------


def task_allocation(
    task, typical: dict | None, calendar: list, start, per_day: float
) -> dict:
    """A task's remaining hours by working day, from `start` on.

    - Hours: `custom_estimated_hours`, else `typical`, the standard estimate for its kind
      of task (task_estimates), less the hours already logged on it.
    - Overdue (due before `start`): all of it is still owed, from the first working day
      on, `per_day` hours a day.
    - Otherwise spread evenly over the working days from its start (today, or a later
      planned start) to its due date. A task without a due date gets one from the
      standard estimate's working days, the way a new task would.
    - No working day in that range (due on a day off): all of it on the next working day.
    """
    hours = flt(task.custom_estimated_hours) or flt(typical["estimated_hours"])
    used_typical = not flt(task.custom_estimated_hours)
    remaining = max(hours - flt(task.logged_hours), 0)
    if not remaining or not calendar:
        return {"by_day": {}, "typical": used_typical}

    task_start = max(getdate(task.exp_start_date or start), start)
    first = bisect_left(calendar, task_start)
    if task.exp_end_date:
        due = getdate(task.exp_end_date)
    else:
        days = min(max(cint(typical["working_days"]), 1), DEFAULT_MAX_DAYS)
        due = calendar[min(first + days - 1, len(calendar) - 1)]

    if due < start:
        by_day = front_load(remaining, calendar, per_day)
    else:
        span = calendar[first : bisect_right(calendar, due)]
        if not span:
            span = calendar[first : first + 1] or calendar[-1:]
        by_day = {day: remaining / len(span) for day in span}
    return {"by_day": by_day, "typical": used_typical}


def front_load(hours: float, calendar: list, per_day: float) -> dict:
    """`hours` from the first working day on, a full day's hours at a time."""
    by_day = {}
    for day in calendar:
        if hours <= 0:
            break
        by_day[day] = min(hours, per_day)
        hours -= by_day[day]
    return by_day


def _typical_estimates(tasks: list, infos: dict) -> dict:
    """task_estimates' standard estimate for tasks missing hours or a due date, reading
    each project type's history once."""
    histories = {}
    estimates = {}
    for task in tasks:
        if flt(task.custom_estimated_hours) and task.exp_end_date:
            continue
        project_type = (infos.get(task.project) or {}).get("project_type")
        if project_type not in histories:
            histories[project_type] = reference_durations(project_type)
        estimates[task.name] = fallback_estimate(
            task, project_type, histories[project_type]
        )
    return estimates


# ---- load and flags ---------------------------------------------------------------------


def load_flag(planned: float, available: float) -> str | None:
    """Overloaded above 100%, Busy from 80%, else Available; None with no time and no work."""
    if available <= 0:
        return OVERLOADED if planned > 0 else None
    utilisation = planned / available * 100
    if utilisation > 100:
        return OVERLOADED
    if utilisation >= BUSY_FROM:
        return BUSY
    return AVAILABLE


def _utilisation(planned: float, available: float) -> int | None:
    return round(planned / available * 100) if available > 0 else None


def _load(planned: float, available: float) -> dict:
    return {
        "available": round(available, 1),
        "planned": round(planned, 1),
        "utilisation": _utilisation(planned, available),
        "flag": load_flag(planned, available),
    }


def _person_row(
    user: str, full_name: str, load: dict, window: list, start, end, per_day
) -> dict:
    days = [{"date": str(day), **_load(load.get(day, 0), per_day)} for day in window]
    weeks = []
    for w_start, w_end in week_ranges(start, end):
        in_week = [d for d in window if w_start <= d <= w_end]
        planned = sum(load.get(d, 0) for d in in_week)
        weeks.append({"start": str(w_start), **_load(planned, per_day * len(in_week))})
    planned = sum(load.values())
    available = per_day * len(window)
    return {
        "user": user,
        "full_name": full_name,
        **_load(planned, available),
        "free": round(max(available - planned, 0), 1),
        "weeks": weeks,
        "days": days,
        "projects": [],
        "tasks": [],
        "typical_estimates": 0,
    }


def _add_contributions(rows: list, shares: list, infos: dict, visible) -> None:
    """Each person's hours by project and their biggest tasks. Work on projects the viewer
    doesn't run shows only as hours under "Other projects", without task names."""
    by_user = {row["user"]: row for row in rows}
    projects = {}
    for person, task, hours, typical in shares:
        row = by_user[person]
        row["typical_estimates"] += typical
        shown = _is_visible(task.project, visible)
        key = task.project if shown else None
        projects.setdefault(person, {}).setdefault(key, 0)
        projects[person][key] += hours
        if shown:
            row["tasks"].append(
                {
                    "name": task.name,
                    "title": task.subject,
                    "project_name": _project_name(task.project, infos),
                    "hours": round(hours, 1),
                    "due": str(task.exp_end_date) if task.exp_end_date else None,
                    "typical": typical,
                }
            )
    for row in rows:
        row["tasks"] = sorted(row["tasks"], key=lambda t: -t["hours"])[:TOP_TASKS]
        row["projects"] = sorted(
            (
                {
                    "project": key,
                    "project_name": _project_name(key, infos),
                    "hours": round(hours, 1),
                }
                for key, hours in projects.get(row["user"], {}).items()
            ),
            key=lambda p: -p["hours"],
        )


def _is_visible(project: str | None, visible) -> bool:
    return visible is None or (bool(project) and project in visible)


def _project_name(project: str | None, infos: dict) -> str | None:
    if not project:
        return None
    return (infos.get(project) or {}).get("project_name") or project


def _totals(rows: list) -> dict:
    available = sum(r["available"] for r in rows)
    planned = sum(r["planned"] for r in rows)
    return {
        "people": len(rows),
        **_load(planned, available),
        "flags": {
            flag: sum(r["flag"] == flag for r in rows)
            for flag in (OVERLOADED, BUSY, AVAILABLE)
        },
    }


def _by_department(shares: list, infos: dict, visible) -> list[dict]:
    """Planned hours by the department of each task's project, in department order.
    Work on projects the viewer doesn't run is one "other" row, last."""
    hours = {}
    other = 0
    for _person, task, value, _typical in shares:
        if not _is_visible(task.project, visible):
            other += value
            continue
        department = (infos.get(task.project) or {}).get("custom_department")
        hours[department] = hours.get(department, 0) + value
    order = {
        name: i
        for i, name in enumerate(
            frappe.get_all("HD Department", order_by="sort_order asc", pluck="name")
        )
    }
    rows = [
        {"department": name, "hours": round(value, 1), "other": False}
        for name, value in sorted(
            hours.items(), key=lambda item: order.get(item[0], len(order))
        )
    ]
    if other:
        rows.append({"department": None, "hours": round(other, 1), "other": True})
    return rows


def _by_project(shares: list, infos: dict, visible) -> list[dict]:
    """Planned hours and people per project; the viewer's other work as one row."""
    rows = {}
    for person, task, value, _typical in shares:
        key = task.project if _is_visible(task.project, visible) else None
        row = rows.setdefault(
            key,
            {
                "project": key,
                "project_name": _project_name(key, infos),
                "hours": 0,
                "people": set(),
            },
        )
        row["hours"] += value
        row["people"].add(person)
    result = [
        {**row, "hours": round(row["hours"], 1), "people": len(row["people"])}
        for row in rows.values()
    ]
    # projects by load, the "other projects" row last
    result.sort(key=lambda r: (r["project"] is None, -r["hours"]))
    return result


# ---- bulk reads ---------------------------------------------------------------------------


def _planned_tasks(people: set[str]) -> list:
    """Open tasks assigned to any of `people`, with the hours already logged on each."""
    if not people:
        return []
    task = frappe.qb.DocType("Task")
    tasks = [
        t
        for t in frappe.qb.from_(task)
        .select(
            task.name,
            task.subject,
            task.project,
            task.priority,
            task.exp_start_date,
            task.exp_end_date,
            task.custom_estimated_hours,
            task.custom_category,
            task["_assign"],
        )
        .where(task.status.isin(PLANNED_STATUSES) & task["_assign"].isnotnull())
        .run(as_dict=True)
        if people & set(_assignees(t._assign))
    ]
    logged = _logged_hours([t.name for t in tasks])
    for t in tasks:
        t.logged_hours = logged.get(t.name, 0)
    return tasks


def _logged_hours(tasks: list[str]) -> dict:
    """Hours in time logs of draft or submitted timesheets, per task."""
    if not tasks:
        return {}
    timesheet = frappe.qb.DocType("Timesheet")
    log = frappe.qb.DocType("Timesheet Detail")
    return dict(
        frappe.qb.from_(log)
        .join(timesheet)
        .on(log.parent == timesheet.name)
        .select(log.task, Sum(log.hours))
        .where(
            (log.parenttype == "Timesheet")
            & log.task.isin(tasks)
            & (timesheet.docstatus < 2)
        )
        .groupby(log.task)
        .run()
    )


def _project_info(projects: set[str]) -> dict:
    if not projects:
        return {}
    project = frappe.qb.DocType("Project")
    return {
        row.name: row
        for row in frappe.qb.from_(project)
        .select(
            project.name,
            project.project_name,
            project.project_type,
            project.custom_department,
        )
        .where(project.name.isin(list(projects)))
        .run(as_dict=True)
    }
