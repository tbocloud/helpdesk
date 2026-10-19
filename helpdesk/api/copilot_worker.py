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

from helpdesk.copilot import fixes, router, runs

WORKER_ROLE = "Copilot Worker"


def ensure_role():
    """Created on migrate; API-only, so no desk access."""
    if frappe.db.exists("Role", WORKER_ROLE):
        return
    frappe.get_doc(
        {"doctype": "Role", "role_name": WORKER_ROLE, "desk_access": 0}
    ).insert(ignore_permissions=True)


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
def claim_job(
    worker_id: str, free_slots: int = 1, capabilities: str = "", run: str | None = None
) -> dict:
    """The oldest queued run (or `run`, if it is queued) with its lease token and context, or {}."""
    worker_only()
    worker_id = (worker_id or "").strip()[:140]
    if not worker_id:
        frappe.throw(_("worker_id is required"))
    if int(free_slots) < 1:
        return {}
    from helpdesk.copilot import pilot
    from helpdesk.copilot import settings as copilot_settings

    if not copilot_settings.is_enabled():
        return (
            {}
        )  # switched off: no work goes out, and a worker mid-run is stopped at its heartbeat
    if not pilot.budget_allows_work():
        return (
            {}
        )  # the month's AI budget is used up: work waits (the managers were told)
    run, token = runs.claim(worker_id, capabilities or "", (run or "").strip() or None)
    if not run:
        return {}
    return {
        "run": run.name,
        "lease_token": token,
        "lease_expires": str(run.lease_expires),
        "context": runs.run_context(run),
    }


@frappe.whitelist(methods=["POST"])
def repo_token(run: str, lease_token: str, repository: str) -> dict:
    """A one-hour key to clone and push the fix's branch to one of the run's site repositories."""
    worker_only()
    doc = runs.check_lease(run, lease_token)
    if not runs.fixing(doc):
        frappe.throw(_("Only a fix job gets a push key."), frappe.PermissionError)
    return fixes.push_key(doc, repository)


# what a worker may download from a ticket: pictures and videos of the problem (Phase 6, W9)
TICKET_FILE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
}
TICKET_FILE_MAX_BYTES = 50 * 1024 * 1024


@frappe.whitelist(methods=["POST"])
def ticket_file(run: str, lease_token: str, file_url: str):
    """One picture or video attached to the run's ticket, as bytes, while the lease holds."""
    from werkzeug.wrappers import Response

    worker_only()
    doc = runs.check_lease(run, lease_token)
    name = frappe.db.get_value(
        "File",
        {
            "file_url": file_url,
            "attached_to_doctype": "HD Ticket",
            "attached_to_name": doc.ticket,
        },
        "name",
    )
    if not name:
        frappe.throw(
            _("That file is not on this run's ticket."), frappe.PermissionError
        )
    file = frappe.get_doc("File", name)
    kind = TICKET_FILE_TYPES.get((file.file_name or "").rsplit(".", 1)[-1].lower())
    if not kind:
        frappe.throw(_("Only pictures and videos are given to the worker."))
    if (file.file_size or 0) > TICKET_FILE_MAX_BYTES:
        frappe.throw(_("The file is larger than 50 MB."))
    content = file.get_content()
    if isinstance(content, str):
        content = content.encode()
    runs.add_event(
        doc, "file_read", {"file": file.file_name, "bytes": len(content)}, runs.WORKER
    )
    return Response(content, status=200, content_type=kind)


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
        runs.add_event(
            doc,
            str(event.get("type") or "note"),
            event.get("payload") or {},
            runs.WORKER,
            seq=seq,
        )
        acked.append(seq)
    return {"acked": acked}


@frappe.whitelist(methods=["POST"])
def submit_result(run: str, lease_token: str, result: dict | str) -> dict:
    """An investigation (`kind: investigation`) is routed; a failure (`kind: failure`) fails the run."""
    worker_only()
    doc = runs.check_lease(run, lease_token)
    result = _parse(result, "result") or {}
    kind = result.get("kind")
    if runs.fixing(doc):
        # a fix job ends with submit_change (the MCP tool), or with this failure
        if kind != "failure":
            frappe.throw(_("A fix job reports its change with submit_change."))
        fixes.fix_failed(doc, str(result.get("reason") or ""))
        doc.reload()
        return {"run": doc.name, "state": doc.state, "fix": doc.fix_status}
    if kind == "investigation":
        doc = router.route(doc, result)
    elif kind == "failure":
        reason = str(result.get("reason") or "")[:2000]
        doc = runs.transition(
            doc, "Failed", runs.WORKER, note="worker failed", failure_reason=reason
        )
        runs.tell_people(
            doc,
            _("Copilot could not investigate ticket {0}: {1}").format(
                doc.ticket, reason[:200]
            ),
        )
    else:
        frappe.throw(_("Unknown result kind: {0}").format(kind))
    return {"run": doc.name, "state": doc.state, "root_cause": doc.root_cause_category}
