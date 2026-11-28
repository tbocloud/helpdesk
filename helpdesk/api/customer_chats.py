# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Support → Customer chats (TBO Copilot phase 32, step 6, docs/messages.md).

The Support chat in each customer's ERP (the TBO Support Client app) already reaches TBO Support:
Copilot's chat engine (`helpdesk.copilot.conversation`) answers it and keeps every message as an
HDS Conversation. Until now staff saw a chat only once its ticket existed. Here they see it live
while the AI talks, step in with "I'll answer", and reply.

Who: the people who work Support's tickets (System and Agent Managers and the ERP team,
`content_team.can_work_tickets`). Every call checks it.
"""

import contextlib
import json

import frappe
from frappe import _
from frappe.utils import cint, get_fullname

from helpdesk.api.ticket_ai import text_to_html
from helpdesk.content_team import ERP_EMPLOYEE_ROLE, can_work_tickets
from helpdesk.tasky.permissions import ADMIN_ROLES
from helpdesk.utils import add_assignment, agent_only, assigned_names_query

CONVERSATION, MESSAGE = "HDS Conversation", "HDS Conversation Message"
ERP = "ERP"
VIEWS = ("waiting", "ai", "mine", "answered", "all")
PAGE = 30
SHOWN = 200
MAX_TEXT = 4096
EVENT = "helpdesk:customer-chat"
AUDIENCE_KEY = "helpdesk:customer-chat-audience"
AUDIENCE_SECONDS = 300
OPEN_STATES = (
    "Talking",
    "Summary",
    "Before a person",
    "Ticket raised",
    "With a person",
)
STATE_LABELS = {
    "Talking": "AI talking",
    "Summary": "AI talking",
    "Before a person": "Waiting for a person",
    "Ticket raised": "Ticket raised",
    "With a person": "With a person",
    "Closed": "Closed",
}
FIELD_LABELS = (
    ("title", "Title"),
    ("actual", "What happened"),
    ("expected", "What they expected"),
    ("steps", "Steps"),
    ("records", "Records"),
    ("since", "Since when"),
    ("scope", "One record or many"),
    ("worked_before", "Worked before"),
)


def can_use(user: str | None = None) -> bool:
    return can_work_tickets(user or frappe.session.user)


def _require_use():
    if not can_use():
        frappe.throw(_("Customer chats aren't open to you."), frappe.PermissionError)


def _conversation(name: str):
    if not name or not frappe.db.exists(CONVERSATION, {"name": name, "channel": ERP}):
        frappe.throw(_("This chat was not found."), frappe.DoesNotExistError)
    return frappe.get_doc(CONVERSATION, name)


# --- live updates -----------------------------------------------------------------------------------


def audience() -> list[str]:
    """Who gets a chat's live updates: the people who may use Customer chats (cached briefly)."""
    cached = frappe.cache().get_value(AUDIENCE_KEY)
    if cached is not None:
        return cached
    users = frappe.get_all(
        "Has Role",
        filters={
            "parenttype": "User",
            "role": ["in", [*ADMIN_ROLES, ERP_EMPLOYEE_ROLE]],
        },
        pluck="parent",
        distinct=True,
    )
    enabled = set(
        frappe.get_all(
            "User", filters={"name": ["in", users or [""]], "enabled": 1}, pluck="name"
        )
    )
    found = sorted(u for u in enabled if can_work_tickets(u))
    frappe.cache().set_value(AUDIENCE_KEY, found, expires_in_sec=AUDIENCE_SECONDS)
    return found


def notify(conversation: str, direction: str):
    """A new message in a customer's ERP chat: each Customer chats screen reloads it. Only its
    name and who wrote travel, and only to the people who may see the chats."""
    for user in audience():
        frappe.publish_realtime(
            EVENT,
            {"conversation": conversation, "direction": direction},
            user=user,
            after_commit=True,
        )


# --- the list ---------------------------------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_customer_chats(
    view: str = "waiting",
    search: str | None = None,
    cursor: int | str | None = None,
    limit: int | str = PAGE,
) -> dict:
    """Customers' ERP chats, newest first. Every view but All and Answered leaves closed chats out."""
    _require_use()
    if view not in VIEWS:
        frappe.throw(_("Unknown view: {0}").format(view))
    start, size = max(cint(cursor), 0), min(max(cint(limit) or PAGE, 1), 100)
    chat = frappe.qb.DocType(CONVERSATION)
    ticket = frappe.qb.DocType("HD Ticket")
    message = frappe.qb.DocType(MESSAGE)
    query = (
        frappe.qb.from_(chat)
        .left_join(ticket)
        .on(ticket.name == chat.ticket)
        .select(
            chat.name,
            chat.customer,
            chat.connection,
            chat.site_user,
            chat.site_user_name,
            chat.title,
            chat.state,
            chat.ticket,
            chat.last_message_at,
            chat.asked_for_person,
            ticket._assign,
        )
        .where(chat.channel == ERP)
    )
    if view == "waiting":
        query = query.where(
            (chat.state == "Before a person")
            | ((chat.asked_for_person == 1) & (chat.state != "Closed"))
        )
    elif view == "ai":
        query = query.where(
            chat.state.isin(["Talking", "Summary"]) & chat.ticket.isnull()
        )
    elif view == "mine":
        query = query.where(
            chat.ticket.isin(
                assigned_names_query("HD Ticket", frappe.session.user, finished=False)
            )
        )
    elif view == "answered":
        # the AI answered from the knowledge base and nobody needed a ticket
        query = query.where(
            chat.ticket.isnull()
            & chat.name.isin(
                frappe.qb.from_(message)
                .select(message.conversation)
                .where(message.kind == "Answer")
            )
        )
    search = (search or "").strip()
    if search:
        like = f"%{search}%"
        query = query.where(
            chat.customer.like(like)
            | chat.site_user_name.like(like)
            | chat.site_user.like(like)
            | chat.title.like(like)
            | (chat.ticket == search)
        )
    rows = (
        query.orderby(chat.last_message_at, order=frappe.qb.desc)
        .limit(size + 1)
        .offset(start)
        .run(as_dict=True)
    )
    more = len(rows) > size
    rows = rows[:size]
    sites = _sites({r.connection for r in rows})
    return {
        "data": [_row(r, sites) for r in rows],
        "next_cursor": start + size if more else None,
    }


def _sites(connections: set) -> dict:
    if not connections:
        return {}
    return dict(
        frappe.get_all(
            "HDS Support Connection",
            filters={"name": ["in", list(connections)]},
            fields=["name", "site_url"],
            as_list=True,
        )
    )


def _last_line(conversation: str) -> tuple[str, str]:
    last = frappe.get_all(
        MESSAGE,
        filters={"conversation": conversation},
        fields=["text", "direction"],
        order_by="creation desc",
        limit=1,
    )
    if not last:
        return "", ""
    return " ".join((last[0].text or "").split())[:140], last[0].direction


def _assignees(raw) -> list[dict]:
    users = []
    with contextlib.suppress(ValueError, TypeError):
        users = json.loads(raw or "[]")
    return [{"user": u, "name": get_fullname(u)} for u in users]


def _row(r, sites: dict) -> dict:
    text, direction = _last_line(r.name)
    return {
        "name": r.name,
        "customer": r.customer or "",
        "site": sites.get(r.connection, ""),
        "user": r.site_user_name or r.site_user or "",
        "title": r.title or "",
        "state": STATE_LABELS.get(r.state or "", r.state or ""),
        "asked_for_person": bool(r.asked_for_person),
        "ticket": str(r.ticket or ""),
        "assignees": _assignees(r._assign),
        "last_message": text,
        "last_from": direction,
        "last_message_at": r.last_message_at,
    }


# --- one chat ---------------------------------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_customer_chat(name: str) -> dict:
    """The chat, what the AI gathered so far, what the customer saw, and the ticket."""
    _require_use()
    doc = _conversation(name)
    messages = frappe.get_all(
        MESSAGE,
        filters={"conversation": doc.name},
        fields=[
            "name",
            "direction",
            "kind",
            "text",
            "card",
            "files",
            "delivered",
            "creation",
        ],
        order_by="creation desc",
        limit=SHOWN,
    )
    messages.reverse()
    context = {}
    with contextlib.suppress(ValueError, TypeError):
        context = json.loads(doc.context or "{}") or {}
    sites = _sites({doc.connection})
    ticket_row = frappe._dict(
        frappe.db.get_value("HD Ticket", doc.ticket, ["_assign"], as_dict=True) or {}
    )
    return {
        "chat": _row(
            frappe._dict(doc.as_dict(), _assign=ticket_row.get("_assign")), sites
        ),
        "context": {
            "page": context.get("page_route") or "",
            "doctype": context.get("ref_doctype") or "",
            "docname": context.get("ref_docname") or "",
            "roles": context.get("user_roles") or [],
            "error": context.get("shown_error") or "",
        },
        "gathered": [
            {"label": _(label), "value": doc.get(field)}
            for field, label in FIELD_LABELS
            if doc.get(field)
        ],
        "ticket": _ticket(doc.ticket),
        "open_tickets": _open_tickets(doc.customer, doc.ticket),
        "messages": [_message(m) for m in messages],
        "can_take_over": doc.state in OPEN_STATES and doc.state != "With a person",
    }


def _message(m) -> dict:
    card, files = None, []
    with contextlib.suppress(ValueError, TypeError):
        card = json.loads(m.card) if m.card else None
    with contextlib.suppress(ValueError, TypeError):
        files = json.loads(m.files) if m.files else []
    return {
        "name": m.name,
        "from": m.direction,
        "kind": m.kind,
        "text": m.text or "",
        "card": card,
        "files": [
            {"name": f.get("file_name") or f.get("name") or _("File")}
            for f in files
            if isinstance(f, dict)
        ],
        "delivered": bool(m.delivered),
        "at": m.creation,
    }


def _ticket(ticket: str | None) -> dict | None:
    if not ticket:
        return None
    t = frappe.db.get_value(
        "HD Ticket",
        ticket,
        ["name", "subject", "status", "priority", "_assign"],
        as_dict=True,
    )
    if not t:
        return None
    return {
        "name": str(t.name),
        "subject": t.subject,
        "status": t.status,
        "priority": t.priority,
        "assignees": _assignees(t._assign),
    }


def _open_tickets(customer: str | None, current: str | None) -> list[dict]:
    if not customer:
        return []
    return [
        {"name": str(t.name), "subject": t.subject, "status": t.status}
        for t in frappe.get_all(
            "HD Ticket",
            filters={
                "customer": customer,
                "status_category": ["in", ["Open", "Paused"]],
                "name": ["!=", current or ""],
            },
            fields=["name", "subject", "status"],
            order_by="creation desc",
            limit=5,
        )
    ]


# --- actions ----------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@agent_only
def take_over(name: str) -> dict:
    """ "I'll answer": the AI stops; a ticket is raised from the chat if there is none (without
    starting Copilot: the person may start it); the ticket is the person's; the customer sees them
    join."""
    from helpdesk.copilot import conversation as engine
    from helpdesk.copilot.assistant import card

    _require_use()
    doc = _conversation(name)
    doc = frappe.get_doc(CONVERSATION, doc.name, for_update=True)
    if doc.state not in OPEN_STATES:
        frappe.throw(_("This chat is closed."))
    if not doc.ticket:
        raised = engine._raise(doc, transcript_only=True, start_copilot=False)
        doc.reload()
        engine._deliver(doc, raised)
    elif doc.state != "With a person":
        doc.db_set("state", "With a person", update_modified=False)
    if not _assignees(frappe.db.get_value("HD Ticket", doc.ticket, "_assign")):
        add_assignment(
            {
                "assign_to": [frappe.session.user],
                "doctype": "HD Ticket",
                "name": str(doc.ticket),
            },
            ignore_permissions=True,
        )
    person = get_fullname(frappe.session.user)
    first = (person or "").split(" ")[0] or _("Someone")
    text = (
        "انضم {0} من فريق TBO Support إلى المحادثة.".format(first)
        if doc.language == "ar"
        else _("{0} from TBO Support joined the chat.").format(first)
    )
    engine.tell(doc.ticket, "Agent", "Text", text, card(person or "", [text]))
    return {"ticket": str(doc.ticket)}


@frappe.whitelist(methods=["POST"])
@agent_only
def send_reply(name: str, text: str) -> dict:
    """A person's reply: a reply on the ticket, as from the ticket page, so it reaches the customer's
    chat at once (and by email where the ticket page's reply would). A chat without a person yet is
    taken over first."""
    _require_use()
    doc = _conversation(name)
    text = (text or "").strip()
    if not text:
        frappe.throw(_("Write a message first."))
    if len(text) > MAX_TEXT:
        frappe.throw(_("A message is at most {0} characters.").format(MAX_TEXT))
    if not doc.ticket or doc.state != "With a person":
        take_over(name)
        doc.reload()
    ticket = frappe.get_doc("HD Ticket", doc.ticket)
    ticket.reply_via_agent(message=text_to_html(text))
    return {"ticket": str(doc.ticket)}
