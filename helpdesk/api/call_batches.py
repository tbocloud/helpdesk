"""Today's calls: the batch of leads a salesperson must call in the current time slot
(docs/leads.md, "Today's calls"). Thin proxies to TBO Smart's hub leads API
(`get_my_calls`, `get_next_batch`, `record_call_outcome`, `get_call_batches_report`); the
ERP site decides the batches, the rules and the outcomes."""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime, today

from helpdesk.api.leads import clear_cached_reads
from helpdesk.integrations.crm.leads import (
    LeadsUnavailableError,
    call_if_deployed,
    require_leads,
)

OUTCOMES = (
    "Connected",
    "Not answered",
    "Busy",
    "Call back",
    "Not interested",
    "Wrong number",
)
OLDER_ERP = (
    "The ERP site can't hand out call batches yet. It needs the latest TBO Smart."
)


@frappe.whitelist()
def get_my_calls() -> dict:
    """The signed-in person's queue (TBO Smart's `get_my_calls`). Never cached: calls made
    another way count on the ERP site the moment it is asked. `available` is false while the
    ERP site is older than this; `enabled` false when no department of theirs hands out
    batches."""
    require_leads()
    result = call_if_deployed("get_my_calls")
    if result is None:
        return {"available": False, "enabled": False}
    return {"available": True, **result}


@frappe.whitelist(methods=["POST"])
def get_next_batch() -> dict:
    """Asks for the next batch. `created` false with a `reason` when the ERP site's rules
    say not yet (calls pending, too many overdue, the day's limit, no open slot)."""
    require_leads()
    result = call_if_deployed("get_next_batch", post=True)
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    clear_cached_reads()
    return result


@frappe.whitelist(methods=["POST"])
def record_call_outcome(
    batch_item: str,
    outcome: str,
    note: str | None = None,
    callback_at: str | None = None,
) -> dict:
    """The outcome of one call in the queue (`batch_item` is the call's `item`). The ERP
    site logs the call and takes it off the queue. A call back needs a time in the future."""
    require_leads()
    if outcome not in OUTCOMES:
        frappe.throw(_("Pick how the call went."))
    callback_at = (callback_at or "").strip() or None
    if outcome == "Call back":
        if not callback_at:
            frappe.throw(_("Pick when to call back."))
        if get_datetime(callback_at) < now_datetime():
            frappe.throw(_("The call back time has to be in the future."))
    result = call_if_deployed(
        "record_call_outcome",
        post=True,
        batch_item=batch_item,
        outcome=outcome,
        note=(note or "").strip() or None,
        callback_at=callback_at,
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    clear_cached_reads()
    return result


@frappe.whitelist()
def get_call_batches_report(date: str | None = None) -> dict:
    """The day's batches per salesperson, for managers and department heads: size, called,
    connected and overdue. `available` is false while the ERP site is older than this."""
    require_leads()
    day = getdate(date or today())
    result = call_if_deployed(
        "get_call_batches_report",
        date=str(day),
        permission_message=_("Only managers and department heads can open this."),
    )
    if result is None:
        return {"available": False, "people": [], "totals": {}}
    return {"available": True, **result}


def report_lines(report: dict) -> list[tuple[str, None]]:
    """The batches of a day as the 18:00 message lists them: one line per person with
    batches, then the day's total; empty when nobody had one."""
    people = report.get("people") or []
    if not people:
        return []
    lines = [
        (
            f"• {p.get('user_name') or p.get('user')}: {cint(p.get('called'))}/{cint(p.get('size'))} "
            f"called, {cint(p.get('connected'))} connected, {cint(p.get('overdue'))} overdue",
            None,
        )
        for p in people
    ]
    totals = report.get("totals") or {}
    lines.append(
        (
            f"Total: {cint(totals.get('called'))}/{cint(totals.get('size'))} called, "
            f"{cint(totals.get('overdue'))} overdue",
            None,
        )
    )
    return lines
