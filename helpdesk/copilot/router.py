# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The root-cause router: what happens after a worker reports its investigation."""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from helpdesk.copilot import customer, runs
from helpdesk.copilot import settings as copilot_settings

CATEGORIES = (
    "question",
    "not_allowed_request",
    "customer_mistake",
    "wrong_setting",
    "bug",
    "data_damaged_by_bug",
    "core_issue",
    "customization_request",
    "unclear",
)
STATE_FOR_CATEGORY = {
    "question": "Explaining",
    "not_allowed_request": "Explaining",
    "customer_mistake": "Explaining",
    "unclear": "Explaining",
    # a feature request: the explanation offers an estimate; an agent starts the estimate flow
    "customization_request": "Explaining",
    "wrong_setting": "Preparing Fix",
    "bug": "Preparing Fix",
    "data_damaged_by_bug": "Preparing Fix",
    "core_issue": "Handed Over",
}
STAGE_FOR_CATEGORY = {
    category: ("With our team" if state == "Handed Over" else "Working on it")
    for category, state in STATE_FOR_CATEGORY.items()
}
LIMITS = {
    "summary": 4000,
    "customer_message": 4000,
    "evidence": 50,
    "questions": 10,
    "text": 2000,
}


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
        frappe.throw(
            _("Evidence must be a list of at most {0} items").format(LIMITS["evidence"])
        )
    if not isinstance(questions, list) or len(questions) > LIMITS["questions"]:
        frappe.throw(
            _("Questions must be a list of at most {0} items").format(
                LIMITS["questions"]
            )
        )
    if not isinstance(proposal, dict):
        frappe.throw(_("The proposal must be an object"))
    from helpdesk.copilot import changes

    change_set = changes.validate_report(result.get("change_set"))
    cost = result.get("cost") if isinstance(result.get("cost"), dict) else {}
    return {
        "root_cause_category": category,
        "confidence": confidence,
        "summary": _text(result.get("summary"), LIMITS["summary"]),
        "customer_message": _text(
            result.get("customer_message"), LIMITS["customer_message"]
        ),
        "evidence": [_item(e) for e in evidence],
        "proposal": {str(k)[:40]: _proposal_value(v) for k, v in proposal.items()},
        "questions": [_text(q, LIMITS["text"]) for q in questions],
        "cost": _cost(cost),
        "change_set": change_set,
        # the errors the diagnosis rests on, as the site gave them (app | method | last line)
        "error_signatures": [
            _text(sig, 600)
            for sig in (result.get("error_signatures") or [])[:10]
            if isinstance(sig, str) and sig.strip()
        ]
        if isinstance(result.get("error_signatures"), list)
        else [],
    }


def _cost(cost: dict) -> dict:
    """Tokens and money as the worker measured them; `tokens` is the total when only in/out are given."""
    tokens_in, tokens_out = max(int(flt(cost.get("tokens_in"))), 0), max(
        int(flt(cost.get("tokens_out"))), 0
    )
    return {
        "tokens": max(int(flt(cost.get("tokens"))), 0) or tokens_in + tokens_out,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "usd": max(flt(cost.get("usd")), 0),
        "model": _text(cost.get("model"), 140),
    }


def _text(value, limit: int) -> str:
    return "" if value is None else str(value)[:limit]


def _proposal_value(value):
    """Text, or a list of texts (the files a fix touches, a build's Done-when checks)."""
    if isinstance(value, list | tuple):
        return [
            _text(v, 300) for v in value[: LIMITS["questions"] * 2] if v is not None
        ]
    return _text(value, LIMITS["text"])


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
    change_set = investigation.pop("change_set", None)
    if change_set:
        # the records live on the change set; the run keeps how many
        investigation["change_set_records"] = len(change_set["changes"])
    target = STATE_FOR_CATEGORY[effective]
    asked = frappe.db.get_value(
        "HDS Copilot Run",
        run if isinstance(run, str) else run.name,
        "prepare_correction",
    )
    if effective == "customer_mistake" and asked and change_set:
        target = (
            "Preparing Fix"  # an agent asked for the correction: a senior approves it
        )
    doc = runs.transition(
        run,
        target,
        runs.SYSTEM,
        note=f"root cause: {effective}"
        + ("" if effective == category else f" (reported {category})"),
        root_cause_category=effective,
        confidence=investigation["confidence"],
        summary=investigation["summary"],
        customer_message=investigation["customer_message"],
        investigation=json.dumps(investigation, indent=1),
        evidence=json.dumps(investigation["evidence"], indent=1),
        proposal=json.dumps(investigation["proposal"], indent=1),
        cost_usd=investigation["cost"]["usd"],
        tokens_in=investigation["cost"]["tokens_in"],
        tokens_out=investigation["cost"]["tokens_out"],
        model_used=investigation["cost"]["model"] or None,
        investigated_at=now_datetime(),
    )
    runs.update_ticket(doc, root_cause=effective)
    from helpdesk.copilot import known_issues

    known_issues.link_run(doc, investigation.get("error_signatures"))
    _flag_suspicious(doc)
    customer.note_diagnosis(doc, investigation)
    if doc.state == "Explaining":
        customer.draft_explanation(doc, explanation_text(investigation, effective))
        if effective == "customization_request" and not doc.shadow:
            from helpdesk.api.customization import estimate_from_copilot

            # the estimate card is ready with Copilot's hours, scope and checks
            estimate_from_copilot(doc)
    elif doc.state == "Handed Over":
        customer.hand_over(
            doc,
            investigation["summary"] or _("Copilot found an issue in the core system"),
        )
    elif doc.state == "Preparing Fix":
        corrected = bool(
            change_set
            and effective
            in ("wrong_setting", "data_damaged_by_bug", "customer_mistake")
        )
        if corrected:
            from helpdesk.copilot import changes

            changes.prepare(doc, change_set, effective)
        # a setting or a customer's entries need no developer; damaged data needs the code fix first
        if not doc.shadow and not (
            corrected and effective in ("wrong_setting", "customer_mistake")
        ):
            _fix_task(doc)
    customer.send_stage(doc, STAGE_FOR_CATEGORY[effective])
    from helpdesk.copilot import assistant

    assistant.tell_watchers(
        doc
    )  # people who started this work from a Copilot chat hear it there
    return doc


def _flag_suspicious(run):
    """Text in the ticket that tries to instruct the AI, recorded for the card; never stops the routing."""
    from helpdesk.copilot import suspicious

    try:
        suspicious.check_ticket(run)
    except Exception:
        frappe.log_error(
            title=f"Copilot could not check ticket {run.ticket} for planted instructions"
        )


def _fix_task(run):
    """A live run that needs a code fix gets its fix task at once; a failure never undoes the routing."""
    from helpdesk.copilot import fixes

    frappe.db.savepoint("copilot_fix_task")
    try:
        fixes.create_fix_task(run)
        if copilot_settings.get_settings().get(
            "copilot_writes_fixes"
        ) and copilot_settings.allows(run.customer, copilot_settings.FIX):
            fixes.request_copilot_fix(run)
    except fixes.NoProject:
        # a setup gap, not a failure: the agents see it on the ticket and can create the task later
        frappe.db.rollback(save_point="copilot_fix_task")
        frappe.clear_last_message()
        runs.add_event(run, "fix_task_missing", {"reason": "no project"}, runs.SYSTEM)
        customer.comment(
            run.ticket,
            _(
                "Copilot could not create the fix task: the customer has no open project and no hand-over project is set."
            ),
        )
    except Exception:
        frappe.db.rollback(save_point="copilot_fix_task")
        frappe.log_error(
            title=_("Copilot could not create the fix task for {0}").format(run.ticket)
        )
        runs.tell_people(
            run,
            _("Copilot could not create the fix task for ticket {0}").format(
                run.ticket
            ),
        )


def explanation_text(investigation: dict, category: str) -> str:
    """What the agent is offered to send: the worker's message, or its questions as a list."""
    text = (investigation.get("customer_message") or "").strip()
    questions = [q for q in investigation.get("questions") or [] if q.strip()]
    if category == "customization_request":
        offer = _(
            "This is a change to how your system works rather than a fault, so we will send you an estimate of the work and a delivery date for your approval."
        )
        return f"{text}\n\n{offer}" if text else offer
    if category == "unclear" and questions:
        asked = "\n".join(f"- {q.strip()}" for q in questions)
        text = (
            f"{text}\n\n{asked}"
            if text
            else _("To find the cause we need a little more:") + "\n\n" + asked
        )
    return text or investigation.get("summary") or ""
