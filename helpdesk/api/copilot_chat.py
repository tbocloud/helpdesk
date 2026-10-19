"""The Copilot panel in TBO Support (Phase 6, H20): the staff assistant on the web.

The same engine as the Teams bot (helpdesk.copilot.assistant); docs/tbo-copilot.md, "Staff assistant".
"""

import json

import frappe

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
