from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.ticket_ai import draft_reply
from helpdesk.test_utils import create_user, make_ticket, make_ticket_communication


class TestDraftReply(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.ticket = make_ticket(
            subject="Booking not confirmed", description="<p>My PNR is not showing.</p>"
        )

    def tearDown(self):
        frappe.set_user("Administrator")

    @patch("helpdesk.api.ticket_ai.call_haiku")
    def test_returns_reply_as_paragraphs(self, call_haiku):
        call_haiku.return_value = {
            "response": {"reply": "Hi Asha,\n\nFlights & hotels are being checked."}
        }

        result = draft_reply(ticket=self.ticket.name)

        self.assertEqual(
            result["reply"],
            "<p>Hi Asha,</p><p>Flights &amp; hotels are being checked.</p>",
        )
        self.assertEqual(call_haiku.call_args.kwargs["ticket_name"], self.ticket.name)

    @patch("helpdesk.api.ticket_ai.call_haiku")
    def test_prompt_includes_latest_message_and_draft(self, call_haiku):
        call_haiku.return_value = {"response": {"reply": "Thanks for the update."}}
        make_ticket_communication(
            self.ticket.name, "<p>Still failing after the 09:12 sync.</p>"
        )

        draft_reply(
            ticket=self.ticket.name,
            instructions="Apologise",
            current_draft="<p>We are on it</p>",
        )

        prompt = call_haiku.call_args.args[1]
        self.assertIn("Still failing after the 09:12 sync.", prompt)
        self.assertIn("Booking not confirmed", prompt)
        self.assertIn("Apologise", prompt)
        self.assertIn("We are on it", prompt)
        self.assertNotIn("<p>", prompt)

    @patch("helpdesk.api.ticket_ai.call_haiku")
    def test_empty_model_reply_is_an_error(self, call_haiku):
        call_haiku.return_value = {
            "response": {"raw_response": "oops", "parse_error": True}
        }

        with self.assertRaises(frappe.ValidationError):
            draft_reply(ticket=self.ticket.name)

    @patch("helpdesk.api.ticket_ai.call_haiku")
    def test_user_without_access_is_denied(self, call_haiku):
        outsider = create_user("ticket-ai-outsider@example.com")
        frappe.set_user(outsider.name)

        with self.assertRaises(frappe.PermissionError):
            draft_reply(ticket=self.ticket.name)
        call_haiku.assert_not_called()
