"""Customer report: one month of work per customer, for billing and reviews.

Per customer: tickets opened and resolved, first reply and resolution times,
SLA kept, customer rating, hours logged on its projects' timesheets, and tasks
completed. Only Agent Managers and project managers (and admins) may see it,
since it covers every customer.
"""

import csv
import io
import re

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Avg, Count, Sum
from frappe.utils import (
    add_days,
    add_months,
    get_first_day,
    get_last_day,
    getdate,
    nowdate,
)

from helpdesk.tasky.permissions import is_project_manager
from helpdesk.utils import agent_only

NO_CUSTOMER = ""
RESOLVED = "Resolved"
SLA_FAILED = "Failed"
SLA_KEPT = "Fulfilled"
CANCELLED_TIMESHEET = 2


@frappe.whitelist()
@agent_only
def get_customer_report(month: str | None = None) -> dict:
    """`month` as YYYY-MM; last month when empty."""
    check_access()
    start, end = month_bounds(month)
    rows = build_rows(start, end)
    return {
        "month": start.strftime("%Y-%m"),
        "start": str(start),
        "end": str(end),
        "customers": rows,
        "totals": totals(rows),
    }


@frappe.whitelist()
@agent_only
def download_customer_report(month: str | None = None):
    """The same report as a CSV file."""
    report = get_customer_report(month)
    frappe.response["filename"] = f"customer-report-{report['month']}.csv"
    frappe.response["filecontent"] = to_csv(report["customers"] + [report["totals"]])
    frappe.response["type"] = "download"


def check_access():
    if not (
        is_project_manager() or "Agent Manager" in frappe.get_roles(frappe.session.user)
    ):
        frappe.throw(
            _("Only Agent Managers and project managers can see the customer report."),
            frappe.PermissionError,
        )


def month_bounds(month: str | None):
    if not month:
        first = get_first_day(add_months(nowdate(), -1))
        return first, get_last_day(first)
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        frappe.throw(_("Pick a month as YYYY-MM."))
    first = getdate(f"{month}-01")
    return first, get_last_day(first)


def build_rows(start, end) -> list[dict]:
    rows: dict[str, dict] = {}

    def row(customer) -> dict:
        key = customer or NO_CUSTOMER
        if key not in rows:
            rows[key] = empty_row(key)
        return rows[key]

    for r in tickets_opened(start, end):
        row(r.customer)["tickets_opened"] = r.count
    for r in tickets_resolved(start, end):
        target = row(r.customer)
        target["tickets_resolved"] = r.count
        target["sla_kept"] = int(r.kept or 0)
        target["sla_failed"] = int(r.failed or 0)
        target["avg_first_reply_hours"] = hours(r.first_reply)
        target["avg_resolution_hours"] = hours(r.resolution)
    for r in ratings(start, end):
        target = row(r.customer)
        target["ratings"] = r.count
        target["avg_rating"] = round(float(r.average) * 5, 1)
    for r in hours_logged(start, end):
        row(r.customer)["hours_logged"] = round(float(r.hours or 0), 2)
    for r in tasks_completed(start, end):
        row(r.customer)["tasks_completed"] = r.count

    for target in rows.values():
        judged = target["sla_kept"] + target["sla_failed"]
        target["sla_kept_percent"] = (
            round(100 * target["sla_kept"] / judged) if judged else None
        )
    return sorted(
        rows.values(),
        key=lambda r: (not r["customer"], -r["hours_logged"], -r["tickets_opened"]),
    )


def empty_row(customer: str) -> dict:
    return {
        "customer": customer,
        "tickets_opened": 0,
        "tickets_resolved": 0,
        "avg_first_reply_hours": None,
        "avg_resolution_hours": None,
        "sla_kept": 0,
        "sla_failed": 0,
        "sla_kept_percent": None,
        "ratings": 0,
        "avg_rating": None,
        "hours_logged": 0.0,
        "tasks_completed": 0,
    }


def in_month(field, start, end):
    return (field >= start) & (field < add_days(end, 1))


def tickets_opened(start, end):
    Ticket = frappe.qb.DocType("HD Ticket")
    return (
        frappe.qb.from_(Ticket)
        .select(Ticket.customer, Count(Ticket.name).as_("count"))
        .where(in_month(Ticket.opening_date, start, end))
        .groupby(Ticket.customer)
        .run(as_dict=True)
    )


def tickets_resolved(start, end):
    Ticket = frappe.qb.DocType("HD Ticket")
    return (
        frappe.qb.from_(Ticket)
        .select(
            Ticket.customer,
            Count(Ticket.name).as_("count"),
            Sum(Case().when(Ticket.agreement_status == SLA_KEPT, 1).else_(0)).as_(
                "kept"
            ),
            Sum(Case().when(Ticket.agreement_status == SLA_FAILED, 1).else_(0)).as_(
                "failed"
            ),
            Avg(Ticket.first_response_time).as_("first_reply"),
            Avg(Ticket.resolution_time).as_("resolution"),
        )
        .where(Ticket.status_category == RESOLVED)
        .where(in_month(Ticket.resolution_date, start, end))
        .groupby(Ticket.customer)
        .run(as_dict=True)
    )


def ratings(start, end):
    Ticket = frappe.qb.DocType("HD Ticket")
    return (
        frappe.qb.from_(Ticket)
        .select(
            Ticket.customer,
            Count(Ticket.name).as_("count"),
            Avg(Ticket.feedback_rating).as_("average"),
        )
        .where(Ticket.feedback_rating > 0)
        .where(in_month(Ticket.resolution_date, start, end))
        .groupby(Ticket.customer)
        .run(as_dict=True)
    )


def hours_logged(start, end):
    Detail = frappe.qb.DocType("Timesheet Detail")
    Sheet = frappe.qb.DocType("Timesheet")
    Project = frappe.qb.DocType("Project")
    return (
        frappe.qb.from_(Detail)
        .join(Sheet)
        .on(Sheet.name == Detail.parent)
        .left_join(Project)
        .on(Project.name == Detail.project)
        .select(Project.customer, Sum(Detail.hours).as_("hours"))
        .where(Detail.parenttype == "Timesheet")
        .where(Sheet.docstatus != CANCELLED_TIMESHEET)
        .where(in_month(Detail.from_time, start, end))
        .groupby(Project.customer)
        .run(as_dict=True)
    )


def tasks_completed(start, end):
    Task = frappe.qb.DocType("Task")
    Project = frappe.qb.DocType("Project")
    return (
        frappe.qb.from_(Task)
        .left_join(Project)
        .on(Project.name == Task.project)
        .select(Project.customer, Count(Task.name).as_("count"))
        .where(Task.status == "Completed")
        .where(in_month(Task.completed_on, start, end))
        .groupby(Project.customer)
        .run(as_dict=True)
    )


def hours(seconds) -> float | None:
    """Duration fields hold seconds."""
    return round(float(seconds) / 3600, 1) if seconds else None


def totals(rows: list[dict]) -> dict:
    total = empty_row(_("Total"))
    for key in (
        "tickets_opened",
        "tickets_resolved",
        "sla_kept",
        "sla_failed",
        "ratings",
        "tasks_completed",
    ):
        total[key] = sum(r[key] for r in rows)
    total["hours_logged"] = round(sum(r["hours_logged"] for r in rows), 2)
    judged = total["sla_kept"] + total["sla_failed"]
    total["sla_kept_percent"] = (
        round(100 * total["sla_kept"] / judged) if judged else None
    )
    rated = [r for r in rows if r["avg_rating"] is not None]
    if rated:
        total["avg_rating"] = round(
            sum(r["avg_rating"] * r["ratings"] for r in rated)
            / sum(r["ratings"] for r in rated),
            1,
        )
    return total


CSV_COLUMNS = (
    ("customer", "Customer"),
    ("tickets_opened", "Tickets opened"),
    ("tickets_resolved", "Tickets resolved"),
    ("avg_first_reply_hours", "Avg first reply (h)"),
    ("avg_resolution_hours", "Avg resolution (h)"),
    ("sla_kept_percent", "SLA kept %"),
    ("avg_rating", "Rating (of 5)"),
    ("ratings", "Ratings"),
    ("hours_logged", "Hours logged"),
    ("tasks_completed", "Tasks completed"),
)


def to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([label for _key, label in CSV_COLUMNS])
    for r in rows:
        values = {**r, "customer": r["customer"] or _("No customer")}
        writer.writerow(
            ["" if values[key] is None else values[key] for key, _label in CSV_COLUMNS]
        )
    return out.getvalue()
