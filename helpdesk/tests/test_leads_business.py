from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk.api import leads as leads_api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsError
from helpdesk.test_utils import FakeCRM, create_agent, enable_leads, hold_commits

BOSS = "boss.agent@business.example"
BDE = "bde.agent@business.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
BUSINESS = {"pipeline": {"count": 12}, "revenue": {"invoiced": 500.0}}


class TestBusinessOverview(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BOSS, "Boss", "Manager")
        create_agent(BDE, "Bina", "BDE")
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["get_business_overview"] = BUSINESS
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_periods_are_worked_out_here(self):
        today = getdate(nowdate())
        start, end = leads_api.business_range("month", None, None)
        self.assertEqual((start.day, end), (1, today))
        start, end = leads_api.business_range("last_month", None, None)
        self.assertEqual((end.month == start.month, add_days(end, 1).day), (True, 1))
        self.assertLess(end, today.replace(day=1))
        start, _end = leads_api.business_range("quarter", None, None)
        self.assertEqual((start.day, start.month % 3), (1, 1))
        start, _end = leads_api.business_range("fy", None, None)
        self.assertEqual((start.month, start.day), (4, 1))
        self.assertLessEqual(start, today)
        self.assertEqual(
            leads_api.business_range("custom", "2026-01-01", "2026-01-31"),
            (getdate("2026-01-01"), getdate("2026-01-31")),
        )
        for args in (
            ("decade", None, None),
            ("custom", "2026-01-01", None),
            ("custom", "2026-02-01", "2026-01-01"),
        ):
            with self.assertRaises(frappe.ValidationError):
                leads_api.business_range(*args)

    def test_it_is_read_from_the_erp_site_as_the_signed_in_person(self):
        frappe.set_user(BOSS)
        result = leads_api.get_business_overview(
            period="custom",
            from_date="2026-10-01",
            to_date="2026-10-31",
            department="Web",
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["pipeline"]["count"], 12)
        [(method, post, params)] = self.crm.lead_calls
        self.assertEqual(
            (method, post, params["acting_user"]),
            ("get_business_overview", False, BOSS),
        )
        self.assertEqual(
            (
                params["from_date"],
                params["to_date"],
                params["department"],
                params["include_profit"],
            ),
            ("2026-10-01", "2026-10-31", "Web", 0),
        )

    def test_a_read_is_kept_per_person_for_a_minute(self):
        frappe.set_user(BOSS)
        leads_api.get_business_overview()
        leads_api.get_business_overview()
        self.assertEqual(len(self.crm.lead_calls), 1)
        leads_api.get_business_overview(fresh=1)
        self.assertEqual(len(self.crm.lead_calls), 2)
        # another period or department is another read
        leads_api.get_business_overview(period="fy")
        leads_api.get_business_overview(department="Web")
        self.assertEqual(len(self.crm.lead_calls), 4)
        # and nobody is handed another person's copy
        self.crm.lead_answers["get_business_overview"] = CRMError(
            "x", 403, "PermissionError"
        )
        frappe.set_user(BDE)
        with self.assertRaises(LeadsError):
            leads_api.get_business_overview()
        self.assertEqual(len(self.crm.lead_calls), 5)

    def test_the_erp_site_decides_who_may_see_it(self):
        self.crm.lead_answers["get_business_overview"] = CRMError(
            "x", 403, "PermissionError"
        )
        frappe.set_user(BDE)
        with self.assertRaises(LeadsError) as refused:
            leads_api.get_business_overview()
        self.assertIn("Only management", str(refused.exception))
        # a refusal is never kept
        self.crm.lead_answers["get_business_overview"] = BUSINESS
        self.assertTrue(leads_api.get_business_overview()["available"])

    def test_an_older_erp_site_says_not_available_and_is_asked_again(self):
        self.crm.lead_answers["get_business_overview"] = CRMError(
            "x",
            403,
            "Function tbo_smart.api.hub_leads.get_business_overview is not whitelisted.",
        )
        frappe.set_user(BOSS)
        self.assertEqual(leads_api.get_business_overview(), {"available": False})
        self.crm.lead_answers["get_business_overview"] = BUSINESS
        self.assertTrue(leads_api.get_business_overview()["available"])

    def test_the_tab_flag_comes_from_the_erp_site_options(self):
        self.crm.lead_answers["get_options"] = {"stages": [], "can_view_business": True}
        frappe.set_user(BOSS)
        self.assertTrue(leads_api.get_options()["can_view_business"])

    def test_leads_off_means_no_business_overview(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        frappe.set_user(BOSS)
        with self.assertRaises(frappe.PermissionError):
            leads_api.get_business_overview()
        self.assertEqual(self.crm.lead_calls, [])
