# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The ticket's Copilot chat on the ticket page (Phase 11, helpdesk.copilot.thread): for agents
who may read the ticket; everything said or pressed here acts as them."""

import json

import frappe
from frappe import _

from helpdesk.copilot import thread
from helpdesk.utils import agent_only


def _parse(value, default):
    if isinstance(value, str):
        try:
            return json.loads(value) if value else default
        except ValueError:
            frappe.throw(_("Not readable JSON"))
    return value or default


def _readable(ticket: str):
    frappe.has_permission("HD Ticket", "read", str(ticket), throw=True)


@frappe.whitelist()
@agent_only
def history(ticket: str | int) -> dict:
    """The ticket's chat, oldest first, and what this person may do now."""
    _readable(ticket)
    return {
        "messages": thread.history(str(ticket)),
        "now": thread.now(str(ticket), frappe.session.user),
        "chat": thread.thread_for(str(ticket)).name,
        "people": thread.people(str(ticket)),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def send(ticket: str | int, text: str = "", files: str | list | None = None) -> dict:
    """A message to Copilot in the ticket's chat: answered, or the action proposed or done."""
    _readable(ticket)
    from helpdesk.copilot import assistant

    # only files uploaded to this ticket's chat: a File named here is copied on (to a new ticket,
    # as its owner), so a name from elsewhere could expose a private file (Phase 23, A7)
    chat = thread.thread_for(str(ticket)).name
    names = [
        name
        for name in _parse(files, [])
        if frappe.db.get_value(
            "File", name, ["attached_to_doctype", "attached_to_name"]
        )
        == (assistant.CHAT, chat)
    ]
    replies = thread.receive(frappe.session.user, str(ticket), text, names, via="Web")
    return {"replies": replies}


@frappe.whitelist(methods=["POST"])
@agent_only
def press(
    ticket: str | int,
    verb: str,
    data: str | dict | None = None,
    inputs: str | dict | None = None,
) -> dict:
    """A button in the ticket's chat or its menu."""
    _readable(ticket)
    return thread.press(
        frappe.session.user,
        str(ticket),
        verb,
        _parse(data, {}),
        _parse(inputs, {}),
        via="Web",
    )
