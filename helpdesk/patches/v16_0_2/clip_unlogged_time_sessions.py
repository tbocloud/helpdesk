"""Clip timer sessions not yet in a timesheet to the work day, and drop duplicates.

Timers left running overnight or over lunch, and two timers running at once, saved sessions
of 10+ hours and the same stretch twice (helpdesk.work_hours has the work windows now). For
every HD Task Time Session with logged = 0: an exact duplicate (same person, start and end)
keeps one; the rest are cut to the work windows (rows outside them are deleted, a row
across a window edge is shortened, one across lunch is split). Logged sessions are left
alone. The hours cut also come off the task's banked time (so the Complete dialog
doesn't offer them again as untracked). A second run finds nothing to change.
"""

import frappe
from frappe.utils import flt

from helpdesk.work_hours import clip_to_windows, hours_between

SESSION = "HD Task Time Session"


def execute():
    rows = frappe.get_all(
        SESSION,
        filters={"logged": 0},
        fields=["name", "task", "user", "started_at", "ended_at", "hours"],
        order_by="started_at, creation",
        limit_page_length=0,
    )
    seen = set()
    cut: dict = {}
    removed = clipped = split = 0
    for row in rows:
        key = (row.user, row.started_at, row.ended_at)
        if key in seen:
            frappe.delete_doc(SESSION, row.name, force=True, ignore_permissions=True)
            removed += 1
            cut[row.task] = cut.get(row.task, 0) + flt(row.hours)
            continue
        seen.add(key)
        pieces = clip_to_windows(row.started_at, row.ended_at)
        if len(pieces) == 1 and pieces[0] == (row.started_at, row.ended_at):
            continue
        kept = sum(hours_between(p) for p in pieces)
        cut[row.task] = cut.get(row.task, 0) + max(flt(row.hours) - kept, 0)
        if not pieces:
            frappe.delete_doc(SESSION, row.name, force=True, ignore_permissions=True)
            removed += 1
            continue
        first, *others = pieces
        frappe.db.set_value(
            SESSION,
            row.name,
            {
                "started_at": first[0],
                "ended_at": first[1],
                "hours": round(hours_between(first), 2),
            },
        )
        clipped += 1
        for start, end in others:
            frappe.get_doc(
                {
                    "doctype": SESSION,
                    "task": row.task,
                    "user": row.user,
                    "started_at": start,
                    "ended_at": end,
                    "hours": round(hours_between((start, end)), 2),
                    "logged": 0,
                }
            ).insert(ignore_permissions=True)
            split += 1
    for task, hours in cut.items():
        values = frappe.db.get_value(
            "Task", task, ["custom_timer_elapsed", "custom_actual_hours"]
        )
        if not values or hours < 0.01:
            continue
        elapsed, actual = values
        frappe.db.set_value(
            "Task",
            task,
            {
                "custom_timer_elapsed": round(max(flt(elapsed) - hours, 0), 2),
                "custom_actual_hours": round(max(flt(actual) - hours, 0), 2),
            },
            update_modified=False,
        )
    print(
        f"Time sessions: {len(rows)} not yet logged; "
        f"{removed} removed (duplicates or outside the work day), "
        f"{clipped} clipped, {split} added by splitting at lunch."
    )
