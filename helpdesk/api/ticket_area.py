"""The agent's ticket list (Phase 15): its queues' counts, the filters plain conditions can't say, and each row's
last message.

Two filters stand for an OR that a list's AND-only conditions can't express, so the server turns them into a
name list, as `__assigned_on` does (api/doc.py):
- `__overdue`: an open ticket past its first-reply time (no reply yet) or past its resolution time;
- `__search`: the words in the number, subject, customer, contact or raiser.

A queue's count and its list use the same conditions, so the number on a tab is the number of rows it opens.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from helpdesk.api.dashboard import COUNT_NAME

TICKET = "HD Ticket"
# enough for a page of matches; a search that finds more than this needs more words
MAX_MATCHES = 1000
SEARCH_FIELDS = ("subject", "customer", "raised_by", "contact")
PREVIEW_CHARS = 140
# where a reply quotes the earlier mail
QUOTE_START = re.compile(
    r"\n\s*(On .{1,200}wrote:|-{2,}\s*Original Message|From: )", re.I
)


def _pop(filters, field: str):
    """The (operator, value) of `field` in `filters` (a dict or a list of conditions), taken out of it."""
    if isinstance(filters, dict):
        if field not in filters:
            return None
        value = filters.pop(field)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return value[0], value[1]
        return "=", value
    for i, condition in enumerate(filters):
        if isinstance(condition, (list, tuple)) and len(condition) >= 3:
            name = condition[1] if len(condition) == 4 else condition[0]
            if name == field:
                filters.pop(i)
                return (condition[-2], condition[-1])
    return None


def overdue_tickets() -> list[str]:
    """Open tickets past their first-reply time without a reply, or past their resolution time."""
    T = frappe.qb.DocType(TICKET)
    now = now_datetime()
    rows = (
        frappe.qb.from_(T)
        .select(T.name)
        .where(T.status_category == "Open")
        .where(
            (T.resolution_by < now)
            | (T.first_responded_on.isnull() & (T.response_by < now))
        )
        .orderby(T.modified, order=frappe.qb.desc)
        .limit(MAX_MATCHES)
        .run()
    )
    return [r[0] for r in rows]


def search_tickets(text: str) -> list[str]:
    """Tickets whose number, subject, customer, contact or raiser contains the words, newest first."""
    words = str(text or "").replace("%", " ").split()
    if not words:
        return []
    T = frappe.qb.DocType(TICKET)
    query = frappe.qb.from_(T).select(T.name)
    for word in words[:6]:
        like = f"%{word}%"
        matches = T.name.like(like)
        for field in SEARCH_FIELDS:
            matches = matches | T[field].like(like)
        query = query.where(matches)
    rows = query.orderby(T.modified, order=frappe.qb.desc).limit(MAX_MATCHES).run()
    return [r[0] for r in rows]


def resolve_filters(filters, doctype: str):
    """Turn `__overdue` and `__search` into the tickets they mean, in place (only for HD Ticket)."""
    if doctype != TICKET or not filters:
        return filters
    from helpdesk.api.doc import _merge_name_filter

    overdue = _pop(filters, "__overdue")
    if overdue and cint(overdue[1]):
        _merge_name_filter(filters, overdue_tickets())
    search = _pop(filters, "__search")
    if search and str(search[1] or "").strip("% "):
        _merge_name_filter(filters, search_tickets(str(search[1])))
    return filters


@frappe.whitelist()
def count(filters: str | list | dict | None = None) -> int:
    """How many tickets the agent may read under `filters`: a queue's number, the same rows its list shows."""
    from helpdesk.api.doc import handle_assigned_to_filter, handle_at_me_support

    filters = frappe.parse_json(filters or "[]")
    handle_at_me_support(filters)
    handle_assigned_to_filter(filters, TICKET)
    resolve_filters(filters, TICKET)
    rows = frappe.get_list(TICKET, filters=filters, fields=[COUNT_NAME])
    return cint(rows[0].get("count")) if rows else 0


def _snippet(html: str) -> str:
    from frappe.core.utils import html2text

    text = html2text(html or "", wrap=False)
    text = QUOTE_START.split(text, maxsplit=1)[0]
    text = " ".join(text.split())
    return (
        text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1].rstrip() + "…"
    )


@frappe.whitelist()
def last_messages(tickets: str | list) -> dict:
    """Each ticket's newest email: who wrote it (customer, team, or Copilot), their name, its first words and when.
    Only the agent's own readable tickets, at most 100 at a time (a page of the list)."""
    from helpdesk.automation import automation_user

    names = [str(t) for t in (frappe.parse_json(tickets) or [])][:100]
    if not names:
        return {}
    readable = frappe.get_list(
        TICKET, filters={"name": ["in", names]}, pluck="name", limit=len(names)
    )
    if not readable:
        return {}
    rows = frappe.get_all(
        "Communication",
        filters={
            "reference_doctype": TICKET,
            "reference_name": ["in", readable],
            "communication_type": "Communication",
        },
        fields=[
            "reference_name",
            "sender",
            "sender_full_name",
            "sent_or_received",
            "content",
            "communication_date",
            "creation",
        ],
        order_by="communication_date desc, creation desc",
        limit=2000,
    )
    bot = automation_user()
    result = {}
    for row in rows:
        if row.reference_name in result:
            continue
        if row.sent_or_received == "Received":
            by = "customer"
        elif row.sender == bot or (row.sender or "").startswith(bot or "\0"):
            by = "copilot"
        else:
            by = "team"
        name = row.sender_full_name or (row.sender or "").split("@")[0]
        result[row.reference_name] = {
            "by": by,
            "author": (name.split() or [_("Someone")])[0],
            "text": _snippet(row.content),
            "at": str(row.communication_date or row.creation),
        }
    return result
