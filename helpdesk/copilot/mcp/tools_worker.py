# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Worker tools: what a Copilot run's agent may do, through its run token only.

Every call is scoped to the run the token belongs to; the customer's ERP is
read through the hub (allow-listed read tools, capped), never directly.
"""

import json

import frappe
from frappe import _

from helpdesk.copilot import router, runs
from helpdesk.copilot.mcp.registry import WORKER_TOOL, register_tool
from helpdesk.copilot.mcp.shape import clip

# read tools of helpdesk_client the agent may call on the customer's site
CUSTOMER_READ_TOOLS = (
    "get_doc",
    "get_list",
    "get_count",
    "get_meta",
    "get_error_log",
    "execute_report",
    "get_installed_apps",
    "get_site_info",
    "get_code_identity",
    "get_customizations",
    "get_deploy_status",
    "get_version_history",
)
MAX_SITE_RESULT_CHARS = 64_000


def _run(caller):
    return frappe.get_doc("HDS Copilot Run", caller.run)


def get_run_context(caller) -> dict:
    return runs.run_context(_run(caller))


def post_event(caller, seq: int, type: str, payload: dict | None = None) -> dict:
    stored = runs.add_event(caller.run, type, payload or {}, runs.WORKER, seq=seq)
    return {"seq": seq, "stored": stored}


def submit_investigation(
    caller,
    root_cause_category: str,
    confidence: float,
    summary: str = "",
    evidence: list | None = None,
    proposal: dict | None = None,
    customer_message: str = "",
    questions: list | None = None,
    cost: dict | None = None,
    change_set: dict | None = None,
) -> dict:
    if runs.fixing(_run(caller)):
        frappe.throw(
            _("This is a fix job; report the change with submit_change."),
            frappe.ValidationError,
        )
    doc = router.route(
        caller.run,
        {
            "kind": "investigation",
            "root_cause_category": root_cause_category,
            "confidence": confidence,
            "summary": summary,
            "evidence": evidence or [],
            "proposal": proposal or {},
            "customer_message": customer_message,
            "questions": questions or [],
            "cost": cost or {},
            "change_set": change_set,
        },
    )
    _log_usage(doc.name, cost, "investigate", 1)
    # the lease ends with the investigation: this token stops working now
    return {"run": doc.name, "state": doc.state, "root_cause": doc.root_cause_category}


def _log_usage(run: str, cost: dict | None, job: str, attempt: int):
    """The worker's spend as usage rows (one per stage); a logging failure never refuses the report."""
    from helpdesk.ai_engine import log_worker_usage

    try:
        log_worker_usage(run, cost, job, attempt)
    except Exception:
        frappe.log_error(title=f"Copilot usage not logged for {run}")


def submit_change(
    caller,
    repository: str,
    number: int,
    head_sha: str,
    branch: str = "",
    summary: str = "",
    evidence: list | None = None,
    tested_on: str = "",
    people_checks: list | None = None,
    risk_notes: str = "",
    cost: dict | None = None,
) -> dict:
    from helpdesk.copilot import fixes

    run = _run(caller)
    if not runs.fixing(run):
        frappe.throw(_("Only a fix job reports a change."), frappe.ValidationError)
    doc = fixes.on_change(
        run,
        {
            "repository": repository,
            "number": number,
            "head_sha": head_sha,
            "branch": branch,
            "summary": summary,
            "evidence": evidence or [],
            "tested_on": tested_on,
            "people_checks": people_checks or [],
            "risk_notes": risk_notes,
            "cost": cost or {},
        },
    )
    _log_usage(doc.name, cost, "fix", doc.get("fix_attempts") or 1)
    # the lease ends with the change: this token stops working now
    return {"run": doc.name, "state": doc.state, "fix": doc.fix_status}


def customer_erp_read(caller, tool: str, arguments: dict | None = None) -> dict:
    from helpdesk.mcp_client import MCPClient

    if tool not in CUSTOMER_READ_TOOLS:
        frappe.throw(
            _("{0} is not a read tool Copilot may use. Allowed: {1}").format(
                tool, ", ".join(CUSTOMER_READ_TOOLS)
            ),
            frappe.ValidationError,
        )
    run = _run(caller)
    if not run.connection:
        frappe.throw(
            _("No customer site is connected for this ticket."), frappe.ValidationError
        )
    result = MCPClient(run.connection).call_tool(
        tool, arguments or {}, session_id=run.name
    )
    text = ((result.get("content") or [{}])[0] or {}).get("text") or ""
    if result.get("isError"):
        frappe.throw(
            _("The customer site refused {0}: {1}").format(tool, clip(text, 400)),
            frappe.ValidationError,
        )
    if len(text) > MAX_SITE_RESULT_CHARS:
        return {
            "tool": tool,
            "cut_at_characters": MAX_SITE_RESULT_CHARS,
            "result": text[:MAX_SITE_RESULT_CHARS],
        }
    try:
        return {"tool": tool, "result": json.loads(text)}
    except ValueError:
        return {"tool": tool, "result": text}


register_tool(
    "get_run_context",
    kind=WORKER_TOOL,
    description="This run's ticket, triage, customer, site and apps, conversation, files and earlier runs.",
    handler=get_run_context,
)
register_tool(
    "post_event",
    kind=WORKER_TOOL,
    description="Record a progress event for this run; a repeated seq is ignored.",
    handler=post_event,
    properties={
        "seq": {"type": "integer", "minimum": 1},
        "type": {"type": "string", "maxLength": 140},
        "payload": {"type": "object"},
    },
    required=["seq", "type"],
    read_only=False,
)
register_tool(
    "submit_investigation",
    kind=WORKER_TOOL,
    description="Report the root cause, confidence, evidence and proposal; ends this run's investigation.",
    handler=submit_investigation,
    properties={
        "root_cause_category": {"type": "string", "enum": list(router.CATEGORIES)},
        "confidence": {"type": "number"},
        "summary": {"type": "string", "maxLength": 4000},
        "evidence": {"type": "array"},
        "proposal": {"type": "object"},
        "customer_message": {"type": "string", "maxLength": 4000},
        "questions": {"type": "array"},
        "cost": {"type": "object"},
        "change_set": {
            "type": "object",
            "description": "For a wrong setting or wrong data: {summary, customer_note, found_by, "
            "changes: [{action: update|create, doctype, name, values, rows, add_rows, why}], "
            "set_aside: [{doctype, name, why}]}. Never deletes; submitted documents go in set_aside.",
        },
    },
    required=["root_cause_category", "confidence"],
    read_only=False,
)
register_tool(
    "submit_change",
    kind=WORKER_TOOL,
    description="Report the pull request a fix job opened and what it tested; ends this run's fix job.",
    handler=submit_change,
    properties={
        "repository": {"type": "string", "maxLength": 200},
        "number": {"type": "integer", "minimum": 1},
        "head_sha": {"type": "string", "maxLength": 64},
        "branch": {"type": "string", "maxLength": 255},
        "summary": {"type": "string", "maxLength": 4000},
        "evidence": {"type": "array"},
        "tested_on": {"type": "string", "maxLength": 200},
        "people_checks": {"type": "array"},
        "risk_notes": {"type": "string", "maxLength": 2000},
        "cost": {"type": "object"},
    },
    required=["repository", "number", "head_sha"],
    read_only=False,
)
register_tool(
    "customer_erp_read",
    kind=WORKER_TOOL,
    description="Read the ticket's customer ERP through the hub with one allow-listed read tool.",
    handler=customer_erp_read,
    properties={
        "tool": {"type": "string", "enum": list(CUSTOMER_READ_TOOLS)},
        "arguments": {"type": "object"},
    },
    required=["tool"],
    open_world=True,
)
