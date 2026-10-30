"""Outreach (docs/leads.md, "Outreach"): AI first messages that a person approves before they
go. Thin proxies to TBO Smart's `tbo_smart.api.hub_outreach`; the ERP site holds the outbox,
checks who may see and approve each message, keeps the daily cap and the send window, and sends
the email. The hub sends nothing itself."""

import frappe
from frappe import _

from helpdesk.api.leads import as_list
from helpdesk.integrations.crm.leads import (
    LeadsUnavailableError,
    call_if_deployed,
    require_leads,
)

OUTREACH = "tbo_smart.api.hub_outreach"
OLDER_ERP = (
    "The ERP site can't draft first messages yet. It needs the latest TBO Smart."
)
CHANNELS = ("Email", "WhatsApp")
MAX_NAMES = 200
EMPTY_OUTBOX = {
    "available": False,
    "enabled": False,
    "email_ready": False,
    "rows": [],
    "counts": {},
    "cap": None,
    "window": None,
    "drafting": None,
    "opt_out": "",
}


def ask(method: str, **params):
    """The ERP site's answer as the signed-in person; an older TBO Smart says so in words."""
    require_leads()
    result = call_if_deployed(method, post=True, api=OUTREACH, **params)
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    return result


def message_names(names: list | str) -> list[str]:
    picked = as_list(names)
    if not picked:
        frappe.throw(_("Pick the messages first."))
    if len(picked) > MAX_NAMES:
        frappe.throw(_("Pick at most {0} messages at once.").format(MAX_NAMES))
    return picked


@frappe.whitelist()
def get_outbox(
    status: list | str | None = None,
    batch: str | None = None,
    run: str | None = None,
) -> dict:
    """The person's drafts and what became of them (a department head sees the department's,
    a manager everyone's), their counts, today's email cap left and the send window. Never
    cached: a draft appears while the AI writes. `available` is false while the ERP site is
    older than this."""
    require_leads()
    outbox = call_if_deployed(
        "get_outbox",
        api=OUTREACH,
        status=frappe.as_json(as_list(status)) if as_list(status) else None,
        batch=(batch or "").strip() or None,
        run=(run or "").strip() or None,
    )
    if outbox is None:
        return EMPTY_OUTBOX
    return {"available": True, **outbox}


@frappe.whitelist(methods=["POST"])
def draft_outreach(
    channel: str, leads: list | str | None = None, run: str | None = None
) -> dict:
    """Asks the ERP site to draft first messages in the background, for `leads` or for a
    prospect run's leads. Returns `{batch, queued, skipped: [{lead, lead_name, reason}]}`; a
    lead that unsubscribed, is lost, has no address or already has a message is skipped with
    its reason. Nothing is sent."""
    if channel not in CHANNELS:
        frappe.throw(_("Pick Email or WhatsApp."))
    picked = as_list(leads)
    run = (run or "").strip()
    if not picked and not run:
        frappe.throw(_("Pick the leads or a prospect run first."))
    if len(picked) > MAX_NAMES:
        frappe.throw(_("Pick at most {0} leads at once.").format(MAX_NAMES))
    return ask("draft_outreach", channel=channel, leads=picked or None, run=run or None)


@frappe.whitelist(methods=["POST"])
def update_outreach(name: str, body: str, subject: str | None = None) -> dict:
    """The person's edit of a draft's subject and text."""
    body = (body or "").strip()
    if not body:
        frappe.throw(_("The message is empty."))
    return ask(
        "update_outreach", name=name, body=body, subject=(subject or "").strip() or None
    )


@frappe.whitelist(methods=["POST"])
def regenerate_outreach(name: str) -> dict:
    """A new AI text for a draft."""
    return ask("regenerate_outreach", name=name)


@frappe.whitelist(methods=["POST"])
def approve_outreach(names: list | str) -> list:
    """Approves drafts as the signed-in person. An email goes out at once when the ERP site's
    send window is open and the person has sends left today, else it waits; a WhatsApp
    message becomes ready for the person to send. Each result says what happened."""
    return ask("approve_outreach", names=message_names(names))


@frappe.whitelist(methods=["POST"])
def cancel_outreach(names: list | str) -> list:
    """Withdraws drafts, approved and failed messages."""
    return ask("cancel_outreach", names=message_names(names))


@frappe.whitelist(methods=["POST"])
def mark_outreach_sent(names: list | str) -> list:
    """The person sent these approved WhatsApp messages from their own phone: they are
    logged on the lead as theirs."""
    return ask("mark_outreach_sent", names=message_names(names))
