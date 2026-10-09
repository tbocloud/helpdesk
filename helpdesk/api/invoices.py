"""Invoice drafts from billable time: the Support hours page and the customer's Support
hours tab (docs/timesheet-invoicing.md).

Only Agent Managers and System Managers bill: an invoice draft lands in the company's
books on the CRM site, and they own the invoicing settings. Project managers and agents
see the hours but can't bill them.
"""

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.invoices import (
    create_draft,
    get_preview,
    list_invoices,
    remote_statuses,
    unlink,
)
from helpdesk.tasky.permissions import is_tasky_admin

MAX_LISTED = 100


def check_biller():
    # frappe.only_for is skipped in tests, so the roles are checked here
    if not is_tasky_admin():
        frappe.throw(
            _("Only Agent Managers and System Managers can create invoices."),
            frappe.PermissionError,
        )


def check_customer(customer: str) -> str:
    customer = str(customer or "")
    if not frappe.db.exists("HD Customer", customer):
        frappe.throw(_("There's no customer {0}.").format(customer))
    return customer


def crm_call(fn, *args, **kwargs):
    """Run fn, turning a CRM site problem into a message the dialog can show."""
    try:
        return fn(*args, **kwargs)
    except CRMError as e:
        frappe.throw(_("The CRM site couldn't be used: {0}").format(str(e)))


@frappe.whitelist()
def get_invoice_preview(
    customer: str,
    start: str | None = None,
    end: str | None = None,
    mode: str = "extra",
    by_task: bool = False,
) -> dict:
    """What an invoice for the customer's unbilled billable time in the dates would hold.

    Without dates, the latest ended contract period (or last month). `mode` is "extra"
    (hours beyond the contract's included hours) or "all".
    """
    check_biller()
    return get_preview(check_customer(customer), start, end, mode, bool(by_task))


@frappe.whitelist(methods=["POST"])
def create_invoice_draft(
    customer: str,
    start: str,
    end: str,
    mode: str = "extra",
    by_task: bool = False,
    expected_hours: float | None = None,
) -> dict:
    """Create the draft Sales Invoice in ERPNext and mark its time logs as billed."""
    check_biller()
    return crm_call(
        create_draft,
        check_customer(customer),
        start,
        end,
        mode,
        bool(by_task),
        expected_hours,
    )


@frappe.whitelist()
def get_invoices(customer: str | None = None, limit: int = 20) -> dict:
    """Invoice drafts created from the hub, newest first (one customer's, or everyone's)."""
    check_biller()
    limit = min(max(int(limit or 20), 1), MAX_LISTED)
    return list_invoices(str(customer) if customer else None, limit)


@frappe.whitelist(methods=["POST"])
def get_invoice_statuses(names: list[str]) -> dict:
    """{invoice record: its status in ERPNext}, fetched when the list is shown.

    POST because the body carries a list; it changes nothing but the status cache.
    """
    check_biller()
    return crm_call(remote_statuses, [str(n) for n in (names or [])][:MAX_LISTED])


@frappe.whitelist(methods=["POST"])
def unlink_invoice(name: str) -> dict:
    """Free the time logs of an invoice that was deleted or cancelled in ERPNext."""
    check_biller()
    return crm_call(unlink, str(name))
