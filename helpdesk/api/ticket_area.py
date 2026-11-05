"""The agent's ticket list (Phase 15): its queues' counts, the filters plain conditions can't say, and each row's
last message.

Two filters stand for an OR that a list's AND-only conditions can't express, so the server turns them into a
name list, as `__assigned_on` does (api/doc.py):
- `__overdue`: an open ticket past its first-reply time (no reply yet) or past its resolution time;
- `__search`: the words in the number, subject, customer, contact or raiser.

A queue's count and its list use the same conditions, so the number on a tab is the number of rows it opens.

The inbox (Phase 16) lists the same rows as chat rows: each ticket's newest message, how many messages the customer
sent since our last reply, and whether Copilot works on it or has a fix waiting for approval.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from helpdesk.api.dashboard import COUNT_NAME
from helpdesk.utils import agent_only

TICKET = "HD Ticket"
# enough for a page of matches; a search that finds more than this needs more words
MAX_MATCHES = 1000
SEARCH_FIELDS = ("subject", "customer", "raised_by", "contact")
PREVIEW_CHARS = 140
INBOX_PAGE = 50
INBOX_FIELDS = (
    "name",
    "subject",
    "status",
    "status_category",
    "priority",
    "customer",
    "contact",
    "raised_by",
    "modified",
    "creation",
    "_assign",
    "_seen",
    "response_by",
    "resolution_by",
    "first_responded_on",
    "resolution_date",
    "agreement_status",
)
# a run in one of these states is Copilot at work on the ticket
COPILOT_WORKING = (
    "Queued",
    "Investigating",
    "Preparing Fix",
    "Approved",
    "Merging",
    "Deploying",
    "Verifying",
    "Applying",
)
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


def _list_filters(filters):
    """The list's filters as the server reads them: @me, assigned-to, overdue and search resolved."""
    from helpdesk.api.doc import handle_assigned_to_filter, handle_at_me_support

    filters = frappe.parse_json(filters or "[]")
    handle_at_me_support(filters)
    handle_assigned_to_filter(filters, TICKET)
    resolve_filters(filters, TICKET)
    return filters


@frappe.whitelist()
def count(filters: str | list | dict | None = None) -> int:
    """How many tickets the agent may read under `filters`: a queue's number, the same rows its list shows."""
    rows = frappe.get_list(TICKET, filters=_list_filters(filters), fields=[COUNT_NAME])
    return cint(rows[0].get("count")) if rows else 0


def _snippet(html: str) -> str:
    from frappe.core.utils import html2text

    text = html2text(html or "", wrap=False)
    text = QUOTE_START.split(text, maxsplit=1)[0]
    text = " ".join(text.split())
    return (
        text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1].rstrip() + "…"
    )


def _author(row, bot) -> tuple[str, str]:
    """Who wrote an email: the customer, Copilot (the automation user) or the team; and their first name."""
    if row.sent_or_received == "Received":
        by = "customer"
    elif bot and (row.sender == bot or (row.sender or "").startswith(bot)):
        by = "copilot"
    else:
        by = "team"
    name = row.sender_full_name or (row.sender or "").split("@")[0]
    return by, (name.split() or [_("Someone")])[0]


def _conversations(names: list[str]) -> dict:
    """Each ticket's newest email (who, their first words, when) and the customer's emails since our last reply."""
    if not names:
        return {}
    rows = frappe.get_all(
        "Communication",
        filters={
            "reference_doctype": TICKET,
            "reference_name": ["in", names],
            "communication_type": "Communication",
        },
        fields=[
            "name",
            "reference_name",
            "sender",
            "sender_full_name",
            "sent_or_received",
            "communication_date",
            "creation",
        ],
        order_by="communication_date desc, creation desc",
        limit=5000,
    )
    newest, waiting, answered, named = {}, {}, set(), {}
    for row in rows:
        ticket = row.reference_name
        newest.setdefault(ticket, row)
        if row.sent_or_received == "Received" and row.sender_full_name:
            named.setdefault(ticket, row.sender_full_name)
        if ticket in answered:
            continue
        if row.sent_or_received == "Received":
            waiting[ticket] = waiting.get(ticket, 0) + 1
        else:
            answered.add(ticket)
    # the text only of the newest email per ticket
    content = dict(
        frappe.get_all(
            "Communication",
            filters={"name": ["in", [row.name for row in newest.values()]]},
            fields=["name", "content"],
            as_list=True,
        )
    )
    from helpdesk.helpdesk.doctype.hd_ticket.api import _automation_sender

    bot = _automation_sender()
    result = {}
    for ticket, row in newest.items():
        by, author = _author(row, bot)
        result[ticket] = {
            "by": by,
            "author": author,
            "text": _snippet(content.get(row.name) or ""),
            "at": str(row.communication_date or row.creation),
            "waiting": waiting.get(ticket, 0),
            # the name the customer's newest email gave: the row's name when the ticket has no contact
            "customer_name": named.get(ticket),
        }
    return result


def _copilot_signals(rows: list[dict]) -> dict:
    """Each row's Copilot signal: approve while a fix waits for approval, working while its latest run is at work."""
    names = [row.name for row in rows]
    if not names:
        return {}
    pending = set(
        frappe.get_all(
            "HDS Copilot Approval",
            filters={"ticket": ["in", names], "status": "Pending"},
            pluck="ticket",
        )
    )
    runs = [
        row.get("custom_copilot_run") for row in rows if row.get("custom_copilot_run")
    ]
    states = (
        dict(
            frappe.get_all(
                "HDS Copilot Run",
                filters={"name": ["in", runs]},
                fields=["name", "state"],
                as_list=True,
            )
        )
        if runs
        else {}
    )
    signals = {}
    for row in rows:
        if row.name in pending:
            signals[row.name] = "approve"
        elif states.get(row.get("custom_copilot_run")) in COPILOT_WORKING:
            signals[row.name] = "working"
    return signals


@frappe.whitelist()
def last_messages(tickets: str | list) -> dict:
    """Each ticket's newest email: who wrote it (customer, team, or Copilot), their name, its first words and when.
    Only the agent's own readable tickets, at most 100 at a time (a page of the list)."""
    names = [str(t) for t in (frappe.parse_json(tickets) or [])][:100]
    if not names:
        return {}
    readable = frappe.get_list(
        TICKET, filters={"name": ["in", names]}, pluck="name", limit=len(names)
    )
    return {
        ticket: {
            key: value
            for key, value in message.items()
            if key not in ("waiting", "customer_name")
        }
        for ticket, message in _conversations(readable).items()
    }


@frappe.whitelist()
@agent_only
def inbox(
    filters: str | list | dict | None = None,
    start: int = 0,
    page_length: int = INBOX_PAGE,
) -> dict:
    """The agent's inbox (Phase 16): a page of the tickets they may read under `filters`, newest change first, the
    same rows a queue counts. Each row has its newest email (`last`, with `waiting`: the customer's emails since our
    last reply) and Copilot's signal (`copilot`: approve, working or nothing). `more`: there is a next page."""
    page_length = min(max(cint(page_length), 1), 100)
    fields = list(INBOX_FIELDS)
    if frappe.get_meta(TICKET).has_field("custom_copilot_run"):
        fields.append("custom_copilot_run")
    rows = frappe.get_list(
        TICKET,
        filters=_list_filters(filters),
        fields=fields,
        order_by="modified desc",
        start=max(cint(start), 0),
        page_length=page_length + 1,
    )
    more = len(rows) > page_length
    rows = rows[:page_length]
    names = [str(row.name) for row in rows]
    messages = _conversations(names)
    signals = _copilot_signals(rows)
    for row in rows:
        row["last"] = messages.get(str(row.name))
        row["copilot"] = signals.get(row.name)
        row.pop("custom_copilot_run", None)
    return {"tickets": rows, "more": more}
