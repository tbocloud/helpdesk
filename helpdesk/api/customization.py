"""Estimates for customization requests: estimate, send, approve, then build.

A customization (a new report filter, print format, field, workflow...) doesn't fit a
fixed resolution SLA, because the work differs every time. Instead:

1. AI triage marks the ticket as Customization and estimates the developer hours.
2. An agent checks the estimate and sends it to the customer with a delivery date.
3. The customer approves it in the portal (or the agent records their approval).
4. The task is created with that date; the ticket waits on it ("Waiting on Task"
   pauses the SLA clock) and the agreed delivery date is the target.

The usual SLA still covers the first reply. See docs/ai-customization-pipeline.md.
"""

import math

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

from helpdesk.task_estimates import add_working_days, weekly_off_days
from helpdesk.utils import agent_only, is_agent

CUSTOMIZATION = "Customization"
ESTIMATED, SENT, APPROVED, DECLINED = "Estimated", "Sent", "Approved", "Declined"
DEFAULT_HOURS_PER_DAY = 6
MAX_HOURS = 2000


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
    if ticket.ticket_type in (None, "", "Unspecified"):
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
    ticket: str | int, hours: float | str, delivery_date: str, note: str = ""
) -> dict:
    """Email the estimate to the customer and wait for their approval."""
    doc = frappe.get_doc("HD Ticket", str(ticket))
    doc.check_permission("write")
    hours = flt(hours)
    if not 0 < hours <= MAX_HOURS:
        frappe.throw(_("Enter the estimate in hours."))
    delivery = getdate(delivery_date)
    if delivery < getdate(nowdate()):
        frappe.throw(_("The delivery date can't be in the past."))

    doc.reply_via_agent(estimate_message(doc, hours, delivery, note))
    doc.reload()
    doc.db_set(
        {
            "ticket_type": CUSTOMIZATION,
            "custom_estimate_hours": round(hours, 1),
            "custom_estimate_status": SENT,
            "custom_estimate_note": (note or "")[:500],
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
        }
    )
    record_decision(doc, approved, hours, delivery, note, by_customer=not agent)
    return get_estimate(doc.name)


def is_ticket_customer(doc) -> bool:
    return frappe.session.user in {doc.raised_by, doc.contact, doc.owner} - {None, ""}


def estimate_message(doc, hours: float, delivery, note: str) -> str:
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
    # the agents on the ticket act next: create the task, or talk to the customer
    notify_users(
        frappe.parse_json(doc.get("_assign") or "[]"),
        "HD Ticket",
        doc.name,
        _("#{0}: the customer approved the estimate. Create the task.").format(doc.name)
        if approved
        else _("#{0}: the customer declined the estimate.").format(doc.name),
    )
