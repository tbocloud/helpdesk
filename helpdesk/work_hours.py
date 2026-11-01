"""The work day: when time can be worked and how much of it a day holds.

One definition for the timer, the Complete task dialog and the hours reports. The days are
the hub's working days (HD Work Settings and the default SLA's holiday list, see
helpdesk.work_calendar) and the hours are the default SLA's for that weekday, less the optional lunch
break (HD Work Settings). Without a default SLA a working day is 10:00 to 18:00. A day holds at
most the daily maximum (8 hours by default), or its windows if they are shorter. Holidays and
the weekly off hold none. See docs/workspace-pages.md, "Hours by day".
"""

from datetime import date, datetime, time, timedelta

import frappe
from frappe.utils import flt, get_datetime, get_time, getdate

DEFAULT_START = time(10, 0)
DEFAULT_END = time(18, 0)
DEFAULT_MAX_HOURS = 8.0
WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
# a timer left on for longer than this is clipped day by day; beyond it only the last
# stretch is looked at, so a forgotten timer from months ago can't loop for long
MAX_STRETCH_DAYS = 62

Window = tuple[datetime, datetime]


def is_working_day(day) -> bool:
    """Not the weekly off, a Saturday off or a holiday on the hub's calendar."""
    from helpdesk.recurrence import working_day_checker

    day = getdate(day)
    return working_day_checker(day, day)(day)


def day_hours(day) -> tuple[time, time] | None:
    """The day's start and end: the default SLA's for that weekday (None when it lists
    none), 10:00 to 18:00 without a default SLA."""
    name = frappe.db.get_value(
        "HD Service Level Agreement", {"default_sla": 1, "enabled": 1}
    )
    if not name:
        return DEFAULT_START, DEFAULT_END
    rows = frappe.get_cached_doc("HD Service Level Agreement", name).get_working_hours()
    hours = rows.get(WEEKDAYS[getdate(day).weekday()])
    if not hours or not hours[0] or not hours[1]:
        return None
    start, end = get_time(hours[0]), get_time(hours[1])
    return (start, end) if start < end else None


def lunch_break() -> tuple[time, time] | None:
    """The lunch break from HD Work Settings; None when it isn't set (optional)."""
    start = frappe.db.get_single_value("HD Work Settings", "lunch_start")
    end = frappe.db.get_single_value("HD Work Settings", "lunch_end")
    if not start or not end:
        return None
    start, end = get_time(start), get_time(end)
    return (start, end) if start < end else None


def max_hours_per_day() -> float:
    """HD Work Settings' daily maximum (8 hours until it is set)."""
    value = frappe.db.get_single_value("HD Work Settings", "max_hours_per_day")
    return flt(value) if flt(value) > 0 else DEFAULT_MAX_HOURS


def work_windows(day) -> list[Window]:
    """The stretches of `day` that can be worked, as (start, end): empty on a day off."""
    day = getdate(day)
    hours = day_hours(day) if is_working_day(day) else None
    if not hours:
        return []
    start, end = hours
    lunch = lunch_break()
    pieces = [(start, end)]
    if lunch and start < lunch[1] and lunch[0] < end:
        lunch_start, lunch_end = lunch
        pieces = [(start, max(start, lunch_start)), (min(end, lunch_end), end)]
    return [
        (datetime.combine(day, a), datetime.combine(day, b)) for a, b in pieces if a < b
    ]


def max_hours(day) -> float:
    """The most a person can work on `day`: the daily maximum setting or the sum of the
    day's windows, whichever is less (0 on a day off)."""
    windows = sum((end - start).total_seconds() for start, end in work_windows(day))
    return round(min(max_hours_per_day(), windows / 3600), 2)


def in_work_window(moment) -> bool:
    moment = get_datetime(moment)
    return any(start <= moment < end for start, end in work_windows(moment.date()))


def clip_to_windows(start, end) -> list[Window]:
    """The parts of the stretch from `start` to `end` that fall in work windows, earliest
    first: nothing before the day starts, at lunch, after it ends or on a day off."""
    start, end = get_datetime(start), get_datetime(end)
    first = max(start.date(), (end - timedelta(days=MAX_STRETCH_DAYS)).date())
    pieces = []
    day: date = first
    while day <= end.date():
        for window_start, window_end in work_windows(day):
            piece = (max(start, window_start), min(end, window_end))
            if piece[0] < piece[1]:
                pieces.append(piece)
        day += timedelta(days=1)
    return pieces


def hours_between(piece: Window) -> float:
    return flt((piece[1] - piece[0]).total_seconds() / 3600)


def day_label(moment) -> str:
    """ "6:00 pm" for the notice that a timer stopped."""
    return get_datetime(moment).strftime("%I:%M %p").lstrip("0").lower()
