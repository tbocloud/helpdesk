from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api.home import get_home
from helpdesk.test_utils import (
    create_customer,
    get_reminder_messages,
    make_assignment,
    make_tasky_user,
    make_ticket,
)

AGENT = ("agent.sla@sla-alerts.example", "Meera Joseph")
MANAGER = ("manager.sla@sla-alerts.example", "Tom Varghese")
CUSTOMER = "SLA Alerts Traders"


class SLAAlertCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        escalation = patch("helpdesk.chat_notifications.post_escalation")
        self.channel = escalation.start()
        self.addCleanup(escalation.stop)
        create_customer(CUSTOMER)
        make_tasky_user(*AGENT)
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        self.now = now_datetime()

    def ticket(self, subject, assignee=None, **values):
        ticket = make_ticket(subject=subject, customer=CUSTOMER)
        # assignment rules may have picked an agent; start from nobody
        frappe.db.set_value(
            "HD Ticket",
            ticket.name,
            {"_assign": None, "first_responded_on": None, **values},
        )
        if assignee:
            make_assignment("HD Ticket", ticket.name, assignee[0])
        return ticket.name

    def channel_posts(self, ticket):
        return [
            c.args[0] for c in self.channel.call_args_list if f"#{ticket}:" in c.args[0]
        ]


class TestLowRatingAlert(SLAAlertCase):
    def rate(self, ticket, stars):
        doc = frappe.get_doc("HD Ticket", ticket)
        doc.feedback_rating = stars / 5
        doc.save(ignore_permissions=True)

    def test_low_rating_alerts_assignee_managers_and_channel(self):
        ticket = self.ticket("Payroll wrong", AGENT)

        self.rate(ticket, 1)

        for user in (AGENT, MANAGER):
            self.assertTrue(
                any(
                    m.startswith("Low rating (1/5)")
                    for m in get_reminder_messages(user[0], ticket)
                ),
                user,
            )
        self.assertEqual(len(self.channel_posts(ticket)), 1)

    def test_good_rating_sends_nothing(self):
        ticket = self.ticket("Thanks for the fix", AGENT)

        self.rate(ticket, 5)

        self.assertEqual(get_reminder_messages(AGENT[0], ticket), [])
        self.assertEqual(self.channel_posts(ticket), [])


class TestHomeTicketHealth(SLAAlertCase):
    def test_home_shows_first_replies_overdue_and_ratings(self):
        self.ticket("Late reply", response_by=add_to_date(self.now, hours=-1))
        low = self.ticket("Unhappy customer")
        frappe.db.set_value("HD Ticket", low, "feedback_rating", 0.2)
        happy = self.ticket("Happy customer")
        frappe.db.set_value("HD Ticket", happy, "feedback_rating", 1.0)

        tickets = get_home()["company"]["tickets"]

        self.assertGreaterEqual(tickets["first_reply_overdue"], 1)
        rating = tickets["rating"]
        self.assertGreaterEqual(rating["count"], 2)
        self.assertGreaterEqual(rating["low"], 1)
        self.assertIsNotNone(rating["average"])
