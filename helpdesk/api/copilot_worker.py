# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The worker API: a Copilot worker claims runs, keeps them alive, reports events and results.

Callers hold the role Copilot Worker (API only, created on migrate). Every call
after a claim carries the lease token, so only the worker that holds a run
can report on it.
"""

import json

import frappe
from frappe import _

from helpdesk.copilot import router, runs

WORKER_ROLE = "Copilot Worker"


def ensure_role():
    """Created on migrate; API-only, so no desk access."""
    if frappe.db.exists("Role", WORKER_ROLE):
        return
    frappe.get_doc({"doctype": "Role", "role_name": WORKER_ROLE, "desk_access": 0}).insert(
        ignore_permissions=True
    )


def worker_only():
    # frappe.only_for is a no-op in tests, so the role is checked directly
    if WORKER_ROLE not in frappe.get_roles():
        frappe.throw(_("Only a Copilot worker may call this."), frappe.PermissionError)


def _parse(value, what: str):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            frappe.throw(_("{0} must be JSON").format(what))
    return value


@frappe.whitelist(methods=["POST"])
def claim_job(worker_id: str, free_slots: int = 1, capabilities: str = "") -> dict:
    """The oldest queued run with its lease token and context, or {} when there is nothing to do."""
    worker_only()
    worker_id = (worker_id or "").strip()[:140]
    if not worker_id:
        frappe.throw(_("worker_id is required"))
    if int(free_slots) < 1:
        return {}
    run, token = runs.claim(worker_id, capabilities or "")
    if not run:
        return {}
    return {
        "run": run.name,
        "lease_token": token,
        "lease_expires": str(run.lease_expires),
        "context": runs.run_context(run),
    }


@frappe.whitelist(methods=["POST"])
def heartbeat(run: str, lease_token: str, stage: str = "") -> dict:
    """Keeps the lease; the answer says `continue` or `cancel`."""
    worker_only()
    answer = runs.heartbeat(run, lease_token)
    if stage and answer.get("action") == "continue":
        runs.add_event(run, "progress", {"stage": stage[:140]}, runs.WORKER)
    return answer


@frappe.whitelist(methods=["POST"])
def post_events(run: str, lease_token: str, events: list | str) -> dict:
    """Stores the worker's events `{seq, type, payload}`; a repeated seq is ignored."""
    worker_only()
    doc = runs.check_lease(run, lease_token)
    acked = []
    for event in _parse(events, "events") or []:
        if not isinstance(event, dict) or "seq" not in event:
            frappe.throw(_("Each event needs a seq"))
        seq = int(event["seq"])
        runs.add_event(doc, str(event.get("type") or "note"), event.get("payload") or {}, runs.WORKER, seq=seq)
        acked.append(seq)
    return {"acked": acked}


@frappe.whitelist(methods=["POST"])
def submit_result(run: str, lease_token: str, result: dict | str) -> dict:
    """An investigation (`kind: investigation`) is routed; a failure (`kind: failure`) fails the run."""
    worker_only()
    doc = runs.check_lease(run, lease_token)
    result = _parse(result, "result") or {}
    kind = result.get("kind")
    if kind == "investigation":
        doc = router.route(doc, result)
    elif kind == "failure":
        reason = str(result.get("reason") or "")[:2000]
        doc = runs.transition(doc, "Failed", runs.WORKER, note="worker failed", failure_reason=reason)
        runs.tell_people(doc, _("Copilot could not investigate ticket {0}: {1}").format(doc.ticket, reason[:200]))
    else:
        frappe.throw(_("Unknown result kind: {0}").format(kind))
    return {"run": doc.name, "state": doc.state, "root_cause": doc.root_cause_category}
