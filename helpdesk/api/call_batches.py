"""Today's calls: the batch of leads a salesperson must call in the current time slot
(docs/leads.md, "Today's calls"). Thin proxies to TBO Smart's hub leads API
(`get_my_calls`, `get_next_batch`, `record_call_outcome`, `get_call_batches_report`, and the
managers' call plans `get_call_plans`, `save_call_plan`); the ERP site decides the batches, the
rules and the outcomes."""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime, today

from helpdesk.api import pending_calls
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
PLANNERS_ONLY = "Only managers and department heads can assign leads."
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
def set_calling_focus(
    department: str | None = None,
    product: str | None = None,
    district: str | None = None,
) -> dict:
    """What the signed-in person calls for now: one of their departments that hands out
    batches, one of its products and a district (both optional). The ERP site saves it, starts
    the next batch for it when its rules allow and answers in plain words (`message`). A blank
    department goes back to every department of theirs."""
    require_leads()
    result = call_if_deployed(
        "set_calling_focus",
        post=True,
        department=(department or "").strip() or None,
        product=(product or "").strip() or None,
        district=(district or "").strip() or None,
    )
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
    lead: str | None = None,
) -> dict:
    """The outcome of one call in the queue (`batch_item` is the call's `item`). The ERP
    site logs the call and takes it off the queue. A call back needs a time in the future.
    `lead` (when known) takes the lead off the person's calls without a result."""
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
    pending_calls.resolve(item=batch_item, lead=lead)
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


@frappe.whitelist()
def get_call_plans() -> dict:
    """Assign leads: per department with call batches on, each member's product and calls per
    slot, for managers and department heads. `available` is false while the ERP site is older
    than this."""
    require_leads()
    result = call_if_deployed(
        "get_call_plans",
        permission_message=_(PLANNERS_ONLY),
    )
    if result is None:
        return {"available": False, "departments": []}
    return {"available": True, **result}


@frappe.whitelist(methods=["POST"])
def save_call_plan(
    department: str,
    users: list | str,
    product: str | None = None,
    sizes: dict | str | None = None,
    clear: int | str | bool = 0,
) -> dict:
    """Hand `users` (members of `department`) the `product` and `sizes` ({slot: calls}) from
    their next slot, or (`clear`) the department's sizes again. The ERP site checks who may and
    what is valid; it answers with the department as `get_call_plans` lists it."""
    require_leads()
    users = frappe.parse_json(users) if isinstance(users, str) else users
    if not users:
        frappe.throw(_("Pick the people to assign leads to."))
    sizes = frappe.parse_json(sizes) if isinstance(sizes, str) else sizes
    result = call_if_deployed(
        "save_call_plan",
        post=True,
        department=department,
        users=list(users),
        product=(product or "").strip() or None,
        sizes=sizes or None,
        clear=cint(clear),
        permission_message=_(PLANNERS_ONLY),
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    clear_cached_reads()
    return result


@frappe.whitelist()
def get_department_leads(
    department: str,
    owner: str | None = None,
    product: str | None = None,
    search: str | None = None,
    start: int | str = 0,
    page_length: int | str = 50,
) -> dict:
    """A page of a department's open leads: a member's (`owner`) or, with no owner, the
    unassigned ones, with how many there are of each product. Never cached: a lead that
    was just moved must show where it went."""
    require_leads()
    result = call_if_deployed(
        "get_department_leads",
        department=department,
        owner=(owner or "").strip() or None,
        product=(product or "").strip() or None,
        search=(search or "").strip() or None,
        start=max(cint(start), 0),
        page_length=min(max(cint(page_length) or 50, 1), 100),
        permission_message=_(PLANNERS_ONLY),
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    return result


@frappe.whitelist(methods=["POST"])
def assign_leads(
    department: str,
    user: str,
    leads: list | str | None = None,
    count: int | str = 0,
    product: str | None = None,
) -> dict:
    """Give a member the `leads` picked (moving them from whoever had them) or the next
    `count` unassigned leads of `product`: {assigned, skipped}."""
    require_leads()
    names = frappe.parse_json(leads) if isinstance(leads, str) else leads
    if not names and cint(count) <= 0:
        frappe.throw(_("Pick the leads, or say how many to give."))
    result = call_if_deployed(
        "assign_leads",
        post=True,
        department=department,
        user=user,
        leads=list(names or []) or None,
        count=0 if names else cint(count),
        product=(product or "").strip() or None,
        permission_message=_(PLANNERS_ONLY),
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    clear_cached_reads()
    return result


@frappe.whitelist(methods=["POST"])
def unassign_leads(department: str, leads: list | str) -> dict:
    """Take the `leads` back to the department's unassigned pool: {unassigned, skipped}."""
    require_leads()
    names = frappe.parse_json(leads) if isinstance(leads, str) else leads
    if not names:
        frappe.throw(_("Pick the leads first."))
    result = call_if_deployed(
        "unassign_leads",
        post=True,
        department=department,
        leads=list(names),
        permission_message=_(PLANNERS_ONLY),
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    clear_cached_reads()
    return result


def report_lines(report: dict) -> list[tuple[str, None]]:
    """The batches of a day as the 18:00 message lists them: one line per person with
    batches, then the day's total; empty when nobody had one."""
    people = report.get("people") or []
    if not people:
        return []
    lines = [
        (
            f"• {p.get('user_name') or p.get('user')}: {line_counts(p)}",
            None,
        )
        for p in people
    ]
    totals = report.get("totals") or {}
    lines.append((f"Total: {line_counts(totals, connected=False)}", None))
    return lines


def line_counts(row: dict, connected: bool = True) -> str:
    """A person's or the day's counts, like 87/100 called, 41 connected, 4 overdue."""
    parts = [f"{cint(row.get('called'))}/{cint(row.get('size'))} called"]
    if connected:
        parts.append(f"{cint(row.get('connected'))} connected")
    parts.append(f"{cint(row.get('overdue'))} overdue")
    return ", ".join(parts)
