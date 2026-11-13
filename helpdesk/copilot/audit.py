# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Copilot Call Log and the per-user rate limit of the hub's MCP server.

The logs keep who, which tool, which record, when, how it went and how long (TBO Copilot Phase 21,
decision 1): identifiers stay readable; free text (a search, a note, a reply, a customer's name or
email) is kept only as its length and a keyed fingerprint, so the same text can be recognised
without being stored; results are kept as their length only.
"""

import hashlib
import hmac
import json
import re

import frappe
from frappe import _
from frappe.utils import cint

from helpdesk.copilot import settings as copilot_settings

RATE_WINDOW_SECONDS = 60
KINDS = {"person": "MCP person", "worker": "MCP worker"}
# values under these names are always text people wrote (or customers' data), whatever they look like
TEXT_KEYS = {
    "body",
    "command",
    "comment",
    "contact",
    "content",
    "customer",
    "description",
    "details",
    "email",
    "explanation",
    "filters",
    "how_to_test",
    "instructions",
    "message",
    "note",
    "payload",
    "query",
    "raised_by",
    "reason",
    "reply",
    "subject",
    "summary",
    "text",
    "title",
    "what_and_why",
}
# a record's name, a site, an action: one word, no address
IDENTIFIER = re.compile(r"^[\w.:/+#-]{1,140}$")
MAX_ARGUMENTS = 2000


def fingerprint(text: str) -> dict:
    """The length and a keyed hash of a text: the same text gives the same mark, the text stays out."""
    key = (
        frappe.local.conf.get("encryption_key") or frappe.local.site or "tbo"
    ).encode()
    mark = hmac.new(key, str(text).encode(), hashlib.sha256).hexdigest()[:12]
    return {"chars": len(str(text)), "mark": mark}


def _safe(value, key: str = "", depth: int = 0):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if key.lower() in TEXT_KEYS:
        return fingerprint(
            json.dumps(value, ensure_ascii=False, default=str)
            if not isinstance(value, str)
            else value
        )
    if isinstance(value, str):
        return (
            value
            if IDENTIFIER.match(value) and "@" not in value
            else fingerprint(value)
        )
    if depth >= 3:
        return fingerprint(json.dumps(value, ensure_ascii=False, default=str))
    if isinstance(value, dict):
        return {
            str(k)[:60]: _safe(v, str(k), depth + 1)
            for k, v in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        return [_safe(v, key, depth + 1) for v in list(value)[:40]]
    return fingerprint(str(value))


def safe_arguments(arguments) -> str:
    """A tool call's arguments as the logs keep them: identifiers as they are, text as a fingerprint."""
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}
    return json.dumps(_safe(arguments), ensure_ascii=False, default=str)[:MAX_ARGUMENTS]


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
LONG_NUMBER = re.compile(r"\d{6,}")


def error_line(message) -> str:
    """An error as the logs keep it: its first line, at most 200 characters, with email addresses and
    long numbers (phones, accounts) masked."""
    first = str(message or "").strip().split("\n")[0][:200]
    return LONG_NUMBER.sub("…", EMAIL.sub("[email]", first))


def result_size(result) -> str:
    """What the logs keep of a result: its size, never its content."""
    return f"{len(result or '')} characters" if result else ""


def rate_key(user: str) -> str:
    return frappe.cache.make_key(f"copilot-mcp-calls:{user}")


def check_rate_limit(user: str) -> None:
    """At most `mcp_calls_per_minute` tool calls per person per minute (the throttle_drafts pattern)."""
    limit = (
        cint(copilot_settings.get_settings().mcp_calls_per_minute)
        or copilot_settings.DEFAULT_MCP_CALLS_PER_MINUTE
    )
    key = rate_key(user)
    count = cint(frappe.cache.incr(key))
    if count == 1:
        frappe.cache.expire(key, RATE_WINDOW_SECONDS)
    if count > limit:
        frappe.throw(
            _(
                "Rate limited: more than {0} tool calls a minute. Wait a minute and try again."
            ).format(limit),
            frappe.RateLimitExceededError,
        )


def log_call(
    caller, tool: str, arguments: dict, status: str, ms: int, result: str
) -> None:
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
            "arguments": safe_arguments(arguments),
            "result": result_size(result),
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
