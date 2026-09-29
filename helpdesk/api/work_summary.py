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


@frappe.whitelist()
@agent_only
def get_summaries(customer: str | None = None, limit: int = 20) -> list:
    """Latest summaries the user may read, newest period first."""
    return frappe.get_list(
        "HD Work Summary",
        filters={"customer": customer} if customer else {},
        fields=LIST_FIELDS,
        order_by="period_end desc, creation desc",
        limit=min(max(cint(limit), 1), MAX_LIMIT),
    )


@frappe.whitelist()
@agent_only
def get_summary(name: str | int) -> dict:
    frappe.has_permission("HD Work Summary", "read", name, throw=True)
    doc = frappe.get_doc("HD Work Summary", name)
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
    user = frappe.session.user
    if not (
        is_tasky_admin(user) or customer in managed_customers(user, include_led=False)
    ):
        frappe.throw(
            _("Only Agent Managers and this customer's project managers can do this."),
            frappe.PermissionError,
        )
    end = getdate(nowdate())
    summary = create_summary(customer, add_days(end, -(PERIOD_DAYS - 1)), end)
    return get_summary(summary.name)
