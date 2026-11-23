"""The Copilot panel in TBO Support (Phase 6, H20): the staff assistant on the web.

The same engine as the Teams bot (helpdesk.copilot.assistant); docs/tbo-copilot.md, "Staff assistant".
"""

import json

import frappe
from frappe import _

from helpdesk.copilot import assistant
from helpdesk.utils import agent_only

CHANNEL = "Web"


def _parse(value, default):
    if isinstance(value, str):
        try:
            return json.loads(value) if value else default
        except ValueError:
            return default
    return value if value is not None else default


@frappe.whitelist()
@agent_only
def history(limit: int = 40) -> dict:
    """The person's panel chat, oldest first, and the chat's name (files are uploaded to it)."""
    chat = assistant.chat_for(frappe.session.user, CHANNEL)
    return {
        "chat": chat.name,
        "messages": assistant.history(frappe.session.user, CHANNEL, int(limit)),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def send(message: str = "", files: list | str | None = None) -> dict:
    """A message (and files already uploaded to the person's chat); the chat after Copilot's answer."""
    user = frappe.session.user
    chat = assistant.chat_for(user, CHANNEL)
    names = [
        name
        for name in _parse(files, [])
        if frappe.db.get_value(
            "File", name, ["attached_to_doctype", "attached_to_name"]
        )
        == (assistant.CHAT, chat.name)
    ]
    assistant.receive(
        user, CHANNEL, message or "", names
    )  # the replies are kept in the chat
    return history()


@frappe.whitelist(methods=["POST"])
@agent_only
def attach():
    """The paperclip in Copilot's chats (Phase 23, A6). Frappe's upload_file calls this with the
    uploaded file instead of saving it, because agents have no write permission on HDS Copilot
    Chat itself: the File goes on the person's own chat, or on a ticket's chat they may write in."""
    from helpdesk.copilot import thread

    user = frappe.session.user
    chat = str(frappe.form_dict.get("docname") or "")
    content = getattr(frappe.local, "uploaded_file", None)
    filename = getattr(frappe.local, "uploaded_filename", None)
    if not chat or content is None or not filename:
        frappe.throw(_("No file came with the upload."))
    row = frappe.db.get_value(assistant.CHAT, chat, ["user", "ticket"], as_dict=True)
    if not row:
        frappe.throw(_("That chat does not exist."), frappe.DoesNotExistError)
    if row.ticket:
        # the answer decides `allowed`; nothing is shown without it
        allowed = frappe.has_permission(  # nosemgrep
            "HD Ticket", "read", str(row.ticket)
        ) and thread.may_write(user, str(row.ticket))
    else:
        allowed = row.user == user
    if not allowed:
        frappe.throw(_("You may not add files to that chat."), frappe.PermissionError)
    return frappe.get_doc(
        {
            "doctype": "File",
            "attached_to_doctype": assistant.CHAT,
            "attached_to_name": chat,
            "file_name": filename,
            "is_private": 1,
            "content": content,
        }
    ).save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
@agent_only
def press(
    verb: str,
    data: dict | str | None = None,
    inputs: dict | str | None = None,
    card_message: str | None = None,
) -> dict:
    """A button on a card; the pressed card (`card_message`) is updated to how it looks now."""
    user = frappe.session.user
    chat = assistant.chat_for(user, CHANNEL)
    result = assistant.press(user, CHANNEL, verb, _parse(data, {}), _parse(inputs, {}))
    if card_message and result.get("card"):
        owner = frappe.db.get_value(assistant.MESSAGE, card_message, "chat")
        if owner == chat.name:
            frappe.db.set_value(
                assistant.MESSAGE,
                card_message,
                "card",
                json.dumps(result["card"], ensure_ascii=False),
                update_modified=False,
            )
    return history()
