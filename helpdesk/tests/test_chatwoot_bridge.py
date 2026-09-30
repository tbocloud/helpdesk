import random
import time
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import chatwoot_bridge
from helpdesk.test_utils import (
    CHATWOOT_TEST_SECRET,
    FakeChatwootAPI,
    ai_chat_answer,
    chatwoot_signature,
    create_contact,
    create_customer,
    enable_chatwoot_bridge,
    get_chat_conversation,
    make_chat_conversation,
    make_chatwoot_payload,
    make_phone_contact,
    make_ticket,
    send_chatwoot_webhook,
)

REQUEST = "helpdesk.chatwoot_bridge.requests.request"
CALL_AI = "helpdesk.chatwoot_bridge.call_haiku"
AI_CONFIGURED = "helpdesk.chatwoot_bridge.is_ai_configured"


class ChatwootCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        enable_chatwoot_bridge()
        # other tests' rows must never collide with ours; message ids stay within an Int column
        self.cid = random.randint(10**6, 10**8)
        self.mid = self.cid * 10
        self.api = FakeChatwootAPI()
        request = patch(REQUEST, self.api)
        request.start()
        self.addCleanup(request.stop)

    def message(self, source="bot", **overrides):
        overrides.setdefault("conversation_id", self.cid)
        overrides.setdefault("message_id", self.mid)
        return send_chatwoot_webhook(
            source, make_chatwoot_payload("message_created", **overrides)
        )

    def conversation_event(self, event, source="account", **overrides):
        overrides.setdefault("conversation_id", self.cid)
        return send_chatwoot_webhook(source, make_chatwoot_payload(event, **overrides))

    def ask_ai(self, answer, **overrides):
        """Sends a customer message while the AI gives `answer` (a return value or an exception)."""
        mock = {"side_effect": answer} if isinstance(answer, Exception) else {}
        with patch(AI_CONFIGURED, return_value=True), patch(
            CALL_AI, return_value=answer, **mock
        ) as ai:
            self.message(**overrides)
        return ai

    def row(self):
        return get_chat_conversation(self.cid)

    def placeholder(self):
        return f"chat-{self.cid}@chat.invalid"


class TestWebhookReceiving(ChatwootCase):
    def test_signed_delivery_is_queued(self):
        result = self.conversation_event("conversation_created")
        self.assertTrue(result.get("queued"))
        self.assertTrue(self.row())

    def test_wrong_signature_is_refused(self):
        with self.assertRaises(frappe.AuthenticationError):
            send_chatwoot_webhook(
                "account",
                make_chatwoot_payload("conversation_created", conversation_id=self.cid),
                signature=chatwoot_signature(
                    b"another body", str(int(time.time())), CHATWOOT_TEST_SECRET
                ),
            )
        self.assertIsNone(self.row())

    def test_missing_signature_is_refused(self):
        with self.assertRaises(frappe.AuthenticationError):
            send_chatwoot_webhook(
                "account",
                make_chatwoot_payload("conversation_created", conversation_id=self.cid),
                signature=None,
            )

    def test_old_timestamp_is_refused(self):
        with self.assertRaises(frappe.AuthenticationError):
            send_chatwoot_webhook(
                "account",
                make_chatwoot_payload("conversation_created", conversation_id=self.cid),
                timestamp=str(int(time.time()) - 10 * 60),
            )

    def test_bot_url_token_works_without_the_bot_secret(self):
        enable_chatwoot_bridge(bot_webhook_secret=None)
        payload = make_chatwoot_payload(
            "conversation_created", conversation_id=self.cid
        )
        with self.assertRaises(frappe.AuthenticationError):
            send_chatwoot_webhook("bot", payload, signature=None, token="guess")
        result = send_chatwoot_webhook(
            "bot", payload, signature=None, token=CHATWOOT_TEST_SECRET
        )
        self.assertTrue(result.get("queued"))

    def test_everything_is_refused_while_disabled(self):
        enable_chatwoot_bridge(enabled=0)
        with self.assertRaises(frappe.AuthenticationError):
            self.conversation_event("conversation_created")

    def test_same_message_from_both_webhooks_is_handled_once(self):
        with patch(AI_CONFIGURED, return_value=True), patch(
            CALL_AI, return_value=ai_chat_answer("Hi Anita, how can I help?")
        ) as ai:
            self.assertTrue(self.message("bot").get("queued"))
            self.assertTrue(self.message("account").get("duplicate"))
            self.assertTrue(self.message("bot").get("duplicate"))
        self.assertEqual(ai.call_count, 1)
        self.assertEqual(self.api.posted(), ["Hi Anita, how can I help?"])

    def test_outgoing_and_private_messages_are_ignored(self):
        self.assertTrue(self.message(message_type="outgoing").get("ignored"))
        self.assertTrue(
            self.message(message_id=self.mid + 1, private=True).get("ignored")
        )
        self.assertTrue(
            self.message(message_id=self.mid + 2, sender_type="agent_bot").get(
                "ignored"
            )
        )
        self.assertFalse(frappe.db.exists("HD Chatwoot Event", f"message:{self.mid}"))


class TestAIFirstReply(ChatwootCase):
    def test_answer_is_posted_as_the_bot(self):
        self.ask_ai(
            ai_chat_answer("Go to Print Settings and pick the Standard format."),
            content="How do I change the invoice print format?",
        )
        posts = self.api.calls_to("/messages")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["token"], "ai-bot-token")
        self.assertEqual(posts[0]["body"]["message_type"], "outgoing")
        self.assertFalse(posts[0]["body"]["private"])
        self.assertEqual(
            posts[0]["body"]["content"],
            "Go to Print Settings and pick the Standard format.",
        )
        row = self.row()
        self.assertEqual(row.ai_reply_count, 1)
        self.assertEqual(row.status, "Pending")
        self.assertFalse(row.hd_ticket)
        self.assertEqual(self.api.statuses(), [])

    def test_unknown_urls_are_removed_from_the_answer(self):
        self.ask_ai(
            ai_chat_answer("See https://phish.example.com/login for the steps.")
        )
        self.assertEqual(self.api.posted(), ["See for the steps."])

    def test_ticket_action_creates_linked_ticket_and_hands_off(self):
        enable_chatwoot_bridge(handoff_team_id=4)
        self.ask_ai(
            ai_chat_answer(
                "Thanks, our team will look into the VAT on your invoices.",
                "ticket",
                ticket_subject="Invoice print shows wrong VAT",
                ticket_summary="VAT on printed invoices is 5% instead of 15%.",
            ),
            content="All my invoices print the wrong VAT amount.",
        )
        row = self.row()
        self.assertTrue(row.hd_ticket)
        self.assertEqual(row.status, "Open")
        ticket = frappe.get_doc("HD Ticket", row.hd_ticket)
        self.assertEqual(ticket.subject, "Invoice print shows wrong VAT")
        self.assertEqual(ticket.raised_by, self.placeholder())
        self.assertIn("5% instead of 15%", ticket.description)
        self.assertIn("All my invoices print the wrong VAT amount.", ticket.description)

        posted = self.api.posted()
        self.assertEqual(len(posted), 1)
        self.assertIn(f"#{ticket.name}", posted[0])
        self.assertTrue(posted[0].startswith("Thanks, our team"))
        self.assertEqual(self.api.statuses(), ["open"])
        self.assertEqual(
            [c["body"] for c in self.api.calls_to("/assignments")], [{"team_id": 4}]
        )
        # the opening message is the customer's, not the Administrator who ran the job
        opening = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Ticket", "reference_name": ticket.name},
            fields=["sender", "sent_or_received"],
        )
        self.assertEqual(
            opening, [{"sender": self.placeholder(), "sent_or_received": "Received"}]
        )

    def test_ai_failure_hands_off_politely(self):
        self.ask_ai(Exception("provider down"))
        self.assertEqual(self.api.posted(), [chatwoot_bridge.failure_text()])
        self.assertEqual(self.api.statuses(), ["open"])
        self.assertEqual(self.row().status, "Open")

    def test_unreadable_answer_hands_off(self):
        self.ask_ai({"response": {"raw_response": "", "parse_error": True}})
        self.assertEqual(self.api.posted(), [chatwoot_bridge.failure_text()])
        self.assertEqual(self.api.statuses(), ["open"])

    def test_human_action_hands_off_without_ticket(self):
        self.ask_ai(ai_chat_answer("Let me get a teammate for you.", "human"))
        self.assertEqual(self.api.posted(), ["Let me get a teammate for you."])
        self.assertEqual(self.api.statuses(), ["open"])
        self.assertFalse(self.row().hd_ticket)

    def test_reply_cap_hands_off_without_asking_the_ai(self):
        make_chat_conversation(self.cid, status="Pending", ai_reply_count=6)
        ai = self.ask_ai(ai_chat_answer("One more answer."))
        ai.assert_not_called()
        self.assertEqual(self.api.posted(), [chatwoot_bridge.handoff_text()])
        self.assertEqual(self.api.statuses(), ["open"])

    def test_chats_handled_by_people_get_no_ai_reply(self):
        ai = self.ask_ai(ai_chat_answer("Hello!"), status="open")
        ai.assert_not_called()
        self.assertEqual(self.api.calls, [])


class TestManualTicket(ChatwootCase):
    def test_ticket_label_creates_ticket_once(self):
        self.api.messages = [
            {
                "id": self.mid,
                "content": "Printer shows blank invoices",
                "message_type": 0,
                "sender": {"type": "contact"},
            }
        ]
        with patch(AI_CONFIGURED, return_value=False):
            self.conversation_event(
                "conversation_updated", status="open", labels=["ticket"], updated_at=1.5
            )
            self.conversation_event(
                "conversation_updated",
                status="open",
                labels=["ticket", "vip"],
                updated_at=2.5,
            )
        row = self.row()
        self.assertTrue(row.hd_ticket)
        self.assertEqual(
            frappe.db.get_value("HD Ticket", row.hd_ticket, "subject"),
            "Printer shows blank invoices",
        )
        notes = self.api.posted(private=True)
        self.assertEqual(len(notes), 1)
        self.assertIn(f"#{row.hd_ticket}", notes[0])
        self.assertEqual(self.api.posted(private=False), [])
        self.assertEqual(row.last_synced_message_id, self.mid)

    def test_other_labels_create_nothing(self):
        self.conversation_event("conversation_updated", status="open", labels=["vip"])
        self.assertFalse(self.row().hd_ticket)


class TestTicketSync(ChatwootCase):
    def setUp(self):
        super().setUp()
        self.ticket = make_ticket(
            subject="Chat: payroll export fails",
            raised_by=f"chat-{self.cid}@chat.invalid",
        )
        make_chat_conversation(self.cid, hd_ticket=self.ticket.name)

    def received(self):
        return frappe.get_all(
            "Communication",
            filters={
                "reference_doctype": "HD Ticket",
                "reference_name": self.ticket.name,
                "sent_or_received": "Received",
                "content": ("like", "%still broken%"),
            },
            pluck="communication_medium",
        )

    def test_agent_reply_is_posted_to_the_chat_without_email(self):
        frappe.db.set_single_value("HD Settings", "enable_reply_email_via_agent", 1)
        self.ticket.reply_via_agent(
            message='<p>Please update to <a href="https://tbo.example.com/fix">the fix</a>.</p>',
            to=self.placeholder(),
        )
        posts = self.api.calls_to("/messages")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["token"], "bridge-user-token")
        self.assertEqual(
            posts[0]["body"]["content"],
            "Please update to [the fix](https://tbo.example.com/fix).",
        )
        self.assertFalse(
            frappe.db.exists("Email Queue Recipient", {"recipient": self.placeholder()})
        )

    def test_customer_message_becomes_a_ticket_reply_once(self):
        self.message("account", content="It is still broken today.", status="open")
        self.message("bot", content="It is still broken today.", status="open")
        self.assertEqual(self.received(), ["Chat"])
        self.assertEqual(self.row().last_synced_message_id, self.mid)
        # nothing echoes back to the chat, and no AI answers a linked chat
        self.assertEqual(self.api.calls, [])

    def test_messages_already_on_the_ticket_are_skipped(self):
        frappe.db.set_value(
            "HD Chat Conversation", self.row().name, "last_synced_message_id", self.mid
        )
        self.message(content="It is still broken today.", status="open")
        self.assertEqual(self.received(), [])

    def test_resolved_ticket_resolves_the_chat(self):
        self.ticket.reload()
        self.ticket.status = "Resolved"
        self.ticket.save()
        self.assertEqual(self.api.posted(), [chatwoot_bridge.resolved_text()])
        self.assertEqual(self.api.statuses(), ["resolved"])
        self.assertEqual(self.row().status, "Resolved")

    def test_reopened_chat_reopens_the_ticket(self):
        frappe.db.set_value(
            "HD Ticket",
            self.ticket.name,
            {"status": "Resolved", "status_category": "Resolved"},
        )
        self.conversation_event("conversation_status_changed", status="open")
        # the reopen status is a setting (Open by default)
        self.assertNotEqual(
            frappe.db.get_value("HD Ticket", self.ticket.name, "status_category"),
            "Resolved",
        )

    def test_closed_ticket_stays_closed(self):
        frappe.db.set_value(
            "HD Ticket",
            self.ticket.name,
            {"status": "Closed", "status_category": "Resolved"},
        )
        self.conversation_event("conversation_status_changed", status="open")
        self.assertEqual(
            frappe.db.get_value("HD Ticket", self.ticket.name, "status"), "Closed"
        )
        self.message(
            content="It is still broken today.", status="open", labels=["ticket"]
        )
        self.assertEqual(self.received(), [])
        self.assertFalse(self.row().hd_ticket)
        self.assertEqual(
            [c["body"] for c in self.api.calls_to("/labels")], [{"labels": []}]
        )
        self.assertEqual(len(self.api.posted(private=True)), 1)


class TestContactMatching(ChatwootCase):
    def test_matches_contact_and_customer_by_email(self):
        contact = create_contact("Meera", "meera@chatwoot-match.example", user=False)[
            "contact"
        ]
        customer = create_customer(
            "Chatwoot Match Traders", contacts=[{"contact_name": contact}]
        )
        self.conversation_event(
            "conversation_created", email="Meera@chatwoot-match.example"
        )
        row = self.row()
        self.assertEqual(row.contact, contact)
        self.assertEqual(row.hd_customer, customer.name)
        self.assertEqual(row.contact_email, "meera@chatwoot-match.example")

    def test_matches_contact_by_phone_in_another_format(self):
        contact = make_phone_contact("Faisal", "058-765-4329")
        self.conversation_event(
            "conversation_created",
            phone="+971587654329",
            channel="Channel::Whatsapp",
        )
        row = self.row()
        self.assertEqual(row.contact, contact.name)
        self.assertTrue(row.identity_verified)

    def test_unknown_contact_is_created_under_the_default_customer(self):
        customer = create_customer("Chatwoot Website Visitors")
        enable_chatwoot_bridge(default_customer=customer.name)
        email = f"visitor-{self.cid}@chatwoot-new.example"
        self.conversation_event("conversation_created", name="Ravi K", email=email)
        row = self.row()
        self.assertTrue(row.contact)
        self.assertEqual(frappe.db.get_value("Contact", row.contact, "email_id"), email)
        self.assertEqual(row.hd_customer, customer.name)
        self.assertIn(
            row.contact,
            [
                c.contact_name
                for c in frappe.get_doc("HD Customer", customer.name).contacts
            ],
        )
        self.assertFalse(row.identity_verified)

    def test_anonymous_visitor_creates_no_contact(self):
        self.conversation_event("conversation_created")
        row = self.row()
        self.assertFalse(row.contact)
        self.assertFalse(row.hd_customer)
