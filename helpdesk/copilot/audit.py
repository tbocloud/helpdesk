# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Copilot Call Log and the per-user rate limit of the hub's MCP server."""

import json

import frappe
from frappe import _
from frappe.utils import cint

from helpdesk.copilot import settings as copilot_settings

RATE_WINDOW_SECONDS = 60
KINDS = {"person": "MCP person", "worker": "MCP worker"}


def rate_key(user: str) -> str:
    return frappe.cache.make_key(f"copilot-mcp-calls:{user}")


def check_rate_limit(user: str) -> None:
    """At most `mcp_calls_per_minute` tool calls per person per minute (the throttle_drafts pattern)."""
    limit = cint(copilot_settings.get_settings().mcp_calls_per_minute) or copilot_settings.DEFAULT_MCP_CALLS_PER_MINUTE
    key = rate_key(user)
    count = cint(frappe.cache.incr(key))
    if count == 1:
        frappe.cache.expire(key, RATE_WINDOW_SECONDS)
    if count > limit:
        frappe.throw(
            _("Rate limited: more than {0} tool calls a minute. Wait a minute and try again.").format(limit),
            frappe.RateLimitExceededError,
        )


def log_call(caller, tool: str, arguments: dict, status: str, ms: int, result: str) -> None:
    """One HDS Copilot Call Log row, written in the request (committed with it)."""
    doc = frappe.get_doc(
        {
            "doctype": "HDS Copilot Call Log",
            "user": caller.user,
            "kind": KINDS.get(caller.kind, caller.kind),
            "tool": tool[:140],
            "status": status,
            "ms": ms,
            "ticket": _ticket(arguments.get("ticket")),
            "task": _ref(arguments.get("task")),
            "run": caller.run,
            "arguments": json.dumps(arguments, ensure_ascii=False, default=str)[:2000],
            "result": (result or "")[:500],
        }
    )
    # a refused call may name a ticket that does not exist; the log keeps what was asked
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)


def _ticket(value) -> str | None:
    """The ticket as stored (0236), whatever way the caller wrote it."""
    from helpdesk.copilot.mcp.shape import ticket_name

    if value in (None, ""):
        return None
    try:
        return ticket_name(value)[:140]
    except Exception:
        return _ref(value)


def _ref(value) -> str | None:
    return str(value).strip()[:140] if value not in (None, "") else None
