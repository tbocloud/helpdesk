# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""TBO Chat (Chatwoot) <-> TBO Support bridge.

Chatwoot is the front door (website chat, later WhatsApp); TBO Support stays the
system of record for tickets, SLAs and tasks. One HD Chat Conversation row links
a Chatwoot conversation to its contact, customer and ticket.

- New chat in a bot inbox (status pending): TBO Support's AI answers from the
  knowledge base, raises a ticket when the team is needed, or hands the chat to
  a person. Any AI failure hands off too, so a customer is never left waiting.
- Label "ticket" on a conversation: an agent asks for a ticket by hand.
- Customer messages on a linked chat are added to the ticket; agent replies on
  the ticket are posted back to the chat.
- Ticket resolved: the chat is told and resolved. Chat reopened by the
  customer: the ticket reopens, unless it is Closed.

Webhooks are verified and logged by `receive_webhook` (one HD Chatwoot Event row
per message or change, which also absorbs Chatwoot's retries and the same event
arriving from both the account and the bot webhook) and processed in the
background by `process_event`. Calls to Chatwoot never raise: a failure is
logged and the rest of the processing carries on.
"""

import hashlib
import html
import json
import re

import frappe
import phonenumbers
import requests
from frappe import _
from frappe.utils import cint, escape_html, get_url, strip_html, validate_email_address
from pypika.functions import Replace

from helpdesk.ai_engine import call_haiku
from helpdesk.ai_suggestion import find_related_articles, is_ai_configured
from helpdesk.api.ticket_ai import html_to_text, text_to_html, truncate
from helpdesk.consts import CHAT_PLACEHOLDER_DOMAIN
from helpdesk.utils import get_customers

SETTINGS = "HD Chatwoot Settings"
CONVERSATION = "HD Chat Conversation"
EVENT = "HD Chatwoot Event"

HANDLED_EVENTS = (
    "message_created",
    "conversation_created",
    "conversation_updated",
    "conversation_status_changed",
)
REQUEST_TIMEOUT = 15
# room for a thinking model's second, larger attempt (see call_haiku)
AI_JOB_TIMEOUT = 360
TICKET_LABEL = "ticket"
CLOSED = "Closed"
DEFAULT_MAX_AI_REPLIES = 6

STATUSES = {
    "pending": "Pending",
    "open": "Open",
    "snoozed": "Open",
    "resolved": "Resolved",
}
# the messages API sends message_type as a number, webhooks as a name
MESSAGE_TYPES = {0: "incoming", 1: "outgoing", 2: "activity", 3: "template"}
CHANNEL_LABELS = {
    "Channel::WebWidget": "Website",
    "Channel::Whatsapp": "WhatsApp",
    "Channel::Api": "API",
    "Channel::Email": "Email",
    "Channel::Sms": "SMS",
    "Channel::TwilioSms": "SMS",
    "Channel::FacebookPage": "Facebook",
    "Channel::Instagram": "Instagram",
    "Channel::Telegram": "Telegram",
}
# a website visitor types any email they like; only Chatwoot's HMAC identity check proves it
SELF_ASSERTED_CHANNELS = ("Channel::WebWidget",)
AI_ACTIONS = ("answer", "ticket", "human")

MAX_TRANSCRIPT_MESSAGES = 20
MAX_MESSAGE_CHARS = 800
MAX_PROMPT_CHARS = 12000
MAX_DESCRIPTION_TRANSCRIPT_CHARS = 4000
MAX_SUBJECT_CHARS = 140
MAX_OPEN_TICKETS = 5
MIN_PHONE_DIGITS = 7
# a conversation's first events arrive together and race to create the same row or contact
SIBLING_RACE_ERRORS = (
    frappe.DuplicateEntryError,
    frappe.UniqueValidationError,
    frappe.QueryDeadlockError,
)
URL_PATTERN = re.compile(r"https?://[^\s<>()\"']+")
LINK_PATTERN = re.compile(
    r'(?is)<a\s[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>'
)

CHAT_SYSTEM_PROMPT = """You are TBO Support's assistant, answering a customer in a live chat (website chat or WhatsApp).
Our support team can see this chat and takes over whenever you hand it to them.

Write in the language of the customer's latest message (English if unsure). Be warm and brief: this is
chat, not email. Use 1-4 short sentences, no greeting after the first message, no signature.

Use only facts from the knowledge base articles, the customer's open tickets and the chat below.
Never invent causes, fixes, prices, refunds, dates, deadlines or commitments. When an article answers
the question, give the steps and you may add its URL exactly as given; never write any other URL.
Never claim to be a person.

Choose one action:
- "answer": you can answer from the articles or the chat, the customer is greeting you, asking about
  one of their open tickets, or you need one more detail before you can help (ask for it).
- "ticket": the customer reports a problem our team has to work on (an error, a bug, wrong data,
  a change or access request) and you know what is wrong and where. Fill ticket_subject (under 100
  characters) and ticket_summary (3-6 short lines: what happens, where, since when, the exact error
  text, what they tried). Your reply tells them the team will look into it; do not mention a ticket
  number, it is added for you. Do not raise a ticket for something an open ticket already covers.
- "human": the customer asks for a person, is upset, the question is about billing, contracts or
  prices, or you cannot help.

Reply with JSON only:
{"reply": "<the chat message>", "action": "answer, ticket or human",
 "ticket_subject": "<only for ticket>", "ticket_summary": "<only for ticket>"}"""

SUMMARY_SYSTEM_PROMPT = """You turn a support chat into a ticket for the support team.
Use only what the chat says; never invent details.
Reply with JSON only:
{"ticket_subject": "<under 100 characters: the problem, not the customer's name>",
 "ticket_summary": "<3-6 short lines: what happens, where, since when, the exact error text, what they tried>"}"""


def failure_text() -> str:
    return _(
        "Sorry, I couldn't look into this right now. I'm passing you to a teammate, who will reply here shortly."
    )


def handoff_text() -> str:
    return _(
        "I'm bringing in a teammate to help you further. They'll reply here shortly."
    )


def ticket_created_text(ticket: str) -> str:
    return _("I've created ticket #{0} for you — our team will follow up here.").format(
        ticket
    )


def resolved_text() -> str:
    return _("This has been resolved — reply here if anything else comes up.")


# --- receiving ---


def receive_webhook(source: str, raw: bytes, headers, token: str | None = None) -> dict:
    """Verify, deduplicate and log one delivery, then process it in the background."""
    settings = frappe.get_single(SETTINGS)
    settings.verify_webhook(source, raw, headers, token)

    payload = parse_payload(raw)
    event = str(payload.get("event") or "")
    note = ignore_reason(settings, event, payload)
    if note:
        return {"ok": True, "ignored": note}

    key = event_key(event, payload, raw)
    if frappe.db.exists(EVENT, key):
        return {"ok": True, "duplicate": True}
    try:
        row = frappe.get_doc(
            {
                "doctype": EVENT,
                "event_key": key,
                "event": event,
                "source": source,
                "conversation_id": conversation_id_of(event, payload),
                "status": "Queued",
                "payload": json.dumps(payload),
            }
        ).insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        # the other webhook delivered the same event while this one was being recorded
        frappe.clear_last_message()
        return {"ok": True, "duplicate": True}

    frappe.enqueue(
        "helpdesk.chatwoot_bridge.process_event",
        queue="short",
        timeout=AI_JOB_TIMEOUT,
        # not "event": frappe.enqueue has its own parameter by that name
        event_name=row.name,
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )
    return {"ok": True, "queued": row.name}


def parse_payload(raw: bytes) -> dict:
    try:
        payload = json.loads((raw or b"").decode("utf-8") or "{}")
    except ValueError:
        frappe.throw(_("The webhook body isn't valid JSON."))
    if not isinstance(payload, dict):
        frappe.throw(_("The webhook body isn't a JSON object."))
    return payload


def ignore_reason(settings, event: str, payload: dict) -> str | None:
    """Why a delivery needs no work; None when it does. Nothing is logged for these."""
    if event not in HANDLED_EVENTS:
        return _("Event {0} isn't used.").format(event or "-")
    account_id = (payload.get("account") or {}).get("id")
    if account_id and cint(account_id) != cint(settings.account_id):
        return _("Account {0} isn't the configured account.").format(account_id)
    if not conversation_id_of(event, payload):
        return _("The delivery names no conversation.")
    if event != "message_created":
        return None
    # our own replies, agents' replies and notes come back as outgoing or private messages
    if message_type_of(payload) != "incoming" or payload.get("private"):
        return _("Only customer messages are used.")
    if sender_type_of(payload) not in ("contact", ""):
        return _("Only customer messages are used.")
    return None


def event_key(event: str, payload: dict, raw: bytes) -> str:
    """Identical for the same event whichever webhook (account or bot) delivered it."""
    if event == "message_created":
        return f"message:{payload.get('id')}"
    conversation_id = conversation_id_of(event, payload)
    stamp = payload.get("updated_at") or payload.get("timestamp")
    if stamp:
        return f"{event}:{conversation_id}:{normalized_stamp(stamp)}"
    return f"{event}:{conversation_id}:{hashlib.sha256(raw or b'').hexdigest()[:32]}"


def normalized_stamp(stamp) -> str:
    """The account and bot webhooks print the same epoch time with different precision."""
    try:
        return f"{float(stamp):.6f}"
    except (TypeError, ValueError):
        return str(stamp)


def conversation_id_of(event: str, payload: dict) -> int:
    """The conversation's display id: the one Chatwoot's URLs and API use."""
    if event.startswith("message_"):
        return cint((payload.get("conversation") or {}).get("id"))
    return cint(payload.get("id"))


def message_type_of(message: dict) -> str:
    kind = message.get("message_type")
    if isinstance(kind, int):
        return MESSAGE_TYPES.get(kind, "")
    return str(kind or "")


def sender_type_of(message: dict) -> str:
    """contact, user or agent_bot."""
    sender = message.get("sender") or {}
    kind = sender.get("type") or message.get("sender_type") or ""
    return {"agentbot": "agent_bot"}.get(str(kind).lower(), str(kind).lower())


# --- processing ---


def process_event(event_name: str):
    """Background job: apply one logged delivery; a failure is recorded, never retried blindly."""
    doc = frappe.get_doc(EVENT, event_name)
    if doc.status != "Queued":
        return
    previous_user = frappe.session.user
    # the job inherits Guest from the webhook; tickets and contacts need a real user
    frappe.set_user("Administrator")  # see above - nosemgrep
    try:
        status, error = apply_event(doc)
    finally:
        # back to whoever enqueued it (Guest, or the test user)
        frappe.set_user(previous_user)  # see above - nosemgrep
    doc.db_set({"status": status, "error": error})


def apply_event(doc) -> tuple[str, str | None]:
    """The event's outcome and, when it failed, the traceback."""
    for attempt in (1, 2):
        frappe.db.savepoint("chatwoot_event")
        try:
            handled = ChatwootEvent(
                frappe.get_single(SETTINGS),
                doc.event,
                frappe.parse_json(doc.payload or "{}"),
            ).handle()
            return ("Processed" if handled else "Ignored"), None
        except SIBLING_RACE_ERRORS:
            if attempt == 2:
                return fail_event(doc)
            # the other event committed the row or contact after this job's snapshot
            # was taken; only a new transaction can read it
            start_fresh_transaction()
            frappe.clear_last_message()
        except Exception:
            return fail_event(doc)


def fail_event(doc) -> tuple[str, str]:
    frappe.db.rollback(save_point="chatwoot_event")
    frappe.log_error(
        title=_("Chatwoot event {0} failed").format(doc.name),
        reference_doctype=EVENT,
        reference_name=doc.name,
    )
    return "Failed", frappe.get_traceback()


def start_fresh_transaction():
    # everything the failed attempt wrote is redone by the retry
    frappe.db.rollback()


class ChatwootEvent:
    """One webhook event, routed to the conversation it belongs to."""

    def __init__(self, settings, event: str, payload: dict):
        self.settings = settings
        self.event = event
        self.payload = payload

    def handle(self) -> bool:
        """Returns whether the event changed anything we track."""
        if self.event == "message_created":
            return self.on_message()
        conversation = ChatConversation.sync(
            self.settings, self.payload, (self.payload.get("meta") or {}).get("sender")
        )
        if self.event == "conversation_updated":
            return conversation.on_labels(self.payload.get("labels") or [])
        if self.event == "conversation_status_changed":
            return conversation.on_status_changed()
        return True

    def on_message(self) -> bool:
        details = self.payload.get("conversation") or {}
        conversation = ChatConversation.sync(
            self.settings, details, self.payload.get("sender")
        )
        if conversation.row.hd_ticket and conversation.ticket_status() == CLOSED:
            conversation.release_closed_ticket(details.get("labels") or [])
        if conversation.row.hd_ticket:
            return conversation.add_customer_message(self.payload)
        if conversation.row.status == "Pending":
            return conversation.first_reply(self.payload)
        return False


class ChatConversation:
    """An HD Chat Conversation row, its Chatwoot conversation and the actions on both."""

    def __init__(self, row, settings, client: "ChatwootClient | None" = None):
        self.row = row
        self.settings = settings
        self.client = client or ChatwootClient(settings)

    @property
    def conversation_id(self) -> int:
        return cint(self.row.conversation_id)

    @classmethod
    def for_ticket(cls, ticket: str) -> "ChatConversation | None":
        name = frappe.db.get_value(CONVERSATION, {"hd_ticket": str(ticket)})
        if not name:
            return None
        return cls(frappe.get_doc(CONVERSATION, name), frappe.get_single(SETTINGS))

    # --- the row ---

    @classmethod
    def sync(cls, settings, details: dict, sender: dict | None) -> "ChatConversation":
        """The row for this Chatwoot conversation, created or refreshed from the payload.

        Rows are written with plain updates, and only when something changed, so
        a long AI job never holds a lock that the conversation's other events
        would wait on.
        """
        conversation_id = cint(details.get("id"))
        name = frappe.db.get_value(CONVERSATION, {"conversation_id": conversation_id})
        if name:
            conversation = cls(frappe.get_doc(CONVERSATION, name), settings)
            conversation.refresh(details, sender)
            return conversation
        conversation = cls(frappe.new_doc(CONVERSATION), settings)
        conversation.row.conversation_id = conversation_id
        conversation.apply_details(details, sender)
        conversation.match_contact()
        # when another event of this conversation inserts it first, the unique
        # conversation_id raises and process_event retries in a new transaction
        conversation.row.insert(ignore_permissions=True)
        return conversation

    def refresh(self, details: dict, sender: dict | None):
        before = self.row.as_dict()
        self.apply_details(details, sender)
        if not self.row.contact:
            self.match_contact()
        changed = {
            field: self.row.get(field)
            for field in (
                "status",
                "channel",
                "inbox_id",
                "contact_name",
                "contact_email",
                "contact_phone",
                "chatwoot_contact_id",
                "identity_verified",
                "contact",
                "hd_customer",
            )
            if self.row.get(field) != before.get(field)
        }
        self.set_values(changed)

    def apply_details(self, details: dict, sender: dict | None):
        """Copy what the payload knows; a missing value never erases a stored one."""
        sender = sender or (details.get("meta") or {}).get("sender") or {}
        status = STATUSES.get(str(details.get("status") or ""))
        if status:
            self.row.status = status
        if details.get("channel"):
            self.row.channel = details["channel"]
        if details.get("inbox_id"):
            self.row.inbox_id = cint(details["inbox_id"])
        if sender.get("id"):
            self.row.chatwoot_contact_id = cint(sender["id"])
        if (sender.get("name") or "").strip():
            self.row.contact_name = sender["name"].strip()[:140]
        email = validate_email_address((sender.get("email") or "").strip())
        if email and "," not in email:
            self.row.contact_email = email.lower()
        if (sender.get("phone_number") or "").strip():
            self.row.contact_phone = sender["phone_number"].strip()
        meta = details.get("meta") or {}
        channel = self.row.channel or ""
        if meta or channel:
            self.row.identity_verified = int(
                bool(meta.get("hmac_verified"))
                or (bool(channel) and channel not in SELF_ASSERTED_CHANNELS)
            )

    def match_contact(self):
        """Link the chat to a TBO Support contact and customer, creating the contact if new."""
        matcher = ContactMatcher(self.row.contact_email, self.row.contact_phone)
        contact = matcher.find_contact()
        created = False
        if not contact and matcher.has_details():
            contact = matcher.create_contact(
                self.row.contact_name, self.settings.default_customer
            )
            created = True
        if contact:
            self.row.contact = contact
        default = self.settings.default_customer or None
        customer = matcher.find_customer(contact)
        if customer:
            # a real match replaces the stand-in customer an anonymous chat got
            if not self.row.hd_customer or self.row.hd_customer == default:
                self.row.hd_customer = customer
        elif not self.row.hd_customer and (created or not contact):
            self.row.hd_customer = default

    def set_values(self, values: dict):
        if not values or not self.row.name:
            return
        self.row.update(values)
        frappe.db.set_value(CONVERSATION, self.row.name, values)

    def lock(self):
        """Re-read the row under a row lock, so two jobs can't both act on the same chat."""
        values = frappe.db.get_value(
            CONVERSATION,
            self.row.name,
            ["hd_ticket", "status", "ai_reply_count", "last_synced_message_id"],
            as_dict=True,
            for_update=True,
        )
        self.row.update(values or {})

    # --- webhook events ---

    def on_labels(self, labels: list) -> bool:
        """An agent asks for a ticket by adding the label; it is created once."""
        if self.row.hd_ticket or TICKET_LABEL not in normalize_labels(labels):
            return True
        messages = self.fetch_messages()
        subject, summary = self.summarise(messages)
        self.lock()
        if self.row.hd_ticket:
            return True
        ticket = self.create_ticket(subject, summary, messages)
        self.client.post_message(
            self.conversation_id,
            _("TBO Support ticket #{0} created: {1}").format(
                ticket, get_url(f"/helpdesk/tickets/{ticket}")
            ),
            private=True,
        )
        return True

    def on_status_changed(self) -> bool:
        """Reopened by the customer: the ticket reopens too, unless it was Closed."""
        if self.row.status != "Open" or not self.row.hd_ticket:
            return True
        ticket = frappe.get_doc("HD Ticket", self.row.hd_ticket)
        if ticket.status_category != "Resolved" or ticket.status == CLOSED:
            return True
        ticket.status = ticket.ticket_reopen_status or "Open"
        ticket.save(ignore_permissions=True)
        return True

    # --- customer messages on a linked ticket ---

    def ticket_status(self) -> str | None:
        return frappe.db.get_value("HD Ticket", self.row.hd_ticket, "status")

    def release_closed_ticket(self, labels: list):
        """A closed ticket stays closed: the chat is unlinked and the agents are told how to open a new one."""
        ticket = self.row.hd_ticket
        self.set_values({"hd_ticket": None})
        remaining = [
            label for label in normalize_labels(labels) if label != TICKET_LABEL
        ]
        if len(remaining) != len(normalize_labels(labels)):
            # otherwise the next change to the chat would open a ticket nobody asked for
            self.client.set_labels(self.conversation_id, remaining)
        self.client.post_message(
            self.conversation_id,
            _(
                'Ticket #{0} is closed, so new messages are not added to it. Add the label "{1}" to open a new ticket.'
            ).format(ticket, TICKET_LABEL),
            private=True,
        )

    def add_customer_message(self, message: dict) -> bool:
        """The customer's chat message becomes a received reply on the ticket, once."""
        message_id = cint(message.get("id"))
        self.lock()
        if not self.row.hd_ticket or message_id <= cint(
            self.row.last_synced_message_id
        ):
            return False
        ticket = frappe.get_doc("HD Ticket", self.row.hd_ticket)
        communication = frappe.get_doc(
            {
                "doctype": "Communication",
                "communication_type": "Communication",
                "communication_medium": "Chat",
                "sent_or_received": "Received",
                "email_status": "Open",
                "status": "Linked",
                "subject": f"Re: {ticket.subject}",
                "sender": self.sender_address(),
                "sender_full_name": self.row.contact_name or None,
                "content": message_html(message),
                "reference_doctype": "HD Ticket",
                "reference_name": ticket.name,
            }
        )
        # tells on_communication_insert this came from the chat, so it isn't echoed back
        communication.flags.from_chatwoot = True
        communication.insert(ignore_permissions=True)
        self.set_values({"last_synced_message_id": message_id})
        if self.row.status == "Pending":
            # a bot inbox parks the reopened chat with the bot; the ticket's agents answer it
            self.hand_off()
        return True

    # --- AI first reply ---

    def first_reply(self, message: dict) -> bool:
        if not self.client.bot_token:
            # without the bot, people answer in Chatwoot as usual
            return False
        if not self.settings.ai_first_reply or not is_ai_configured():
            return self.hand_off()
        max_replies = cint(self.settings.max_ai_replies or DEFAULT_MAX_AI_REPLIES)
        if cint(self.row.ai_reply_count) >= max_replies:
            return self.hand_off(handoff_text())

        message_id = cint(message.get("id"))
        messages = self.fetch_messages() or [message]
        if any(
            message_type_of(m) == "incoming" and cint(m.get("id")) > message_id
            for m in messages
        ):
            # a newer message is on its way; its job answers with the fuller chat
            return False
        try:
            articles = self.find_articles(messages)
            result = call_haiku(
                CHAT_SYSTEM_PROMPT, self.build_prompt(messages, articles)
            )
            decision = parse_decision(result.get("response"), articles)
            if not decision:
                raise ValueError(
                    "AI chat reply was empty or not JSON: "
                    + str(result.get("response"))[:1000]
                )
        except Exception:  # noqa: BLE001 - whatever failed, the customer gets a person
            frappe.log_error(
                title=_("TBO Chat AI reply failed for conversation {0}").format(
                    self.conversation_id
                ),
                message=frappe.get_traceback(),
            )
            return self.hand_off(failure_text())
        return self.act_on(decision, messages)

    def act_on(self, decision: dict, messages: list[dict]) -> bool:
        self.lock()
        if self.row.status != "Pending" or self.row.hd_ticket:
            # a person or another job took the chat over while the AI was thinking
            return False
        if decision["action"] == "ticket":
            ticket = self.create_ticket(
                decision["ticket_subject"] or self.fallback_subject(messages),
                decision["ticket_summary"],
                messages,
            )
            reply = "\n\n".join(
                part
                for part in (decision["reply"], ticket_created_text(ticket))
                if part
            )
            return self.hand_off(reply)
        if decision["action"] == "human":
            return self.hand_off(decision["reply"] or handoff_text())
        if (
            self.client.post_message(
                self.conversation_id, decision["reply"], as_bot=True
            )
            is None
        ):
            return self.hand_off()
        self.set_values({"ai_reply_count": cint(self.row.ai_reply_count) + 1})
        return True

    def hand_off(self, text: str | None = None) -> bool:
        """The chat leaves the bot: open for people, and on the hand-off team when one is set."""
        if text:
            self.client.post_message(self.conversation_id, text, as_bot=True)
        self.client.toggle_status(self.conversation_id, "open", as_bot=True)
        if cint(self.settings.handoff_team_id):
            self.client.assign_team(
                self.conversation_id, cint(self.settings.handoff_team_id), as_bot=True
            )
        self.set_values({"status": "Open"})
        return True

    def find_articles(self, messages: list[dict]) -> list[dict]:
        customer_text = [
            message_text(m) for m in messages if message_type_of(m) == "incoming"
        ]
        if not customer_text:
            return []
        # find_related_articles reads keywords from a ticket's subject and description
        return find_related_articles(
            frappe._dict(
                subject=customer_text[-1][:200],
                description="\n".join(reversed(customer_text)),
            )
        )

    def build_prompt(self, messages: list[dict], articles: list[dict]) -> str:
        lines = []
        if self.row.contact_name:
            lines.append(f"Customer name: {self.row.contact_name}")
        if self.row.hd_customer and self.row.hd_customer != (
            self.settings.default_customer or None
        ):
            lines.append(f"Customer organisation: {self.row.hd_customer}")
        tickets = self.open_tickets()
        if tickets:
            lines.append(
                "The customer's open tickets:\n"
                + "\n".join(f"- #{t.name} {t.subject} ({t.status})" for t in tickets)
            )
        if articles:
            lines.append(
                "Knowledge base articles:\n"
                + "\n".join(
                    f"- {a['title']}\n  URL: {a['url']}\n  Excerpt: {a['excerpt']}"
                    for a in articles
                )
            )
        else:
            lines.append("Knowledge base articles: none match this chat.")
        lines.append("The chat so far, oldest first (the last one is the latest):")
        lines.extend(transcript_lines(messages))
        prompt = "\n\n".join(lines)
        # keep the tail: the latest messages matter most
        return prompt if len(prompt) <= MAX_PROMPT_CHARS else prompt[-MAX_PROMPT_CHARS:]

    def open_tickets(self) -> list:
        """The contact's own open tickets, and only when the chat proves who they are.

        Matching by customer would show a colleague's tickets, and a website
        visitor can type anyone's email.
        """
        if not self.row.identity_verified or not (
            self.row.contact or self.row.contact_email
        ):
            return []
        ticket = frappe.qb.DocType("HD Ticket")
        owner = []
        if self.row.contact:
            owner.append(ticket.contact == self.row.contact)
        if self.row.contact_email:
            owner.append(ticket.raised_by == self.row.contact_email)
        condition = owner[0] if len(owner) == 1 else owner[0] | owner[1]
        return (
            frappe.qb.from_(ticket)
            .select(ticket.name, ticket.subject, ticket.status)
            .where(condition)
            .where(ticket.status_category != "Resolved")
            .orderby(ticket.modified, order=frappe.qb.desc)
            .limit(MAX_OPEN_TICKETS)
            .run(as_dict=True)
        )

    # --- tickets ---

    def summarise(self, messages: list[dict]) -> tuple[str, str]:
        """(subject, summary) for a hand-made ticket: the AI's when it can, else the first message."""
        if is_ai_configured() and messages:
            try:
                result = call_haiku(
                    SUMMARY_SYSTEM_PROMPT, "\n\n".join(transcript_lines(messages))
                )
                response = result.get("response")
                if isinstance(response, dict) and not response.get("parse_error"):
                    subject = one_line(response.get("ticket_subject"))
                    summary = html_to_text(str(response.get("ticket_summary") or ""))
                    if subject:
                        return subject, summary
            except Exception:  # noqa: BLE001 - the transcript alone still makes a ticket
                frappe.log_error(
                    title=_(
                        "TBO Chat ticket summary failed for conversation {0}"
                    ).format(self.conversation_id),
                    message=frappe.get_traceback(),
                )
        return self.fallback_subject(messages), ""

    def fallback_subject(self, messages: list[dict]) -> str:
        for message in messages:
            if message_type_of(message) == "incoming":
                text = one_line(message_text(message))
                if text:
                    return truncate(text, 100)
        return _("Chat with {0}").format(self.row.contact_name or _("a customer"))

    def create_ticket(self, subject: str, summary: str, messages: list[dict]) -> str:
        """A ticket from this chat, linked to it; the caller holds the row lock."""
        ticket = frappe.get_doc(
            {
                "doctype": "HD Ticket",
                "subject": truncate(one_line(subject), MAX_SUBJECT_CHARS - 2),
                "description": self.ticket_description(summary, messages),
                "raised_by": self.sender_address(),
                "contact": self.row.contact or None,
                "customer": self.row.hd_customer or None,
            }
        )
        ticket.insert(ignore_permissions=True)
        self.attribute_opening_message(ticket.name)
        synced = max(
            [cint(m.get("id")) for m in messages]
            + [cint(self.row.last_synced_message_id)]
        )
        self.set_values(
            {"hd_ticket": str(ticket.name), "last_synced_message_id": synced}
        )
        return ticket.name

    def ticket_description(self, summary: str, messages: list[dict]) -> str:
        parts = []
        if summary:
            parts.append(text_to_html(summary))
        transcript = "\n\n".join(transcript_lines(messages))
        if len(transcript) > MAX_DESCRIPTION_TRANSCRIPT_CHARS:
            transcript = "…" + transcript[-MAX_DESCRIPTION_TRANSCRIPT_CHARS:]
        if transcript:
            parts.append(f"<p><strong>{escape_html(_('Chat transcript'))}</strong></p>")
            parts.append(text_to_html(transcript))
        channel = CHANNEL_LABELS.get(self.row.channel or "", self.row.channel or "")
        origin = _("Raised from TBO Chat conversation #{0}").format(
            self.conversation_id
        )
        link = f"{self.settings.base_url}/app/accounts/{cint(self.settings.account_id)}/conversations/{self.conversation_id}"
        note = f'<a href="{escape_html(link)}">{escape_html(origin)}</a>'
        if channel:
            note += f" ({escape_html(channel)})"
        if not self.row.identity_verified:
            note += ". " + escape_html(
                _(
                    "The customer's email or phone was typed in the chat and isn't verified."
                )
            )
        parts.append(f"<p>{note}</p>")
        return "".join(parts)

    def attribute_opening_message(self, ticket: str):
        """HD Ticket records its description as a message from the session user (Administrator here); it is the customer's."""
        communication = frappe.qb.DocType("Communication")
        query = (
            frappe.qb.update(communication)
            .set(communication.sender, self.sender_address())
            .set(communication.communication_medium, "Chat")
            .where(communication.reference_doctype == "HD Ticket")
            .where(communication.reference_name == ticket)
            .where(communication.sent_or_received == "Received")
        )
        if self.row.contact_name:
            query = query.set(communication.sender_full_name, self.row.contact_name)
        query.run()

    def sender_address(self) -> str:
        return (
            self.row.contact_email
            or f"chat-{self.conversation_id}@{CHAT_PLACEHOLDER_DOMAIN}"
        )

    # --- messages from TBO Support ---

    def post_agent_reply(self, content: str) -> bool:
        text = html_to_chat_text(content)
        if not text:
            return False
        return self.client.post_message(self.conversation_id, text) is not None

    def announce_resolution(self):
        self.client.post_message(self.conversation_id, resolved_text())
        self.client.toggle_status(self.conversation_id, "resolved")
        self.set_values({"status": "Resolved"})

    def fetch_messages(self) -> list[dict]:
        """The latest messages, oldest first; empty when Chatwoot can't be reached."""
        data = self.client.get_messages(self.conversation_id)
        messages = (data or {}).get("payload") if isinstance(data, dict) else data
        if not isinstance(messages, list):
            return []
        messages = [m for m in messages if isinstance(m, dict)]
        messages.sort(key=lambda m: cint(m.get("id")))
        return messages[-MAX_TRANSCRIPT_MESSAGES:]


class ContactMatcher:
    """Finds the TBO Support contact and customer behind a chat's email or phone."""

    def __init__(self, email: str | None, phone: str | None):
        self.email = (email or "").strip().lower()
        self.phone = (phone or "").strip()

    def has_details(self) -> bool:
        return bool(self.email or self.national_number())

    def find_contact(self) -> str | None:
        return self.contact_by_email() or self.contact_by_phone()

    def contact_by_email(self) -> str | None:
        if not self.email:
            return None
        contact = frappe.db.get_value("Contact", {"email_id": self.email})
        if contact:
            return contact
        return frappe.db.get_value(
            "Contact Email",
            {"email_id": self.email, "parenttype": "Contact"},
            "parent",
        )

    def contact_by_phone(self) -> str | None:
        """Compares national numbers, so +971 50 123 4567 matches a stored 050-1234567."""
        number = self.national_number()
        if not number:
            return None
        pattern = f"%{number}"
        contact = frappe.qb.DocType("Contact")
        rows = (
            frappe.qb.from_(contact)
            .select(contact.name)
            .where(
                normalized_phone(contact.mobile_no).like(pattern)
                | normalized_phone(contact.phone).like(pattern)
            )
            .orderby(contact.modified, order=frappe.qb.desc)
            .limit(1)
            .run(pluck="name")
        )
        if rows:
            return rows[0]
        phone = frappe.qb.DocType("Contact Phone")
        rows = (
            frappe.qb.from_(phone)
            .select(phone.parent)
            .where(phone.parenttype == "Contact")
            .where(normalized_phone(phone.phone).like(pattern))
            .limit(1)
            .run(pluck="parent")
        )
        return rows[0] if rows else None

    def national_number(self) -> str:
        """The number without country code or trunk zero; empty when too short to match safely."""
        if not self.phone:
            return ""
        digits = re.sub(r"\D", "", self.phone)
        try:
            parsed = phonenumbers.parse(
                self.phone if self.phone.startswith("+") else f"+{digits}", None
            )
            digits = str(parsed.national_number)
        except phonenumbers.NumberParseException:
            digits = digits.lstrip("0")
        return digits if len(digits) >= MIN_PHONE_DIGITS else ""

    def find_customer(self, contact: str | None) -> str | None:
        """The contact's customer when it has exactly one, else a customer with this email or phone."""
        if contact:
            customers = get_customers(contact=contact)
            if len(customers) == 1:
                return customers[0]
            if customers:
                return None
        if self.email:
            customer = frappe.db.get_value("HD Customer", {"email_id": self.email})
            if customer:
                return customer
        number = self.national_number()
        if number:
            customer = frappe.qb.DocType("HD Customer")
            rows = (
                frappe.qb.from_(customer)
                .select(customer.name)
                .where(normalized_phone(customer.mobile_no).like(f"%{number}"))
                .limit(1)
                .run(pluck="name")
            )
            if rows:
                return rows[0]
        return None

    def create_contact(self, name: str | None, customer: str | None) -> str:
        contact = frappe.get_doc(
            {
                "doctype": "Contact",
                "first_name": (name or self.email or self.phone or _("Chat contact"))[
                    :140
                ],
            }
        )
        if self.email:
            contact.append("email_ids", {"email_id": self.email, "is_primary": 1})
        if self.phone:
            contact.append(
                "phone_nos", {"phone": self.phone, "is_primary_mobile_no": 1}
            )
        contact.insert(ignore_permissions=True)
        if customer:
            doc = frappe.get_doc("HD Customer", customer)
            doc.append("contacts", {"contact_name": contact.name})
            doc.save(ignore_permissions=True)
        return contact.name


class ChatwootClient:
    """Chatwoot's REST API. Every failure is logged and answered with None, never raised."""

    def __init__(self, settings):
        self.base = f"{(settings.base_url or '').rstrip('/')}/api/v1/accounts/{cint(settings.account_id)}"
        self.user_token = settings.get_password(
            "api_access_token", raise_exception=False
        )
        self.bot_token = settings.get_password(
            "bot_access_token", raise_exception=False
        )

    def get_messages(self, conversation_id: int):
        return self.request("GET", f"/conversations/{conversation_id}/messages")

    def post_message(
        self,
        conversation_id: int,
        content: str,
        private: bool = False,
        as_bot: bool = False,
    ):
        return self.request(
            "POST",
            f"/conversations/{conversation_id}/messages",
            {
                "content": content,
                "message_type": "outgoing",
                "private": private,
                "content_type": "text",
            },
            as_bot=as_bot,
        )

    def toggle_status(self, conversation_id: int, status: str, as_bot: bool = False):
        return self.request(
            "POST",
            f"/conversations/{conversation_id}/toggle_status",
            {"status": status},
            as_bot=as_bot,
        )

    def assign_team(self, conversation_id: int, team_id: int, as_bot: bool = False):
        return self.request(
            "POST",
            f"/conversations/{conversation_id}/assignments",
            {"team_id": team_id},
            as_bot=as_bot,
        )

    def set_labels(self, conversation_id: int, labels: list[str]):
        """Chatwoot replaces the conversation's labels with this list."""
        return self.request(
            "POST", f"/conversations/{conversation_id}/labels", {"labels": labels}
        )

    def request(
        self, method: str, path: str, body: dict | None = None, as_bot: bool = False
    ):
        # the bot may only post, toggle and assign; everything else goes through the bridge user
        token = (self.bot_token if as_bot else None) or self.user_token
        if not token:
            frappe.log_error(
                title=_("TBO Chat request skipped"),
                message=f"{method} {path}: no access token in {SETTINGS}",
            )
            return None
        try:
            response = requests.request(
                method,
                self.base + path,
                json=body,
                # dashes, not underscores: proxies such as Caddy/nginx drop
                # underscore header names, and Chatwoot reads both spellings
                headers={"Api-Access-Token": token, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            frappe.log_error(
                title=_("TBO Chat request failed"),
                message=f"{method} {path}\n{frappe.get_traceback()}",
            )
            return None
        if response.status_code >= 400:
            frappe.log_error(
                title=_("TBO Chat request failed"),
                message=f"{method} {path}: HTTP {response.status_code}\n{(response.text or '')[:1000]}",
            )
            return None
        try:
            return response.json()
        except ValueError:
            return {}


# --- hooks from TBO Support ---


def on_communication_insert(doc, method=None):
    """Communication after_insert: an agent's reply on a chat ticket goes to the chat too."""
    try:
        if (
            doc.reference_doctype != "HD Ticket"
            or doc.sent_or_received != "Sent"
            or doc.communication_type != "Communication"
            or doc.flags.from_chatwoot
            or not is_enabled()
        ):
            return
        if not frappe.db.exists(CONVERSATION, {"hd_ticket": str(doc.reference_name)}):
            return
        frappe.enqueue(
            "helpdesk.chatwoot_bridge.post_agent_reply",
            queue="short",
            communication=doc.name,
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )
    except Exception:  # noqa: BLE001 - the agent's reply must go through whatever happens here
        frappe.log_error(
            title=_("TBO Chat reply not queued"), message=frappe.get_traceback()
        )


def on_ticket_update(doc, method=None):
    """HD Ticket on_update: a chat ticket that becomes resolved tells the chat and resolves it."""
    try:
        before = doc.get_doc_before_save()
        if (
            not before
            or doc.status_category != "Resolved"
            or before.status_category == "Resolved"
            or not is_enabled()
        ):
            return
        conversation = frappe.db.get_value(
            # ticket names are numbers; a string keeps the lookup on the index
            CONVERSATION,
            {"hd_ticket": str(doc.name), "status": ("!=", "Resolved")},
        )
        if conversation:
            frappe.enqueue(
                "helpdesk.chatwoot_bridge.announce_resolution",
                queue="short",
                conversation=conversation,
                enqueue_after_commit=True,
                now=frappe.flags.in_test,
            )
    except Exception:  # noqa: BLE001 - resolving the ticket must not fail over the chat
        frappe.log_error(
            title=_("TBO Chat resolution not queued"), message=frappe.get_traceback()
        )


def post_agent_reply(communication: str):
    """Background job: post an agent's ticket reply into the linked chat."""
    row = frappe.db.get_value(
        "Communication", communication, ["reference_name", "content"], as_dict=True
    )
    if not row:
        return
    conversation = ChatConversation.for_ticket(row.reference_name)
    if conversation:
        conversation.post_agent_reply(row.content)


def announce_resolution(conversation: str):
    """Background job: tell the chat its ticket is resolved and resolve the conversation."""
    ChatConversation(
        frappe.get_doc(CONVERSATION, conversation), frappe.get_single(SETTINGS)
    ).announce_resolution()


def is_enabled() -> bool:
    return bool(frappe.db.get_single_value(SETTINGS, "enabled"))


# --- text ---


def parse_decision(response, articles: list[dict]) -> dict | None:
    """The AI's reply and action; None for an empty or unreadable answer."""
    if not isinstance(response, dict) or response.get("parse_error"):
        return None
    reply = remove_unknown_urls(
        html_to_text(str(response.get("reply") or "")), articles
    )
    action = str(response.get("action") or "").strip().lower()
    if action not in AI_ACTIONS:
        # unsure what it meant: a person decides
        action = "human"
    if not reply and action == "answer":
        return None
    return {
        "reply": reply,
        "action": action,
        "ticket_subject": one_line(response.get("ticket_subject")),
        "ticket_summary": html_to_text(str(response.get("ticket_summary") or "")),
    }


def remove_unknown_urls(text: str, articles: list[dict]) -> str:
    """The customer reads this unreviewed, so only the article URLs we gave the model survive."""
    allowed = [a["url"] for a in articles]

    def keep(match):
        url = match.group(0).rstrip(".,;:!?")
        if any(url == a or url.startswith(a + "#") for a in allowed):
            return match.group(0)
        return ""

    text = URL_PATTERN.sub(keep, text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def transcript_lines(messages: list[dict]) -> list[str]:
    lines = []
    for message in messages:
        kind = message_type_of(message)
        if kind not in ("incoming", "outgoing") or message.get("private"):
            continue
        text = truncate(message_text(message), MAX_MESSAGE_CHARS)
        if not text:
            continue
        if kind == "incoming":
            role = "Customer"
        elif sender_type_of(message) == "agent_bot":
            role = "You (assistant)"
        else:
            role = "Agent"
        lines.append(f"[{role}]\n{text}")
    return lines


def message_text(message: dict) -> str:
    text = html_to_text(str(message.get("content") or ""))
    attachments = [a for a in message.get("attachments") or [] if isinstance(a, dict)]
    if attachments:
        kinds = ", ".join(str(a.get("file_type") or "file") for a in attachments)
        text = f"{text}\n[{_('Attachment')}: {kinds}]".strip()
    return text


def message_html(message: dict) -> str:
    """A chat message as ticket HTML, attachments as links (Chatwoot serves them)."""
    parts = [text_to_html(html_to_text(str(message.get("content") or "")))]
    for attachment in message.get("attachments") or []:
        url = str((attachment or {}).get("data_url") or "")
        if url.startswith(("https://", "http://")):
            label = _("Attachment ({0})").format(attachment.get("file_type") or "file")
            parts.append(
                f'<p><a href="{escape_html(url)}">{escape_html(label)}</a></p>'
            )
    return "".join(parts) or "<p></p>"


def html_to_chat_text(content: str | None) -> str:
    """An agent's HTML reply as chat text, links kept as Markdown (Chatwoot renders it)."""

    def as_markdown(match):
        url = html.unescape(match.group(1)).strip()
        label = html.unescape(strip_html(match.group(2))).strip()
        if not url.startswith(("https://", "http://", "mailto:")):
            return label
        return url if not label or label == url else f"[{label}]({url})"

    return html_to_text(LINK_PATTERN.sub(as_markdown, content or ""))


def normalize_labels(labels) -> list[str]:
    return [str(label).strip().lower() for label in labels or [] if str(label).strip()]


def one_line(value) -> str:
    return " ".join(str(value or "").split())


def normalized_phone(field):
    """`field` with the usual separators removed, for comparing phone numbers in SQL."""
    for separator in (" ", "-", "(", ")", "+", "."):
        field = Replace(field, separator, "")
    return field
