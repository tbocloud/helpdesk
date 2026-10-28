"""Estimates for customization requests: estimate, send, approve, then build.

A customization (a new report filter, print format, field, workflow...) doesn't fit a
fixed resolution SLA, because the work differs every time. Instead:

1. AI triage marks the ticket as Customization and estimates the developer hours.
2. An agent checks the estimate and sends it to the customer with a delivery date.
3. The customer approves it in the portal (or the agent records their approval).
4. The task is created with that date; the ticket waits on it ("Waiting on Task"
   pauses the SLA clock) and the agreed delivery date is the target.

The estimate can carry a written scope: **What we will build** and **Done when** (one
check per line). The customer approves that text with the hours, and its hash is kept:
Copilot builds only an approved scope that was not edited afterwards (Phase 8). When
Copilot finds a customization request, the estimate starts by itself from its proposal.

The usual SLA still covers the first reply. See docs/ai-customization-pipeline.md.
"""

import hashlib
import json
import math
import re

import frappe
from frappe import _
from frappe.utils import (
    cint,
    escape_html,
    flt,
    formatdate,
    get_url,
    getdate,
    now_datetime,
    nowdate,
)

from helpdesk.routing import is_default_ticket_type
from helpdesk.task_estimates import add_working_days, weekly_off_days
from helpdesk.utils import agent_only, is_agent

CUSTOMIZATION = "Customization"
ESTIMATED, SENT, APPROVED, DECLINED = "Estimated", "Sent", "Approved", "Declined"
DEFAULT_HOURS_PER_DAY = 6
MAX_HOURS = 2000
MAX_SCOPE_CHARS = 4000
MAX_CHECKS = 15
MAX_CHECK_CHARS = 300


def ensure_ticket_type():
    """The Customization ticket type, so triage and agents can use it."""
    if frappe.db.exists("HD Ticket Type", CUSTOMIZATION):
        return
    frappe.get_doc(
        {
            "doctype": "HD Ticket Type",
            "name": CUSTOMIZATION,
            "description": "A new or changed report, print format, field, workflow or automation the customer wants built.",
        }
    ).insert(ignore_permissions=True)


def hours_per_day() -> int:
    return (
        cint(frappe.db.get_single_value("HD Work Settings", "dev_hours_per_day"))
        or DEFAULT_HOURS_PER_DAY
    )


def delivery_for(hours: float, start=None):
    """The working day the work is done if it starts on `start` (today by default)."""
    days = max(1, math.ceil(flt(hours) / hours_per_day()))
    return add_working_days(start or nowdate(), days)


def record_triage_estimate(ticket_id: str, triage: dict):
    """After AI triage: mark a customization and keep the AI's hour estimate (once)."""
    if (triage.get("request_type") or "").lower() != "customization":
        return
    ticket = frappe.db.get_value(
        "HD Ticket",
        ticket_id,
        ["ticket_type", "custom_estimate_status"],
        as_dict=True,
    )
    if not ticket:
        return
    ensure_ticket_type()
    updates = {}
    # the default type (Bug on the hub) was never chosen by anyone, so it counts as unset
    if is_default_ticket_type(ticket.ticket_type):
        updates["ticket_type"] = CUSTOMIZATION
    hours = flt(triage.get("estimate_hours"))
    # an estimate an agent already worked on is theirs, not the AI's
    if 0 < hours <= MAX_HOURS and not ticket.custom_estimate_status:
        updates.update(
            {
                "custom_estimate_hours": round(hours, 1),
                "custom_estimate_status": ESTIMATED,
                "custom_estimate_note": (triage.get("estimate_note") or "")[:500],
            }
        )
    if updates:
        frappe.db.set_value("HD Ticket", ticket_id, updates, update_modified=False)


def checks_of(text: str | list | None) -> list[str]:
    """The Done-when checks, one per line, without bullets or numbers."""
    lines = text if isinstance(text, list) else (text or "").splitlines()
    checks = []
    for line in lines:
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", str(line or "")).strip()
        if line:
            checks.append(line[:MAX_CHECK_CHARS])
    return checks[:MAX_CHECKS]


def scope_hash(hours, scope: str | None, checks: str | list | None) -> str:
    """What the customer approves: the hours, the scope and the checks, as written."""
    content = {
        "hours": round(flt(hours), 1),
        "scope": (scope or "").strip(),
        "checks": checks_of(checks),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def current_scope_hash(doc) -> str:
    return scope_hash(
        doc.get("custom_estimate_hours"),
        doc.get("custom_estimate_scope"),
        doc.get("custom_estimate_checks"),
    )


def approved_scope(doc) -> dict | None:
    """The scope the customer approved, when it is still exactly what they approved."""
    stored = doc.get("custom_estimate_scope_hash")
    if (
        doc.get("custom_estimate_status") != APPROVED
        or not stored
        or stored != current_scope_hash(doc)
    ):
        return None
    return {
        "hours": flt(doc.get("custom_estimate_hours")),
        "scope": doc.get("custom_estimate_scope") or "",
        "checks": checks_of(doc.get("custom_estimate_checks")),
        "approved_by": doc.get("custom_estimate_decided_by"),
        "approved_on": str(doc.get("custom_estimate_decided_on") or ""),
        "hash": stored,
    }


def fill_scope(ticket: str, scope: str, checks: str | list):
    """A first draft of the scope (Copilot's), kept until the estimate is sent."""
    doc = frappe.db.get_value(
        "HD Ticket",
        ticket,
        ["custom_estimate_status", "custom_estimate_scope", "custom_estimate_checks"],
        as_dict=True,
    )
    if not doc or doc.custom_estimate_status in (SENT, APPROVED):
        return
    updates = {}
    if scope and not doc.custom_estimate_scope:
        updates["custom_estimate_scope"] = scope.strip()[:MAX_SCOPE_CHARS]
    if checks and not doc.custom_estimate_checks:
        updates["custom_estimate_checks"] = "\n".join(checks_of(checks))
    if updates:
        frappe.db.set_value("HD Ticket", ticket, updates, update_modified=False)


def estimate_from_copilot(run):
    """Copilot found a feature request: the ticket becomes a Customization with Copilot's hours
    (unless triage or an agent estimated it already) and its draft of the scope, ready on the
    estimate card for an agent to check and send. Nothing goes to the customer here."""
    from helpdesk.copilot import runs

    proposal = frappe.parse_json(run.proposal or "{}") or {}
    hours = next(
        (
            proposal.get(key)
            for key in ("estimate_hours", "hours")
            if str(proposal.get(key) or "").replace(".", "", 1).isdigit()
        ),
        0,
    )
    record_triage_estimate(
        run.ticket,
        {
            "request_type": "customization",
            "estimate_hours": hours,
            "estimate_note": _("From Copilot run {0}: {1}").format(
                run.name, run.summary or ""
            ),
        },
    )
    # what will be built: the worker's scope and checks when it wrote them, else its proposal
    scope = proposal.get("scope") or proposal.get("action") or run.summary or ""
    fill_scope(run.ticket, str(scope), proposal.get("done_when") or "")
    runs.add_event(run, "estimate_started", {"hours": hours}, runs.SYSTEM)


@frappe.whitelist()
def get_estimate(ticket: str | int) -> dict:
    """The ticket's estimate, for the agent card and the customer's approval banner."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    hours = flt(doc.get("custom_estimate_hours"))
    status = doc.get("custom_estimate_status") or ""
    agent = is_agent()
    return {
        "is_customization": doc.ticket_type == CUSTOMIZATION,
        "hours": hours,
        "status": status,
        "note": doc.get("custom_estimate_note") or "",
        "scope": doc.get("custom_estimate_scope") or "",
        "checks": checks_of(doc.get("custom_estimate_checks")),
        # approved, and not edited since: what Copilot may build
        "scope_approved": bool(
            approved_scope(doc) and doc.get("custom_estimate_scope")
        ),
        "delivery_date": doc.get("custom_agreed_delivery"),
        "suggested_delivery": str(delivery_for(hours)) if hours else None,
        "hours_per_day": hours_per_day(),
        # days off as JavaScript weekdays (Sunday = 0), for the date the card suggests
        "off_days": sorted((day + 1) % 7 for day in weekly_off_days()),
        "decided_on": doc.get("custom_estimate_decided_on"),
        "decided_by": frappe.utils.get_fullname(doc.get("custom_estimate_decided_by"))
        if doc.get("custom_estimate_decided_by")
        else None,
        "can_manage": agent,
        "can_decide": status == SENT and (agent or is_ticket_customer(doc)),
    }


@frappe.whitelist(methods=["POST"])
@agent_only
def send_estimate(
    ticket: str | int,
    hours: float | str,
    delivery_date: str,
    note: str = "",
    scope: str = "",
    checks: str = "",
) -> dict:
    """Email the estimate (and the scope, when written) to the customer and wait for their approval."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("write")
    hours = flt(hours)
    if not 0 < hours <= MAX_HOURS:
        frappe.throw(_("Enter the estimate in hours."))
    delivery = getdate(delivery_date)
    if delivery < getdate(nowdate()):
        frappe.throw(_("The delivery date can't be in the past."))
    scope = (scope or "").strip()[:MAX_SCOPE_CHARS]
    checks = checks_of(checks)
    if checks and not scope:
        frappe.throw(_("Write what we will build before the Done-when checks."))

    doc.reply_via_agent(estimate_message(doc, hours, delivery, note, scope, checks))
    doc.reload()
    doc.db_set(
        {
            "ticket_type": CUSTOMIZATION,
            "custom_estimate_hours": round(hours, 1),
            "custom_estimate_status": SENT,
            "custom_estimate_note": (note or "")[:500],
            "custom_estimate_scope": scope,
            "custom_estimate_checks": "\n".join(checks),
            # a new estimate is approved afresh
            "custom_estimate_scope_hash": None,
            "custom_agreed_delivery": delivery,
            "custom_estimate_sent_on": now_datetime(),
            "custom_estimate_decided_on": None,
            "custom_estimate_decided_by": None,
        }
    )
    return get_estimate(doc.name)


@frappe.whitelist(methods=["POST"])
def decide_estimate(
    ticket: str | int, approve: bool | int | str, note: str = ""
) -> dict:
    """The customer (or an agent on their behalf) approves or declines the estimate."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("read")
    agent = is_agent()
    if not (agent or is_ticket_customer(doc)):
        frappe.throw(
            _("Only the customer or our team can decide on this estimate."),
            frappe.PermissionError,
        )
    status = doc.get("custom_estimate_status") or ""
    # the customer decides on what was sent; an agent may also record a phone or email approval
    allowed = (SENT, ESTIMATED) if agent else (SENT,)
    if status not in allowed:
        frappe.throw(_("There is no estimate waiting for a decision on this ticket."))
    approved = frappe.utils.sbool(approve)
    hours = flt(doc.get("custom_estimate_hours"))
    delivery = doc.get("custom_agreed_delivery")
    # approved later than planned: the work can only start now
    if approved and (not delivery or getdate(delivery) < getdate(nowdate())):
        delivery = delivery_for(hours) if hours else getdate(nowdate())

    doc.db_set(
        {
            "custom_estimate_status": APPROVED if approved else DECLINED,
            "custom_agreed_delivery": delivery
            if approved
            else doc.get("custom_agreed_delivery"),
            "custom_estimate_decided_on": now_datetime(),
            "custom_estimate_decided_by": frappe.session.user,
            "custom_estimate_scope_hash": current_scope_hash(doc) if approved else None,
        }
    )
    record_decision(doc, approved, hours, delivery, note, by_customer=not agent)
    return get_estimate(doc.name)


def is_ticket_customer(doc) -> bool:
    return frappe.session.user in {doc.raised_by, doc.contact, doc.owner} - {None, ""}


def estimate_message(
    doc, hours: float, delivery, note: str, scope: str = "", checks: list | None = None
) -> str:
    portal = get_url(f"/helpdesk/my-tickets/{doc.name}")
    parts = [
        "<p>{0}</p>".format(_("Thank you for the request. Here is our estimate:")),
        "<ul><li>{0}</li><li>{1}</li></ul>".format(
            _("Work: {0} hours").format(f"<b>{frappe.format(hours, 'Float')}</b>"),
            _("Ready by: {0}, once you approve").format(
                f"<b>{formatdate(delivery, 'EEEE, d MMMM')}</b>"
            ),
        ),
    ]
    if scope:
        parts.append(
            "<p><b>{0}</b></p><p>{1}</p>".format(
                escape_html(_("What we will build")),
                escape_html(scope).replace("\n", "<br>"),
            )
        )
    if checks:
        parts.append(
            "<p><b>{0}</b></p><ul>{1}</ul>".format(
                escape_html(_("Done when")),
                "".join(f"<li>{escape_html(check)}</li>" for check in checks),
            )
        )
    if note:
        parts.append(f"<p>{escape_html(note)}</p>")
    parts.append(
        "<p>{0}</p>".format(
            _(
                'To go ahead, approve the estimate on your ticket: <a href="{0}">{0}</a>. You can also reply to this email if you have questions.'
            ).format(portal)
        )
    )
    return "".join(parts)


def record_decision(
    doc, approved: bool, hours: float, delivery, note: str, by_customer: bool
):
    from helpdesk.work_reminders import notify_users

    who = frappe.utils.get_fullname(frappe.session.user)
    if approved:
        text = _("Estimate approved by {0}: {1} hours, delivery {2}.").format(
            who, frappe.format(hours, "Float"), formatdate(delivery)
        )
    else:
        text = _("Estimate declined by {0}.").format(who)
    if note:
        text += " " + note
    frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": doc.name,
            "content": escape_html(text),
        }
    ).insert(ignore_permissions=True)
    if not by_customer:
        return
    # the agents on the ticket act next: create the task (or Copilot builds it), or talk to the customer
    if not approved:
        text = _("#{0}: the customer declined the estimate.").format(doc.name)
    elif copilot_can_build(doc.name):
        text = _(
            "#{0}: the customer approved the estimate. Copilot can build it: press Build with Copilot."
        ).format(doc.name)
    else:
        text = _("#{0}: the customer approved the estimate. Create the task.").format(
            doc.name
        )
    notify_users(
        frappe.parse_json(doc.get("_assign") or "[]"), "HD Ticket", doc.name, text
    )


def copilot_can_build(ticket: str) -> bool:
    """Copilot found this customization and may build it now (Phase 8)."""
    from helpdesk.copilot import customer as copilot_customer
    from helpdesk.copilot import fixes

    run = copilot_customer.latest_run(ticket)
    return bool(
        run and run.root_cause_category == "customization_request"
    ) and not fixes.build_refusal(run)
