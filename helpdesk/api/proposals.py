"""Proposals and the segment rate card on the Leads page (docs/proposals.md). Thin proxies
to TBO Smart's hub proposals API (and the rate card in its hub leads API) on the CRM site,
as the signed-in person, the same way as helpdesk.api.leads. The CRM site decides who may
see, change and send what; the API key never leaves the hub."""

import base64

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.html_utils import sanitize_html

from helpdesk.integrations.crm.leads import call, require_leads

PROPOSALS = "tbo_smart.api.hub_proposals"


# the ERP site checks it too; refusing here spares sending a big file there
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def proposals(method: str, post: bool = False, **params):
    return call(method, post=post, api=PROPOSALS, **params)


def proposal(method: str, post: bool = False, **params) -> dict:
    """A call that answers with a proposal."""
    return clean_letter_head(proposals(method, post=post, **params) or {})


def clean_letter_head(data: dict) -> dict:
    """The letter head's HTML sanitised here too (the ERP site already did), since the
    preview renders it."""
    head = data.get("letter_head_preview") if isinstance(data, dict) else None
    for part in ("header", "footer"):
        if head and isinstance(head.get(part), dict) and head[part].get("html"):
            head[part]["html"] = sanitize_html(head[part]["html"], always_sanitize=True)
    return data


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
    result = (
        proposals(
            "create_proposal",
            post=True,
            lead=lead,
            template=template or None,
            ai_draft=1 if cint(ai_draft) else 0,
        )
        or {}
    )
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist()
def get_proposal(name: str) -> dict:
    require_leads()
    return proposal("get_proposal", name=name)


@frappe.whitelist(methods=["POST"])
def save_proposal(name: str, data: dict | str) -> dict:
    require_leads()
    return proposal("save_proposal", post=True, name=name, data=as_json_value(data))


@frappe.whitelist()
def get_pricing_form(name: str) -> dict:
    require_leads()
    return proposals("get_pricing_form", name=name) or {}


@frappe.whitelist(methods=["POST"])
def save_pricing(name: str, values: dict | str) -> dict:
    require_leads()
    return proposal("save_pricing", post=True, name=name, values=as_json_value(values))


@frappe.whitelist(methods=["POST"])
def request_approval(name: str, reason: str) -> dict:
    require_leads()
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Say why the pricing needs it."))
    return proposal("request_approval", post=True, name=name, reason=reason)


@frappe.whitelist(methods=["POST"])
def send_proposal(
    name: str,
    recipients: str | None = None,
    message: str | None = None,
    attach_pdf: int | str = 0,
) -> dict:
    require_leads()
    return proposal(
        "send_proposal",
        post=True,
        name=name,
        recipients=(recipients or "").strip() or None,
        message=(message or "").strip() or None,
        attach_pdf=1 if cint(attach_pdf) else 0,
    )


@frappe.whitelist(methods=["POST"])
def create_revision(name: str) -> dict:
    require_leads()
    return proposal("create_revision", post=True, name=name)


@frappe.whitelist(methods=["POST"])
def upload_proposal_image(name: str, filename: str, content: str) -> dict:
    """A private image on a draft, sent on to the ERP site (`content` base64). Returns
    {file, url}; the builder puts `file` in a block and saves."""
    require_leads()
    try:
        size = len(base64.b64decode(content or "", validate=True))
    except ValueError:  # binascii.Error is a ValueError
        frappe.throw(_("Send the image as base64."))
    if not size:
        frappe.throw(_("Choose an image to upload."))
    if size > MAX_IMAGE_BYTES:
        frappe.throw(_("The image is larger than 5 MB. Make it smaller and try again."))
    return (
        proposals(
            "upload_proposal_image",
            post=True,
            name=name,
            filename=(filename or "image")[:140],
            content=content,
        )
        or {}
    )


@frappe.whitelist(methods=["POST"])
def set_default_letter_head(letter_head: str | None = None) -> dict:
    """The letter head every proposal uses unless it picks another (editors only, checked
    on the ERP site). Returns the proposal options."""
    require_leads()
    return (
        proposals("set_default_letter_head", post=True, letter_head=letter_head or None)
        or {}
    )


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
