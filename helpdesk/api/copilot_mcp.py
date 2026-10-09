# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The hub's MCP server endpoint (TASK-2026-00013).

Streamable HTTP without sessions or event streams: every request is a POST
carrying its own credentials. People send their own API key
(`Authorization: token key:secret`), which Frappe checks before this runs;
the Copilot worker sends a run token (see helpdesk.copilot.mcp.auth).
Replies are raw JSON-RPC, not Frappe's {"message": ...} wrapper.
"""

import json

import frappe
from werkzeug.wrappers import Response

from helpdesk.copilot import settings as copilot_settings
from helpdesk.copilot.mcp import auth, server
from helpdesk.copilot.mcp.protocol import AUTH_REQUIRED, FORBIDDEN, PARSE_ERROR, make_error
from helpdesk.copilot.mcp.registry import message_of


@frappe.whitelist(allow_guest=True, methods=["POST", "GET", "DELETE"])  # the MCP server checks every caller itself - nosemgrep
def handle() -> Response:
    if frappe.request.method != "POST":
        # no event stream and no sessions to end: everything is a POST
        return Response(status=405, headers={"Allow": "POST"})
    try:
        payload = json.loads(frappe.request.get_data() or b"null")
    except ValueError:
        return _json(make_error(None, PARSE_ERROR, "The body is not JSON"), 400)
    first_id = _first_id(payload)
    try:
        caller = auth.identify()
    except frappe.AuthenticationError as e:
        return _json(make_error(first_id, AUTH_REQUIRED, message_of(e)), 401)
    except frappe.PermissionError as e:
        return _json(make_error(first_id, FORBIDDEN, message_of(e)), 403)
    if not copilot_settings.get_settings().mcp_enabled:
        return _json(make_error(first_id, FORBIDDEN, "The TBO Support MCP server is switched off"), 503)
    reply = server.dispatch(caller, payload)
    if reply is None:
        return Response(status=202)
    return _json(reply)


def _json(data, status: int = 200) -> Response:
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type="application/json",
    )


def _first_id(payload):
    message = payload[0] if isinstance(payload, list) and payload else payload
    return message.get("id") if isinstance(message, dict) else None
