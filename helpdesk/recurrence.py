"""When a recurring task falls due (see docs/recurring-tasks.md).

Date math only: a rule (an HD Recurring Task, or any object with the same fields)
goes in, its occurrences come out. Each occurrence has the date the rule falls on,
the due date (moved off non-working days when the rule asks) and the day its task
is created (the due date minus the lead time). Which days are working days is
passed in, so the math can be tested without a calendar.
"""

import calendar
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from typing import NamedTuple

import frappe
from frappe import _
from frappe.utils import cint, get_time, getdate

FREQUENCIES = ("Daily", "Weekly", "Monthly", "Quarterly", "Yearly")
MONTHS_PER_STEP = {"Monthly": 1, "Quarterly": 3, "Yearly": 12}
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
NEVER = "Never"
ON_DATE = "On date"
AFTER = "After"
ENDS = (NEVER, ON_DATE, AFTER)
# a due date moves at most this far looking for a working day (a long shutdown)
MAX_SHIFT_DAYS = 31


class Occurrence(NamedTuple):
    # the date the rule falls on; with the rule, it identifies the task
    on: date
    due: date
    create_on: date


def weekday_numbers(value: str | None) -> list[int]:
    """ "Monday,Friday" -> [0, 4]; unknown names are dropped."""
    names = {w.strip() for w in (value or "").split(",")}
    return [i for i, name in enumerate(WEEKDAYS) if name in names]


def weekday_names(numbers: list[int]) -> str:
    return ",".join(WEEKDAYS[i] for i in sorted(set(numbers)))


def rule_dates(rule) -> Iterator[date]:
    """Every date the rule falls on, from its start date, until its end date (or
    forever). "After N tasks" is counted in occurrences(), on tasks, not dates."""
    end = getdate(rule.end_date) if rule.ends == ON_DATE and rule.end_date else None
    for day in _dates_from_start(rule):
        if end and day > end:
            return
        yield day


def _dates_from_start(rule) -> Iterator[date]:
    start = getdate(rule.start_date)
    interval = max(cint(rule.interval), 1)
    if rule.frequency == "Daily":
        day = start
        while True:
            yield day
            day += timedelta(days=interval)
    if rule.frequency == "Weekly":
        weekdays = weekday_numbers(rule.weekdays) or [start.weekday()]
        monday = start - timedelta(days=start.weekday())
        while True:
            for weekday in weekdays:
                day = monday + timedelta(days=weekday)
                if day >= start:
                    yield day
            monday += timedelta(weeks=interval)
    step = MONTHS_PER_STEP[rule.frequency] * interval
    months = 0
    while True:
        index = start.month - 1 + months
        day = day_in_month(start.year + index // 12, index % 12 + 1, rule, start)
        if day >= start:
            yield day
        months += step


def day_in_month(year: int, month: int, rule, start: date) -> date:
    """The rule's day in that month; the 29th-31st become the month's last day when it is shorter."""
    last = calendar.monthrange(year, month)[1]
    if cint(rule.last_day_of_month):
        return date(year, month, last)
    return date(year, month, min(cint(rule.month_day) or start.day, last))


def due_date(day: date, rule, is_working: Callable[[date], bool]) -> date | None:
    """`day` itself, or with skip_non_working_days the next working day.

    A daily rule drops non-working days instead: moving them would put two tasks on
    the next working day.
    """
    if not cint(rule.skip_non_working_days):
        return day
    if rule.frequency == "Daily":
        return day if is_working(day) else None
    for shift in range(MAX_SHIFT_DAYS):
        moved = day + timedelta(days=shift)
        if is_working(moved):
            return moved
    return day


def occurrences(
    rule,
    is_working: Callable[[date], bool],
    until: date,
    after: date | None = None,
    created: int | None = 0,
) -> Iterator[Occurrence]:
    """Occurrences in order, for the dates the rule falls on after `after` up to `until`.

    The bound matters: a rule that never ends, or a daily one whose days are all off,
    would otherwise run forever. "After N tasks" counts tasks: `created` have been
    made, so at most N - created more are yielded. Dates dropped as non-working and
    dates up to `after` (created, or skipped as past) don't count. `created=None`
    ignores the limit (finding the dates already past).
    """
    lead = timedelta(days=max(cint(rule.lead_days), 0))
    left = (
        cint(rule.max_occurrences) - cint(created)
        if rule.ends == AFTER and created is not None
        else None
    )
    for day in rule_dates(rule):
        if day > until or (left is not None and left <= 0):
            return
        if after and day <= after:
            continue
        due = due_date(day, rule, is_working)
        if due:
            if left is not None:
                left -= 1
            yield Occurrence(day, due, due - lead)


def upcoming(
    rule,
    is_working: Callable[[date], bool],
    after: date | None,
    count: int,
    created: int = 0,
) -> list[Occurrence]:
    """The next `count` occurrences falling after `after` (from the start when None),
    with `created` tasks already made, looking at most ten years ahead."""
    base = max(getdate(after or rule.start_date), getdate(rule.start_date))
    found = []
    for occurrence in occurrences(
        rule, is_working, base + timedelta(days=3660), after, created
    ):
        found.append(occurrence)
        if len(found) >= count:
            break
    return found


def working_day_checker(start, end) -> Callable[[date], bool]:
    """Whether a day between `start` and `end` is worked: not the weekly off, not a
    Saturday off (HD Work Settings) and not on the hub's holiday list."""
    from helpdesk.task_estimates import is_working_day
    from helpdesk.work_calendar import company_holidays, saturday_rule

    holidays = company_holidays(start, end)
    rule = saturday_rule()

    def is_working(day: date) -> bool:
        return day not in holidays and is_working_day(day, rule)

    return is_working


def time_label(value) -> str:
    """A Time field's value (a timedelta from the database, or "9:00:00") as "09:00"."""
    return get_time(value).strftime("%H:%M") if value else ""


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def describe(rule) -> str:
    """ "Monthly on the 1st · due 18:00 · created 3 days ahead"."""
    parts = [_describe_dates(rule)]
    if rule.due_time:
        parts.append(_("due {0}").format(time_label(rule.due_time)))
    lead = cint(rule.lead_days)
    if lead == 1:
        parts.append(_("created 1 day ahead"))
    elif lead > 1:
        parts.append(_("created {0} days ahead").format(lead))
    if cint(rule.skip_non_working_days):
        parts.append(
            _("working days only")
            if rule.frequency == "Daily"
            else _("moved to the next working day")
        )
    return " · ".join(parts)


def _describe_dates(rule) -> str:
    interval = max(cint(rule.interval), 1)
    start = getdate(rule.start_date) if rule.start_date else None
    if rule.frequency == "Daily":
        return _("Every day") if interval == 1 else _("Every {0} days").format(interval)
    if rule.frequency == "Weekly":
        numbers = weekday_numbers(rule.weekdays) or ([start.weekday()] if start else [])
        days = _join([_(WEEKDAYS[i]) for i in numbers])
        if interval == 1:
            return _("Weekly on {0}").format(days)
        return _("Every {0} weeks on {1}").format(interval, days)
    if cint(rule.last_day_of_month):
        day = _("the last day")
    else:
        day = _("the {0}").format(
            ordinal(cint(rule.month_day) or (start.day if start else 1))
        )
    if rule.frequency == "Monthly":
        if interval == 1:
            return _("Monthly on {0}").format(day)
        return _("Every {0} months on {1}").format(interval, day)
    if rule.frequency == "Quarterly":
        if interval == 1:
            return _("Quarterly on {0}").format(day)
        return _("Every {0} quarters on {1}").format(interval, day)
    month = _(calendar.month_name[start.month]) if start else ""
    if interval == 1:
        return _("Yearly on {0} of {1}").format(day, month)
    return _("Every {0} years on {1} of {2}").format(interval, day, month)


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return _("{0} and {1}").format(", ".join(items[:-1]), items[-1])


def validate_rule(rule):
    """Throws with a message a person can act on when the rule can't produce dates."""
    if rule.frequency not in FREQUENCIES:
        frappe.throw(_("Repeat must be one of: {0}").format(", ".join(FREQUENCIES)))
    if not rule.start_date:
        frappe.throw(_("Pick the date the schedule starts."))
    if not 1 <= cint(rule.interval) <= 99:
        frappe.throw(_("Repeat every 1 to 99 periods."))
    if (
        rule.frequency in MONTHS_PER_STEP
        and not cint(rule.last_day_of_month)
        and not 1 <= cint(rule.month_day) <= 31
    ):
        frappe.throw(_("Pick a day of the month from 1 to 31, or the last day."))
    if rule.ends not in ENDS:
        frappe.throw(_("Ends must be one of: {0}").format(", ".join(ENDS)))
    if rule.ends == ON_DATE and (
        not rule.end_date or getdate(rule.end_date) < getdate(rule.start_date)
    ):
        frappe.throw(_("Pick an end date on or after the start date."))
    if rule.ends == AFTER and cint(rule.max_occurrences) < 1:
        frappe.throw(_("Say after how many tasks the schedule ends."))
    if not 0 <= cint(rule.lead_days) <= 365:
        frappe.throw(_("Create the task 0 to 365 days before it is due."))
