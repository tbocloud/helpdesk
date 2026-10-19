"""Proposals and the segment rate card on the Leads page (docs/proposals.md). Thin proxies
to TBO Smart's hub proposals API (and the rate card in its hub leads API) on the CRM site,
as the signed-in person, the same way as helpdesk.api.leads. The CRM site decides who may
see, change and send what; the API key never leaves the hub."""

import frappe
from frappe import _
from frappe.utils import cint

from helpdesk.integrations.crm.leads import call, require_leads

PROPOSALS = "tbo_smart.api.hub_proposals"


def proposals(method: str, post: bool = False, **params):
    return call(method, post=post, api=PROPOSALS, **params)


def as_json_value(value, kind=dict):
    value = frappe.parse_json(value) if isinstance(value, str) else value
    if not isinstance(value, kind):
        frappe.throw(_("Send the values as a set of fields."))
    return value


@frappe.whitelist()
def get_proposal_options() -> dict:
    """Whether proposals (and the AI draft) are on, the templates, packages, block types
    and themes."""
    require_leads()
    return proposals("get_proposal_options") or {"enabled": False}


@frappe.whitelist(methods=["POST"])
def create_proposal(
    lead: str, template: str | None = None, ai_draft: int | str = 0
) -> dict:
    require_leads()
    return (
        proposals(
            "create_proposal",
            post=True,
            lead=lead,
            template=template or None,
            ai_draft=1 if cint(ai_draft) else 0,
        )
        or {}
    )


@frappe.whitelist()
def get_proposal(name: str) -> dict:
    require_leads()
    return proposals("get_proposal", name=name) or {}


@frappe.whitelist(methods=["POST"])
def save_proposal(name: str, data: dict | str) -> dict:
    require_leads()
    return (
        proposals("save_proposal", post=True, name=name, data=as_json_value(data)) or {}
    )


@frappe.whitelist()
def get_pricing_form(name: str) -> dict:
    require_leads()
    return proposals("get_pricing_form", name=name) or {}


@frappe.whitelist(methods=["POST"])
def save_pricing(name: str, values: dict | str) -> dict:
    require_leads()
    return (
        proposals("save_pricing", post=True, name=name, values=as_json_value(values))
        or {}
    )


@frappe.whitelist(methods=["POST"])
def request_approval(name: str, reason: str) -> dict:
    require_leads()
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Say why the pricing needs it."))
    return proposals("request_approval", post=True, name=name, reason=reason) or {}


@frappe.whitelist(methods=["POST"])
def send_proposal(
    name: str,
    recipients: str | None = None,
    message: str | None = None,
    attach_pdf: int | str = 0,
) -> dict:
    require_leads()
    return (
        proposals(
            "send_proposal",
            post=True,
            name=name,
            recipients=(recipients or "").strip() or None,
            message=(message or "").strip() or None,
            attach_pdf=1 if cint(attach_pdf) else 0,
        )
        or {}
    )


@frappe.whitelist(methods=["POST"])
def create_revision(name: str) -> dict:
    require_leads()
    return proposals("create_revision", post=True, name=name) or {}


@frappe.whitelist(methods=["POST"])
def save_template(data: dict | str) -> dict:
    require_leads()
    return proposals("save_template", post=True, data=as_json_value(data)) or {}


# ---------- the segment rate card (TBO Smart's hub leads API) ----------


@frappe.whitelist()
def get_rate_card() -> dict:
    require_leads()
    return call("get_rate_card") or {}


@frappe.whitelist(methods=["POST"])
def save_rate_card(rows: list | str) -> dict:
    require_leads()
    return call("save_rate_card", post=True, rows=as_json_value(rows, list)) or {}


@frappe.whitelist(methods=["POST"])
def set_segment_rate(
    item_code: str, rate: float | str, segment: str | None = None
) -> dict:
    require_leads()
    return (
        call(
            "set_segment_rate",
            post=True,
            item_code=item_code,
            rate=rate,
            segment=segment or None,
        )
        or {}
    )
