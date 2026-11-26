# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Scheduled jobs for the TBO Support hub."""

import frappe
from frappe.utils import now_datetime

from helpdesk import client_api
from helpdesk.mcp_client import MCPClient

HEALTH_CHECKED_STATUSES = ("Connected", "Disconnected", "Error", "Unreachable")


def health_check_connections():
    """Daily: ping each customer MCP endpoint and update connection status. A site in
    an outage is checked once its backoff is over, like the per-minute pull."""
    from helpdesk.ticket_puller import due_connections

    for name in due_connections(HEALTH_CHECKED_STATUSES):
        conn = frappe.get_doc("HDS Support Connection", name)
        try:
            healthy = MCPClient(name).health_check()
            error = "" if healthy else "Health check failed: no tools returned"
            if healthy:
                client_api.refresh_capabilities(name)
        except Exception as e:
            error = str(e)
        conn.db_set("last_health_check", now_datetime(), update_modified=False)
        if error:
            conn.record_failure(error)
        else:
            conn.record_success()

    frappe.db.commit()  # scheduled job: keep each connection's health result even if a later one fails - nosemgrep


def retry_pending_triages():
    """Daily, and when an AI provider recovers (ai_engine.retry_failed_triages):
    re-enqueue failed/pending triages within the retry limit. The manual cooldown
    doesn't apply: a triage that failed seconds before the recovery must run too."""
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

            run_triage_now(str(ticket.name), ignore_cooldown=True)
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
    """Every minute: import Pending tickets from customer sites over MCP."""
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
