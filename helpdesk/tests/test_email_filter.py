import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.email_filter import UnwantedTicketEmail, is_unwanted_sender
from helpdesk.test_utils import make_email_account


class TestEmailFilter(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.clear_document_cache, "HD Settings", "HD Settings")
        self.settings(ignore_automated_emails=1, ignored_email_senders="")

    def settings(self, **values):
        for field, value in values.items():
            frappe.db.set_single_value("HD Settings", field, value)
        frappe.clear_document_cache("HD Settings", "HD Settings")

    def test_automated_senders_are_unwanted(self):
        for sender in (
            "noreply@facebookmail.com",
            "no-reply@email.claude.com",
            "NoReply@Example.com",
            "notifications@github.com",
            "notification+abc123@example.com",
            "mailer-daemon@googlemail.com",
            "do-not-reply@bank.example",
        ):
            self.assertTrue(is_unwanted_sender(sender), sender)

    def test_people_and_shared_mailboxes_are_wanted(self):
        for sender in (
            "accounts@galominternational.com",
            "info@averaiot.com",
            "noreen@example.com",
            "",
            None,
        ):
            self.assertFalse(is_unwanted_sender(sender), sender)

    def test_listed_domains_and_addresses_are_unwanted(self):
        self.settings(
            ignored_email_senders="gamma.app\n@news.example.com, promo@shop.example"
        )
        self.assertTrue(is_unwanted_sender("hello@gamma.app"))
        self.assertTrue(is_unwanted_sender("team@mail.gamma.app"))
        self.assertFalse(is_unwanted_sender("hello@notgamma.app"))
        self.assertTrue(is_unwanted_sender("weekly@news.example.com"))
        self.assertTrue(is_unwanted_sender("promo@shop.example"))
        self.assertFalse(is_unwanted_sender("orders@shop.example"))

    def test_automated_filter_can_be_turned_off(self):
        self.settings(ignore_automated_emails=0)
        self.assertFalse(is_unwanted_sender("noreply@facebookmail.com"))

    def test_email_from_an_unwanted_sender_opens_no_ticket(self):
        inbox = make_email_account(
            "filter-inbox@example.com", enable_outgoing=0, enable_incoming=1
        )
        ticket = frappe.get_doc(
            {
                "doctype": "HD Ticket",
                "subject": "You have 25 new notifications",
                "raised_by": "noreply@facebookmail.com",
                "email_account": inbox.name,
            }
        )
        with self.assertRaises(UnwantedTicketEmail):
            ticket.insert(ignore_permissions=True)

        wanted = frappe.get_doc(
            {
                "doctype": "HD Ticket",
                "subject": "Filter not working",
                "raised_by": "accounts@galominternational.com",
                "email_account": inbox.name,
            }
        ).insert(ignore_permissions=True)
        self.assertTrue(wanted.name)

    def test_tickets_not_from_email_are_never_filtered(self):
        ticket = frappe.get_doc(
            {
                "doctype": "HD Ticket",
                "subject": "Raised by an agent for a no-reply contact",
                "raised_by": "noreply@example.com",
            }
        ).insert(ignore_permissions=True)
        self.assertTrue(ticket.name)
