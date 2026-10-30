"""A task's timer, kept day by day, inside the work day.

Every stretch the timer runs (Start to Pause, or to the task leaving In progress, going on
hold or being completed) is saved as an HD Task Time Session, clipped to the work windows
(helpdesk.work_hours: nothing before the day starts, at lunch, after it ends or on a day
off), so the time knows the day it was worked and never exceeds it. Completing the task
offers those days with their hours (`completion_days`), and the timesheet gets one row per
day (tasky.api.complete_task). A person has one timer at a time, and a scheduler job pauses
every timer when a window closes (`stop_timers_outside_work_hours`).
See docs/workspace-pages.md, "Hours by day".
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.query_builder.functions import Date, Sum
from frappe.utils import add_to_date, flt, get_datetime, getdate, now, now_datetime

from helpdesk.work_hours import (
    clip_to_windows,
    day_label,
    hours_between,
    in_work_window,
    max_hours,
)

SESSION = "HD Task Time Session"
# hours entered by hand may only be for this many days back (today and yesterday)
BACKDATE_DAYS = 1
# banked time with no sessions behind it (from before sessions were kept) below this is rounding
UNTRACKED_MIN_HOURS = 0.05
# slack for hours kept to two decimals
TOLERANCE = 0.01


def record_session(
    task: str, start, end=None, user: str | None = None, settled: bool = False
) -> float:
    """Save the timer's stretch from `start` to `end` (now), one row per work window it
    touched, and return the hours kept. Time outside the work day is not kept, and neither
    is time beyond what the day has left for the person (`day_left`).

    `settled` keeps it for the record without offering it at completion: a stretch that
    ended with the task cancelled was never banked, as before sessions were kept."""
    start = get_datetime(start)
    end = get_datetime(end) if end else now_datetime()
    user = user or frappe.session.user
    kept = 0.0
    for piece_start, piece_end in clip_to_windows(start, end):
        left = day_left(user, piece_start.date())
        if left < TOLERANCE:
            continue
        if hours_between((piece_start, piece_end)) > left:
            piece_end = add_to_date(piece_start, hours=left)
        hours = round(hours_between((piece_start, piece_end)), 2)
        frappe.get_doc(
            {
                "doctype": SESSION,
                "task": task,
                "user": user,
                "started_at": piece_start,
                "ended_at": piece_end,
                "hours": hours,
                "logged": 1 if settled else 0,
            }
        ).insert(ignore_permissions=True)
        kept += hours
    return round(kept, 2)


def counted_hours(start, end=None) -> float:
    """The hours of the stretch that fall in the work day, before any daily cap."""
    pieces = clip_to_windows(start, end or now_datetime())
    return round(sum(hours_between(p) for p in pieces), 2)


def day_logged_hours(user: str, day, exclude_task: str | None = None) -> float:
    """What the person has on `day`: hours in their timesheets plus timer sessions not
    yet in one (apart from those of `exclude_task`, which a completion replaces)."""
    day = getdate(day)
    log = frappe.qb.DocType("Timesheet Detail")
    sheet = frappe.qb.DocType("Timesheet")
    logged = (
        frappe.qb.from_(log)
        .join(sheet)
        .on(sheet.name == log.parent)
        .select(Sum(log.hours))
        .where(
            (log.parenttype == "Timesheet")
            & (sheet.docstatus < 2)
            & (sheet.owner == user)
            & (Date(log.from_time) == day)
        )
        .run()[0][0]
    )
    session = frappe.qb.DocType(SESSION)
    query = (
        frappe.qb.from_(session)
        .select(Sum(session.hours))
        .where(
            (session.user == user)
            & (session.logged == 0)
            & (Date(session.started_at) == day)
        )
    )
    if exclude_task:
        query = query.where(session.task != exclude_task)
    return flt(logged) + flt(query.run()[0][0])


def day_left(user: str, day, exclude_task: str | None = None) -> float:
    """Hours the person can still put on `day`: the day's work hours less what they have."""
    return max(max_hours(day) - day_logged_hours(user, day, exclude_task), 0.0)


def check_hand_entered(task_doc, user: str, worked: list[tuple], reason: str | None):
    """Refuse hours that don't fit the days: [(date, hours)] for `task_doc` by `user`.

    A day takes at most what is left of its work hours (hours already in the person's
    timesheets and timers count). Only today and yesterday can be filled in by hand;
    an older day only up to what the task's timer recorded on it, unless a System
    Manager gives a `reason`."""
    today = getdate()
    oldest = add_to_date(today, days=-BACKDATE_DAYS)
    tracked: dict = {}
    for row in unlogged_sessions(task_doc.name):
        day = getdate(row.started_at)
        tracked[day] = tracked.get(day, 0) + flt(row.hours)
    override = "System Manager" in frappe.get_roles(user) and bool(
        (reason or "").strip()
    )
    for day, hours in worked:
        label = frappe.utils.formatdate(day)
        if day < oldest and not override and hours > tracked.get(day, 0) + TOLERANCE:
            frappe.throw(
                _(
                    "{0} is too long ago to enter hours by hand: you can log hours for today or yesterday, or what the timer recorded."
                ).format(label)
            )
        left = day_left(user, day, exclude_task=task_doc.name)
        if hours > left + TOLERANCE:
            if not max_hours(day):
                frappe.throw(_("{0} is not a working day.").format(label))
            frappe.throw(
                _(
                    "{0}: you can log at most {1} h more. A working day is {2} h, and you have {3} h on it already."
                ).format(
                    label,
                    f"{left:g}",
                    f"{max_hours(day):g}",
                    f"{max_hours(day) - left:g}",
                )
            )


def timer_user(task: dict) -> str | None:
    """Whose timer it is: who started it, else the task's only assignee."""
    if task.get("custom_timer_user"):
        return task["custom_timer_user"]
    assignees = frappe.parse_json(task.get("_assign") or "[]")
    return assignees[0] if len(assignees) == 1 else None


def running_timers(user: str, except_task: str | None = None) -> list[str]:
    """The tasks whose timer is running for the person."""
    rows = frappe.get_all(
        "Task",
        filters={"custom_timer_start": ("is", "set"), "status": "Working"},
        fields=["name", "custom_timer_user", "_assign"],
        limit_page_length=0,
    )
    return [r.name for r in rows if r.name != except_task and timer_user(r) == user]


def pause_timer(task: str, user: str | None = None) -> float:
    """Pause the task's timer: save its stretch and bank the hours; the task stays in
    progress. Returns the hours banked (0 when it wasn't running)."""
    start, actual, paused = frappe.db.get_value(
        "Task",
        task,
        ["custom_timer_start", "custom_actual_hours", "custom_timer_elapsed"],
    )
    if not start:
        return 0.0
    hours = record_session(task, start, user=user)
    frappe.db.set_value(
        "Task",
        task,
        {
            "custom_timer_start": None,
            "custom_timer_user": None,
            "custom_actual_hours": flt(actual) + hours,
            "custom_timer_elapsed": flt(paused) + hours,
        },
    )
    return hours


def pause_other_timers(task: str, user: str) -> list[str]:
    """One timer per person: pause the person's other running timers; returns them."""
    paused = running_timers(user, except_task=task)
    for other in paused:
        pause_timer(other, user)
    return paused


def begin_timer(task: str, user: str, strict: bool = True) -> list[str]:
    """Start the task's timer for the person: their other running timers are paused first,
    and outside the work day it is refused (`strict`) or left paused. Returns the tasks
    paused."""
    if not in_work_window(now_datetime()):
        if strict:
            frappe.throw(
                _(
                    "The work day is over. Timers run during work hours only, so start it again when you resume."
                )
            )
        return []
    paused = pause_other_timers(task, user)
    frappe.db.set_value(
        "Task", task, {"custom_timer_start": now(), "custom_timer_user": user}
    )
    return paused


def stop_timers_outside_work_hours() -> list[str]:
    """Scheduler job: pause every running timer once the work day (or the stretch before
    lunch) has closed, and tell its person. Safe to run often; it does nothing while a
    window is open. Returns the tasks paused."""
    from helpdesk.tasky.api import notify_task_list

    now_ = now_datetime()
    if in_work_window(now_):
        return []
    paused = []
    rows = frappe.get_all(
        "Task",
        filters={"custom_timer_start": ("is", "set")},
        fields=[
            "name",
            "subject",
            "custom_timer_start",
            "custom_timer_user",
            "_assign",
        ],
        limit_page_length=0,
    )
    for row in rows:
        user = timer_user(row)
        stopped = clip_to_windows(row.custom_timer_start, now_)
        pause_timer(row.name, user)
        paused.append(row.name)
        notify_timer_stopped(row, user, stopped[-1][1] if stopped else now_)
        notify_task_list(row.name)
    return paused


def notify_timer_stopped(task: dict, user: str | None, at) -> None:
    from helpdesk.work_reminders import notify_users

    users = [user] if user else frappe.parse_json(task.get("_assign") or "[]")
    notify_users(
        users,
        "Task",
        task["name"],
        _("Your timer on {0} stopped at {1}. Start it again when you resume.").format(
            task["subject"], day_label(at)
        ),
        once=False,
    )


def unlogged_sessions(task: str) -> list:
    """The task's timer stretches not yet in a timesheet, earliest first."""
    session = frappe.qb.DocType(SESSION)
    return (
        frappe.qb.from_(session)
        .select(session.name, session.started_at, session.ended_at, session.hours)
        .where(session.task == task)
        .where(session.logged == 0)
        .orderby(session.started_at)
        .run(as_dict=True)
    )


def completion_days(task_doc, user: str | None = None) -> dict:
    """The hours to offer when completing the task: {today, yesterday, days, left}.

    `days` has one entry per day it was worked: {date, hours, from_time (the day's first
    start, or None)}, from the unlogged sessions, the stretch still running (inside the work
    day) and any banked time that has no sessions behind it (tracked before sessions were
    kept), which goes on today. `left` is {date: hours the person can still put on that
    day} for those days, today and yesterday ("x h left today").
    """
    user = user or frappe.session.user
    days: dict[str, dict] = {}

    def add(day: str, hours: float, starts_at=None):
        entry = days.setdefault(day, {"date": day, "hours": 0.0, "from_time": None})
        entry["hours"] += hours
        if starts_at and (not entry["from_time"] or starts_at < entry["from_time"]):
            entry["from_time"] = starts_at

    sessions = unlogged_sessions(task_doc.name)
    for row in sessions:
        add(str(getdate(row.started_at)), flt(row.hours), get_datetime(row.started_at))
    if task_doc.get("custom_timer_start"):
        for piece in clip_to_windows(task_doc.custom_timer_start, now_datetime()):
            add(str(piece[0].date()), hours_between(piece), piece[0])
    untracked = flt(task_doc.get("custom_timer_elapsed")) - sum(
        flt(r.hours) for r in sessions
    )
    if untracked >= UNTRACKED_MIN_HOURS:
        add(str(getdate()), untracked)

    today = getdate()
    yesterday = add_to_date(today, days=-BACKDATE_DAYS)
    shown = {str(today), str(yesterday), *days}
    # the site's today, so the dialog checks dates against the same day the server does
    return {
        "today": str(today),
        "yesterday": str(yesterday),
        "days": [
            {
                "date": e["date"],
                "hours": round(e["hours"], 2),
                "from_time": str(e["from_time"]) if e["from_time"] else None,
            }
            for e in sorted(days.values(), key=lambda e: e["date"])
            if round(e["hours"], 2) > 0
        ],
        "left": {
            day: round(day_left(user, day, exclude_task=task_doc.name), 2)
            for day in sorted(shown)
        },
    }


def first_start_on(task: str, day) -> datetime | None:
    """When the task's timer first started on `day`, among its unlogged sessions."""
    day = getdate(day)
    starts = [
        get_datetime(r.started_at)
        for r in unlogged_sessions(task)
        if getdate(r.started_at) == day
    ]
    return min(starts) if starts else None


def mark_logged(task: str, timesheet: str | None, day=None) -> None:
    """The task's sessions (on `day`, when given) are in this timesheet now, so a later
    completion starts afresh."""
    session = frappe.qb.DocType(SESSION)
    query = (
        frappe.qb.update(session)
        .set(session.logged, 1)
        .set(session.timesheet, timesheet)
        .where(session.task == task)
        .where(session.logged == 0)
    )
    if day:
        query = query.where(Date(session.started_at) == frappe.utils.getdate(day))
    query.run()
