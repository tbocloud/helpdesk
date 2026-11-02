# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""WhatsApp outreach through TBO Chat (docs/whatsapp-outreach.md).

The ERP site (TBO Smart) holds the lead and the outbox; this hub holds the Chatwoot
connection. When a BD approves a WhatsApp first message the ERP queues it, and
`send_pending` (every minute, and right after an approval) takes the queue, sends each
message through the WhatsApp inbox and reports back. WhatsApp only lets us start a
conversation with an approved template, so a message goes as free text only while the
lead's last message is less than 24 hours old (the ERP says so with `window_open`).

Replies and delivery receipts arrive on the bridge's webhooks (verified there, with its HMAC
check) and are handed here before the support AI sees them: a chat from a lead's number is
forwarded to the ERP, a chat from anyone else carries on as support. Calls to Chatwoot never
raise (see ChatwootClient); a failure becomes "failed" or "manual" on the message, in words.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint

from helpdesk.integrations.crm.client import CRMClient, CRMError

SETTINGS = "HD Chatwoot Settings"
ERP_API = "tbo_smart.api.hub_whatsapp"
RECEIPTS = ("sent", "delivered", "read", "failed")
BLANK = re.compile(r"\{\{\s*(\d+)\s*\}\}")
# what each blank may be filled with, and the words used when the lead has none of it
SOURCES = {
    "name": ("first_name", "there"),
    "company": ("company_name", "your business"),
    "why_call": ("why_call", "your business"),
}
DEFAULT_SOURCES = ("name", "why_call", "company")
MAX_VALUE_CHARS = 200
CATEGORY = "MARKETING"
APPROVED = "APPROVED"


class SendFailure(Exception):
    """A message TBO Chat did not take; the text is for the person."""


class NotReady(SendFailure):
    """WhatsApp is not set up far enough to send this one (no inbox, no template): the BD
    sends it by hand instead."""


def template_hint() -> str:
    return _("WhatsApp only allows approved message templates for a first message.")


def get_settings():
    return frappe.get_single(SETTINGS)


def inbox_ready(settings=None) -> bool:
    """TBO Chat is connected and a WhatsApp inbox is chosen."""
    settings = settings or get_settings()
    return bool(
        settings.enabled
        and settings.base_url
        and cint(settings.account_id)
        and cint(settings.whatsapp_inbox_id)
        and settings.get_password("api_access_token", raise_exception=False)
    )


def auto_send(settings=None) -> bool:
    """Approved WhatsApp messages go out by themselves."""
    settings = settings or get_settings()
    return inbox_ready(settings) and bool(settings.whatsapp_auto_send)


def client(settings=None):
    from helpdesk.chatwoot_bridge import ChatwootClient

    return ChatwootClient(settings or get_settings())


def erp(method: str, post: bool = False, **params):
    """The ERP site's `hub_whatsapp.<method>` as the hub's own integration user."""
    return CRMClient.from_settings().call(f"{ERP_API}.{method}", post=post, **params)


def conversation_url(settings, conversation_id) -> str | None:
    if not (conversation_id and settings.base_url and cint(settings.account_id)):
        return None
    return f"{settings.base_url}/app/accounts/{cint(settings.account_id)}/conversations/{conversation_id}"


# ---------- templates ----------


def usable_templates(settings=None) -> list:
    settings = settings or get_settings()
    return [row for row in settings.whatsapp_templates or [] if row.enabled]


def first_message_template(settings=None):
    """The template for a first message: the one ticked, else the first in use."""
    rows = usable_templates(settings)
    return next((row for row in rows if row.is_default), rows[0] if rows else None)


def find_template(name: str | None, settings=None):
    return next(
        (row for row in usable_templates(settings) if row.template_name == name), None
    )


def clean_value(value) -> str:
    """One line, no runs of spaces: WhatsApp rejects newlines and long gaps in a blank."""
    return " ".join(str(value or "").split())[:MAX_VALUE_CHARS]


def blanks_of(template) -> int:
    numbers = [int(n) for n in BLANK.findall(template.body or "")]
    return max(numbers) if numbers else 0


def variable_values(template, facts: dict) -> list[str]:
    """What fills {{1}}, {{2}}, … of `template` from the lead's facts (first_name,
    company_name, why_call). A blank with nothing to fill it gets a neutral word."""
    chosen = [part.strip() for part in (template.variables or "").split(",")]
    values = []
    for position in range(blanks_of(template)):
        wanted = chosen[position] if position < len(chosen) else ""
        if wanted not in SOURCES:
            wanted = DEFAULT_SOURCES[position % len(DEFAULT_SOURCES)]
        key, fallback = SOURCES[wanted]
        values.append(clean_value(facts.get(key)) or fallback)
    return values


def render(template, values: list[str]) -> str:
    return BLANK.sub(
        lambda found: values[int(found.group(1)) - 1]
        if 0 < int(found.group(1)) <= len(values)
        else found.group(0),
        template.body or "",
    )


def plan(facts: dict, settings=None, template_name: str | None = None) -> dict:
    """How a WhatsApp message to this lead would go, in words for the person:
    {mode: "text" | "template" | "manual", template, preview, note}. `facts` are first_name,
    company_name, why_call, window_open and the message `body`."""
    settings = settings or get_settings()
    if not inbox_ready(settings):
        return {"mode": "manual", "template": None, "preview": None, "note": None}
    if facts.get("window_open") and not template_name:
        return {
            "mode": "text",
            "template": None,
            "preview": facts.get("body"),
            "note": _("They wrote in the last 24 hours, so your own words can go."),
        }
    template = find_template(template_name, settings) or first_message_template(
        settings
    )
    if not template:
        return {
            "mode": "manual",
            "template": None,
            "preview": None,
            "note": f"{template_hint()} {_('Add an approved template in Settings → TBO Chat to send it from here.')}",
        }
    return {
        "mode": "template",
        "template": template.template_name,
        "preview": render(template, variable_values(template, facts)),
        "note": template_hint(),
    }


def sync_templates(settings=None) -> dict:
    """Reads the inbox's approved templates from Chatwoot into the settings table: new ones are
    added, known ones refreshed (keeping what the owner set), ones no longer approved are put
    out of use. Returns {found, added, removed}. Raises SendFailure in words when Chatwoot
    does not answer."""
    settings = settings or get_settings()
    if not inbox_ready(settings):
        raise SendFailure(
            _("Add the WhatsApp inbox ID and the TBO Chat connection first.")
        )
    inbox = client(settings).get_inbox(cint(settings.whatsapp_inbox_id))
    if inbox is None:
        raise SendFailure(
            _("TBO Chat did not answer. Check the Chatwoot URL, account and token.")
        )
    approved = {}
    for row in inbox.get("message_templates") or []:
        if str(row.get("status") or APPROVED).upper() == APPROVED and row.get("name"):
            approved[(row["name"], row.get("language") or "en")] = body_of(row)
    existing = {
        (row.template_name, row.language): row for row in settings.whatsapp_templates
    }
    added = 0
    for key, body in approved.items():
        if key in existing:
            existing[key].body, existing[key].enabled = body or existing[key].body, 1
        else:
            settings.append(
                "whatsapp_templates",
                {
                    "template_name": key[0],
                    "language": key[1],
                    "body": body or key[0],
                    "enabled": 1,
                },
            )
            added += 1
    removed = 0
    for key, row in existing.items():
        if key not in approved and row.enabled:
            row.enabled = 0
            removed += 1
    settings.save(ignore_permissions=True)
    return {"found": len(approved), "added": added, "removed": removed}


def body_of(template: dict) -> str:
    """The BODY text of a Chatwoot message template (Meta's "components")."""
    for component in template.get("components") or []:
        if str(component.get("type")).upper() == "BODY":
            return component.get("text") or ""
    return template.get("body") or ""


# ---------- sending ----------


def contact_for(api, settings, to: str, name: str, known) -> int:
    """The Chatwoot contact for this number: the one the ERP remembers, else one found by
    phone, else a new one."""
    if known:
        return cint(known)
    found = api.search_contacts(to)
    for contact in (found or {}).get("payload") or []:
        if contact.get("phone_number") == to:
            return cint(contact.get("id"))
    created = api.create_contact(cint(settings.whatsapp_inbox_id), name, to)
    contact = (created or {}).get("payload") or created or {}
    contact = contact.get("contact") or contact
    if not cint(contact.get("id")):
        raise SendFailure(_("TBO Chat could not add this number as a contact."))
    return cint(contact["id"])


def conversation_for(api, settings, contact_id: int, known) -> int:
    if known:
        return cint(known)
    opened = api.create_conversation(cint(settings.whatsapp_inbox_id), contact_id)
    if not cint((opened or {}).get("id")):
        raise SendFailure(_("TBO Chat could not open a WhatsApp conversation."))
    return cint(opened["id"])


def deliver(
    settings,
    to: str,
    name: str,
    facts: dict,
    contact_id=None,
    conversation_id=None,
    template_name: str | None = None,
    text: str | None = None,
) -> dict:
    """Sends one message to `to` (+E.164) through the WhatsApp inbox and returns
    {text, template, contact_id, conversation_id, message_id}. Free text only when the lead
    wrote in the last 24 hours (`facts.window_open`) and no template was asked for; otherwise
    an approved template. Raises SendFailure in words."""
    chosen = plan({**facts, "body": text}, settings, template_name)
    if chosen["mode"] == "manual":
        raise NotReady(chosen["note"] or _("WhatsApp is not connected yet."))
    api = client(settings)
    contact = contact_for(api, settings, to, name, contact_id)
    conversation = conversation_for(api, settings, contact, conversation_id)
    if chosen["mode"] == "text":
        sent = api.post_message(conversation, text)
        used = None
    else:
        template = find_template(chosen["template"], settings)
        sent = api.post_template(
            conversation,
            chosen["preview"],
            {
                "name": template.template_name,
                "category": CATEGORY,
                "language": template.language,
                "processed_params": {
                    str(position): value
                    for position, value in enumerate(
                        variable_values(template, facts), 1
                    )
                },
            },
        )
        used = template.template_name
    if not sent or not sent.get("id"):
        raise SendFailure(
            _("TBO Chat did not accept the message. Try again in a minute.")
        )
    return {
        "text": text if chosen["mode"] == "text" else chosen["preview"],
        "template": used,
        "contact_id": str(contact),
        "conversation_id": str(conversation),
        "message_id": str(sent["id"]),
    }


def send_pending() -> int:
    """Scheduler (every minute) and after an approval: sends the ERP's queue of approved
    WhatsApp messages and reports each. Returns how many were taken."""
    settings = get_settings()
    if not auto_send(settings):
        return 0
    try:
        queue = erp(
            "get_whatsapp_queue",
            country_code=settings.whatsapp_country_code or "91",
        )
    except CRMError:
        frappe.log_error(title=_("WhatsApp outreach: the ERP queue could not be read"))
        return 0
    for row in queue or []:
        send_one(settings, row)
    return len(queue or [])


def send_one(settings, row: dict) -> None:
    report = {"name": row["name"]}
    try:
        sent = deliver(
            settings,
            row["to"],
            row.get("lead_name") or row.get("company_name") or row["to"],
            row,
            row.get("contact_id"),
            row.get("conversation_id"),
            text=row.get("body"),
        )
        report.update(state="sent", **sent)
    except NotReady as error:
        report.update(state="manual", error=str(error))
    except SendFailure as error:
        report.update(state="failed", error=str(error))
    except Exception:  # noqa: BLE001 - one bad message must not stop the rest of the queue
        frappe.log_error(
            title=_("WhatsApp outreach: sending {0} failed").format(row["name"])
        )
        report.update(state="failed", error=_("TBO Chat could not send it."))
    try:
        erp("report_whatsapp", post=True, **report)
    except CRMError:
        frappe.log_error(
            title=_("WhatsApp outreach: reporting {0} failed").format(row["name"])
        )
    frappe.db.commit()  # nosemgrep - one message at a time, so a later failure never repeats a send


def send_soon() -> None:
    """Right after an approval, so the BD does not wait for the next minute."""
    frappe.enqueue(
        "helpdesk.whatsapp_outreach.send_pending",
        queue="short",
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )


# ---------- what Chatwoot sends us ----------


def inbox_of(payload: dict):
    return cint(
        (payload.get("inbox") or {}).get("id")
        or (payload.get("conversation") or {}).get("inbox_id")
    )


def in_outreach_inbox(settings, payload: dict) -> bool:
    inbox = cint(settings.whatsapp_inbox_id)
    return bool(inbox) and inbox_of(payload) == inbox


def is_receipt(settings, payload: dict) -> bool:
    """A delivery receipt (sent, delivered, read, failed) for a message we sent in the
    WhatsApp inbox."""
    return (
        in_outreach_inbox(settings, payload)
        and payload.get("message_type") in ("outgoing", 1)
        and not payload.get("private")
        and str(payload.get("status") or "").lower() in RECEIPTS
    )


def on_receipt(settings, payload: dict) -> bool:
    if not is_receipt(settings, payload):
        return False
    error = (payload.get("content_attributes") or {}).get("external_error")
    answer = erp(
        "whatsapp_status",
        post=True,
        message_id=str(payload.get("id")),
        status=str(payload["status"]).lower(),
        error=error,
    )
    return bool(answer and answer.get("matched"))


def phone_of(payload: dict) -> str:
    sender = payload.get("sender") or {}
    meta = (payload.get("conversation") or {}).get("meta", {}).get("sender") or {}
    phone = sender.get("phone_number") or meta.get("phone_number") or ""
    if not phone:
        source = ((payload.get("conversation") or {}).get("contact_inbox") or {}).get(
            "source_id"
        )
        phone = f"+{source}" if source and str(source).isdigit() else ""
    return phone


def on_incoming(settings, payload: dict) -> bool:
    """A message in the WhatsApp inbox from a lead's number goes to the ERP and is handled
    there (the lead's timeline, the reply sorter); True means the support AI must not see it.
    A chat from anyone else is not a lead's and carries on as support. When the ERP cannot
    be asked this raises, so the event shows as failed rather than the AI answering a lead."""
    if not in_outreach_inbox(settings, payload):
        return False
    text = (payload.get("content") or "").strip()
    if not text and payload.get("attachments"):
        text = _("(sent an attachment)")
    phone = phone_of(payload)
    if not (text and phone):
        return False
    conversation = payload.get("conversation") or {}
    sender = payload.get("sender") or {}
    answer = erp(
        "receive_whatsapp",
        post=True,
        phone=phone,
        text=text,
        conversation_id=str(conversation.get("id") or ""),
        contact_id=str(sender.get("id") or ""),
        message_id=str(payload.get("id") or ""),
        sender_name=sender.get("name"),
    )
    return bool(answer and answer.get("matched"))


# ---------- the lead page ----------


def lead_box(lead: dict, settings=None) -> dict:
    """What the lead page's WhatsApp card needs besides the ERP's own `lead.whatsapp`:
    {chat_ready, chat_url, templates: [{name, preview}], hint}. A template's preview is
    filled with this lead's facts."""
    settings = settings or get_settings()
    state = lead.get("whatsapp") or {}
    facts = lead_facts(lead)
    return {
        "chat_ready": inbox_ready(settings),
        "chat_url": conversation_url(settings, state.get("conversation_id")),
        "templates": [
            {
                "name": row.template_name,
                "preview": render(row, variable_values(row, facts)),
                "is_default": bool(row.is_default),
            }
            for row in usable_templates(settings)
        ],
        "hint": template_hint(),
    }


def lead_facts(lead: dict) -> dict:
    name = (lead.get("lead_name") or "").split()
    return {
        "first_name": name[0] if name else "",
        "company_name": lead.get("company_name"),
        "why_call": ((lead.get("prospect") or {}).get("why_call")),
    }
