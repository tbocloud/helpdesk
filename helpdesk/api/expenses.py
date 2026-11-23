"""Expense claims (docs/expenses.md): thin proxies to TBO Smart's `tbo_smart.api.hub_expenses`
on the ERP site of the person's active division. The ERP site holds the claims and decides who
may claim (an active Employee linked to them), whose claims they see and which they approve;
the hub only shows and asks. Nothing here is cached: a claim changes when it is decided."""

import frappe
from frappe import _

from helpdesk.api.leads import send_file
from helpdesk.integrations.crm.leads import (
    LeadsUnavailableError,
    call_if_deployed,
    download,
    require_leads,
)

EXPENSES = "tbo_smart.api.hub_expenses"
OLDER_ERP = "Expense claims need the latest TBO Smart on the ERP site."
NOT_ALLOWED = "The ERP site didn't allow this. Ask its admin to check your roles there."


def ask(method: str, post: bool = False, **params):
    """The ERP site's answer as the signed-in person; an older TBO Smart says so in words."""
    require_leads()
    result = call_if_deployed(
        method, post=post, api=EXPENSES, permission_message=_(NOT_ALLOWED), **params
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    return result


@frappe.whitelist()
def get_expenses(page: int = 1) -> dict:
    """{available, employee, can_approve, currency, types, claims, approvals}: the person's own
    claims and the ones waiting for them. `available` is false on an older ERP site."""
    require_leads()
    result = call_if_deployed(
        "get_expenses", api=EXPENSES, permission_message=_(NOT_ALLOWED), page=page
    )
    if result is None:
        return {"available": False}
    return {**result, "available": True}


@frappe.whitelist(methods=["POST"])
def create_expense_claim(
    expense_type: str,
    amount: float,
    expense_date: str,
    description: str | None = None,
    receipt_filename: str | None = None,
    receipt_base64: str | None = None,
) -> dict:
    """A draft claim of one expense, routed to the person's expense approver; the receipt (a
    PDF or picture, base64) is kept private on the ERP site."""
    return ask(
        "create_expense_claim",
        post=True,
        expense_type=expense_type,
        amount=amount,
        expense_date=expense_date,
        description=(description or "").strip() or None,
        receipt_filename=receipt_filename or None,
        receipt_base64=receipt_base64 or None,
    )


@frappe.whitelist(methods=["POST"])
def decide_expense(name: str, approve: int, reason: str | None = None) -> dict:
    """Approve (1) or reject (0) a claim waiting for the person; a rejection needs a reason."""
    return ask(
        "decide_expense",
        post=True,
        name=name,
        approve=1 if int(approve) else 0,
        reason=(reason or "").strip() or None,
    )


@frappe.whitelist()
def expense_receipt(name: str, filename: str | None = None) -> None:
    """A claim's receipt, streamed from the ERP site, which serves it only to people who may
    read the claim. `filename` is only the name the browser saves it as."""
    require_leads()
    content, content_type = download("get_expense_receipt", api=EXPENSES, name=name)
    send_file(content, content_type, filename, name)
