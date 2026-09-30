import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import ai_suggestion, session_manager, triage
from helpdesk.api import ai_suggestion as ai_suggestion_api
from helpdesk.test_utils import (
    create_agent,
    create_user,
    make_ai_support_session,
    make_article,
    make_team,
    make_ticket,
    run_as_user,
)

SESSION_TIMELINE = (
    "What the customer did before raising the ticket (session timeline):\n"
    't+12s clicked "Save"\n'
    "t+13s server error: 417 ValidationError: Posting Date cannot be before Invoice Date"
)
DIAGNOSIS = (
    "## DIAGNOSIS\nSINV-0042 has Posting Date 2026-09-01 but Invoice Date 2026-09-05."
)


def model_answer(reply: str, confidence: str = "high", note: str = "matches the error"):
    return {
        "response": {"reply": reply, "confidence": confidence, "note": note},
        "usage": {},
        "cost": 0,
    }


class TestGenerateSuggestion(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.ticket = make_ticket(
            subject="Sales Invoice posting date error on save",
            description="Saving Sales Invoice SINV-0042 fails with a posting date error.",
        )
        self.article = make_article(
            "Fixing posting date errors on a Sales Invoice",
            "<p>Set the Posting Date on or after the Invoice Date, then save again.</p>",
        )
        frappe.db.set_value(
            "HD Ticket",
            self.ticket.name,
            {
                "custom_triage_status": "Completed",
                "custom_triage_summary": "Save fails on posting date validation.",
                "custom_triage_data": json.dumps(
                    {
                        "likely_cause": "Posting Date is before the Invoice Date.",
                        "steps_to_reproduce": ["Open SINV-0042", "Click Save"],
                    }
                ),
            },
        )
        self.session = make_ai_support_session(
            self.ticket.name, status="Completed", diagnosis=DIAGNOSIS
        )
        replay = patch.object(
            ai_suggestion, "build_triage_context", return_value=SESSION_TIMELINE
        )
        replay.start()
        self.addCleanup(replay.stop)

    def get_ticket_values(self):
        return frappe.db.get_value(
            "HD Ticket",
            self.ticket.name,
            [
                "custom_ai_suggestion_status",
                "custom_ai_suggested_reply",
                "custom_ai_suggestion_note",
                "custom_ai_suggestion_at",
                "custom_ai_suggestion_sources",
            ],
            as_dict=True,
        )

    def test_stores_ready_reply_with_its_sources(self):
        article_url = frappe.utils.get_url(
            f"/helpdesk/kb-public/articles/{self.article.name}"
        )
        reply = (
            "Hi,\n\nPlease set the Posting Date of SINV-0042 on or after 2026-09-05 "
            f"and save again. This guide shows how: {article_url}"
        )
        with patch.object(
            ai_suggestion, "call_haiku", return_value=model_answer(reply)
        ) as model:
            ai_suggestion.generate_suggestion(self.ticket.name)

        prompt = model.call_args.args[1]
        self.assertIn("Posting Date is before the Invoice Date.", prompt)
        self.assertIn('clicked "Save"', prompt)
        self.assertIn("SINV-0042 has Posting Date 2026-09-01", prompt)
        self.assertIn(article_url, prompt)

        values = self.get_ticket_values()
        self.assertEqual(values.custom_ai_suggestion_status, "Ready")
        self.assertIn("<p>Hi,</p>", values.custom_ai_suggested_reply)
        self.assertIn(f'<a href="{article_url}">', values.custom_ai_suggested_reply)
        self.assertEqual(
            values.custom_ai_suggestion_note, "Confidence: high — matches the error"
        )
        self.assertTrue(values.custom_ai_suggestion_at)

        sources = json.loads(values.custom_ai_suggestion_sources)
        self.assertEqual(
            [s["kind"] for s in sources[:3]], ["triage", "replay", "investigation"]
        )
        self.assertEqual(sources[2]["name"], self.session.name)
        # other tests' articles may match too; ours must be among them
        self.assertIn(
            self.article.name,
            [s["name"] for s in sources if s["kind"] == "article"],
        )

    def test_empty_answer_fails_and_stores_nothing(self):
        with patch.object(
            ai_suggestion, "call_haiku", return_value=model_answer("  ")
        ), patch.object(frappe, "log_error") as log_error:
            ai_suggestion.generate_suggestion(self.ticket.name)

        values = self.get_ticket_values()
        self.assertEqual(values.custom_ai_suggestion_status, "Failed")
        self.assertFalse(values.custom_ai_suggested_reply)
        self.assertFalse(values.custom_ai_suggestion_at)
        self.assertTrue(log_error.called)

    @patch("frappe.enqueue")
    def test_closed_ticket_is_skipped(self, enqueue):
        frappe.db.set_value("HD Ticket", self.ticket.name, "status", "Closed")

        with patch.object(ai_suggestion, "is_ai_configured", return_value=True):
            self.assertFalse(ai_suggestion.queue_suggestion(self.ticket.name))
        with patch.object(ai_suggestion, "call_haiku") as model:
            ai_suggestion.generate_suggestion(self.ticket.name)

        enqueue.assert_not_called()
        model.assert_not_called()
        self.assertFalse(self.get_ticket_values().custom_ai_suggestion_status)

    @patch("frappe.enqueue")
    def test_nothing_is_queued_without_ai(self, enqueue):
        with patch.object(ai_suggestion, "is_ai_configured", return_value=False):
            self.assertFalse(ai_suggestion.queue_suggestion(self.ticket.name))
        enqueue.assert_not_called()


class TestSuggestionTriggers(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.ticket = make_ticket(
            subject="Stock balance report is wrong",
            description="The Stock Balance report shows the wrong quantity for ABC-001.",
        )
        configured = patch.object(ai_suggestion, "is_ai_configured", return_value=True)
        configured.start()
        self.addCleanup(configured.stop)

    @patch("frappe.enqueue")
    def test_successful_triage_queues_a_suggestion(self, enqueue):
        answer = {
            "response": {
                "category": "Stock",
                "priority": "Medium",
                "summary": "Stock Balance shows a wrong quantity for ABC-001.",
                "recommended_track": "manual",
            },
            "usage": {},
            "cost": 0,
        }
        with patch.object(triage, "call_haiku", return_value=answer), patch.object(
            frappe.cache, "set", return_value=True
        ), patch.object(frappe.db, "commit"):
            triage.run_triage(self.ticket.name, start_investigation=False)

        calls = [
            c
            for c in enqueue.call_args_list
            if c.args and c.args[0] == "helpdesk.ai_suggestion.generate_suggestion"
        ]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].kwargs["ticket_id"], self.ticket.name)
        self.assertTrue(calls[0].kwargs["enqueue_after_commit"])
        self.assertEqual(
            frappe.db.get_value(
                "HD Ticket", self.ticket.name, "custom_ai_suggestion_status"
            ),
            "Pending",
        )

    def test_completed_investigation_queues_a_suggestion(self):
        session = make_ai_support_session(
            self.ticket.name, status="Completed", diagnosis=DIAGNOSIS
        )
        with patch.object(session_manager, "queue_suggestion") as queue, patch.object(
            frappe.db, "commit"
        ):
            session_manager.post_investigation_comment(session.name, self.ticket.name)

        queue.assert_called_once_with(self.ticket.name)

    def test_failed_investigation_does_not(self):
        session = make_ai_support_session(
            self.ticket.name, status="Failed", diagnosis="Investigation failed: timeout"
        )
        with patch.object(session_manager, "queue_suggestion") as queue, patch.object(
            frappe.db, "commit"
        ):
            session_manager.post_investigation_comment(session.name, self.ticket.name)

        queue.assert_not_called()


class TestRelatedArticles(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)

    def test_picks_published_article_and_ignores_drafts(self):
        published = make_article(
            "Reconciling a Zorblax bank statement",
            "<p>Open Bank Reconciliation and match each Zorblax entry.</p>",
        )
        draft = make_article(
            "Reconciling a Zorblax bank statement (draft)",
            "<p>Work in progress about Zorblax reconciliation.</p>",
            status="Draft",
        )
        unrelated = make_article(
            "Changing your password", "<p>Use the Forgot password link.</p>"
        )
        ticket = make_ticket(
            subject="Zorblax bank statement will not reconcile",
            description="The Zorblax statement lines do not match in Bank Reconciliation.",
        )

        names = [a["name"] for a in ai_suggestion.find_related_articles(ticket)]

        self.assertIn(published.name, names)
        self.assertNotIn(draft.name, names)
        self.assertNotIn(unrelated.name, names)


class TestSuggestionApi(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.ticket = make_ticket(
            subject="Cannot print a Delivery Note",
            description="The print preview of the Delivery Note is blank.",
        )

    def test_agent_outside_the_tickets_team_is_denied(self):
        agent = create_agent("suggestion-other-team@example.com").name
        team = make_team(
            "Suggestion Restricted Team",
            members=[create_agent("suggestion-team@example.com").name],
        )
        frappe.db.set_value("HD Ticket", self.ticket.name, "agent_group", team.name)
        frappe.db.set_single_value(
            "HD Settings",
            {
                "restrict_tickets_by_agent_group": 1,
                "do_not_restrict_tickets_without_an_agent_group": 0,
            },
        )

        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                agent, lambda: ai_suggestion_api.get_suggestion(self.ticket.name)
            )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                agent,
                lambda: ai_suggestion_api.regenerate_suggestion(self.ticket.name),
            )

    def test_non_agent_is_denied(self):
        outsider = create_user("suggestion-outsider@example.com").name

        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                outsider, lambda: ai_suggestion_api.get_suggestion(self.ticket.name)
            )

    @patch("frappe.enqueue")
    def test_regenerate_queues_with_instructions(self, enqueue):
        with patch.object(
            ai_suggestion, "is_ai_configured", return_value=True
        ), patch.object(ai_suggestion_api, "is_ai_configured", return_value=True):
            result = ai_suggestion_api.regenerate_suggestion(
                self.ticket.name, instructions="Ask for a screenshot"
            )

        self.assertEqual(result["status"], "Pending")
        self.assertEqual(
            enqueue.call_args.kwargs["instructions"], "Ask for a screenshot"
        )
