"""A task's timer, kept day by day.

Every stretch the timer runs (Start to Pause, or to the task leaving In progress, going on
hold or being completed) is saved as an HD Task Time Session, split at midnight, so the
time knows the day it was worked. Completing the task offers those days with their hours
(`completion_days`), and the timesheet gets one row per day (tasky.api.complete_task).
See docs/workspace-pages.md, "Hours by day".
"""

from datetime import datetime, time, timedelta

import frappe
from frappe.query_builder.functions import Date
from frappe.utils import flt, get_datetime, getdate, now_datetime

SESSION = "HD Task Time Session"
# a day longer than this is usually a timer left running overnight: the dialog flags it
LONG_DAY_HOURS = 10
# banked time with no sessions behind it (from before sessions were kept) below this is rounding
UNTRACKED_MIN_HOURS = 0.05


def record_session(
    task: str, start, end=None, user: str | None = None, settled: bool = False
) -> None:
    """Save the timer's stretch from `start` to `end` (now), one row per calendar day.

    `settled` keeps it for the record without offering it at completion: a stretch that
    ended with the task cancelled was never banked, as before sessions were kept."""
    start = get_datetime(start)
    end = get_datetime(end) if end else now_datetime()
    user = user or frappe.session.user
    for piece_start, piece_end in split_by_day(start, end):
        frappe.get_doc(
            {
                "doctype": SESSION,
                "task": task,
                "user": user,
                "start": piece_start,
                "end": piece_end,
                "hours": round((piece_end - piece_start).total_seconds() / 3600, 2),
                "logged": 1 if settled else 0,
            }
        ).insert(ignore_permissions=True)


def split_by_day(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """(start, end) pieces that each stay within one calendar day; nothing for an empty stretch."""
    pieces = []
    cursor = start
    while cursor < end:
        midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min)
        piece_end = min(end, midnight)
        pieces.append((cursor, piece_end))
        cursor = piece_end
    return pieces


def unlogged_sessions(task: str) -> list:
    """The task's timer stretches not yet in a timesheet, earliest first."""
    session = frappe.qb.DocType(SESSION)
    return (
        frappe.qb.from_(session)
        .select(session.name, session.start, session.end, session.hours)
        .where(session.task == task)
        .where(session.logged == 0)
        .orderby(session.start)
        .run(as_dict=True)
    )


def completion_days(task_doc) -> dict:
    """The hours to offer when completing the task: {today, days}, one entry in `days` per
    day it was worked: {date, hours, from_time (the day's first start, or None), long (over
    LONG_DAY_HOURS)}.

    From the unlogged sessions, the stretch still running, and any banked time that has no
    sessions behind it (tracked before sessions were kept), which goes on today.
    """
    days: dict[str, dict] = {}

    def add(day: str, hours: float, starts_at=None):
        entry = days.setdefault(day, {"date": day, "hours": 0.0, "from_time": None})
        entry["hours"] += hours
        if starts_at and (not entry["from_time"] or starts_at < entry["from_time"]):
            entry["from_time"] = starts_at

    sessions = unlogged_sessions(task_doc.name)
    for row in sessions:
        add(str(getdate(row.start)), flt(row.hours), get_datetime(row.start))
    if task_doc.get("custom_timer_start"):
        for piece_start, piece_end in split_by_day(
            get_datetime(task_doc.custom_timer_start), now_datetime()
        ):
            add(
                str(piece_start.date()),
                (piece_end - piece_start).total_seconds() / 3600,
                piece_start,
            )
    untracked = flt(task_doc.get("custom_timer_elapsed")) - sum(
        flt(r.hours) for r in sessions
    )
    if untracked >= UNTRACKED_MIN_HOURS:
        add(str(getdate()), untracked)

    # the site's today, so the dialog checks dates against the same day the server does
    return {
        "today": str(getdate()),
        "days": [
            {
                "date": e["date"],
                "hours": round(e["hours"], 2),
                "from_time": str(e["from_time"]) if e["from_time"] else None,
                "long": e["hours"] > LONG_DAY_HOURS,
            }
            for e in sorted(days.values(), key=lambda e: e["date"])
            if round(e["hours"], 2) > 0
        ],
    }


def first_start_on(task: str, day) -> datetime | None:
    """When the task's timer first started on `day`, among its unlogged sessions."""
    day = getdate(day)
    starts = [
        get_datetime(r.start)
        for r in unlogged_sessions(task)
        if getdate(r.start) == day
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
        query = query.where(Date(session.start) == frappe.utils.getdate(day))
    query.run()
