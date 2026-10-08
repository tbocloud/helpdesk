# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The root-cause router: what happens after a worker reports its investigation."""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from helpdesk.copilot import runs
from helpdesk.copilot import settings as copilot_settings

CATEGORIES = (
    "question",
    "not_allowed_request",
    "customer_mistake",
    "wrong_setting",
    "bug",
    "data_damaged_by_bug",
    "core_issue",
    "unclear",
)
STATE_FOR_CATEGORY = {
    "question": "Explaining",
    "not_allowed_request": "Explaining",
    "customer_mistake": "Explaining",
    "unclear": "Explaining",
    "wrong_setting": "Preparing Fix",
    "bug": "Preparing Fix",
    "data_damaged_by_bug": "Preparing Fix",
    "core_issue": "Handed Over",
}
STAGE_FOR_CATEGORY = {
    category: ("With our team" if state == "Handed Over" else "Working on it")
    for category, state in STATE_FOR_CATEGORY.items()
}
LIMITS = {"summary": 4000, "customer_message": 4000, "evidence": 50, "questions": 10, "text": 2000}


def validate_investigation(result: dict) -> dict:
    """The cleaned investigation, or a ValidationError naming what is wrong."""
    if not isinstance(result, dict):
        frappe.throw(_("The investigation must be an object"))
    category = result.get("root_cause_category")
    if category not in CATEGORIES:
        frappe.throw(_("Unknown root cause category: {0}").format(category))
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        frappe.throw(_("Confidence must be a number between 0 and 1"))
    if not 0 <= confidence <= 1:
        frappe.throw(_("Confidence must be a number between 0 and 1"))
    evidence = result.get("evidence") or []
    questions = result.get("questions") or []
    proposal = result.get("proposal") or {}
    if not isinstance(evidence, list) or len(evidence) > LIMITS["evidence"]:
        frappe.throw(_("Evidence must be a list of at most {0} items").format(LIMITS["evidence"]))
    if not isinstance(questions, list) or len(questions) > LIMITS["questions"]:
        frappe.throw(_("Questions must be a list of at most {0} items").format(LIMITS["questions"]))
    if not isinstance(proposal, dict):
        frappe.throw(_("The proposal must be an object"))
    cost = result.get("cost") if isinstance(result.get("cost"), dict) else {}
    return {
        "root_cause_category": category,
        "confidence": confidence,
        "summary": _text(result.get("summary"), LIMITS["summary"]),
        "customer_message": _text(result.get("customer_message"), LIMITS["customer_message"]),
        "evidence": [_item(e) for e in evidence],
        "proposal": {str(k)[:40]: _text(v, LIMITS["text"]) for k, v in proposal.items()},
        "questions": [_text(q, LIMITS["text"]) for q in questions],
        "cost": {"tokens": int(flt(cost.get("tokens"))), "usd": flt(cost.get("usd"))},
    }


def _text(value, limit: int) -> str:
    return "" if value is None else str(value)[:limit]


def _item(item) -> dict:
    if isinstance(item, dict):
        return {str(k)[:40]: _text(v, LIMITS["text"]) for k, v in item.items()}
    return {"note": _text(item, LIMITS["text"])}


def route(run, result: dict):
    """Moves the run on by the root cause the worker found; low confidence counts as unclear."""
    investigation = validate_investigation(result)
    threshold = flt(copilot_settings.get_settings().min_confidence or 0)
    category = investigation["root_cause_category"]
    effective = category if investigation["confidence"] >= threshold else "unclear"
    doc = runs.transition(
        run,
        STATE_FOR_CATEGORY[effective],
        runs.SYSTEM,
        note=f"root cause: {effective}" + ("" if effective == category else f" (reported {category})"),
        root_cause_category=effective,
        confidence=investigation["confidence"],
        summary=investigation["summary"],
        customer_message=investigation["customer_message"],
        investigation=json.dumps(investigation, indent=1),
        evidence=json.dumps(investigation["evidence"], indent=1),
        proposal=json.dumps(investigation["proposal"], indent=1),
        cost_usd=investigation["cost"]["usd"],
        investigated_at=now_datetime(),
    )
    runs.update_ticket(doc, stage=STAGE_FOR_CATEGORY[effective], root_cause=effective)
    return doc
