# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The monitor API (Phase 18): the watcher server opens and resolves alerts, files follow-up
tasks, sends its heartbeat and reads the hub's self-check. Callers hold the role TBO Monitor
(API only, made on migrate) and an API key (helpdesk.monitor)."""

import json

import frappe
from frappe import _

from helpdesk import monitor
from helpdesk.utils import is_agent


def _json(value):
    if isinstance(value, str) and value.strip()[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


@frappe.whitelist(methods=["POST"])
def alert(
    key: str,
    state: str,
    title: str = "",
    text: str = "",
    severity: str = "warning",
    evidence=None,
    runbook: str | None = None,
    source: str = "watcher",
) -> dict:
    """`state` open: the ticket for the key (one while it is open); resolved: the ticket is
    resolved by the monitor. Sending the same thing twice changes nothing."""
    monitor.monitor_only()
    return monitor.alert(
        key,
        state,
        title=title,
        text=text,
        severity=severity,
        evidence=_json(evidence),
        runbook=runbook,
        source=source[:40],
    )


@frappe.whitelist(methods=["POST"])
def followup(
    key: str, subject: str, details: str = "", priority: str = "Medium"
) -> dict:
    """A slow-burning issue: one task in the internal project per key while it is open."""
    monitor.monitor_only()
    return monitor.followup(key, subject, details=details, priority=priority)


@frappe.whitelist(methods=["POST"])
def heartbeat(source: str = "watcher") -> dict:
    monitor.monitor_only()
    return monitor.heartbeat(source)


@frappe.whitelist()
def self_check() -> dict:
    """The hub's own numbers, for the watcher (and for an agent who wants to look)."""
    if monitor.ROLE not in frappe.get_roles() and not is_agent():
        frappe.throw(
            _("Only a monitor or an agent may call this."), frappe.PermissionError
        )
    return monitor.self_check()
