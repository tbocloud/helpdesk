from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime

from helpdesk.api.duplicates import get_possible_duplicates
from helpdesk.duplicates import normalized_subject
from helpdesk.test_utils import create_customer, make_ticket

CUSTOMER = "Duplicate Check Traders"
OTHER_CUSTOMER = "Someone Else Trading"


class TestDuplicates(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)

    def ticket(self, subject, description="", customer=CUSTOMER, **values):
        name = make_ticket(
            subject=subject, description=description, customer=customer
        ).name
        if values:
            frappe.db.set_value("HD Ticket", name, values)
        return name

    def duplicates(self, ticket):
        return [d["name"] for d in get_possible_duplicates(ticket)]

    def test_same_subject_from_the_same_customer(self):
        first = self.ticket(
            "Sales invoice print format broken",
            creation=add_to_date(now_datetime(), hours=-3),
        )
        second = self.ticket("RE: Sales Invoice print format broken")

        found = get_possible_duplicates(second)

        self.assertEqual([d["name"] for d in found], [first])
        self.assertTrue(found[0]["same_subject"])
        # the older ticket is the original
        self.assertTrue(found[0]["is_older"])
        self.assertFalse(get_possible_duplicates(first)[0]["is_older"])

    def test_same_problem_in_other_words(self):
        first = self.ticket(
            "Payroll salary slip shows wrong deduction",
            "The salary slip for March shows a wrong PF deduction for employees",
        )
        second = self.ticket(
            "Wrong PF deduction",
            "Employees salary slip deduction for PF is wrong this month",
        )
        unrelated = self.ticket(
            "Stock ledger report slow", "The stock ledger report takes minutes"
        )

        found = self.duplicates(second)

        self.assertIn(first, found)
        self.assertNotIn(unrelated, found)

    def test_other_customers_closed_merged_and_old_tickets_are_left_out(self):
        subject = "Cannot submit purchase order"
        other_customer = self.ticket(subject, customer=OTHER_CUSTOMER)
        closed = self.ticket(subject, status="Closed", status_category="Resolved")
        merged = self.ticket(subject, is_merged=1)
        old = self.ticket(subject, creation=add_days(now_datetime(), -30))
        current = self.ticket(subject)

        found = self.duplicates(current)

        for name in (other_customer, closed, merged, old):
            self.assertNotIn(name, found)

    def test_reply_prefixes_are_ignored(self):
        self.assertEqual(
            normalized_subject("Fwd: RE:  Invoice  Issue"), "invoice issue"
        )
