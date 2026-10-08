# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Whitelisted API endpoints for HD Form Script and external calls."""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from helpdesk.utils import agent_manager_only, agent_only


@frappe.whitelist()
@agent_only
def get_triage(ticket: str | int):
    """Get triage results for a ticket."""
    ticket = str(ticket)
    ticket_doc = frappe.get_doc("HD Ticket", ticket)
    ticket_doc.check_permission("read")
    triage_data = (
        json.loads(ticket_doc.custom_triage_data or "{}")
        if ticket_doc.custom_triage_data
        else {}
    )

    return {
        "status": ticket_doc.custom_triage_status or "",
        "category": ticket_doc.custom_triage_category or "",
        "priority": ticket_doc.custom_triage_priority or "",
        "complexity": ticket_doc.custom_triage_complexity or "",
        "summary": ticket_doc.custom_triage_summary or "",
        "recommended_track": ticket_doc.custom_triage_recommended_track or "",
        "timestamp": str(ticket_doc.custom_triage_timestamp)
        if ticket_doc.custom_triage_timestamp
        else "",
        "data": triage_data,
    }


@frappe.whitelist()
@agent_only
def run_triage_now(ticket: str | int):
    """Manually trigger triage for a ticket."""
    from helpdesk.triage import run_triage_now as _run_triage_now

    return _run_triage_now(str(ticket))


@frappe.whitelist()
@agent_only
def start_investigation(ticket: str | int, connection: str, agent_notes: str = ""):
    """Start an AI investigation session."""
    from helpdesk.session_manager import start_investigation as _start

    session_name = _start(str(ticket), str(connection), agent_notes)
    return {"session": session_name, "status": "started"}


@frappe.whitelist()
@agent_only
def get_sessions(ticket: str | int):
    """Get all investigation sessions for a ticket."""
    ticket = str(ticket)
    sessions = frappe.get_list(
        "HDS AI Support Session",
        filters={"ticket": ticket},
        fields=[
            "name",
            "status",
            "started_at",
            "ended_at",
            "total_tool_calls",
            "estimated_cost_usd",
            "model_used",
            "customer_name",
            "diagnosis",
        ],
        order_by="creation desc",
    )
    return sessions


@frappe.whitelist()
@agent_only
def get_session_detail(session: str):
    """Get full session details including MCP call logs."""
    doc = frappe.get_doc("HDS AI Support Session", session)
    return doc.as_dict()


@frappe.whitelist()
@agent_only
def resume_session(session: str, agent_guidance: str = ""):
    """Resume a paused (Awaiting Review) session with optional agent guidance."""
    from helpdesk.session_manager import resume_investigation

    session_name = resume_investigation(str(session), agent_guidance or "")
    return {"session": session_name, "status": "resumed"}


@frappe.whitelist()
@agent_only
def cancel_session(session: str):
    """Cancel a paused session permanently."""
    doc = frappe.get_doc("HDS AI Support Session", str(session))
    if doc.status not in ("Awaiting Review", "Active"):
        frappe.throw("Cannot cancel a session in status '%s'" % doc.status)
    doc.status = "Cancelled"
    doc.ended_at = frappe.utils.now_datetime()
    doc.conversation_state = ""
    doc.save(ignore_permissions=True)
    return {"status": "cancelled"}


@frappe.whitelist()
@agent_only
def get_pending_actions(ticket: str | int):
    """Get pending action requests for a ticket."""
    ticket = str(ticket)
    return frappe.get_list(
        "HDS Support Action Request",
        filters={"ticket": ticket, "status": "Pending Approval"},
        fields=["name", "status", "diagnosis", "session"],
        order_by="creation desc",
    )


@frappe.whitelist()
@agent_only
def get_connections():
    """Get all support connections."""
    return frappe.get_list(
        "HDS Support Connection",
        fields=["name", "customer_name", "site_url", "connection_status"],
        order_by="customer_name asc",
    )


@frappe.whitelist()
@agent_manager_only
def get_login_url(connection: str, ticket: str | int | None = None):
    """Get a one-time login URL for a customer site.

    Calls the customer's generate_login_url API via MCP credentials.
    Logs every attempt (success or failure) to HDS Site Login Log.

    Auth gate: caller must be logged in and have read on HDS Support
    Connection (Agent or System Manager). User Permission filtering on
    the customer_name Link is bypassed here so agents are not blocked
    from sites whose HD Customer they aren't directly permissioned for -
    the action is audit-logged so misuse is traceable.
    """
    import requests
    from frappe.utils.password import get_decrypted_password

    connection = str(connection)
    conn = frappe.get_doc("HDS Support Connection", connection)

    if not conn.api_key or not conn.site_url:
        _log_login_attempt(connection, ticket, "Failed", "Connection not configured")
        frappe.throw(_("Connection not configured"))

    api_secret = get_decrypted_password(
        "HDS Support Connection", connection, "api_secret"
    )
    if not api_secret:
        _log_login_attempt(connection, ticket, "Failed", "API secret not found")
        frappe.throw(_("API secret not found for connection"))

    url = f"{conn.site_url}{conn.client_method('api.generate_login_url')}"

    try:
        response = requests.post(
            url,
            headers={"Authorization": "Token %s:%s" % (conn.api_key, api_secret)},
            timeout=15,
        )
        if response.status_code != 200:
            _log_login_attempt(
                connection,
                ticket,
                "Failed",
                "HTTP %d: %s" % (response.status_code, response.text[:150]),
            )
            frappe.throw("Failed to generate login URL: %s" % response.text[:200])

        data = response.json().get("message", {})
        login_url = data.get("login_url")

        # Structured audit log
        _log_login_attempt(connection, ticket, "Success", "")

        return {"login_url": login_url, "site_url": conn.site_url}

    except requests.Timeout:
        _log_login_attempt(connection, ticket, "Failed", "Timeout")
        frappe.throw(_("Customer site unreachable (timeout)"))
    except requests.ConnectionError as e:
        _log_login_attempt(
            connection, ticket, "Failed", "Connection error: %s" % str(e)[:100]
        )
        frappe.throw("Cannot connect to customer site: %s" % str(e)[:100])


def _log_login_attempt(connection, ticket, status, error_message, event_type="Login"):
    """Insert a HDS Site Login Log entry."""
    try:
        frappe.get_doc(
            {
                "doctype": "HDS Site Login Log",
                "agent": frappe.session.user,
                "connection": connection,
                "ticket": str(ticket) if ticket else None,
                "status": status,
                "event_type": event_type,
                "error_message": error_message or "",
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error("Failed to write login log")


@frappe.whitelist()
@agent_manager_only
def get_remote_audit_log(
    connection: str,
    action_type: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    limit: int = 100,
):
    """Return audit log entries for a connection.

    Entries are written directly by the Hub after every MCP call (see mcp_client._log_audit).
    """
    connection = str(connection)
    filters = {"connection": connection}
    if action_type:
        filters["action_type"] = action_type
    if tool_name:
        filters["tool_name"] = tool_name
    if status:
        filters["status"] = status

    entries = frappe.get_list(
        "HDS Remote Audit Log",
        filters=filters,
        fields=[
            "name",
            "timestamp",
            "tool_name",
            "action_type",
            "status",
            "arguments",
            "result_summary",
            "error_message",
            "execution_time_ms",
            "session_id",
        ],
        order_by="timestamp desc",
        limit_page_length=int(limit),
    )

    return {"entries": entries}


@frappe.whitelist()
def view_connection_credentials(connection: str):
    """Return decrypted credentials + ready-to-paste client configs.

    System Manager only. Every access is audit-logged.
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        _log_login_attempt(
            connection,
            None,
            "Failed",
            "Not a System Manager",
            event_type="Credential View",
        )
        frappe.throw(
            _("Only System Managers can view credentials"), frappe.PermissionError
        )

    from frappe.utils.password import get_decrypted_password

    connection = str(connection)
    conn = frappe.get_doc("HDS Support Connection", connection)

    if not conn.api_key:
        _log_login_attempt(
            connection,
            None,
            "Failed",
            "No API key on connection",
            event_type="Credential View",
        )
        frappe.throw(_("No API key set on this connection"))

    api_secret = get_decrypted_password(
        "HDS Support Connection", connection, "api_secret", raise_exception=False
    )
    if not api_secret:
        _log_login_attempt(
            connection,
            None,
            "Failed",
            "No API secret on connection",
            event_type="Credential View",
        )
        frappe.throw(_("No API secret set on this connection"))

    # Build a Claude Desktop config snippet
    mcp_url = f"{conn.site_url}{conn.client_method('mcp.handler.handle')}"

    slug = (conn.customer_name or conn.name).lower().replace(" ", "-").replace(".", "-")
    desktop_args = [
        "C:\\\\Users\\\\<YOUR_USER>\\\\AppData\\\\Roaming\\\\npm\\\\node_modules\\\\mcp-remote\\\\dist\\\\proxy.js",
        mcp_url,
        "--header",
        "Authorization: Token %s:%s" % (conn.api_key, api_secret),
    ]
    if conn.site_url.startswith("http://"):
        desktop_args.append("--allow-http")

    import json

    desktop_config = json.dumps(
        {
            "mcpServers": {
                slug: {
                    "command": "node",
                    "args": desktop_args,
                }
            }
        },
        indent=2,
    )

    # Audit log BEFORE returning credentials
    _log_login_attempt(connection, None, "Success", "", event_type="Credential View")

    return {
        "api_key": conn.api_key,
        "api_secret": api_secret,
        "token": "%s:%s" % (conn.api_key, api_secret),
        "site_url": conn.site_url,
        "mcp_url": mcp_url,
        "desktop_config": desktop_config,
    }


@frappe.whitelist()
@agent_only
def get_action_request_detail(action_request: str):
    """Get full action request details including proposed actions."""
    doc = frappe.get_doc("HDS Support Action Request", str(action_request))
    return doc.as_dict()


@frappe.whitelist()
@agent_manager_only
def approve_and_execute(
    action_request: str,
    approved_indices: str | list | None = None,
    execute: bool = True,
):
    """Approve actions and optionally execute them.

    Args:
            action_request: HDS Support Action Request name
            approved_indices: JSON list of indices to approve (0-based). None = approve all.
            execute: Whether to execute immediately after approval
    """
    from helpdesk.approval import approve_actions, execute_approved_actions

    action_request = str(action_request)

    if approved_indices and isinstance(approved_indices, str):
        import json

        approved_indices = json.loads(approved_indices)

    status = approve_actions(action_request, approved_indices)

    result = {"approval_status": status}

    if execute and status in ("Approved", "Partially Approved"):
        exec_result = execute_approved_actions(action_request)
        result["execution"] = exec_result

    return result


@frappe.whitelist()
@agent_manager_only
def reject_action_request(action_request: str):
    """Reject all actions in an action request."""
    from helpdesk.approval import reject_actions

    return {"status": reject_actions(str(action_request))}


def _call_client(conn, connection_name, path: str, payload: dict | None = None) -> dict:
    """Helper: POST to a customer site endpoint with Token auth from the Connection."""
    import requests
    from frappe.utils.password import get_decrypted_password

    if not conn.api_key:
        frappe.throw(_("API Key is missing on this connection."))
    api_secret = get_decrypted_password(
        "HDS Support Connection", connection_name, "api_secret", raise_exception=False
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


LEGACY_SUPPORT_USER = "support@quarkcs.com"
PAIRING_CODE_HOURS = 24
PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread


@frappe.whitelist()
def register_client(connection: str):
    """Hub-initiated connection handshake, for a Connection whose API keys were pasted in.

    A connection code (create_pairing_code / pair_client) does the same without
    anyone copying keys. This call uses Token auth (api_key:api_secret) against
    the customer site; it records the Hub URL + client_id there and marks this
    Connection as Connected here.
    """
    frappe.only_for("System Manager")
    conn = frappe.get_doc("HDS Support Connection", connection)
    return _register(conn)


def _register(conn) -> dict:
    from frappe.utils import get_url

    if not conn.site_url:
        _log_login_attempt(
            conn.name, None, "Failed", "Site URL missing", event_type="Register"
        )
        frappe.throw(_("Site URL is required on the connection"))

    try:
        result = _call_client(
            conn,
            conn.name,
            conn.client_method("api.register_connection"),
            {"hub_url": get_url(), "client_id": conn.name},
        )
    except Exception as e:
        _log_login_attempt(
            conn.name, None, "Failed", str(e)[:200], event_type="Register"
        )
        raise

    conn.connection_status = "Connected"
    conn.mcp_client_installed = 1
    conn.last_token_update = frappe.utils.now_datetime()
    # older clients don't report it; they all used the original support user
    conn.support_user = (
        result.get("support_user") or conn.support_user or LEGACY_SUPPORT_USER
    )
    conn.save(ignore_permissions=True)

    _log_login_attempt(conn.name, None, "Success", "", event_type="Register")

    return {
        "status": "registered",
        "connection": conn.name,
        "site": result.get("site"),
    }


def _hash_code(code: str) -> str:
    import hashlib

    cleaned = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return hashlib.sha256(cleaned.encode()).hexdigest()


@frappe.whitelist()
def create_pairing_code(connection: str) -> dict:
    """A one-time code the customer's admin enters in their ERP to connect it, instead of copying API keys."""
    import secrets

    # only_for is skipped while testing, so check the role directly
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            _("Only System Managers can create connection codes."),
            frappe.PermissionError,
        )
    conn = frappe.get_doc("HDS Support Connection", connection)
    if not conn.site_url:
        frappe.throw(_("Save the customer's Site URL first."))
    raw = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(10))
    code = f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"
    expires = frappe.utils.add_to_date(
        frappe.utils.now_datetime(), hours=PAIRING_CODE_HOURS
    )
    conn.db_set(
        {"pairing_code_hash": _hash_code(code), "pairing_code_expires": expires}
    )
    return {"code": code, "expires": str(expires), "site_url": conn.site_url}


@frappe.whitelist(  # the customer site isn't a hub user yet; the one-time code is the credential - nosemgrep
    allow_guest=True, methods=["POST"]
)
@rate_limit(limit=10, seconds=60 * 60)
def pair_client(
    code: str,
    site_url: str,
    api_key: str,
    api_secret: str,
    client_app: str = "helpdesk_client",
    support_user: str = "",
) -> dict:
    """Called by the customer site with a connection code and the API key it just made for the hub.

    The code must be unused, unexpired and issued for this site URL; the hub then
    runs the normal registration against that URL to prove the key works.
    """
    from helpdesk.utils import normalize_site_url

    invalid = _(
        "This connection code is invalid or has expired. Ask TBO Support for a new one."
    )
    name = frappe.db.get_value(
        "HDS Support Connection", {"pairing_code_hash": _hash_code(code)}, "name"
    )
    if not name:
        frappe.throw(invalid, frappe.AuthenticationError)
    conn = frappe.get_doc("HDS Support Connection", name)
    if (
        not conn.pairing_code_expires
        or frappe.utils.get_datetime(conn.pairing_code_expires)
        < frappe.utils.now_datetime()
    ):
        frappe.throw(invalid, frappe.AuthenticationError)
    if normalize_site_url(site_url) != normalize_site_url(conn.site_url):
        frappe.throw(
            _("This code was issued for {0}, not {1}.").format(conn.site_url, site_url),
            frappe.AuthenticationError,
        )
    if not api_key or not api_secret:
        frappe.throw(_("The customer site didn't send an API key."))

    conn.api_key = api_key
    conn.api_secret = api_secret
    conn.client_app = client_app or conn.client_app
    conn.support_user = support_user or conn.support_user
    conn.pairing_code_hash = None
    conn.pairing_code_expires = None
    conn.save(ignore_permissions=True)
    result = _register(conn)
    return {"status": "connected", "connection": result["connection"]}


@frappe.whitelist()
def rotate_credentials(connection: str):
    """Hub-initiated credential rotation.

    The Hub generates a new api_key + api_secret, calls the customer site
    with the CURRENT credentials (Token auth), and on success swaps its
    stored credentials to the new ones.
    """
    frappe.only_for("System Manager")
    conn = frappe.get_doc("HDS Support Connection", connection)
    if not conn.site_url:
        _log_login_attempt(
            connection,
            None,
            "Failed",
            "Site URL missing",
            event_type="Rotate Credentials",
        )
        frappe.throw(_("Site URL is required"))

    new_api_key = frappe.generate_hash(length=15)
    new_api_secret = frappe.generate_hash(length=15)

    try:
        # Call customer site with CURRENT credentials (before swapping).
        _call_client(
            conn,
            connection,
            conn.client_method("api.rotate_credentials"),
            {"new_api_key": new_api_key, "new_api_secret": new_api_secret},
        )
    except Exception as e:
        _log_login_attempt(
            connection, None, "Failed", str(e)[:200], event_type="Rotate Credentials"
        )
        raise

    # Swap stored credentials. save() encrypts the Password field.
    conn.api_key = new_api_key
    conn.api_secret = new_api_secret
    conn.last_token_update = frappe.utils.now_datetime()
    conn.save(ignore_permissions=True)
    frappe.db.commit()  # the customer site already switched credentials; losing them would lock us out - nosemgrep

    _log_login_attempt(connection, None, "Success", "", event_type="Rotate Credentials")

    return {"status": "rotated", "connection": connection}


@frappe.whitelist()
def deregister_client(connection: str):
    """Hub-initiated deregistration.

    Calls the customer site (Token auth) to clear its client_id/contract_active,
    then marks this Connection as Disconnected. Does NOT revoke the api_key on
    the customer site - the customer admin controls that via User -> API Access.
    """
    frappe.only_for("System Manager")
    conn = frappe.get_doc("HDS Support Connection", connection)
    if not conn.site_url:
        _log_login_attempt(
            connection, None, "Failed", "Site URL missing", event_type="Deregister"
        )
        frappe.throw(_("Site URL is required"))

    try:
        _call_client(
            conn,
            connection,
            conn.client_method("api.deregister"),
            {},
        )
    except Exception as e:
        _log_login_attempt(
            connection, None, "Failed", str(e)[:200], event_type="Deregister"
        )
        raise

    conn.connection_status = "Disconnected"
    conn.save(ignore_permissions=True)

    _log_login_attempt(connection, None, "Success", "", event_type="Deregister")

    return {"status": "deregistered", "connection": connection}


@frappe.whitelist(  # a customer site saying "check me now"; it carries no data and only queues our own pull - nosemgrep
    allow_guest=True, methods=["POST"]
)
@rate_limit(limit=60, seconds=60)
def ticket_raised(client_id: str) -> dict:
    """Pull that site's new tickets right away instead of waiting for the next scheduled run.

    Answers the same whether or not the connection exists, so it can't be used
    to discover connection names.
    """
    from helpdesk.ticket_puller import PULLABLE_STATUSES

    status = frappe.db.get_value(
        "HDS Support Connection", client_id, "connection_status"
    )
    if status in PULLABLE_STATUSES:
        frappe.enqueue(
            "helpdesk.ticket_puller.pull_connection",
            connection=client_id,
            queue="short",
            job_id=f"pull-client-tickets-{client_id}",
            deduplicate=True,
            enqueue_after_commit=True,
        )
    return {"ok": True}
