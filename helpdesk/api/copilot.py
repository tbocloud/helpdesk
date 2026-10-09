# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot on the ticket page: start, see and cancel a run (agents); confirm or reopen (the customer)."""

import json

import frappe
from frappe import _
from frappe.utils import sbool

from helpdesk.api.customization import is_ticket_customer
from helpdesk.copilot import customer, runs
from helpdesk.utils import agent_only, is_agent


@frappe.whitelist(methods=["POST"])
@agent_only
def start_run(ticket: str | int) -> dict:
    """Queues a Copilot run for the ticket (or returns the active one)."""
    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    runs.start_run(str(ticket), actor=runs.AGENT)
    return get_run(ticket)


@frappe.whitelist(methods=["POST"])
@agent_only
def cancel_run(ticket: str | int) -> dict:
    frappe.has_permission("HD Ticket", "write", str(ticket), throw=True)
    run = runs.active_run(str(ticket))
    if run and run.state in runs.CANCELLABLE:
        runs.transition(run, "Cancelled", runs.AGENT, note=f"cancelled by {frappe.session.user}")
    return get_run(ticket)


@frappe.whitelist()
@agent_only
def get_run(ticket: str | int) -> dict:
    """The latest run on a ticket, for the Copilot dialog."""
    frappe.has_permission("HD Ticket", "read", str(ticket), throw=True)
    run = customer.latest_run(str(ticket))
    if not run:
        return {"run": None, "can_start": True}
    events = [
        {
            "creation": str(e.creation)[:19],
            "event_type": e.event_type,
            "actor": e.actor,
            "note": _event_note(e.payload),
        }
        for e in frappe.get_all(
            "HDS Copilot Event",
            filters={"run": run.name},
            fields=["creation", "event_type", "actor", "payload"],
            order_by="creation desc",
            limit=20,
        )
    ]
    return {
        "run": run.name,
        "kind": run.kind,
        "state": run.state,
        "stage": frappe.db.get_value("HD Ticket", run.ticket, "custom_copilot_stage"),
        "root_cause": run.root_cause_category,
        "confidence": run.confidence,
        "summary": run.summary,
        "customer_message": run.customer_message,
        "evidence": json.loads(run.evidence or "[]"),
        "task": run.task,
        "handed_over_to": run.handed_over_to,
        "failure_reason": run.failure_reason,
        "worker_id": run.worker_id,
        "lease_expires": str(run.lease_expires) if run.lease_expires else None,
        "queued_at": str(run.queued_at) if run.queued_at else None,
        "events": events,
        "can_cancel": run.state in runs.CANCELLABLE,
        "can_start": runs.active_run(run.ticket) is None,
    }


def _event_note(payload) -> str:
    try:
        data = json.loads(payload or "{}")
    except ValueError:
        return ""
    if data.get("to"):
        return f"{data.get('from') or '—'} → {data['to']}" + (f" ({data['note']})" if data.get("note") else "")
    if data.get("stage"):
        return f"{data['stage']}: {data.get('message', '')}"[:200]
    return (data.get("note") or data.get("tool") or "")[:200]


@frappe.whitelist()
def get_resolution(ticket: str | int) -> dict:
    """For the customer portal banner: whether the ticket waits for the customer's confirmation."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    stage = doc.get("custom_copilot_stage")
    confirmation = doc.get("custom_customer_confirmation")
    run = customer.latest_run(doc.name)
    return {
        "stage": stage,
        "confirmation": confirmation,
        "message": _stage_message(run) if run else "",
        "can_decide": bool(
            stage == "Resolved" and not confirmation and (is_agent() or is_ticket_customer(doc))
        ),
    }


def _stage_message(run) -> str:
    rows = frappe.get_all(
        "HDS Copilot Event",
        filters={"run": run.name, "event_type": "stage"},
        fields=["payload"],
        order_by="creation desc",
        limit=1,
    )
    if not rows:
        return ""
    try:
        return json.loads(rows[0].payload or "{}").get("message", "")
    except ValueError:
        return ""


@frappe.whitelist(methods=["POST"])
def decide_resolution(ticket: str | int, confirmed: bool | int | str, note: str = "") -> dict:
    """The customer (or an agent on their behalf) says the ticket is solved, or still broken."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    agent = is_agent()
    if not (agent or is_ticket_customer(doc)):
        frappe.throw(_("Only the customer or our team can answer this."), frappe.PermissionError)
    if doc.get("custom_copilot_stage") != "Resolved" and not agent:
        frappe.throw(_("There is nothing to confirm yet on this ticket."))
    result = customer.decide_resolution(
        doc.name, bool(sbool(confirmed)), note, actor=runs.AGENT if agent else runs.CUSTOMER
    )
    return {**result, "ticket": doc.name}
