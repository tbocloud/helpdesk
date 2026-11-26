# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot Pilot: the pilot's numbers per week and customer (helpdesk.copilot.pilot)."""

from frappe import _
from frappe.utils import add_days, nowdate

from helpdesk.copilot.pilot import pilot_rows

COLUMNS = (
    ("week", "Week of", "Date", 100),
    ("customer", "Customer", "Link/HD Customer", 160),
    ("tickets", "Tickets", "Int", 80),
    ("diagnoses", "Diagnoses", "Int", 90),
    ("rated", "Rated", "Int", 70),
    ("right", "Right", "Int", 70),
    ("partly", "Partly", "Int", 70),
    ("wrong", "Wrong", "Int", 70),
    ("rating_rate", "Rated right %", "Percent", 110),
    ("root_causes", "Root causes", "Data", 220),
    ("explanations_sent", "Explanations sent", "Int", 130),
    ("median_edit", "Median edit %", "Percent", 110),
    ("fixes_asked", "Fixes asked", "Int", 100),
    ("fixes_opened", "Fixes opened", "Int", 100),
    ("fixes_approved", "Fixes approved", "Int", 110),
    ("fixes_merged", "Fixes merged", "Int", 100),
    ("fixes_deployed", "Fixes deployed", "Int", 110),
    ("fixes_undone", "Fixes undone", "Int", 100),
    ("builds_started", "Builds started", "Int", 110),
    ("builds_merged", "Builds merged", "Int", 110),
    ("builds_reopened", "Builds reopened", "Int", 120),
    ("build_hours", "Build hours estimated", "Float", 140),
    ("build_ai_cost", "Build AI cost ($)", "Float", 130),
    ("watch_tickets", "Error watch tickets", "Int", 130),
    ("repeats_known", "Known repeats", "Int", 110),
    ("corrections_applied", "Corrections applied", "Int", 140),
    ("records_skipped", "Records skipped", "Int", 120),
    ("corrections_undone", "Corrections undone", "Int", 140),
    ("refused", "Approvals refused", "Int", 130),
    ("escalated", "Escalated or handed over", "Int", 170),
    ("median_approval_hours", "Median approval wait (h)", "Float", 170),
    ("median_resolution_hours", "Median time to resolve (h)", "Float", 180),
    ("ai_cost", "AI cost (USD)", "Currency", 110),
    ("ai_cost_per_ticket", "AI cost per ticket (USD)", "Currency", 170),
    ("wrong_runs", "Rated Wrong (runs)", "Data", 220),
)


def execute(filters=None):
    filters = filters or {}
    from_date = filters.get("from_date") or add_days(nowdate(), -28)
    to_date = filters.get("to_date") or nowdate()
    columns = [
        {"fieldname": key, "label": _(label), "fieldtype": kind, "width": width}
        if "/" not in kind
        else {
            "fieldname": key,
            "label": _(label),
            "fieldtype": kind.split("/")[0],
            "options": kind.split("/")[1],
            "width": width,
        }
        for key, label, kind, width in COLUMNS
    ]
    return columns, pilot_rows(from_date, to_date, filters.get("customer"))
