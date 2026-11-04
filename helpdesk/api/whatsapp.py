"""WhatsApp through TBO Chat: Settings → TBO Chat → WhatsApp, and the lead page's reply box
(docs/whatsapp-outreach.md). The sending itself is `helpdesk/whatsapp_outreach.py`."""

import frappe
from frappe import _

from helpdesk import whatsapp_outreach
from helpdesk.api.chatwoot_sso import check_admin
from helpdesk.integrations.crm.leads import call, require_leads

SETTINGS = whatsapp_outreach.SETTINGS
ERP_API = whatsapp_outreach.ERP_API
TEMPLATE_FIELDS = (
    "template_name",
    "language",
    "enabled",
    "is_default",
    "body",
    "variables",
)
PLAIN_FIELDS = ("whatsapp_inbox_id", "whatsapp_country_code", "whatsapp_auto_send")
MAX_TEXT_CHARS = 4000


def settings_payload(doc) -> dict:
    return {
        "settings": {f: doc.get(f) for f in PLAIN_FIELDS},
        "templates": [
            {f: row.get(f) for f in TEMPLATE_FIELDS} for row in doc.whatsapp_templates
        ],
        "connected": whatsapp_outreach.inbox_ready(doc),
        "chat_configured": bool(doc.enabled and doc.base_url),
    }


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return settings_payload(frappe.get_single(SETTINGS))


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str, templates: list | str | None = None) -> dict:
    """The WhatsApp inbox, the default country code, the automatic-send switch and (when
    sent) the whole template list."""
    check_admin()
    values = frappe.parse_json(values) or {}
    doc = frappe.get_single(SETTINGS)
    doc.update({k: v for k, v in values.items() if k in PLAIN_FIELDS})
    if templates is not None:
        doc.set("whatsapp_templates", [])
        for row in frappe.parse_json(templates) or []:
            doc.append(
                "whatsapp_templates",
                {f: row.get(f) for f in TEMPLATE_FIELDS if f in row},
            )
    doc.save(ignore_permissions=True)
    return settings_payload(frappe.get_single(SETTINGS))


@frappe.whitelist(methods=["POST"])
def sync_templates() -> dict:
    """Reads the approved templates of the WhatsApp inbox from TBO Chat. Also the way to
    check the connection: it says in words what is missing."""
    check_admin()
    try:
        counts = whatsapp_outreach.sync_templates()
    except whatsapp_outreach.SendFailure as error:
        return {"ok": False, "message": str(error)}
    return {
        "ok": True,
        "message": _(
            "{0} approved templates found: {1} new, {2} no longer approved."
        ).format(counts["found"], counts["added"], counts["removed"]),
        **settings_payload(frappe.get_single(SETTINGS)),
    }


@frappe.whitelist(methods=["POST"])
def reply(lead: str, text: str | None = None, template: str | None = None) -> dict:
    """Sends a WhatsApp message to a lead from its page, as the signed-in person: their own
    `text` when the lead wrote in the last 24 hours, otherwise the approved `template`
    (default: the first-message template) filled with the lead's details. It is filed on
    the lead's timeline. Raises in words when the lead cannot be written to."""
    require_leads()
    settings = whatsapp_outreach.get_settings()
    if not whatsapp_outreach.inbox_ready(settings):
        frappe.throw(
            _("WhatsApp isn't connected to TBO Chat yet. Use Open WhatsApp instead.")
        )
    state = call("get_lead_whatsapp", api=ERP_API, lead=lead)
    if not state.get("can_write"):
        frappe.throw(_("You can't write to this lead."), frappe.PermissionError)
    if state.get("blocked"):
        frappe.throw(state["blocked"])
    if not state.get("to"):
        frappe.throw(_("The lead has no usable mobile number."))
    text = (text or "").strip()[:MAX_TEXT_CHARS]
    if not (text or template or not state["window_open"]):
        frappe.throw(_("Write the message first."))
    detail = call("get_lead", name=lead)["lead"]
    try:
        sent = whatsapp_outreach.deliver(
            settings,
            state["to"],
            detail.get("lead_name") or lead,
            {
                **whatsapp_outreach.lead_facts(detail),
                "window_open": state["window_open"],
            },
            state.get("contact_id"),
            state.get("conversation_id"),
            template_name=template or None,
            text=text or None,
        )
    except whatsapp_outreach.SendFailure as error:
        frappe.throw(str(error))
    call(
        "log_lead_whatsapp",
        post=True,
        api=ERP_API,
        lead=lead,
        text=sent["text"],
        message_id=sent["message_id"],
        contact_id=sent["contact_id"],
        conversation_id=sent["conversation_id"],
    )
    return {
        "ok": True,
        "template": sent["template"],
        "chat_url": whatsapp_outreach.conversation_url(
            settings, sent["conversation_id"]
        ),
    }
