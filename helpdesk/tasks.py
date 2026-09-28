# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Scheduled jobs for QCS Support Hub."""

import frappe
from frappe.utils import now_datetime

from helpdesk.mcp_client import MCPClient


def health_check_connections():
    """Daily: ping each customer MCP endpoint and update connection status."""
    connections = frappe.get_all(
        "HDS Support Connection",
        filters={"connection_status": ["in", ["Connected", "Disconnected", "Error"]]},
        fields=["name", "site_url", "customer_name"],
    )

    for conn in connections:
        try:
            mcp = MCPClient(conn.name)
            is_healthy = mcp.health_check()

            frappe.db.set_value(
                "HDS Support Connection",
                conn.name,
                {
                    "connection_status": "Connected" if is_healthy else "Error",
                    "last_health_check": now_datetime(),
                    "last_error": ""
                    if is_healthy
                    else "Health check failed: no tools returned",
                },
                update_modified=False,
            )

        except Exception as e:
            frappe.db.set_value(
                "HDS Support Connection",
                conn.name,
                {
                    "connection_status": "Error",
                    "last_health_check": now_datetime(),
                    "last_error": str(e)[:200],
                },
                update_modified=False,
            )

    frappe.db.commit()  # scheduled job: keep each connection's health result even if a later one fails - nosemgrep


def retry_pending_triages():
    """Daily: re-enqueue failed/pending triages within retry limit."""
    tickets = frappe.get_all(
        "HD Ticket",
        filters={
            "custom_triage_status": ["in", ["Pending", "Failed"]],
            "status": ["!=", "Closed"],
        },
        fields=["name"],
        limit=20,
    )

    for ticket in tickets:
        try:
            from helpdesk.triage import run_triage_now

            run_triage_now(str(ticket.name))
        except Exception:  # noqa: BLE001 - one ticket must not stop the rest
            frappe.log_error(
                title=f"Triage retry failed for {ticket.name}",
                message=frappe.get_traceback(),
            )


def sync_model_pricing():
    """Weekly: remind System Managers to review HDS Model Pricing older than 90 days.

    Anthropic does not publish a machine-readable price list, so this job does not
    fetch prices automatically. Rows never reviewed count as stale too.
    """
    from frappe.desk.doctype.notification_log.notification_log import (
        enqueue_create_notification,
    )
    from frappe.utils import add_days

    cutoff = add_days(now_datetime(), -90)
    stale = sorted(
        set(
            frappe.get_all(
                "HDS Model Pricing",
                filters={"is_active": 1, "last_synced_on": ["<", cutoff]},
                pluck="name",
            )
        )
        | set(
            frappe.get_all(
                "HDS Model Pricing",
                filters={"is_active": 1, "last_synced_on": ["is", "not set"]},
                pluck="name",
            )
        )
    )

    if not stale:
        return

    managers = [
        u
        for u in frappe.get_all(
            "Has Role",
            filters={
                "role": "System Manager",
                "parenttype": "User",
                "parent": ("not in", ["Administrator", "Guest"]),
            },
            pluck="parent",
        )
        if frappe.db.get_value("User", u, "enabled")
    ]
    message = (
        f"{len(stale)} AI model price(s) not reviewed in 90+ days: {', '.join(stale)}. "
        "Check the provider's pricing page and update 'Last Synced On'."
    )
    if not managers:
        frappe.log_error(title="HDS Model Pricing review due", message=message)
        return
    enqueue_create_notification(
        list(set(managers)),
        {
            "type": "Alert",
            "document_type": "HDS Model Pricing",
            "subject": message,
            "from_user": "Administrator",
        },
    )


def pull_client_tickets():
    """Every 5 min: import Pending tickets from customer sites over MCP."""
    from helpdesk.ticket_puller import pull_client_tickets as _pull

    return _pull()


def push_ticket_statuses():
    """Every 5 min: mirror HD Ticket status back onto customer sites."""
    from helpdesk.ticket_puller import push_ticket_statuses as _push

    return _push()


def sync_conversations():
    """Every 5 min: two-way comments + client close requests over MCP."""
    from helpdesk.ticket_puller import sync_conversations as _sync

    return _sync()
