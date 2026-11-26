# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot's signature on an approved correction, which the customer's site checks before it writes.

The site made the key when its System Manager connected it (helpdesk_client's
`connect_to_hub`) and handed it to the hub with the pairing; the hub's own API key
can never set it. A signed approval is `<base64url JSON>.<base64url HMAC-SHA256>`,
the JSON naming the change set, the ticket, who approved it and when, its expiry,
and the records it covers, each with the digest of its exact values. The site's
side is helpdesk_client.mcp.write_guard; both must sign and digest alike.
"""

import base64
import hashlib
import hmac
import json
import time

from frappe import _

APPROVAL_SECONDS = 2 * 3600


def key_for(connection: str | None) -> str:
    from frappe.utils.password import get_decrypted_password

    if not connection:
        return ""
    return (
        get_decrypted_password(
            "HDS Support Connection", connection, "approval_key", raise_exception=False
        )
        or ""
    )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def sign(key: str, payload: dict) -> str:
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def change_digest(change: dict, expect=None) -> str:
    """What exactly one change does: its new values and rows, and the old values it expects."""
    content = {
        "values": change.get("values") or {},
        "rows": change.get("rows") or [],
        "add_rows": change.get("add_rows") or [],
        "expect": expect if expect is not None else None,
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def approval_for(
    connection: str,
    change_set: str,
    ticket: str,
    approved_by: str,
    approved_at,
    records: list[dict],
) -> str | None:
    """A signed approval for these records, valid two hours; None when the connection has no key."""
    key = key_for(connection)
    if not key:
        return None
    return sign(
        key,
        {
            "v": 1,
            "change_set": change_set,
            "ticket": ticket,
            "approved_by": approved_by,
            "approved_at": str(approved_at or ""),
            "exp": time.time() + APPROVAL_SECONDS,
            "records": records,
        },
    )


def no_key_message() -> str:
    return _(
        "The customer's site has no approval key yet: its System Manager connects it to TBO Support again."
    )
