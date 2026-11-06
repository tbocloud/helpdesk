"""The BD view: a salesperson sees Today's calls, their own leads and follow-ups only, on the
server as well as in the page; and what they call for is switched in one place (docs/leads.md)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import call_batches
from helpdesk.api import leads as leads_api
from helpdesk.api import pending_calls, prospects
from helpdesk.api.auth import get_user
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRM,
    bd_options,
    clear_pending_calls,
    create_agent,
    enable_leads,
    hold_commits,
    make_sales_employee,
    make_sales_manager,
    my_calls,
    queue_call,
)

BD = "fidha.bd@bdview.example"
HEAD = "head.bd@bdview.example"
MANAGER = "manager.bd@bdview.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
ROWS = {"rows": [{"name": "LEAD-1", "lead_name": "Asha Traders"}], "total": 1}


class BDCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_sales_employee(BD, "Fidha Bd")
        make_sales_employee(HEAD, "Hari Head")
        make_sales_manager(MANAGER)
        enable_leads()
        clear_pending_calls()
        self.addCleanup(clear_pending_calls)
        self.crm = FakeCRM()
        self.crm.lead_answers["list_leads"] = ROWS
        self.crm.lead_answers["get_options"] = bd_options(head_of=())
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def calls(self, method):
        return [params for name, _post, params in self.crm.lead_calls if name == method]

    def head_options(self):
        self.crm.lead_answers["get_options"] = bd_options(
            member_of=(), head_of=("GrowthX",)
        )
        frappe.cache.delete_keys("hd_leads:")


class TestBDGate(BDCase):
    def test_a_sales_employee_who_is_no_manager_is_a_bd(self):
        frappe.set_user(BD)
        self.assertTrue(leads_api.is_bd())
        self.assertTrue(leads_api.get_options()["is_bd"])
        self.assertTrue(get_user()["is_sales_bd"])

    def test_managers_and_heads_are_not(self):
        frappe.set_user(MANAGER)
        self.assertFalse(leads_api.is_bd())
        frappe.set_user("Administrator")
        self.assertFalse(leads_api.is_bd())
        frappe.set_user(HEAD)
        self.head_options()
        self.assertFalse(leads_api.is_bd())
        self.assertFalse(leads_api.get_options()["is_bd"])

    def test_a_support_agent_is_no_bd(self):
        create_agent("support.bd@bdview.example", "Sunil", "Support")
        frappe.set_user("support.bd@bdview.example")
        self.assertFalse(get_user()["is_sales_bd"])

    def test_the_all_view_becomes_their_own_leads(self):
        frappe.set_user(BD)
        leads_api.list_leads(view="all", owner="someone@else.example")
        sent = self.calls("list_leads")[-1]
        self.assertEqual(sent["view"], "mine")
        self.assertEqual(sent["owner"], BD)

    def test_their_other_views_are_kept_but_only_their_own_leads(self):
        frappe.set_user(BD)
        leads_api.list_leads(view="follow_up", owner="someone@else.example")
        sent = self.calls("list_leads")[-1]
        self.assertEqual((sent["view"], sent["owner"]), ("follow_up", BD))

    def test_a_bd_opens_only_their_own_lead(self):
        self.crm.lead_answers["get_lead"] = {
            "lead": {"name": "LEAD-1", "lead_owner": "someone@else.example"}
        }
        frappe.set_user(BD)
        with self.assertRaises(frappe.PermissionError):
            leads_api.get_lead("LEAD-1")
        self.crm.lead_answers["get_lead"] = {
            "lead": {"name": "LEAD-1", "lead_owner": BD}
        }
        self.assertEqual(leads_api.get_lead("LEAD-1")["lead"]["name"], "LEAD-1")

    def test_a_head_opens_a_lead_of_their_team(self):
        self.crm.lead_answers["get_lead"] = {
            "lead": {"name": "LEAD-1", "lead_owner": "someone@else.example"}
        }
        frappe.set_user(HEAD)
        self.head_options()
        self.assertEqual(leads_api.get_lead("LEAD-1")["lead"]["name"], "LEAD-1")

    def test_a_manager_and_a_head_keep_the_all_view(self):
        frappe.set_user(MANAGER)
        leads_api.list_leads(view="all")
        self.assertEqual(self.calls("list_leads")[-1]["view"], "all")
        frappe.set_user(HEAD)
        self.head_options()
        leads_api.list_leads(view="all", owner="x@y.example")
        sent = self.calls("list_leads")[-1]
        self.assertEqual((sent["view"], sent["owner"]), ("all", "x@y.example"))

    def test_the_team_figures_and_manager_tools_refuse_a_bd(self):
        frappe.set_user(BD)
        for refused in (
            lambda: leads_api.get_overview(),
            lambda: leads_api.get_overview_page(),
            lambda: leads_api.get_lead_intake(),
            lambda: leads_api.get_proposal_money(),
            lambda: leads_api.get_business_overview(),
            lambda: leads_api.get_daily_report(),
            lambda: prospects.get_prospect_runs(),
            lambda: prospects.estimate_prospect_run({"industry": "Hotels"}),
        ):
            with self.assertRaises(frappe.PermissionError):
                refused()
        self.assertEqual(self.calls("get_overview"), [])

    def test_a_manager_still_opens_the_overview(self):
        self.crm.lead_answers["get_overview"] = {"funnel": []}
        frappe.set_user(MANAGER)
        self.assertEqual(leads_api.get_overview()["funnel"], [])

    def test_when_the_erp_site_cannot_say_a_sales_employee_is_treated_as_a_bd(self):
        self.crm.lead_answers["get_options"] = CRMError("down", 502)
        frappe.set_user(BD)
        self.assertTrue(leads_api.is_bd())


class TestCallingFor(BDCase):
    def test_the_switch_goes_to_the_erp_site_as_the_person(self):
        self.crm.lead_answers["set_calling_focus"] = {
            "focus": {"department": "StayVeX", "product": None, "district": "Kochi"},
            "label": "StayVeX in Kochi",
            "message": "Calling for StayVeX in Kochi.",
            "next_batch": {"created": True},
        }
        frappe.set_user(BD)
        result = call_batches.set_calling_focus("StayVeX", "", "Kochi")
        self.assertEqual(result["label"], "StayVeX in Kochi")
        sent = [c for c in self.crm.lead_calls if c[0] == "set_calling_focus"][-1]
        self.assertTrue(sent[1])
        self.assertEqual(sent[2]["department"], "StayVeX")
        self.assertIsNone(sent[2]["product"])
        self.assertEqual(sent[2]["district"], "Kochi")

    def test_the_queue_carries_the_choice_and_the_options(self):
        focus = {"department": "GrowthX", "product": "PhoebiX", "district": None}
        self.crm.lead_answers["get_my_calls"] = my_calls(
            pending=(queue_call("a"),),
            focus=focus,
            focus_options=[{"department": "GrowthX", "products": []}],
        )
        frappe.set_user(BD)
        result = call_batches.get_my_calls()
        self.assertEqual(result["focus"], focus)
        self.assertEqual(result["focus_options"][0]["department"], "GrowthX")


class TestCallsWithoutAResult(BDCase):
    def start(self, lead="LEAD-1", **fields):
        return pending_calls.start_call(lead, "Asha Traders", "9847012345", **fields)

    def test_a_tapped_call_waits_for_its_result(self):
        frappe.set_user(BD)
        result = self.start(item="CBI-1")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["calls"][0]["lead"], "LEAD-1")
        self.assertEqual(result["calls"][0]["item"], "CBI-1")
        self.assertEqual(pending_calls.get_pending_calls()["count"], 1)

    def test_tapping_call_again_keeps_one_entry_for_the_lead(self):
        frappe.set_user(BD)
        self.start()
        self.assertEqual(self.start()["count"], 1)

    def test_the_list_is_per_person_and_oldest_first(self):
        frappe.set_user(BD)
        self.start("LEAD-1")
        self.start("LEAD-2")
        self.assertEqual(
            [c["lead"] for c in pending_calls.get_pending_calls()["calls"]],
            ["LEAD-1", "LEAD-2"],
        )
        frappe.set_user(HEAD)
        self.assertEqual(pending_calls.get_pending_calls()["count"], 0)

    def test_a_result_from_todays_calls_clears_it(self):
        self.crm.lead_answers["record_call_outcome"] = {"item": "CBI-1"}
        frappe.set_user(BD)
        self.start("LEAD-1", item="CBI-1")
        self.start("LEAD-2")
        call_batches.record_call_outcome("CBI-1", "Busy")
        self.assertEqual(
            [c["lead"] for c in pending_calls.get_pending_calls()["calls"]], ["LEAD-2"]
        )
        call_batches.record_call_outcome("CBI-2", "Busy", lead="LEAD-2")
        self.assertEqual(pending_calls.get_pending_calls()["count"], 0)

    def test_a_logged_call_clears_it(self):
        self.crm.lead_answers["log_call"] = {"name": "LEAD-1"}
        frappe.set_user(BD)
        self.start("LEAD-1")
        leads_api.log_call("LEAD-1", "Not answered")
        self.assertEqual(pending_calls.get_pending_calls()["count"], 0)

    def test_a_refused_result_keeps_it_waiting(self):
        self.crm.lead_answers["record_call_outcome"] = CRMError("no", 417)
        frappe.set_user(BD)
        self.start("LEAD-1", item="CBI-1")
        with self.assertRaises(Exception):
            call_batches.record_call_outcome("CBI-1", "Busy", lead="LEAD-1")
        self.assertEqual(pending_calls.get_pending_calls()["count"], 1)

    def test_dismissing_needs_a_reason_from_the_list(self):
        frappe.set_user(BD)
        self.start()
        with self.assertRaises(frappe.ValidationError):
            pending_calls.dismiss_pending_call("LEAD-1", "just because")
        self.assertEqual(pending_calls.get_pending_calls()["count"], 1)
        result = pending_calls.dismiss_pending_call("LEAD-1", "Didn't call")
        self.assertEqual(result["count"], 0)

    def test_an_old_call_is_forgotten(self):
        frappe.set_user(BD)
        self.start()
        key = pending_calls.key_of(BD)
        entry = frappe.cache.hget(key, "LEAD-1")
        entry["at"] = "2020-01-01 10:00:00"
        frappe.cache.hset(key, "LEAD-1", entry)
        self.assertEqual(pending_calls.get_pending_calls()["count"], 0)

    def test_the_list_holds_the_latest_calls_only(self):
        frappe.set_user(BD)
        for number in range(pending_calls.MAX_PENDING + 3):
            self.start(f"LEAD-{number}")
        calls = pending_calls.get_pending_calls()["calls"]
        self.assertEqual(len(calls), pending_calls.MAX_PENDING)
        self.assertEqual(calls[-1]["lead"], f"LEAD-{pending_calls.MAX_PENDING + 2}")

    def test_a_person_without_leads_cannot_use_it(self):
        create_agent("plain.bd@bdview.example", "Plain", "Agent")
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        frappe.set_user("plain.bd@bdview.example")
        with self.assertRaises(frappe.PermissionError):
            pending_calls.start_call("LEAD-1")


class TestWhoGetsTheBDView(BDCase):
    def test_a_sales_employee_who_also_administers_does_not_get_it(self):
        from helpdesk.content_team import is_sales_bd_role

        self.assertTrue(is_sales_bd_role(BD))
        self.assertFalse(is_sales_bd_role(MANAGER))
        for role in ("System Manager", "Agent Manager"):
            frappe.get_doc("User", HEAD).add_roles(role)
            self.assertFalse(is_sales_bd_role(HEAD), role)
            frappe.get_doc("User", HEAD).remove_roles(role)
