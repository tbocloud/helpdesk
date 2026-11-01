from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import prospects as api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsError, LeadsUnavailableError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    make_sales_manager,
    prospect_run,
)

MANAGER = "prospects.manager@leads.example"
BDE = "prospects.bde@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
VALUES = {
    "industry": "Resorts",
    "state": "Kerala",
    "districts": ["Idukki"],
    "provider": "OpenStreetMap",
    "max_results": 50,
    "department": "GrowthX",
}
OLDER_ERP = CRMError(
    "x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x"
)


class TestFindProspects(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_sales_manager(MANAGER, "Mia")
        create_agent(BDE, "Bina", "BDE")
        enable_leads(teams=())
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(MANAGER)

    def calls(self, method):
        return [
            (post, params)
            for name, post, params in self.crm.lead_calls
            if name == method
        ]

    def test_an_estimate_goes_to_the_erp_site_as_the_signed_in_person(self):
        self.crm.lead_answers["estimate_prospect_run"] = prospect_run()
        run = api.estimate_prospect_run(frappe.as_json(VALUES))
        self.assertEqual((run["status"], run["expected_count"]), ("Estimated", 37))
        post, params = self.calls("estimate_prospect_run")[0]
        self.assertTrue(post)
        self.assertEqual(params["values"], VALUES)
        self.assertEqual(params["acting_user"], MANAGER)

    def test_a_run_is_started_by_name_and_the_cached_reads_go(self):
        self.crm.lead_answers["start_prospect_run"] = prospect_run(status="Running")
        with patch("helpdesk.api.prospects.clear_cached_reads") as clear:
            run = api.start_prospect_run("PR-0001")
        self.assertEqual(run["status"], "Running")
        self.assertEqual(self.calls("start_prospect_run")[0][1]["name"], "PR-0001")
        self.assertTrue(self.calls("start_prospect_run")[0][0])
        clear.assert_called_once()

    def test_the_runs_and_one_run_are_read_live(self):
        self.crm.lead_answers["get_prospect_runs"] = [
            prospect_run("PR-0002", status="Running", count_found=12),
            prospect_run(),
        ]
        self.crm.lead_answers["get_prospect_run"] = {
            **prospect_run(status="Done", count_created=2),
            "log": "Idukki: 5 from OpenStreetMap, 4 inside the district.",
            "leads": [
                {
                    "name": "CRM-LEAD-1",
                    "company_name": "Palm Resort",
                    "phone": "9847012345",
                    "why_call": "No online booking on the site.",
                }
            ],
        }
        first = api.get_prospect_runs()
        api.get_prospect_runs()
        self.assertTrue(first["available"])
        self.assertEqual([r["name"] for r in first["runs"]], ["PR-0002", "PR-0001"])
        self.assertEqual(len(self.calls("get_prospect_runs")), 2)
        opened = api.get_prospect_run("PR-0001")
        self.assertEqual(
            opened["leads"][0]["why_call"], "No online booking on the site."
        )

    def test_a_refusal_says_who_may_find_prospects(self):
        self.crm.lead_answers["estimate_prospect_run"] = CRMError(
            "x", 403, "PermissionError"
        )
        self.crm.lead_answers["start_prospect_run"] = CRMError(
            "x", 403, "PermissionError", "Estimate the run first."
        )
        with self.assertRaises(LeadsError) as caught:
            api.estimate_prospect_run(VALUES)
        self.assertIn("managers and department heads", str(caught.exception))
        self.assertNotIn("sales account", str(caught.exception))
        with self.assertRaises(LeadsError) as caught:
            api.start_prospect_run("PR-0001")
        self.assertIn("Estimate the run first.", str(caught.exception))

    def test_an_older_erp_site_says_so_in_words_and_the_list_just_hides(self):
        for method in (
            "get_prospect_runs",
            "estimate_prospect_run",
            "start_prospect_run",
        ):
            self.crm.lead_answers[method] = OLDER_ERP
        frappe.clear_messages()
        self.assertEqual(api.get_prospect_runs(), {"available": False, "runs": []})
        self.assertEqual(frappe.message_log, [])
        with self.assertRaises(LeadsUnavailableError) as caught:
            api.estimate_prospect_run(VALUES)
        self.assertIn("latest TBO Smart", str(caught.exception))
        with self.assertRaises(LeadsUnavailableError):
            api.start_prospect_run("PR-0001")

    def test_it_is_for_people_who_use_leads(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        frappe.cache.delete_keys("hd_leads:")
        for call in (
            lambda: api.estimate_prospect_run(VALUES),
            lambda: api.start_prospect_run("PR-0001"),
            api.get_prospect_runs,
            lambda: api.get_prospect_run("PR-0001"),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()
        self.assertEqual(self.crm.lead_calls, [])
