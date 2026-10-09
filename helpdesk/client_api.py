# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Calls to a customer site's helpdesk_client endpoints (pairing and hub_api) as the support user.

`hub_api` is the client's own door to its Support Ticket (stages, updates,
replies, the customer's confirmation); a client that does not advertise
`hub_api_v1` is an older version, and the hub keeps using the MCP write tools.
"""

import json

import frappe
from frappe import _

LEGACY_SUPPORT_USER = "support@quarkcs.com"
HUB_API = "hub_api_v1"


def call(conn, path: str, payload: dict | None = None) -> dict:
    """POST to a whitelisted method on the customer site with the connection's token; the reply's `message`."""
    import requests
    from frappe.utils.password import get_decrypted_password

    if not conn.api_key:
        frappe.throw(_("API Key is missing on this connection."))
    api_secret = get_decrypted_password(
        "HDS Support Connection", conn.name, "api_secret", raise_exception=False
    )
    if not api_secret:
        frappe.throw(_("API Secret is missing on this connection."))

    url = f"{conn.site_url}{path}"
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Token {conn.api_key}:{api_secret}"},
            json=payload or {},
            timeout=30,
        )
    except requests.Timeout:
        frappe.throw(
            _("Customer site unreachable (timeout): {0}").format(conn.site_url)
        )
    except requests.ConnectionError as e:
        frappe.throw(
            _("Cannot connect to {0}: {1}").format(conn.site_url, str(e)[:150])
        )

    if response.status_code == 401:
        frappe.throw(
            _(
                "Authentication failed on {0}. Verify the API Key/Secret belong to {1} on the customer site."
            ).format(conn.site_url, conn.support_user or LEGACY_SUPPORT_USER)
        )
    if response.status_code != 200:
        frappe.throw(
            _("Customer site refused request: {0}").format(response.text[:400])
        )
    return response.json().get("message", {})


def hub_api(conn, method: str, payload: dict | None = None) -> dict:
    """A `helpdesk_client.hub_api` call on the customer site."""
    return call(conn, conn.client_method(f"hub_api.{method}"), payload)


def capabilities(conn) -> list[str]:
    try:
        caps = json.loads(conn.client_capabilities or "[]")
    except ValueError:
        return []
    return [str(c) for c in caps] if isinstance(caps, list) else []


def supports(conn, capability: str) -> bool:
    """Whether the client on the customer site advertised `capability` (at pairing or the daily check)."""
    return capability in capabilities(conn)


def apply_capabilities(conn, info: dict) -> bool:
    """Puts what the client said it can do (`capabilities`, `client_version`) on the connection document."""
    caps = info.get("capabilities") if isinstance(info, dict) else None
    if not isinstance(caps, list):
        return False
    conn.client_capabilities = json.dumps([str(c) for c in caps])
    conn.client_version = str(info.get("client_version") or "")[:40]
    return True


def refresh_capabilities(connection: str) -> None:
    """Asks the client what it can do. An older client has no such endpoint and stays as it is."""
    conn = frappe.get_doc("HDS Support Connection", connection)
    try:
        info = hub_api(conn, "capabilities")
    except Exception:
        return
    if apply_capabilities(conn, info):
        conn.db_set(
            {"client_capabilities": conn.client_capabilities, "client_version": conn.client_version},
            update_modified=False,
        )
