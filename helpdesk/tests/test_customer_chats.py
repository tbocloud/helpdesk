"""Support → Customer chats (phase 32, step 6): customers' ERP chats seen live, I'll answer, replies."""

from unittest.mock import patch

import frappe

from helpdesk.api import customer_chats
from helpdesk.copilot import conversation
from helpdesk.test_utils import make_agent
from helpdesk.tests.test_copilot_conversation import ChatCase


class CustomerChatsCase(ChatCase):
    def setUp(self):
        super().setUp()
        # the audience of live updates is cached: never from another test
        frappe.cache().delete_value(customer_chats.AUDIENCE_KEY)
        self.addCleanup(frappe.cache().delete_value, customer_chats.AUDIENCE_KEY)

    def listed(self, view):
        return {
            r["name"]
            for r in customer_chats.get_customer_chats(view=view, limit=100)["data"]
        }

    def pushed_texts(self):
        return [
            (payload or {}).get("text")
            for method, payload in self.pushed
            if method == "post_message"
        ]


class TestTheList(CustomerChatsCase):
    def test_a_chat_shows_while_the_ai_talks(self):
        self.gathered()
        self.assertIn(self.chat, self.listed("ai"))
        self.assertIn(self.chat, self.listed("all"))
        row = next(
            r
            for r in customer_chats.get_customer_chats(view="all", limit=100)["data"]
            if r["name"] == self.chat
        )
        self.assertEqual((row["user"], row["customer"]), ("Ali Hassan", self.customer))
        self.assertEqual(row["state"], "AI talking")

    def test_a_customer_asking_for_a_person_waits_for_us(self):
        self.say(action="start")
        self.answers.append({"next": "handover", "text": "", "language": "en"})
        self.say(action="person")
        self.assertIn(self.chat, self.listed("waiting"))

    def test_only_the_people_who_work_tickets_see_them(self):
        outsider = make_agent("cc-outsider@example.com")
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            customer_chats.get_customer_chats(view="all")


class TestOneChat(CustomerChatsCase):
    def test_opening_shows_what_the_ai_gathered_and_where_the_user_was(self):
        self.gathered()
        opened = customer_chats.get_customer_chat(self.chat)
        self.assertIn(
            {"label": "Title", "value": "Sales Invoice won't submit"},
            opened["gathered"],
        )
        self.assertEqual(
            (opened["context"]["doctype"], opened["context"]["docname"]),
            ("Sales Invoice", "SINV-0042"),
        )
        texts = [m["text"] for m in opened["messages"] if m["from"] == "Customer"]
        self.assertIn("it won't submit, says margin error", texts)
        self.assertTrue(opened["can_take_over"])


class TestIllAnswer(CustomerChatsCase):
    def test_it_raises_a_ticket_without_copilot_and_the_customer_sees_the_person(self):
        self.gathered()
        answer = customer_chats.take_over(self.chat)
        doc = self.doc()
        self.assertEqual(doc.ticket, answer["ticket"])
        self.assertEqual(doc.state, "With a person")
        self.assertFalse(frappe.db.exists("HDS Copilot Run", {"ticket": doc.ticket}))
        self.assertIn(
            "Administrator",
            frappe.parse_json(frappe.db.get_value("HD Ticket", doc.ticket, "_assign")),
        )
        texts = self.pushed_texts()
        self.assertTrue(any("is raised" in (t or "") for t in texts), texts)
        self.assertTrue(any("joined the chat" in (t or "") for t in texts), texts)

    def test_a_reply_reaches_the_customers_chat(self):
        self.gathered()
        customer_chats.send_reply(self.chat, "We are checking the margin rule now.")
        self.assertIn("We are checking the margin rule now.", self.pushed_texts())
        self.assertEqual(self.doc().state, "With a person")
        self.assertTrue(
            frappe.db.exists(
                "Communication",
                {
                    "reference_doctype": "HD Ticket",
                    "reference_name": self.doc().ticket,
                    "sent_or_received": "Sent",
                },
            )
        )

    def test_a_closed_chat_is_not_taken_over(self):
        self.gathered()
        self.doc().db_set("state", "Closed")
        with self.assertRaises(frappe.ValidationError):
            customer_chats.take_over(self.chat)


class TestLiveUpdates(CustomerChatsCase):
    def test_each_message_goes_only_to_the_people_who_may_see_it(self):
        with patch.object(
            customer_chats, "audience", return_value=["a@example.com", "b@example.com"]
        ), patch("helpdesk.api.customer_chats.frappe.publish_realtime") as published:
            self.say(action="start")
        ours = [
            c for c in published.call_args_list if c.args[0] == customer_chats.EVENT
        ]
        self.assertTrue(ours)
        self.assertEqual(
            {c.kwargs.get("user") for c in ours}, {"a@example.com", "b@example.com"}
        )
        for c in ours:
            self.assertNotIn("text", c.args[1])

    def test_the_tbo_chat_mirror_sends_nothing(self):
        doc = frappe.get_doc(
            {"doctype": conversation.CONVERSATION, "channel": "TBO Chat"}
        ).insert(ignore_permissions=True)
        with patch("helpdesk.api.customer_chats.frappe.publish_realtime") as published:
            conversation._record(doc, "Customer", "Text", "hi")
        self.assertFalse(
            [c for c in published.call_args_list if c.args[0] == customer_chats.EVENT]
        )
