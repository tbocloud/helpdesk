from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import kb_drafts
from helpdesk.test_utils import (
    get_reminder_messages,
    make_article,
    make_tasky_user,
    make_ticket,
    make_ticket_communication,
)

MANAGER = ("manager.kb@kb-drafts.example", "Sneha Thomas")
ARTICLE_BODY = "Export a report to Excel in three steps.\n\n1. Open the report\n2. Click **Menu → Export**\n3. Choose **Excel**"


def answer(**fields) -> dict:
    return {
        "response": {
            "write": True,
            "reason": "Common question",
            "covered_by": "",
            "title": "How do I export a report to Excel?",
            "body": ARTICLE_BODY,
            **fields,
        }
    }


class TestKBDrafts(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        frappe.db.set_single_value("HDS Hub Settings", "draft_kb_articles", 1)
        configured = patch.object(kb_drafts, "is_ai_configured", return_value=True)
        configured.start()
        self.addCleanup(configured.stop)
        make_tasky_user(*MANAGER, roles=("Agent Manager",))

    def answered_ticket(self, subject="Export sales register to excel"):
        ticket = make_ticket(subject=subject, description="How do I export it?")
        make_ticket_communication(
            ticket.name,
            "Open the report, then Menu → Export → Excel.",
            sender="support@kb-drafts.example",
            sent_or_received="Sent",
        )
        return ticket.name

    def resolve(self, ticket, ai_answer):
        doc = frappe.get_doc("HD Ticket", ticket)
        doc.status = "Resolved"
        with patch.object(kb_drafts, "call_haiku", return_value=ai_answer) as model:
            doc.save(ignore_permissions=True)
        return model

    def drafts(self, ticket):
        return frappe.get_all(
            "HD Article",
            filters={"source_ticket": ticket},
            fields=["name", "title", "status", "content"],
        )

    def test_resolved_ticket_becomes_a_draft_for_review(self):
        ticket = self.answered_ticket()

        self.resolve(ticket, answer())

        drafts = self.drafts(ticket)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].status, "Draft")
        self.assertEqual(drafts[0].title, "How do I export a report to Excel?")
        self.assertIn("<ol>", drafts[0].content)
        self.assertTrue(
            any(
                m.startswith(f"KB draft to review, from ticket #{ticket}")
                for m in get_reminder_messages(MANAGER[0], drafts[0].name)
            )
        )

    def test_nothing_is_drafted_when_the_ai_says_no_or_it_is_covered(self):
        no = self.answered_ticket("Customer specific stock error")
        self.resolve(no, answer(write=False, body=""))
        covered = self.answered_ticket("Export purchase register to excel")
        self.resolve(covered, answer(covered_by="abc123"))

        self.assertEqual(self.drafts(no), [])
        self.assertEqual(self.drafts(covered), [])

    def test_existing_articles_are_given_to_the_ai(self):
        make_article(
            "Export a report to Excel",
            "<p>Open any report, Menu, Export, Excel.</p>",
        )
        ticket = self.answered_ticket("Export report excel")

        prompt = self.resolve(ticket, answer(write=False)).call_args.args[1]

        self.assertIn("Export a report to Excel", prompt)

    def test_unanswered_or_disabled_tickets_skip_the_ai(self):
        unanswered = make_ticket(subject="Export to excel?").name
        self.assertFalse(self.resolve(unanswered, answer()).called)

        frappe.db.set_single_value("HDS Hub Settings", "draft_kb_articles", 0)
        ticket = self.answered_ticket()
        self.assertFalse(self.resolve(ticket, answer()).called)

    def test_a_ticket_is_drafted_only_once(self):
        ticket = self.answered_ticket()
        self.resolve(ticket, answer())

        doc = frappe.get_doc("HD Ticket", ticket)
        doc.status = "Open"
        doc.save(ignore_permissions=True)
        model = self.resolve(ticket, answer())

        self.assertFalse(model.called)
        self.assertEqual(len(self.drafts(ticket)), 1)
