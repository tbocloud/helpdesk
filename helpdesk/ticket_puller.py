# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Pull Pending Support Tickets from customer sites over MCP and turn them
into HD Tickets.

The customer site holds no credentials. Every call originates here, using
the per-connection API key stored on the Hub's HDS Support Connection —
the only place a credential belongs.
"""

import hashlib
import json

import frappe
import requests

from helpdesk.automation import automation_user
from helpdesk.mcp_client import MCPClient
from helpdesk.session_replay import is_diagnostics_file, is_replay_file

PULL_LIMIT = 20
RECORDING_TIMEOUT = 60
MAX_RECORDING_BYTES = 100 * 1024 * 1024


def _unwrap(result: dict):
    """MCP tool results arrive as {"content": [{"type": "text", "text": "<json>"}]}."""
    if not result or result.get("isError"):
        raise ValueError("MCP call failed: %s" % result)

    for block in result.get("content", []):
        if block.get("type") == "text":
            return json.loads(block["text"])

    return None


def _pending_tickets(mcp: MCPClient) -> list[dict]:
    """Fetch tickets the customer has raised but we have not imported."""
    result = mcp.call_tool(
        "get_list",
        {
            "doctype": "Support Ticket",
            "filters": {"status": "Pending"},
            "fields": [
                "name",
                "subject",
                "description",
                "raised_by",
                "screen_recording",
                "creation",
            ],
            "limit": PULL_LIMIT,
        },
    )
    return _unwrap(result) or []


def _ticket_files(mcp: MCPClient, ticket_name: str) -> list[dict]:
    """All files the customer attached to the ticket (recording, screenshots).

    Falls back to an empty list if the customer blocks the File doctype in
    their MCP access control — the ticket still imports, just without media.
    """
    try:
        result = mcp.call_tool(
            "get_list",
            {
                "doctype": "File",
                "filters": {
                    "attached_to_doctype": "Support Ticket",
                    "attached_to_name": ticket_name,
                },
                "fields": ["file_url", "file_name"],
                "limit": 20,
            },
        )
        return _unwrap(result) or []
    except Exception:
        frappe.log_error(
            title=f"File listing failed for {ticket_name}",
            message=frappe.get_traceback(),
        )
        return []


def _already_imported(connection_name: str, client_ticket: str) -> bool:
    """Guard against re-importing when a previous push-back failed.

    If we created the HD Ticket but could not write the status back, the
    client ticket stays Pending and we would otherwise import it again on
    the next cycle.
    """
    return bool(
        frappe.db.exists(
            "HD Ticket",
            {
                "custom_qcs_connection": connection_name,
                "custom_client_ticket": client_ticket,
            },
        )
    )


def _create_hd_ticket(connection_name: str, customer: str, ticket: dict) -> str:
    """Create the Helpdesk ticket for a pulled customer request.

    AI triage fires automatically from the HD Ticket after_insert hook
    (see hooks.py doc_events) — do not enqueue it again here.
    """
    hd = frappe.get_doc(
        {
            "doctype": "HD Ticket",
            "subject": ticket.get("subject") or "Support request",
            "description": ticket.get("description") or "",
            "customer": customer,
            "raised_by": ticket.get("raised_by"),
            "via_customer_portal": 1,
        }
    ).insert(ignore_permissions=True)

    frappe.db.set_value(
        "HD Ticket",
        hd.name,
        {
            "custom_qcs_connection": connection_name,
            "custom_client_ticket": ticket.get("name"),
        },
        update_modified=False,
    )

    return hd.name


def _attach_recording(
    mcp: MCPClient,
    hd_ticket_name: str,
    file_url: str | None,
    file_name: str | None = None,
) -> str | None:
    """Download the customer's screen recording and attach it to the HD Ticket.

    The recording is a private File on the customer's site. We already hold
    that site's API key on the connection, so this is a plain authenticated
    GET — no new MCP tool required, and nothing is uploaded by the client.

    `file_name` is the customer File's name; its URL may carry a suffix Frappe
    added to keep the stored path unique (session-replay.json3f2a1c.gz).
    """
    if not file_url:
        return None

    response = requests.get(
        f"{mcp.site_url.rstrip('/')}{file_url}",
        headers={"Authorization": f"token {mcp.api_key}:{mcp.api_secret}"},
        timeout=RECORDING_TIMEOUT,
        stream=True,
    )
    response.raise_for_status()

    content = response.raw.read(MAX_RECORDING_BYTES + 1, decode_content=True)
    if len(content) > MAX_RECORDING_BYTES:
        frappe.log_error(
            title=f"Recording too large for {hd_ticket_name}",
            message=f"{file_url} exceeded {MAX_RECORDING_BYTES} bytes; not attached",
        )
        return None

    file_name = file_name or file_url.rsplit("/", 1)[-1]
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": "HD Ticket",
            "attached_to_name": hd_ticket_name,
            "is_private": 1,
            "content": content,
        }
    ).insert(ignore_permissions=True)
    _keep_file_name(file_doc, file_name)

    note = _media_note(file_doc)
    if note:
        # Surface the file inside the Helpdesk agent UI. The agent portal renders
        # its own HD Ticket Comment doctype — a core frappe Comment only shows in
        # the desk view, which agents never open.
        comment = frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": hd_ticket_name,
                "commented_by": automation_user(),
                "content": note,
            }
        )
        comment.flags.skip_notifications = True
        comment.insert(ignore_permissions=True)

    return file_doc.name


def _keep_file_name(file_doc, file_name: str) -> None:
    """Restore the customer's file name when Frappe suffixed it for a unique path.

    The session replay card finds files by name, and the conversation sync
    recognises files it already imported by name; only the stored path needs
    to be unique.
    """
    if file_doc.file_name == file_name:
        return
    frappe.db.set_value(
        "File", file_doc.name, "file_name", file_name, update_modified=False
    )
    file_doc.file_name = file_name


def _media_note(file_doc) -> str | None:
    """The ticket comment announcing an attached file, or None to stay quiet.

    Session replay files are machine data the agent opens from the ticket's
    Session replay card; links to raw .json/.gz files would only be noise.
    """
    if is_diagnostics_file(file_doc.file_name):
        return None
    if is_replay_file(file_doc.file_name):
        return "\N{FILM FRAMES} Session replay attached: see the Session replay card on this ticket."

    is_video = file_doc.file_name.rsplit(".", 1)[-1].lower() in (
        "webm",
        "mp4",
        "mov",
        "mkv",
    )
    label = "Screen recording" if is_video else "Screenshot"
    icon = "\N{VIDEO CAMERA}" if is_video else "\N{FRAME WITH PICTURE}"
    return (
        f"{icon} {label} from the customer: "
        f'<a href="{file_doc.file_url}" target="_blank">{file_doc.file_name}</a>'
    )


def _push_back(mcp: MCPClient, client_ticket: str, values: dict) -> None:
    """Write status/ID/triage back onto the customer's local Support Ticket.

    Raises when the customer site refuses the write (writes disabled there, a
    value its Select does not accept, ...): a refused update used to count as
    a success, so the customer's ticket stayed "Pending" with no hub number.
    """
    result = mcp.call_tool(
        "set_values",
        {
            "doctype": "Support Ticket",
            "name": client_ticket,
            "values": values,
        },
    )
    _raise_if_refused(result, f"update of {client_ticket}")


def _raise_if_refused(result: dict, what: str) -> None:
    """MCP reports a refused tool call as a normal result with isError set."""
    if not result or result.get("isError"):
        content = ""
        if result and result.get("content"):
            content = result["content"][0].get("text", "")
        raise ValueError(f"Customer site refused the {what}: {content[:300]}")


def _log_once(title: str, key: str, seconds: int = 3600) -> None:
    """Log an error at most once an hour per key: a refused write-back repeats every run."""
    cache = frappe.cache()
    if cache.get_value(key):
        return
    cache.set_value(key, 1, expires_in_sec=seconds)
    frappe.log_error(title=title, message=frappe.get_traceback())


# The customer app's Support Ticket status Select; any other hub label would
# make the whole update fail, ticket number included.
CLIENT_STATUSES = ("Pending", "Open", "Replied", "Paused", "Resolved", "Closed")
CATEGORY_TO_CLIENT_STATUS = {"Open": "Open", "Paused": "Paused", "Resolved": "Resolved"}


def client_status_for(status: str) -> str | None:
    """The customer-side status label for a hub status, or None when there is none."""
    if status in CLIENT_STATUSES:
        return status
    category = frappe.get_cached_value("HD Ticket Status", status, "category") or ""
    return CATEGORY_TO_CLIENT_STATUS.get(category)


# "Error" is retried every run so a brief outage on the customer site (e.g. during
# its own update) doesn't stop tickets for the rest of the day
PULLABLE_STATUSES = ("Connected", "Error")


def pull_client_tickets() -> int:
    """Scheduled: turn Pending client tickets into HD Tickets."""
    connections = frappe.get_all(
        "HDS Support Connection",
        filters={"connection_status": ("in", PULLABLE_STATUSES)},
        fields=["name", "customer_name"],
    )
    return sum(pull_connection(conn.name, conn.customer_name) for conn in connections)


# A pull can take a minute on a slow site; a lock older than this is stale
PULL_LOCK_SECONDS = 300


def pull_connection(connection: str, customer_name: str | None = None) -> int:
    """Import one customer site's Pending tickets; also used right after the site pings us.

    Only one pull per site runs at a time: the site's ping and the scheduled
    pull can start in the same minute, and without the lock both passed the
    "already imported" check and every ticket was imported twice.
    """
    if frappe.session.user == "Guest":
        # queued by the customer site's ping, which is a guest request; the
        # import must run as the hub's own user or every permission check fails
        frappe.set_user(automation_user())
    if customer_name is None:
        customer_name = frappe.db.get_value(
            "HDS Support Connection", connection, "customer_name"
        )
    lock_key = f"hds_pull_lock:{connection}"
    # site-prefixed like delete_value() below, so the release matches (as in triage.py)
    if not frappe.cache.set(
        frappe.cache.make_key(lock_key), 1, nx=True, ex=PULL_LOCK_SECONDS
    ):
        return 0
    try:
        return _pull_connection(connection, customer_name)
    finally:
        frappe.cache.delete_value(lock_key)


def _pull_connection(connection: str, customer_name: str | None) -> int:
    try:
        mcp = MCPClient(connection)
        tickets = _pending_tickets(mcp)
    except Exception as e:
        frappe.log_error(
            title=f"Ticket pull failed for {connection}",
            message=frappe.get_traceback(),
        )
        _set_connection_health(connection, error=str(e)[:500])
        return 0
    _set_connection_health(connection)

    created = 0
    for ticket in tickets:
        try:
            if _already_imported(connection, ticket["name"]):
                # HD Ticket exists; the previous push-back must have failed.
                try:
                    _push_back(mcp, ticket["name"], {"status": "Open"})
                except Exception:
                    _log_once(
                        f"Status push-back refused for {ticket.get('name')}",
                        f"hds_pushback_refused:{connection}:{ticket.get('name')}",
                    )
                continue

            hd_name = _create_hd_ticket(connection, customer_name, ticket)

            # Media is nice-to-have; never let a fetch failure (403,
            # timeout, ...) block the ticket import — that would retry
            # the same ticket every cycle forever.
            files = _ticket_files(mcp, ticket["name"])
            if not files and ticket.get("screen_recording"):
                # older clients that don't attach files to the ticket
                files = [{"file_url": ticket["screen_recording"]}]
            for f in files:
                try:
                    _attach_recording(
                        mcp, hd_name, f.get("file_url"), f.get("file_name")
                    )
                except Exception:
                    frappe.log_error(
                        title=f"Media attach failed for {ticket.get('name')}",
                        message=frappe.get_traceback(),
                    )
            frappe.db.commit()  # keep each imported ticket even if a later one fails - nosemgrep

            _push_back(mcp, ticket["name"], {"ticket_id": hd_name, "status": "Open"})
            created += 1
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"Ticket import failed for {ticket.get('name')}",
                message=frappe.get_traceback(),
            )

    return created


def _set_connection_health(connection: str, error: str | None = None):
    status = "Error" if error else "Connected"
    current = frappe.db.get_value(
        "HDS Support Connection",
        connection,
        ["connection_status", "last_error"],
        as_dict=True,
    )
    if current and (current.connection_status, current.last_error or "") == (
        status,
        error or "",
    ):
        return
    frappe.db.set_value(
        "HDS Support Connection",
        connection,
        {"connection_status": status, "last_error": error or ""},
        update_modified=False,
    )


def _status_payload(row) -> dict:
    """What the customer's ticket should show for this hub ticket."""
    values = {
        "priority": row.priority or "",
        # keeps the customer's "TBO #" right if the hub ticket
        # was restored under a new number
        "ticket_id": row.name,
    }
    status = client_status_for(row.status)
    if status:
        values["status"] = status
    return values


def _payload_hash(values: dict) -> str:
    return hashlib.sha1(json.dumps(values, sort_keys=True).encode()).hexdigest()


def push_ticket_statuses() -> int:
    """Scheduled: mirror HD Ticket status onto the customer's local tickets.

    Only tickets whose payload changed since the last successful push are
    sent (custom_client_push_hash remembers it), so a quiet hub makes no
    writes on customer sites instead of 200 every five minutes.
    """
    rows = frappe.get_all(
        "HD Ticket",
        filters={
            "custom_client_ticket": ["is", "set"],
            "custom_qcs_connection": ["is", "set"],
        },
        fields=[
            "name",
            "status",
            "priority",
            "custom_client_ticket",
            "custom_qcs_connection",
            "custom_client_push_hash",
        ],
        order_by="modified desc",
    )

    by_connection = {}
    for row in rows:
        values = _status_payload(row)
        digest = _payload_hash(values)
        if digest == (row.custom_client_push_hash or ""):
            continue
        by_connection.setdefault(row.custom_qcs_connection, []).append((row, values, digest))

    pushed = 0
    for connection_name, tickets in by_connection.items():
        try:
            mcp = MCPClient(connection_name)
        except Exception:
            frappe.log_error(
                title=f"Status push failed for {connection_name}",
                message=frappe.get_traceback(),
            )
            continue

        for row, values, digest in tickets:
            try:
                _push_back(mcp, row.custom_client_ticket, values)
                frappe.db.set_value(
                    "HD Ticket",
                    row.name,
                    "custom_client_push_hash",
                    digest,
                    update_modified=False,
                )
                pushed += 1
            except Exception:
                _log_once(
                    f"Status push failed for {row.name}",
                    f"hds_status_push_failed:{row.name}",
                )

    return pushed


def _load_conv_state(raw) -> dict:
    """Synced-record bookkeeping; a damaged value starts over instead of stopping the sync."""
    try:
        state = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def sync_conversations() -> int:
    """Scheduled: two-way conversation + client close requests, per linked ticket.

    - Client comments (not authored by the support user) become HD Ticket
      Comments so agents see the customer's replies.
    - Agent replies (Sent Communications on the HD Ticket) are pushed to the
      client as support-user comments; the client notifies the reporter.
    - close_requested on the client closes the HD Ticket; the status push
      mirrors Closed back, confirming to the user.

    Idempotency: synced record names are tracked in custom_sync_state.
    """
    rows = frappe.get_all(
        "HD Ticket",
        filters={
            "custom_client_ticket": ["is", "set"],
            "custom_qcs_connection": ["is", "set"],
            "status": ["!=", "Closed"],
        },
        fields=[
            "name",
            "custom_client_ticket",
            "custom_qcs_connection",
            "custom_conv_state",
            "custom_sync_state",
        ],
        limit=100,
    )
    by_conn = {}
    for r in rows:
        by_conn.setdefault(r.custom_qcs_connection, []).append(r)

    synced = 0
    for conn_name, tickets in by_conn.items():
        # comments the hub itself wrote on the customer site aren't pulled back
        support_user = (
            frappe.db.get_value("HDS Support Connection", conn_name, "support_user")
            or "support@quarkcs.com"
        )
        try:
            mcp = MCPClient(conn_name)
        except Exception:
            frappe.log_error(
                title=f"Conversation sync failed for {conn_name}",
                message=frappe.get_traceback(),
            )
            continue

        for row in tickets:
            try:
                # older tickets kept the state in custom_conv_state
                state = _load_conv_state(row.custom_sync_state or row.custom_conv_state)
                state.setdefault("client", [])
                state.setdefault("hub", [])
                ct = row.custom_client_ticket

                # client -> hub: customer comments
                comments = (
                    _unwrap(
                        mcp.call_tool(
                            "get_list",
                            {
                                "doctype": "Comment",
                                "filters": {
                                    "reference_doctype": "Support Ticket",
                                    "reference_name": ct,
                                    "comment_type": "Comment",
                                },
                                "fields": ["name", "content", "owner"],
                                "limit": 50,
                            },
                        )
                    )
                    or []
                )
                for c in comments:
                    if c["name"] in state["client"] or c.get("owner") == support_user:
                        continue
                    # the customer's own words relayed from their ERP: not the
                    # hub's work, so not credited to the automation user
                    hd_comment = frappe.get_doc(
                        {
                            "doctype": "HD Ticket Comment",
                            "reference_ticket": row.name,
                            "commented_by": "Administrator",
                            "content": "\N{SPEECH BALLOON} Customer (%s): %s"
                            % (c.get("owner"), c.get("content") or ""),
                        }
                    )
                    hd_comment.flags.skip_notifications = True
                    hd_comment.insert(ignore_permissions=True)
                    state["client"].append(c["name"])
                    synced += 1
                # MCPClient commits after every call it audits, so anything
                # written above outlives a rollback; record it now, or a later
                # failure in this ticket would re-import the same comments.
                _save_sync_state(row.name, state)

                # hub -> client: agent replies (sent communications)
                replies = frappe.get_all(
                    "Communication",
                    filters={
                        "reference_doctype": "HD Ticket",
                        "reference_name": row.name,
                        "communication_type": "Communication",
                        "sent_or_received": "Sent",
                    },
                    fields=["name", "content"],
                    limit=50,
                )
                for m in replies:
                    if m.name in state["hub"]:
                        continue
                    result = mcp.call_tool(
                        "create_doc",
                        {
                            "doctype": "Comment",
                            "values": {
                                "comment_type": "Comment",
                                "reference_doctype": "Support Ticket",
                                "reference_name": ct,
                                "content": m.content or "",
                            },
                        },
                    )
                    # a refused reply is retried next run, never marked as sent
                    _raise_if_refused(result, f"reply {m.name}")
                    state["hub"].append(m.name)
                    _save_sync_state(row.name, state)
                    synced += 1

                # new files attached to the client ticket after import
                # (e.g. a follow-up recording or screenshot on a reply)
                state.setdefault("files", [])
                for f in _ticket_files(mcp, ct):
                    url = f.get("file_url")
                    if not url or url in state["files"]:
                        continue
                    fname = f.get("file_name") or url.rsplit("/", 1)[-1]
                    if frappe.db.exists(
                        "File",
                        {
                            "attached_to_doctype": "HD Ticket",
                            "attached_to_name": row.name,
                            "file_name": fname,
                        },
                    ):
                        state["files"].append(url)  # imported at creation
                        continue
                    attached = _attach_recording(mcp, row.name, url, fname)
                    state["files"].append(url)
                    synced += 1
                    if attached and is_replay_file(fname):
                        from helpdesk.triage import retriage_with_session_replay

                        retriage_with_session_replay(row.name)

                # client close request?
                req = (
                    _unwrap(
                        mcp.call_tool(
                            "get_list",
                            {
                                "doctype": "Support Ticket",
                                "filters": {"name": ct, "close_requested": 1},
                                "fields": ["name"],
                                "limit": 1,
                            },
                        )
                    )
                    or []
                )
                if req:
                    _close_ticket(row.name)

                _save_sync_state(row.name, state)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                _log_once(
                    f"Conversation sync failed for {row.name}",
                    f"hds_conversation_sync_failed:{row.name}",
                )
    return synced


def _save_sync_state(ticket: str, state: dict) -> None:
    frappe.db.set_value(
        "HD Ticket",
        ticket,
        "custom_sync_state",
        json.dumps(state),
        update_modified=False,
    )


def _close_ticket(ticket: str) -> None:
    """Close through the controller, so the status category, SLA and hooks follow."""
    doc = frappe.get_doc("HD Ticket", ticket)
    if doc.status == "Closed":
        return
    doc.status = "Closed"
    doc.save(ignore_permissions=True)
