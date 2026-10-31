import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import commission as api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsError, LeadsUnavailableError
from helpdesk.test_utils import (
    FakeCRM,
    commission_month,
    create_agent,
    enable_leads,
    hold_commits,
)

BDE = "commission.bde@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
COMMISSION = "tbo_smart.api.hub_commission"
OLDER_ERP = CRMError(
    "x", 417, "Failed to get method for command tbo_smart.api.hub_commission.x"
)


class TestCommission(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "BDE")
        enable_leads(teams=())
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(BDE)

    def calls(self, method):
        return [
            (post, params)
            for name, post, params in self.crm.lead_calls
            if name == method
        ]

    def test_the_month_is_read_live_as_the_signed_in_person(self):
        self.crm.lead_answers["get_commission"] = commission_month()
        first = api.get_commission("2026-10")
        api.get_commission("2026-10")
        self.assertTrue(first["available"])
        self.assertEqual(first["rows"][0]["commission"], 11000.0)
        self.assertEqual(len(self.calls("get_commission")), 2, "never cached")
        post, params = self.calls("get_commission")[0]
        self.assertFalse(post)
        self.assertEqual(
            (params["acting_user"], params["month"], params["user"]),
            (BDE, "2026-10", None),
        )
        self.assertIn(COMMISSION, self.crm.lead_paths[0])

    def test_filters_are_passed_trimmed(self):
        self.crm.lead_answers["get_commission"] = commission_month()
        api.get_commission("2026-10", user=" a@x.example ", department=" GrowthX ")
        [(_post, params)] = self.calls("get_commission")
        self.assertEqual(
            (params["user"], params["department"]), ("a@x.example", "GrowthX")
        )

    def test_an_older_erp_site_hides_commission_quietly(self):
        self.crm.lead_answers["get_commission"] = OLDER_ERP
        frappe.clear_messages()
        self.assertEqual(api.get_commission("2026-10"), {"available": False})
        self.assertEqual(frappe.message_log, [])

    def test_a_refusal_says_what_is_needed(self):
        self.crm.lead_answers["get_commission_plans"] = CRMError("x", 403, "no")
        with self.assertRaises(LeadsError):
            api.get_commission_plans()

    def test_writes_go_to_the_erp_site_as_posts(self):
        self.crm.lead_answers["generate_statements"] = [
            {"user": BDE, "name": "COMM-00001", "status": "Draft", "skipped": 0}
        ]
        self.crm.lead_answers["approve_statement"] = {"status": "Approved"}
        self.crm.lead_answers["mark_paid"] = {"status": "Paid"}
        self.assertEqual(api.generate_statements("2026-10")[0]["name"], "COMM-00001")
        api.approve_statement("COMM-00001")
        api.mark_paid("COMM-00001")
        for method in ("generate_statements", "approve_statement", "mark_paid"):
            [(post, params)] = self.calls(method)
            self.assertTrue(post)
            self.assertEqual(params["acting_user"], BDE)

    def test_writes_on_an_older_erp_site_say_so(self):
        self.crm.lead_answers["approve_statement"] = OLDER_ERP
        with self.assertRaises(LeadsUnavailableError):
            api.approve_statement("COMM-00001")

    def test_a_plan_is_saved_with_its_values_as_json(self):
        self.crm.lead_answers["save_commission_plan"] = {"name": "Default"}
        values = {"plan_name": "Default", "slabs": [{"from_amount": 0, "rate": 2}]}
        api.save_commission_plan(values)
        api.save_commission_plan(json.dumps(values), name="Default")
        (_p, new), (_q, edit) = self.calls("save_commission_plan")
        self.assertEqual(json.loads(new["values"])["slabs"][0]["rate"], 2)
        self.assertEqual((new["name"], edit["name"]), (None, "Default"))
        with self.assertRaises(frappe.ValidationError):
            api.save_commission_plan("[1]")

    def test_a_project_set_up_is_read_and_saved(self):
        self.crm.lead_answers["get_project_commission"] = {
            "setup": None,
            "collected": 0,
        }
        self.crm.lead_answers["save_project_commission"] = {"setup": {}}
        self.assertIsNone(api.get_project_commission("PROJ-0001")["setup"])
        api.save_project_commission({"project": "PROJ-0001", "earners": []})
        [(post, params)] = self.calls("save_project_commission")
        self.assertTrue(post)
        self.assertEqual(json.loads(params["values"])["project"], "PROJ-0001")
