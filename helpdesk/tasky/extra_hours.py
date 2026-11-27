"""Hours over a task's estimate wait for the project manager (docs/extra-hours.md).

Completing a task with more hours than its estimate leaves needs an explanation: the hours
within the estimate go on the timesheet at once, the rest are held on the task (taken from
the latest days worked) and the task goes to review. The project's manager or lead approves
them (they are logged on their own days for the person who worked them, and the task
completes) or declines them with a note (they are never logged, and the task completes).
A task sent back while hours wait keeps them: the same person's next completion carries
them along. A task without an estimate has no limit.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate

from helpdesk.tasky.permissions import can_manage_project
from helpdesk.tasky.time_sessions import TOLERANCE

MAX_REASON = 1000


def logged_before(doc) -> float:
    """Hours already on the task's timesheets: its actual hours without the timer's banked
    time, which the completion replaces (as tasky.api._mark_completed counts it)."""
    return max(flt(doc.get("custom_actual_hours")) - flt(doc.custom_timer_elapsed), 0)


def held(doc) -> list[tuple]:
    """[(date, hours)] waiting on the task, earliest first."""
    return [(getdate(row[0]), flt(row[1])) for row in _stored(doc).get("days", [])]


def held_starts(doc) -> dict:
    """{date: when the held hours start}: right after that day's hours within the
    estimate, so the day's two time logs follow each other."""
    return {
        getdate(row[0]): get_datetime(row[2])
        for row in _stored(doc).get("days", [])
        if len(row) > 2 and row[2]
    }


def carry(doc, worked: list[tuple], user: str) -> list[tuple]:
    """The completion's days with the hours still held from this person's earlier
    completion (a task sent back while they waited) added, so they are asked for again.
    Someone else's held hours are dropped, with a line on the task: the task moved on."""
    waiting = held(doc)
    if not waiting:
        return worked
    if doc.get("extra_hours_by") != user:
        doc.add_comment(
            "Info",
            frappe.utils.escape_html(
                _("{0} h over the estimate asked for by {1} were not logged.").format(
                    f"{flt(doc.extra_hours):g}",
                    frappe.utils.get_fullname(doc.extra_hours_by),
                )
            ),
        )
        clear(doc)
        return worked
    days: dict = dict(worked)
    for day, hours in waiting:
        days[day] = round(days.get(day, 0) + hours, 2)
    return sorted(days.items())


def split(doc, worked: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    """(logged now, held) from [(date, hours)] earliest first: what fits in the estimate
    after the hours already logged, from the earliest days; the rest, from the latest
    days, waits. Everything is logged now on a task without an estimate."""
    estimate = flt(doc.get("custom_estimated_hours"))
    if estimate <= 0:
        return worked, []
    room = max(estimate - logged_before(doc), 0)
    now, waiting = [], []
    for day, hours in worked:
        take = round(min(hours, room), 2)
        room -= take
        if take > 0:
            now.append((day, take))
        rest = round(hours - take, 2)
        if rest > TOLERANCE:
            waiting.append((day, rest))
    return now, waiting


def require_reason(reason: str | None, extra: float, estimate: float) -> str:
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(
            _(
                "This is {0} h over the task's {1} h estimate. Explain the extra hours for the project manager."
            ).format(f"{extra:g}", f"{estimate:g}"),
            title=_("Over the estimate"),
        )
    if len(reason) > MAX_REASON:
        frappe.throw(_("Keep the explanation under {0} characters.").format(MAX_REASON))
    return reason


def hold(
    doc, waiting: list[tuple], starts: dict, reason: str, notes: str, user: str
) -> float:
    """Keep the hours over the estimate on the task (in memory: the caller saves), each
    day with when it starts (`starts`), and say so on its timeline. Returns the hours
    held."""
    extra = round(sum(hours for _day, hours in waiting), 2)
    doc.extra_hours = extra
    doc.extra_hours_by = user
    doc.extra_hours_reason = reason
    doc.extra_hours_days = json.dumps(
        {
            "days": [[str(day), hours, str(starts[day])] for day, hours in waiting],
            "notes": notes,
        }
    )
    doc.add_comment(
        "Info",
        frappe.utils.escape_html(
            _("Asked for {0} h over the {1} h estimate: {2}").format(
                f"{extra:g}", f"{flt(doc.custom_estimated_hours):g}", reason
            )
        ),
    )
    return extra


def clear(doc) -> None:
    doc.extra_hours = 0
    doc.extra_hours_by = None
    doc.extra_hours_reason = None
    doc.extra_hours_days = None


def notes(doc) -> str:
    """The completion's note, for the timesheets of the approved hours."""
    return _stored(doc).get("notes") or doc.extra_hours_reason or ""


def require_manager(doc) -> None:
    """Only the project's manager or lead decides hours over the estimate (admins too;
    for a task without a project, only admins)."""
    if not can_manage_project(doc.project):
        frappe.throw(
            _("Only the project's manager or lead can decide hours over the estimate."),
            frappe.PermissionError,
        )


def require_waiting(doc) -> None:
    if not flt(doc.get("extra_hours")):
        frappe.throw(_("No extra hours are waiting on this task."))


def _stored(doc) -> dict:
    raw = doc.get("extra_hours_days")
    if not raw:
        return {}
    return raw if isinstance(raw, dict) else json.loads(raw)
