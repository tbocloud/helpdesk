# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The customer's chat (Phase 5): a customer's site relays its user's message here, signed."""

import json

import frappe
from werkzeug.wrappers import Response


@frappe.whitelist(allow_guest=True, methods=["POST"])
def message():
    """One message or button press from a chat on a paired customer site; the assistant's replies.

    Guest by design: the site signs each request with a key derived from its pairing
    key (helpdesk.copilot.conversation.verify), and vouches for its own logged-in user.
    """
    from helpdesk.copilot import conversation

    body = frappe.request.get_data() or b""
    try:
        connection = conversation.verify(frappe.request.headers, body)
    except frappe.PermissionError as e:
        frappe.clear_last_message()
        return Response(
            json.dumps({"error": str(e)}), status=403, content_type="application/json"
        )
    payload = json.loads(body or b"{}")
    reply = conversation.receive(
        connection, payload if isinstance(payload, dict) else {}
    )
    return Response(
        json.dumps(reply, default=str), status=200, content_type="application/json"
    )
