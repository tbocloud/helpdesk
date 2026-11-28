# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Messages section's screen and actions (TBO Copilot phase 32, docs/messages.md).

Who may use it (`chat_messages.can_use`): System and Agent Managers, and the front-desk team's
members, while the Messages section is on. Each call checks it again.
"""

import contextlib
import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, get_fullname, now_datetime

from helpdesk import chat_messages
from helpdesk.utils import (
    add_assignment,
    agent_only,
    assigned_names_query,
    get_agents_team,
)

VIEWS = ("mine", "team", "unassigned", "waiting", "ai", "all")
MAX_TEXT = 4096
PAGE = 30
MESSAGES_SHOWN = 200
STATES = {"Pending": "AI talking", "Open": "With a person", "Resolved": "Closed"}


def _require_use():
    if not chat_messages.can_use():
        frappe.throw(_("Messages isn't open to you."), frappe.PermissionError)


def _settings():
    return frappe.get_cached_doc(chat_messages.SETTINGS)


def _chat(name: str):
    """The bridge's ChatConversation for a Messages conversation the user may work."""
    from helpdesk.chatwoot_bridge import ChatConversation

    if not name or not frappe.db.exists(chat_messages.CONVERSATION, name):
        frappe.throw(_("This conversation was not found."), frappe.DoesNotExistError)
    row = frappe.get_doc(chat_messages.CONVERSATION, name)
    if row.hd_ticket and not chat_messages.in_messages(row.hd_ticket):
        frappe.throw(_("This conversation's ticket is in Support now."))
    return ChatConversation(row, frappe.get_single(chat_messages.SETTINGS))


# --- the list ---------------------------------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_conversations(
    view: str = "mine",
    search: str | None = None,
    cursor: int | str | None = None,
    limit: int | str = PAGE,
) -> dict:
    """The Messages list: newest message first. Every view but All leaves closed chats out."""
    _require_use()
    if view not in VIEWS:
        frappe.throw(_("Unknown view: {0}").format(view))
    if view == "all" and not chat_messages.is_manager():
        frappe.throw(_("Only managers see all conversations."), frappe.PermissionError)
    start, size = max(cint(cursor), 0), min(max(cint(limit) or PAGE, 1), 100)

    chat = frappe.qb.DocType(chat_messages.CONVERSATION)
    ticket = frappe.qb.DocType("HD Ticket")
    query = (
        frappe.qb.from_(chat)
        .left_join(ticket)
        .on(ticket.name == chat.hd_ticket)
        .select(
            chat.name,
            chat.conversation_id,
            chat.channel,
            chat.contact_name,
            chat.contact_phone,
            chat.hd_customer,
            chat.hd_ticket,
            chat.status,
            chat.waiting_on,
            chat.unread,
            chat.last_message,
            chat.last_message_at,
            chat.window_closes_at,
            ticket.status.as_("ticket_status"),
            ticket.agent_group,
            ticket._assign,
        )
        # Messages only: a chat whose ticket moved to Support is worked there
        .where(ticket.name.isnull() | (ticket.custom_section == chat_messages.MESSAGES))
    )
    if view != "all":
        query = query.where(chat.status != "Resolved")
    user = frappe.session.user
    if view == "mine":
        query = query.where(
            ticket.name.isin(assigned_names_query("HD Ticket", user, finished=False))
        )
    elif view == "team":
        teams = [t.team_name for t in get_agents_team()] or [""]
        query = query.where(ticket.agent_group.isin(teams))
    elif view == "unassigned":
        query = query.where(ticket._assign.isnull() | ticket._assign.isin(["", "[]"]))
    elif view == "waiting":
        query = query.where(chat.waiting_on == "Us")
    elif view == "ai":
        query = query.where(chat.status == "Pending")
    search = (search or "").strip()
    if search:
        like = f"%{search}%"
        query = query.where(
            chat.contact_name.like(like)
            | chat.contact_phone.like(like)
            | chat.last_message.like(like)
            | (chat.hd_ticket == search)
        )
    rows = (
        query.orderby(chat.last_message_at, order=frappe.qb.desc)
        .limit(size + 1)
        .offset(start)
        .run(as_dict=True)
    )
    more = len(rows) > size
    return {
        "data": [_row(r) for r in rows[:size]],
        "next_cursor": start + size if more else None,
    }


def _row(r) -> dict:
    from helpdesk.chatwoot_bridge import CHANNEL_LABELS

    assignees = []
    with contextlib.suppress(ValueError):
        assignees = json.loads(r._assign or "[]")
    return {
        "name": r.name,
        "channel": CHANNEL_LABELS.get(r.channel or "", r.channel or ""),
        "channel_key": r.channel or "",
        "contact_name": r.contact_name or r.contact_phone or _("Customer"),
        "contact_phone": r.contact_phone or "",
        "customer": r.hd_customer or "",
        "ticket": r.hd_ticket or "",
        "ticket_status": r.ticket_status or "",
        "team": r.agent_group or "",
        "assignees": [{"user": u, "name": get_fullname(u)} for u in assignees],
        "state": STATES.get(r.status or "", r.status or ""),
        "waiting_on": r.waiting_on or "",
        "unread": bool(r.unread),
        "last_message": r.last_message or "",
        "last_message_at": r.last_message_at,
        "window": _window(r.channel, r.window_closes_at),
    }


def _window(channel: str | None, closes_at) -> dict | None:
    """The 24-hour reply window of WhatsApp, Instagram and Facebook; None for other channels."""
    if (channel or "") not in chat_messages.WINDOW_CHANNELS:
        return None
    open_ = bool(closes_at) and get_datetime(closes_at) > now_datetime()
    return {"open": open_, "closes_at": closes_at}


# --- one conversation -------------------------------------------------------------------------------


@frappe.whitelist()
@agent_only
def get_conversation(name: str) -> dict:
    """The chat, its context and its latest messages; opening it marks it read."""
    _require_use()
    chat = _chat(name)
    row = chat.row
    messages = frappe.get_all(
        chat_messages.MESSAGE,
        filters={"conversation": row.name},
        fields=[
            "name",
            "direction",
            "sender_type",
            "author",
            "kind",
            "content",
            "sent_at",
            "status",
            "error",
            "reply_to",
            "chatwoot_message_id",
        ],
        order_by="sent_at desc, chatwoot_message_id desc",
        limit=MESSAGES_SHOWN,
    )
    messages.reverse()
    files = _files_of([m.name for m in messages])
    if row.unread:
        chat.set_values({"unread": 0})
    ticket = (
        frappe.db.get_value(
            "HD Ticket",
            row.hd_ticket,
            ["status", "agent_group", "_assign"],
            as_dict=True,
        )
        if row.hd_ticket
        else None
    ) or frappe._dict()
    listed = frappe._dict(
        row.as_dict(),
        ticket_status=ticket.status or "",
        agent_group=ticket.agent_group or "",
        _assign=ticket._assign or "",
    )
    return {
        "conversation": _row(listed),
        "contact": {
            "name": row.contact_name or "",
            "email": row.contact_email or "",
            "phone": row.contact_phone or "",
            "contact": row.contact or "",
            "customer": row.hd_customer or "",
            "verified": bool(row.identity_verified),
        },
        "ticket": _ticket_card(row.hd_ticket),
        "earlier": _earlier_tickets(row),
        "messages": [_message(m, files.get(m.name, [])) for m in messages],
        "can_move_to_support": bool(row.hd_ticket),
    }


def _files_of(names: list[str]) -> dict:
    if not names:
        return {}
    rows = frappe.get_all(
        "HD Chat Message File",
        filters={"parent": ["in", names], "parenttype": chat_messages.MESSAGE},
        fields=[
            "parent",
            "file_type",
            "file",
            "file_name",
            "size",
            "note",
            "source_url",
        ],
        order_by="idx asc",
    )
    found = {}
    for f in rows:
        found.setdefault(f.parent, []).append(
            {
                "type": f.file_type,
                "url": f.file or "",
                "name": f.file_name or "",
                "size": cint(f.size),
                "note": f.note or "",
                # a location's map link; a file's Chatwoot address stays on the server
                "link": f.source_url if f.file_type == "Location" else "",
            }
        )
    return found


def _message(m, files: list[dict]) -> dict:
    return {
        "name": m.name,
        "direction": m.direction,
        "from": m.sender_type,
        "author": get_fullname(m.author) if m.author else "",
        "kind": m.kind,
        "text": m.content or "",
        "sent_at": m.sent_at,
        "status": m.status or "",
        "error": m.error or "",
        "reply_to": cint(m.reply_to),
        "id": cint(m.chatwoot_message_id),
        "files": files,
    }


def _ticket_card(ticket: str | None) -> dict | None:
    if not ticket:
        return None
    t = frappe.db.get_value(
        "HD Ticket",
        ticket,
        [
            "name",
            "subject",
            "status",
            "priority",
            "agent_group",
            "_assign",
            "opening_date",
        ],
        as_dict=True,
    )
    if not t:
        return None
    try:
        assignees = json.loads(t._assign or "[]")
    except ValueError:
        assignees = []
    return {
        "name": str(t.name),
        "subject": t.subject,
        "status": t.status,
        "priority": t.priority,
        "team": t.agent_group or "",
        "assignees": [{"user": u, "name": get_fullname(u)} for u in assignees],
        "opened": t.opening_date,
    }


def _earlier_tickets(row) -> list[dict]:
    """The contact's other Messages tickets, newest first."""
    filters = {
        "custom_section": chat_messages.MESSAGES,
        "name": ["!=", row.hd_ticket or ""],
    }
    if row.contact:
        filters["contact"] = row.contact
    else:
        conversations = frappe.get_all(
            chat_messages.CONVERSATION,
            filters={"chatwoot_contact_id": row.chatwoot_contact_id or -1},
            pluck="hd_ticket",
        )
        filters["name"] = [
            "in",
            [t for t in conversations if t and t != row.hd_ticket] or [""],
        ]
    return [
        {"name": str(t.name), "subject": t.subject, "status": t.status}
        for t in frappe.get_all(
            "HD Ticket",
            filters=filters,
            fields=["name", "subject", "status"],
            order_by="creation desc",
            limit=5,
        )
    ]


# --- actions ----------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@agent_only
def send_message(name: str, text: str, private: int | str = 0) -> dict:
    """A person's reply (or, with `private`, an internal note) on the chat's channel. A reply
    takes the chat over from the AI; WhatsApp, Instagram and Facebook refuse a free-form reply
    once their 24-hour window has closed."""
    _require_use()
    chat = _chat(name)
    text = (text or "").strip()
    if not text:
        frappe.throw(_("Write a message first."))
    if len(text) > MAX_TEXT:
        frappe.throw(_("A message is at most {0} characters.").format(MAX_TEXT))
    private = bool(cint(private))
    window = _window(chat.row.channel, chat.row.window_closes_at)
    if not private and window and not window["open"]:
        frappe.throw(
            _(
                "The 24-hour window closed, so this channel takes only an approved template now."
            )
        )
    if not private:
        _take_over(chat)
    posted = chat.client.post_message(chat.conversation_id, text, private=private)
    if posted is None:
        frappe.throw(_("TBO Chat didn't take the message. Try again in a moment."))
    # what Chatwoot answers is the message; what we sent fills in anything it leaves out
    message = {
        "content": text,
        "private": private,
        "message_type": "outgoing",
        **(posted if isinstance(posted, dict) else {}),
    }
    kept = chat_messages.keep(
        chat, message, author=frappe.session.user, sender_type="Staff"
    )
    return {"message": kept}


@frappe.whitelist(methods=["POST"])
@agent_only
def take_over(name: str) -> dict:
    """ "I'll answer": the AI stops on this chat, and its ticket is the person's."""
    _require_use()
    chat = _chat(name)
    _take_over(chat)
    return {"state": STATES["Open"]}


def _take_over(chat):
    if chat.row.status == "Pending":
        # as the bridge's user, not the bot: a person has the chat now
        chat.client.toggle_status(chat.conversation_id, "open")
        chat.set_values({"status": "Open"})
    ticket = chat.row.hd_ticket
    if ticket and not _assignees(ticket):
        add_assignment(
            {
                "assign_to": [frappe.session.user],
                "doctype": "HD Ticket",
                "name": str(ticket),
            },
            ignore_permissions=True,
        )


def _assignees(ticket) -> list[str]:
    try:
        return json.loads(frappe.db.get_value("HD Ticket", ticket, "_assign") or "[]")
    except ValueError:
        return []


@frappe.whitelist(methods=["POST"])
@agent_only
def assign(name: str, user: str | None = None, team: str | None = None) -> dict:
    """The chat's ticket to a person, a team, or both."""
    _require_use()
    chat = _chat(name)
    ticket = chat.row.hd_ticket
    if not ticket:
        frappe.throw(_("This chat has no ticket yet."))
    if team:
        if not frappe.db.exists("HD Team", team):
            frappe.throw(_("Team {0} was not found.").format(team))
        frappe.db.set_value("HD Ticket", ticket, "agent_group", team)
    if user:
        if not frappe.db.exists("HD Agent", {"user": user, "is_active": 1}):
            frappe.throw(_("{0} is not an active agent.").format(user))
        if user not in _assignees(ticket):
            add_assignment(
                {"assign_to": [user], "doctype": "HD Ticket", "name": str(ticket)},
                ignore_permissions=True,
            )
    return {"ticket": _ticket_card(ticket)}


@frappe.whitelist(methods=["POST"])
@agent_only
def move_to_support(ticket: str) -> dict:
    """A Messages chat that is really a customer's ERP problem goes to Support."""
    ticket = str(ticket or "").strip()
    if not ticket or not frappe.db.exists("HD Ticket", ticket):
        frappe.throw(_("Ticket {0} was not found.").format(ticket))
    if not frappe.has_permission("HD Ticket", "write", doc=ticket):
        frappe.throw(
            _("You may not change ticket {0}.").format(ticket), frappe.PermissionError
        )
    return {
        "ticket": chat_messages.move_to_support(ticket),
        "section": chat_messages.SUPPORT,
    }
