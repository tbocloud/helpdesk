# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, getdate, now_datetime

from helpdesk.helpdesk.report.content_delivery.content_delivery import execute
from helpdesk.test_utils import create_customer, make_content_post

CUSTOMER = "Al Noor Trading LLC"


class TestContentDelivery(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        create_customer(CUSTOMER)

    def test_counts_per_customer(self):
        today = now_datetime()
        on_time = make_content_post(
            "On time",
            CUSTOMER,
            status="Approved",
            publish_on=add_to_date(today, minutes=1),
        )
        on_time.status = "Published"
        on_time.published_url = "https://instagram.com/p/1"
        on_time.save()
        make_content_post(
            "Late", CUSTOMER, status="Drafting", publish_on=add_to_date(today, hours=-2)
        )
        waiting = make_content_post(
            "Waiting",
            CUSTOMER,
            status="Client Review",
            publish_on=add_to_date(today, hours=5),
        )
        waiting.db_set(
            {
                "sent_for_approval_on": add_to_date(today, hours=-10),
                "client_decided_on": add_to_date(today, hours=-4),
            }
        )

        _columns, rows, _msg, chart = execute(
            {
                "from_date": getdate(add_to_date(today, days=-1)),
                "to_date": getdate(add_to_date(today, days=1)),
                "customer": CUSTOMER,
            }
        )

        row = rows[0]
        self.assertEqual(row["customer"], CUSTOMER)
        self.assertEqual(row["planned"], 3)
        self.assertEqual(row["published"], 1)
        self.assertEqual(row["on_time"], 1)
        self.assertEqual(row["on_time_pct"], 100)
        self.assertEqual(row["awaiting_client"], 1)
        self.assertEqual(row["avg_approval_hours"], 6.0)
        self.assertGreaterEqual(row["overdue"], 1)
        self.assertEqual(chart["type"], "bar")
