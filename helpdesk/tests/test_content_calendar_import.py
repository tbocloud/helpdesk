# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.content_calendar_import import import_item
from helpdesk.test_utils import create_customer, hold_commits

CUSTOMER = "Import Test Bakery"


class TestContentCalendarImport(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)
        self.calendar = frappe._dict(name="CAL-1", workflow_status="Draft")

    def item(self, **values):
        return frappe._dict(
            {
                "name": "ITEM-1",
                "campaign_name": "Weekend offer",
                "deliverable": "Post",
                "status": "Draft",
                "published": 0,
                "postponed": 0,
                "posting_date": None,
                "planned_date": None,
                "posting_time": None,
                **values,
            }
        )

    def test_an_undated_item_is_reported_not_imported(self):
        # a post without a date would have no slot on the calendar
        self.assertEqual(
            import_item(self.item(), self.calendar, CUSTOMER, "Instagram"), "no-date"
        )
        self.assertFalse(frappe.db.exists("HD Content Post", {"customer": CUSTOMER}))

    def test_a_dated_item_is_imported_once(self):
        item = self.item(posting_date="2026-11-02", posting_time="10:00:00")
        self.assertEqual(
            import_item(item, self.calendar, CUSTOMER, "Instagram"), "imported"
        )
        self.assertEqual(
            import_item(item, self.calendar, CUSTOMER, "Instagram"), "duplicate"
        )
