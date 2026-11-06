"""Calls without a result (docs/leads.md, "Recording results").

When a salesperson taps Call on a lead, the lead is remembered here; it stays until a result is
recorded (Today's calls' outcome, or Log call) or it is dismissed with a reason. The Leads
screens show them as "You have N calls without a result" and open the result sheet for them
one by one. Kept in the cache per person, newest last: it is a reminder, not a record, so it
may be lost with a restart and ages out after `MAX_AGE_DAYS`.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

from helpdesk.integrations.crm.leads import require_leads

KEY = "hd_pending_calls"
MAX_AGE_DAYS = 3
MAX_PENDING = 50
MAX_TEXT = 140
# why a call can be taken off without a result
DISMISS_REASONS = ("Didn't call", "Tapped by mistake")
# how the call was placed: the phone's own dialler, or MyOperator ringing the person's phone
VIAS = ("phone", "myoperator")


def key_of(user: str) -> str:
    return f"{KEY}:{user}"


def short(value) -> str:
    return " ".join(str(value or "").split())[:MAX_TEXT]


def entries(user: str | None = None) -> list[dict]:
    """The person's calls without a result, oldest first, those past `MAX_AGE_DAYS` dropped."""
    user = user or frappe.session.user
    saved = frappe.cache.hgetall(key_of(user)) or {}
    oldest = add_days(now_datetime(), -MAX_AGE_DAYS)
    fresh = []
    for lead, entry in saved.items():
        if get_datetime(entry["at"]) < oldest:
            frappe.cache.hdel(key_of(user), lead)
        else:
            fresh.append(entry)
    return sorted(fresh, key=lambda entry: entry["at"])


@frappe.whitelist(methods=["POST"])
def start_call(
    lead: str,
    lead_name: str | None = None,
    phone: str | None = None,
    item: str | None = None,
    via: str = "phone",
    number: str | None = None,
) -> dict:
    """The person tapped Call on `lead` (`item`: the call in Today's calls it belongs to).
    Remembered until a result is recorded. Tapping Call again keeps one entry per lead.
    `number` is the lead's number that was dialled (blank: its main number)."""
    require_leads()
    lead = short(lead)
    if not lead:
        frappe.throw(_("Say which lead you are calling."))
    user = frappe.session.user
    if len(entries(user)) >= MAX_PENDING and not frappe.cache.hexists(
        key_of(user), lead
    ):
        # the oldest make room: they would never be answered now
        frappe.cache.hdel(key_of(user), entries(user)[0]["lead"])
    frappe.cache.hset(
        key_of(user),
        lead,
        {
            "lead": lead,
            "lead_name": short(lead_name) or lead,
            "phone": short(phone),
            "number": short(number) or None,
            "item": short(item) or None,
            "via": via if via in VIAS else "phone",
            "at": str(now_datetime()),
        },
    )
    return get_pending_calls()


@frappe.whitelist()
def get_pending_calls() -> dict:
    """{count, calls: [{lead, lead_name, phone, number, item, via, at}]} oldest first. Never cached
    by the browser: it changes with every call."""
    require_leads()
    calls = entries()
    return {"count": len(calls), "calls": calls}


@frappe.whitelist(methods=["POST"])
def dismiss_pending_call(lead: str, reason: str) -> dict:
    """Takes a call off without a result, for a reason the person gives."""
    require_leads()
    if reason not in DISMISS_REASONS:
        frappe.throw(
            _("Say why: {0}.").format(", ".join(_(r) for r in DISMISS_REASONS))
        )
    frappe.cache.hdel(key_of(frappe.session.user), short(lead))
    return get_pending_calls()


def resolve(lead: str | None = None, item: str | None = None) -> None:
    """A result was recorded for `lead` or for the Today's calls `item`: both stop waiting."""
    user = frappe.session.user
    for entry in entries(user):
        if (lead and entry["lead"] == short(lead)) or (
            item and entry.get("item") == short(item)
        ):
            frappe.cache.hdel(key_of(user), entry["lead"])
