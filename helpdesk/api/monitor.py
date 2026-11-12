# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The monitor API (Phase 18): the watcher server opens and resolves alerts, files follow-up
tasks, sends its heartbeat and reads the hub's self-check. Phase 19 adds auto-repair: the
switch, one record per repair, and repairs that wait for an approver. Callers hold the role TBO
Monitor (API only, made on migrate) and an API key (helpdesk.monitor, helpdesk.repairs)."""

import json

import frappe
from frappe import _
from frappe.utils import sbool

from helpdesk import monitor, repairs
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


# --- auto-repair (Phase 19) ----------------------------------------------------------------


@frappe.whitelist()
def repair_policy() -> dict:
    """The switch, the runbooks turned off and the hourly cap; read every minute."""
    monitor.monitor_only()
    return repairs.policy()


@frappe.whitelist(methods=["POST"])
def repair_started(
    key: str,
    runbook: str,
    level: str = "Automatic",
    target: str = "",
    attempt: int = 1,
    evidence=None,
    action=None,
) -> dict:
    monitor.monitor_only()
    return repairs.started(
        key,
        runbook,
        level=level,
        target=target,
        attempt=int(attempt or 1),
        evidence=_json(evidence),
        action=_json(action),
    )


@frappe.whitelist(methods=["POST"])
def repair_finished(
    repair: str, outcome: str, text: str = "", verify=None, escalate=False
) -> dict:
    """The outcome; `escalate` gives the ticket to DevOps and tells the channel."""
    monitor.monitor_only()
    return repairs.finished(
        repair, outcome, text=text, verify=_json(verify), escalate=bool(sbool(escalate))
    )


@frappe.whitelist(methods=["POST"])
def request_repair(
    key: str,
    runbook: str,
    target: str,
    title: str,
    why: str = "",
    details: str = "",
    payload=None,
    risk: str = "normal",
) -> dict:
    """An approval-level repair: the card goes to an approver; the same ask returns the live one."""
    monitor.monitor_only()
    return repairs.request(
        key, runbook, target, title, why, details, _json(payload), risk=risk
    )


@frappe.whitelist()
def approved_repairs() -> list[dict]:
    """Repairs someone approved that the watcher has not run yet. `payload_hash` is the sha256
    of json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)."""
    monitor.monitor_only()
    return repairs.approved()


@frappe.whitelist(methods=["POST"])
def repair_executed(approval: str, ok, log: str = "") -> dict:
    monitor.monitor_only()
    return repairs.executed(approval, sbool(ok), log)
