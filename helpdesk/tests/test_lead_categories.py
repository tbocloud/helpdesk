import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import leads as leads_api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsUnavailableError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    lead_category_options,
    make_team,
)

BDE = "bde.agent@categories.example"
TEAM = "Lead Categories Sales"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class TestLeadCategories(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "BDE")
        make_team(TEAM, [BDE])
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["list_leads"] = {"rows": [], "total": 0}
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(BDE)

    def last_params(self, method: str) -> dict:
        return [
            params for name, _post, params in self.crm.lead_calls if name == method
        ][-1]

    def test_options_carry_the_categories(self):
        self.crm.lead_answers["get_options"] = lead_category_options()
        options = leads_api.get_options(fresh=1)
        self.assertEqual(options["industries"], ["Resorts", "Builders & Developers"])
        self.assertEqual(options["districts_by_state"]["Kerala"], ["Kozhikode"])

    def test_list_sends_each_filter_as_a_json_list(self):
        leads_api.list_leads(
            industry=["Resorts", "Hotels & Restaurants"],
            state="Kerala",
            district=json.dumps(["Kozhikode", "Wayanad"]),
            org_size=["11-50"],
        )
        params = self.last_params("list_leads")
        self.assertEqual(
            json.loads(params["industry"]), ["Resorts", "Hotels & Restaurants"]
        )
        self.assertEqual(json.loads(params["state"]), ["Kerala"])
        self.assertEqual(json.loads(params["district"]), ["Kozhikode", "Wayanad"])
        self.assertEqual(json.loads(params["org_size"]), ["11-50"])

    def test_the_last_call_result_is_sent_as_a_json_list_and_checked(self):
        leads_api.list_leads(last_call_result=["Busy", "Not answered"])
        params = self.last_params("list_leads")
        self.assertEqual(
            json.loads(params["last_call_result"]), ["Busy", "Not answered"]
        )
        leads_api.list_leads(last_call_result="Not interested")
        params = self.last_params("list_leads")
        self.assertEqual(json.loads(params["last_call_result"]), ["Not interested"])
        calls = len(self.crm.lead_calls)
        with self.assertRaises(frappe.ValidationError):
            leads_api.list_leads(last_call_result="Talked")
        self.assertEqual(len(self.crm.lead_calls), calls)

    def test_no_filter_sends_none(self):
        leads_api.list_leads(industry=[], state="  ")
        params = self.last_params("list_leads")
        self.assertEqual(
            [
                params[key]
                for key in (
                    "industry",
                    "state",
                    "district",
                    "org_size",
                    "last_call_result",
                )
            ],
            [None, None, None, None, None],
        )

    def test_a_lead_is_saved_with_its_categories(self):
        data = {
            "company_name": "Palm",
            "industry": "Resorts",
            "state": "Kerala",
            "district": "Kozhikode",
        }
        self.crm.lead_answers["create_lead"] = {"lead": {"name": "L-1"}}
        leads_api.create_lead(data)
        self.assertEqual(self.last_params("create_lead")["data"], data)

    def test_counts_are_read_and_empty_on_an_older_erp_site(self):
        self.crm.lead_answers["get_category_counts"] = {"industry": {"Resorts": 3}}
        self.assertEqual(
            leads_api.get_category_counts(fresh=1), {"industry": {"Resorts": 3}}
        )
        self.crm.lead_answers["get_category_counts"] = CRMError(
            "no", 404, "AttributeError: module has no attribute get_category_counts"
        )
        self.assertEqual(leads_api.get_category_counts(fresh=1), {})

    def test_a_manager_adds_an_industry(self):
        self.crm.lead_answers["add_industry"] = {"name": "Salons", "created": True}
        self.assertEqual(
            leads_api.add_industry(" Salons "), {"name": "Salons", "created": True}
        )
        self.assertEqual(self.last_params("add_industry")["name"], "Salons")

    def test_a_refusal_says_who_may_add_an_industry(self):
        self.crm.lead_answers["add_industry"] = CRMError("no", 403, "PermissionError")
        with self.assertRaises(frappe.ValidationError) as caught:
            leads_api.add_industry("Salons")
        self.assertIn("Sales Manager", str(caught.exception))

    def test_bulk_set_sends_the_leads_and_values(self):
        self.crm.lead_answers["bulk_set_lead_category"] = {"updated": 2, "skipped": []}
        result = leads_api.bulk_set_lead_category(
            ["L-1", "L-2"], json.dumps({"industry": "Resorts", "district": ""})
        )
        self.assertEqual(result["updated"], 2)
        params = self.last_params("bulk_set_lead_category")
        self.assertEqual(params["leads"], ["L-1", "L-2"])
        self.assertEqual(params["values"], {"industry": "Resorts", "district": ""})

    def test_bulk_set_needs_leads(self):
        with self.assertRaises(frappe.ValidationError):
            leads_api.bulk_set_lead_category([], {"industry": "Resorts"})
        self.assertEqual(
            [c for c in self.crm.lead_calls if c[0] == "bulk_set_lead_category"], []
        )

    def test_bulk_set_on_an_older_erp_site_says_so(self):
        self.crm.lead_answers["bulk_set_lead_category"] = CRMError(
            "no", 404, "AttributeError: module has no attribute bulk_set_lead_category"
        )
        with self.assertRaises(LeadsUnavailableError):
            leads_api.bulk_set_lead_category(["L-1"], {"industry": "Resorts"})
