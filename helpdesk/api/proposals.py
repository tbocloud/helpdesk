"""Proposals, the client documents after them, and the segment rate card on the Leads
page (docs/proposals.md). Thin proxies
to TBO Smart's hub proposals API (and the rate card in its hub leads API) on the CRM site,
as the signed-in person, the same way as helpdesk.api.leads. The CRM site decides who may
see, change and send what; the API key never leaves the hub."""

import base64
import re

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.html_utils import sanitize_html

from helpdesk.integrations.crm.leads import call, require_leads

PROPOSALS = "tbo_smart.api.hub_proposals"


# the ERP site checks it too; refusing here spares sending a big file there
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# a website as people type it: vasthubuilders.com, https://www.client.co.in/about
WEBSITE = re.compile(
    r"^(https?://)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(/\S*)?$", re.I
)


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
    lead: str,
    template: str | None = None,
    ai_draft: int | str = 0,
    scoping: dict | str | None = None,
    requirements: str | None = None,
    client_profile: dict | str | None = None,
    chat: list | str | None = None,
) -> dict:
    require_leads()
    result = (
        proposals(
            "create_proposal",
            post=True,
            lead=lead,
            template=template or None,
            ai_draft=1 if cint(ai_draft) else 0,
            scoping=as_json_value(scoping) if scoping else None,
            requirements=(requirements or "").strip() or None,
            client_profile=as_json_value(client_profile) if client_profile else None,
            chat=as_json_value(chat, list) if chat else None,
        )
        or {}
    )
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


# the documents made from an accepted one (TBO Smart's docs/client-documents.md)
DOCUMENT_TYPES = ("Quotation", "Work Order", "BRD", "SRS")


@frappe.whitelist(methods=["POST"])
def create_document(source: str, document_type: str) -> dict:
    """The next client document, made on the ERP site from the accepted `source`
    (a quotation from a proposal, a project agreement from a quotation)."""
    require_leads()
    if document_type not in DOCUMENT_TYPES:
        frappe.throw(_("Pick a quotation, a project agreement, a BRD or an SRS."))
    result = (
        proposals(
            "create_document", post=True, source=source, document_type=document_type
        )
        or {}
    )
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


# --- a BRD's questionnaire for the client --------------------------------------


@frappe.whitelist(methods=["POST"])
def save_questions(name: str, questions: list | str) -> dict:
    """A draft BRD's questions for the client; the answered ones stay on the ERP site."""
    require_leads()
    return proposal(
        "save_questions", post=True, name=name, questions=as_json_value(questions, list)
    )


@frappe.whitelist(methods=["POST"])
def share_questionnaire(name: str) -> dict:
    """The client's questionnaire link (only the questions, never the draft)."""
    require_leads()
    result = proposals("share_questionnaire", post=True, name=name) or {}
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist(methods=["POST"])
def send_questionnaire(
    name: str, recipients: str | None = None, message: str | None = None
) -> dict:
    """Email the client the questionnaire link from the ERP site."""
    require_leads()
    result = (
        proposals(
            "send_questionnaire",
            post=True,
            name=name,
            recipients=(recipients or "").strip() or None,
            message=(message or "").strip() or None,
        )
        or {}
    )
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist(methods=["POST"])
def apply_answers(name: str) -> dict:
    """The client's new answers into the BRD (only the sections they touch)."""
    require_leads()
    result = proposals("apply_answers", post=True, name=name) or {}
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist()
def get_document_chain(lead: str) -> dict:
    """The lead's documents in order (Proposal → Quotation → Project Agreement), each
    with its status, and the one next action."""
    require_leads()
    return proposals("get_document_chain", lead=lead) or {"steps": [], "next": None}


@frappe.whitelist()
def get_proposal(name: str) -> dict:
    require_leads()
    return proposal("get_proposal", name=name)


@frappe.whitelist(methods=["POST"])
def save_proposal(name: str, data: dict | str) -> dict:
    require_leads()
    return proposal("save_proposal", post=True, name=name, data=as_json_value(data))


@frappe.whitelist()
def get_client_profile(lead: str) -> dict:
    """What the lead says about the client, and the website summary read earlier."""
    require_leads()
    return proposals("get_client_profile", lead=lead) or {}


@frappe.whitelist(methods=["POST"])
def read_client_website(
    lead: str, url: str | None = None, refresh: int | str = 0
) -> dict:
    """The client's website read and summarised on the ERP site (guarded there), kept on
    the lead."""
    require_leads()
    url = (url or "").strip()
    if url and not WEBSITE.match(url):
        frappe.throw(
            _(
                "That doesn't look like a website. Type it like vasthubuilders.com, or go on without one."
            )
        )
    return (
        proposals(
            "read_client_website",
            post=True,
            lead=lead,
            url=url or None,
            refresh=1 if cint(refresh) else 0,
        )
        or {}
    )


@frappe.whitelist()
def get_requirements_from_lead(lead: str) -> dict:
    """The lead's notes and minutes as one text, to start the requirements box (no AI)."""
    require_leads()
    return proposals("get_requirements_from_lead", lead=lead) or {}


@frappe.whitelist(methods=["POST"])
def extract_requirements(lead: str, text: str) -> dict:
    """The requirements box read into the scoping form by one small AI call; nothing saved."""
    require_leads()
    text = (text or "").strip()
    if not text:
        frappe.throw(_("Write or paste the client's requirements first."))
    return proposals("extract_requirements", post=True, lead=lead, text=text) or {}


@frappe.whitelist(methods=["POST"])
def regenerate_section(name: str, index: int | str, force: int | str = 0) -> dict:
    require_leads()
    result = (
        proposals(
            "regenerate_section",
            post=True,
            name=name,
            index=cint(index),
            force=1 if cint(force) else 0,
        )
        or {}
    )
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist(methods=["POST"])
def regenerate_proposal(name: str, force: int | str = 0) -> dict:
    require_leads()
    result = (
        proposals(
            "regenerate_proposal", post=True, name=name, force=1 if cint(force) else 0
        )
        or {}
    )
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist(methods=["POST"])
def chat_edit(name: str, message: str) -> dict:
    """The assistant: a change in words, read on the ERP site into structured changes."""
    require_leads()
    message = (message or "").strip()
    if not message:
        frappe.throw(_("Say what to change."))
    result = proposals("chat_edit", post=True, name=name, message=message[:1000]) or {}
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist(methods=["POST"])
def price_from_modules(name: str) -> dict:
    require_leads()
    return proposal("price_from_modules", post=True, name=name)


@frappe.whitelist(methods=["POST"])
def share_proposal(name: str) -> dict:
    """The client's link without an email (a draft goes out as Send does)."""
    require_leads()
    result = proposals("share_proposal", post=True, name=name) or {}
    if result.get("proposal"):
        clean_letter_head(result["proposal"])
    return result


@frappe.whitelist(methods=["POST"])
def use_library_image(name: str, image: str) -> dict:
    require_leads()
    return proposals("use_library_image", post=True, name=name, image=image) or {}


# ---------- the libraries (editors change them; checked on the ERP site) ----------


@frappe.whitelist()
def get_proposal_library() -> dict:
    require_leads()
    return proposals("get_proposal_library") or {}


@frappe.whitelist(methods=["POST"])
def save_library_record(kind: str, data: dict | str) -> dict:
    require_leads()
    return (
        proposals("save_library_record", post=True, kind=kind, data=as_json_value(data))
        or {}
    )


@frappe.whitelist(methods=["POST"])
def delete_library_record(kind: str, name: str) -> dict:
    require_leads()
    return proposals("delete_library_record", post=True, kind=kind, name=name) or {}


@frappe.whitelist(methods=["POST"])
def draft_library_module(module: str) -> dict:
    """The AI's draft of a catalogue module's text, for an editor to review (library upkeep)."""
    require_leads()
    return proposals("draft_library_module", post=True, module=module) or {}


@frappe.whitelist(methods=["POST"])
def upload_library_image(filename: str, content: str, data: dict | str) -> dict:
    require_leads()
    check_image_size(content)
    return (
        proposals(
            "upload_library_image",
            post=True,
            filename=(filename or "image")[:140],
            content=content,
            data=as_json_value(data),
        )
        or {}
    )


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
    check_image_size(content)
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


def check_image_size(content: str) -> None:
    """Refused here (before anything is sent on) when it isn't base64 or is over 5 MB."""
    try:
        size = len(base64.b64decode(content or "", validate=True))
    except ValueError:  # binascii.Error is a ValueError
        frappe.throw(_("Send the image as base64."))
    if not size:
        frappe.throw(_("Choose an image to upload."))
    if size > MAX_IMAGE_BYTES:
        frappe.throw(_("The image is larger than 5 MB. Make it smaller and try again."))


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
