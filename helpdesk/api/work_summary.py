"""Weekly work summaries per customer (see helpdesk.work_summary)."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

from helpdesk.helpdesk.doctype.hd_work_summary.hd_work_summary import managed_customers
from helpdesk.tasky.permissions import is_tasky_admin
from helpdesk.utils import agent_only
from helpdesk.work_summary import PERIOD_DAYS, create_summary

MAX_LIMIT = 100
LIST_FIELDS = [
    "name",
    "customer",
    "period_start",
    "period_end",
    "generated_by_ai",
    "creation",
]
# the list's kind filter: written by AI, or the plain fallback
SUMMARY_KINDS = {"ai": 1, "plain": 0}


@frappe.whitelist()
@agent_only
def get_summaries(
    customer: str | None = None,
    week: str | None = None,
    kind: str | None = None,
    limit: int = 20,
) -> dict:
    """Latest summaries the user may read, newest period first, with each week's key figures.

    `week` is the Monday of a week: summaries whose period ends in it. `kind` is "ai" or "plain".
    """
    filters = {}
    if customer:
        filters["customer"] = customer
    if week:
        start = getdate(week)
        filters["period_end"] = ("between", [start, add_days(start, 6)])
    if kind in SUMMARY_KINDS:
        filters["generated_by_ai"] = SUMMARY_KINDS[kind]
    rows = frappe.get_list(
        "HD Work Summary",
        filters=filters,
        fields=[*LIST_FIELDS, "stats"],
        order_by="period_end desc, creation desc",
        limit=min(max(cint(limit), 1), MAX_LIMIT),
    )
    for row in rows:
        row["highlights"] = _highlights(row.pop("stats"))
    return {"summaries": rows, "can_generate": _can_generate()}


def _highlights(stats: str | None) -> dict:
    """The few figures the list shows from a summary's stats; None where a summary has none."""
    try:
        stats = json.loads(stats or "{}")
    except ValueError:
        stats = None
    if not isinstance(stats, dict):
        stats = {}
    tickets = stats.get("tickets") or {}
    tasks = stats.get("tasks") or {}
    return {
        "tickets_opened": tickets.get("opened"),
        "tickets_resolved": tickets.get("resolved"),
        "tasks_completed": tasks.get("completed"),
        "tasks_overdue": tasks.get("overdue"),
    }


def _can_generate(customer: str | None = None) -> bool:
    """Agent Managers may summarise any customer; project managers their projects' customers."""
    user = frappe.session.user
    if is_tasky_admin(user):
        return True
    customers = managed_customers(user, include_led=False)
    return customer in customers if customer else bool(customers)


@frappe.whitelist()
@agent_only
def get_summary(name: str | int) -> dict:
    doc = frappe.get_doc("HD Work Summary", name)
    doc.check_permission("read")
    return {
        **{field: doc.get(field) for field in LIST_FIELDS},
        "summary": doc.summary,
        "stats": json.loads(doc.stats or "{}"),
    }


@frappe.whitelist()
@agent_only
def generate_summary(customer: str) -> dict:
    """Summarise the last 7 days (including today) now, for an Agent Manager or the customer's project manager."""
    if not frappe.db.exists("HD Customer", customer):
        frappe.throw(_("Customer not found."), frappe.DoesNotExistError)
    if not _can_generate(customer):
        frappe.throw(
            _("Only Agent Managers and this customer's project managers can do this."),
            frappe.PermissionError,
        )
    end = getdate(nowdate())
    summary = create_summary(customer, add_days(end, -(PERIOD_DAYS - 1)), end)
    return get_summary(summary.name)
