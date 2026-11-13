# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Action approvals for agents and the desktop app (Phase 18): ask, look up, decide, and mark
an approved action as run. Every caller is a signed-in agent; the record keeps who asked,
who decided and what happened (helpdesk.copilot.actions)."""

import json

import frappe
from frappe import _
from frappe.utils import sbool

from helpdesk.copilot import actions
from helpdesk.utils import agent_only


def _payload(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            frappe.throw(_("The payload must be JSON."))
    if not isinstance(value, dict):
        frappe.throw(_("The payload must be a JSON object."))
    return value


def _readable(name: str):
    doc = frappe.get_doc(actions.ACTION, name)
    user = frappe.session.user
    if not (
        user == doc.requested_by
        or user == doc.assigned_to
        or frappe.has_permission(actions.ACTION, "read", doc.name)
    ):
        frappe.throw(_("Not your request."), frappe.PermissionError)
    return doc


@frappe.whitelist(methods=["POST"])
@agent_only
def request_action_approval(
    kind: str,
    title: str,
    details: str,
    payload,
    risk: str = "normal",
    via: str = "Desktop",
    ticket: str | None = None,
) -> dict:
    """Asks for an approval of exactly `payload`; the same ask twice returns the live request."""
    doc = actions.request(
        kind,
        title,
        details,
        _payload(payload),
        risk=risk,
        user=frappe.session.user,
        via=via[:40],
        ticket=ticket or None,
    )
    return actions.as_dict(doc)


@frappe.whitelist()
@agent_only
def get_action_approval(name: str) -> dict:
    return actions.as_dict(_readable(name))


@frappe.whitelist()
@agent_only
def approved_action(kind: str, payload) -> dict | None:
    """The caller's live approval of exactly this payload, if someone else approved it."""
    doc = actions.approved_for(kind, _payload(payload), frappe.session.user)
    return actions.as_dict(doc) if doc else None


@frappe.whitelist(methods=["POST"])
@agent_only
def decide_action(name: str, approve, note: str = "") -> dict:
    approve = bool(sbool(approve))
    if not approve and not (note or "").strip():
        frappe.throw(_("Write the reason to reject: the person who asked gets it."))
    actions.decide(name, frappe.session.user, approve, (note or "").strip(), via="Web")
    doc = frappe.get_doc(actions.ACTION, name)
    _log(doc, "decide_action", {"approve": approve, "note": note})
    return actions.as_dict(doc)


@frappe.whitelist(methods=["POST"])
@agent_only
def mark_action_executed(name: str, ok, log: str = "") -> dict:
    """Only the person who asked (they ran it) may say how it went."""
    doc = frappe.get_doc(actions.ACTION, name)
    if frappe.session.user != doc.requested_by and not frappe.has_permission(
        actions.ACTION, "write", doc.name
    ):
        frappe.throw(
            _("Only the person who asked may mark this as run."), frappe.PermissionError
        )
    doc = actions.mark_executed(name, bool(sbool(ok)), log or "")
    _log(doc, "mark_action_executed", {"ok": bool(sbool(ok)), "log": log})
    return actions.as_dict(doc)


def _log(doc, tool: str, arguments: dict):
    """A decision or an outcome sent from the desktop app goes to HDS Copilot Call Log too
    (identifiers kept, text as a fingerprint), like the Teams card's buttons."""
    from helpdesk.copilot import assistant

    assistant.log_action(
        frappe.session.user,
        "Desktop",
        tool,
        "OK",
        {"approval": doc.name, "kind": doc.get("kind"), **arguments},
        ticket=doc.get("ticket"),
    )
