from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk import daily_sales_report as job
from helpdesk.api import call_batches as api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsForbiddenError
from helpdesk.test_utils import (
    FakeCRM,
    call_batches_report,
    call_plans,
    create_agent,
    enable_leads,
    hold_commits,
    make_sales_manager,
    my_calls,
    queue_call,
)

BDE = "calls.bde@leads.example"
OUTSIDER = "calls.outsider@leads.example"
MANAGER = "calls.manager@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
OLDER_ERP = CRMError(
    "x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x"
)


class TestTodaysCalls(FrappeTestCase):
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

    def in_an_hour(self):
        return str(add_to_date(now_datetime(), hours=1))

    def test_the_queue_is_read_live_as_the_signed_in_person(self):
        self.crm.lead_answers["get_my_calls"] = my_calls(
            pending=(queue_call("a"), queue_call("b"))
        )
        first = api.get_my_calls()
        api.get_my_calls()
        self.assertTrue(first["available"])
        self.assertEqual(first["counts"]["pending"], 2)
        # never served from the cache: calls made another way count on the ERP site
        self.assertEqual(len(self.calls("get_my_calls")), 2)
        self.assertEqual(self.calls("get_my_calls")[0][1]["acting_user"], BDE)

    def test_the_product_a_call_is_for_reaches_the_person(self):
        call = queue_call(
            "a",
            product="PhoebiX",
            intro_line="PhoebiX - solar ERP for installers",
            calling_for="PhoebiX",
        )
        self.crm.lead_answers["get_my_calls"] = my_calls(
            pending=(call,), batch_fields={"campaign_product": "PhoebiX"}
        )
        result = api.get_my_calls()
        self.assertEqual(result["pending"][0]["calling_for"], "PhoebiX")
        self.assertEqual(
            result["pending"][0]["intro_line"], "PhoebiX - solar ERP for installers"
        )
        self.assertEqual(result["batch"]["campaign_product"], "PhoebiX")

    def test_an_older_erp_site_says_it_is_not_available(self):
        self.crm.lead_answers["get_my_calls"] = OLDER_ERP
        frappe.clear_messages()
        self.assertEqual(api.get_my_calls(), {"available": False, "enabled": False})
        self.assertEqual(frappe.message_log, [])

    def test_a_department_without_batches_is_just_not_enabled(self):
        self.crm.lead_answers["get_my_calls"] = my_calls(enabled=False)
        self.assertFalse(api.get_my_calls()["enabled"])

    def test_someone_without_leads_gets_nothing(self):
        create_agent(OUTSIDER, "Olive", "Support")
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        frappe.cache.delete_keys("hd_leads:")
        self.assertRaises(frappe.PermissionError, api.get_my_calls)
        self.assertEqual(self.crm.lead_calls, [])

    def test_an_outcome_goes_to_the_erp_site_as_a_post_with_a_trimmed_note(self):
        self.crm.lead_answers["record_call_outcome"] = {
            "item": "a",
            "outcome": "Connected",
            "retry_at": None,
        }
        api.record_call_outcome("a", "Connected", note="  Wants a demo  ")
        ((post, params),) = self.calls("record_call_outcome")
        self.assertTrue(post)
        self.assertEqual(
            (params["batch_item"], params["outcome"], params["note"]),
            ("a", "Connected", "Wants a demo"),
        )
        self.assertIsNone(params["callback_at"])

    def test_every_outcome_the_erp_site_knows_is_accepted(self):
        self.crm.lead_answers["record_call_outcome"] = {}
        for outcome in ("Not answered", "Busy", "Not interested", "Wrong number"):
            api.record_call_outcome("a", outcome)
        self.assertEqual(len(self.calls("record_call_outcome")), 4)

    def test_a_made_up_outcome_is_refused_before_the_erp_site_is_asked(self):
        self.assertRaises(
            frappe.ValidationError, api.record_call_outcome, "a", "No answer"
        )
        self.assertEqual(self.crm.lead_calls, [])

    def test_a_call_back_needs_a_time_in_the_future(self):
        self.crm.lead_answers["record_call_outcome"] = {}
        self.assertRaises(
            frappe.ValidationError, api.record_call_outcome, "a", "Call back"
        )
        past = str(add_to_date(now_datetime(), hours=-1))
        self.assertRaises(
            frappe.ValidationError,
            api.record_call_outcome,
            "a",
            "Call back",
            None,
            past,
        )
        self.assertEqual(self.crm.lead_calls, [])
        api.record_call_outcome("a", "Call back", callback_at=self.in_an_hour())
        self.assertEqual(len(self.calls("record_call_outcome")), 1)

    def test_an_outcome_clears_the_cached_reads(self):
        self.crm.lead_answers["record_call_outcome"] = {}
        with patch.object(api, "clear_cached_reads") as clear:
            api.record_call_outcome("a", "Busy")
        clear.assert_called_once()

    def test_the_erp_sites_reason_for_a_failed_outcome_reaches_the_person(self):
        self.crm.lead_answers["record_call_outcome"] = CRMError(
            "x", 417, "boom", user_message="This call is already recorded as Busy."
        )
        with self.assertRaises(Exception) as caught:
            api.record_call_outcome("a", "Connected")
        self.assertIn("already recorded", str(caught.exception))

    def test_the_next_batch_is_asked_for_with_a_post_and_its_reason_is_passed_on(self):
        self.crm.lead_answers["get_next_batch"] = {
            "created": False,
            "reason": "Finish the 3 calls still waiting first.",
        }
        result = api.get_next_batch()
        self.assertFalse(result["created"])
        self.assertIn("3 calls", result["reason"])
        ((post, _params),) = self.calls("get_next_batch")
        self.assertTrue(post)

    def test_the_next_batch_needs_the_latest_erp_site(self):
        self.crm.lead_answers["get_next_batch"] = OLDER_ERP
        self.assertRaises(frappe.ValidationError, api.get_next_batch)


class TestCallBatchesReport(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_sales_manager(MANAGER, "Maya")
        enable_leads()
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.crm.lead_answers["get_call_batches_report"] = call_batches_report(
            [
                {
                    "user": "shahana@tbo.example",
                    "user_name": "Shahana V K",
                    "size": 100,
                    "called": 87,
                    "connected": 41,
                    "overdue": 4,
                }
            ]
        )

    def test_a_manager_reads_the_day(self):
        frappe.set_user(MANAGER)
        report = api.get_call_batches_report("2026-10-26")
        self.assertTrue(report["available"])
        self.assertEqual(report["totals"]["called"], 87)
        ((_post, params),) = [
            (p, q) for n, p, q in self.crm.lead_calls if n == "get_call_batches_report"
        ]
        self.assertEqual(params["date"], "2026-10-26")
        self.assertEqual(params["acting_user"], MANAGER)

    def test_an_older_erp_site_has_no_report(self):
        self.crm.lead_answers["get_call_batches_report"] = OLDER_ERP
        frappe.set_user(MANAGER)
        self.assertEqual(api.get_call_batches_report()["available"], False)

    def test_the_6_pm_message_lists_each_salesperson_and_the_total(self):
        lines = api.report_lines(self.crm.lead_answers["get_call_batches_report"])
        self.assertEqual(
            lines[0][0],
            "• Shahana V K: 87/100 called, 41 connected, 4 overdue",
        )
        self.assertEqual(lines[-1][0], "Total: 87/100 called, 4 overdue")
        self.assertEqual(api.report_lines({"people": []}), [])

    def test_the_daily_message_gets_a_call_batches_section(self):
        report = {
            "date": "2026-10-26",
            "people": [
                {"user": "shahana@tbo.example", "full_name": "Shahana V K"},
            ],
        }
        with patch("helpdesk.follow_ups.deliver_digest") as deliver, patch(
            "helpdesk.content_team.only_sales_team",
            side_effect=lambda people, *_: (people, False),
        ):
            job.send_report(MANAGER, report)
        _user, _subject, sections = deliver.call_args.args
        self.assertEqual(sections[-1][0], "📞 Call batches")

    def test_the_message_is_unchanged_when_the_erp_site_has_no_batches(self):
        self.crm.lead_answers["get_call_batches_report"] = OLDER_ERP
        report = {
            "date": "2026-10-26",
            "people": [{"user": "shahana@tbo.example", "full_name": "Shahana V K"}],
        }
        with patch("helpdesk.follow_ups.deliver_digest") as deliver, patch(
            "helpdesk.content_team.only_sales_team",
            side_effect=lambda people, *_: (people, False),
        ):
            job.send_report(MANAGER, report)
        _user, _subject, sections = deliver.call_args.args
        self.assertEqual([title for title, _ in sections], ["👤 Shahana V K"])


class TestCallPlans(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_sales_manager(MANAGER, "Maya")
        enable_leads()
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.crm.lead_answers["get_call_plans"] = call_plans()
        self.crm.lead_answers["save_call_plan"] = call_plans()["departments"][0]
        frappe.set_user(MANAGER)

    def calls(self, method):
        return [
            (post, params)
            for name, post, params in self.crm.lead_calls
            if name == method
        ]

    def test_the_plans_are_read_as_the_manager(self):
        plans = api.get_call_plans()
        self.assertTrue(plans["available"])
        self.assertEqual(plans["departments"][0]["members"][0]["sizes"]["Morning"], 50)
        ((_post, params),) = self.calls("get_call_plans")
        self.assertEqual(params["acting_user"], MANAGER)

    def test_an_older_erp_site_has_no_plans(self):
        self.crm.lead_answers["get_call_plans"] = OLDER_ERP
        self.assertEqual(api.get_call_plans(), {"available": False, "departments": []})

    def test_someone_who_may_not_assign_is_told_so(self):
        self.crm.lead_answers["get_call_plans"] = CRMError("x", 403, "no")
        with self.assertRaises(LeadsForbiddenError) as raised:
            api.get_call_plans()
        self.assertIn("assign leads", str(raised.exception))

    def test_a_plan_is_sent_with_its_people_product_and_sizes(self):
        result = api.save_call_plan(
            "GrowthX",
            frappe.as_json(["shahana@tbo.example"]),
            "  PhoebiX ",
            frappe.as_json({"Morning": 50, "Afternoon": 50}),
        )
        self.assertEqual(result["department"], "GrowthX")
        ((post, params),) = self.calls("save_call_plan")
        self.assertTrue(post)
        self.assertEqual(params["users"], ["shahana@tbo.example"])
        self.assertEqual(params["product"], "PhoebiX")
        self.assertEqual(params["sizes"], {"Morning": 50, "Afternoon": 50})
        self.assertEqual(params["clear"], 0)

    def test_clearing_sends_no_product_or_sizes(self):
        api.save_call_plan("GrowthX", ["shahana@tbo.example"], clear=1)
        ((_post, params),) = self.calls("save_call_plan")
        self.assertEqual(params["clear"], 1)
        self.assertIsNone(params["product"])
        self.assertIsNone(params["sizes"])

    def test_a_department_without_products_plans_and_gives_by_industry(self):
        api.save_call_plan(
            "TBO",
            ["shahana@tbo.example"],
            industry=" Hospitality ",
            sizes={"Morning": 40},
        )
        ((_post, params),) = self.calls("save_call_plan")
        self.assertEqual((params["industry"], params["product"]), ("Hospitality", None))
        self.crm.lead_answers["assign_leads"] = {"assigned": 3, "skipped": []}
        api.assign_leads("TBO", "shahana@tbo.example", count=3, industry="Hospitality")
        ((_post, params),) = self.calls("assign_leads")
        self.assertEqual((params["count"], params["industry"]), (3, "Hospitality"))
        # no industry chosen: nothing is sent for it, so an older ERP site is not asked
        api.save_call_plan("TBO", ["shahana@tbo.example"], sizes={"Morning": 40})
        self.assertNotIn("industry", self.calls("save_call_plan")[-1][1])

    def test_a_plan_needs_people(self):
        self.assertRaises(
            frappe.ValidationError, api.save_call_plan, "GrowthX", "[]", "PhoebiX"
        )
        self.assertEqual(self.calls("save_call_plan"), [])

    def test_saving_needs_the_latest_erp_site(self):
        self.crm.lead_answers["save_call_plan"] = OLDER_ERP
        self.assertRaises(
            frappe.ValidationError,
            api.save_call_plan,
            "GrowthX",
            ["shahana@tbo.example"],
        )

    def test_a_departments_leads_are_read_live_for_one_member_or_the_pool(self):
        self.crm.lead_answers["get_department_leads"] = {
            "rows": [],
            "total": 0,
            "products": {},
        }
        api.get_department_leads("GrowthX", " shahana@tbo.example ", "PhoebiX")
        api.get_department_leads("GrowthX", page_length=1000)
        first, second = [params for _post, params in self.calls("get_department_leads")]
        self.assertEqual(first["owner"], "shahana@tbo.example")
        self.assertEqual(first["product"], "PhoebiX")
        self.assertIsNone(second["owner"])
        self.assertEqual(second["page_length"], 100)

    def test_picked_leads_or_a_number_are_assigned(self):
        self.crm.lead_answers["assign_leads"] = {"assigned": 2, "skipped": []}
        api.assign_leads(
            "GrowthX", "shahana@tbo.example", frappe.as_json(["L-1", "L-2"])
        )
        api.assign_leads("GrowthX", "shahana@tbo.example", count="25", product="BillaX")
        picked, by_number = [params for post, params in self.calls("assign_leads")]
        self.assertEqual((picked["leads"], picked["count"]), (["L-1", "L-2"], 0))
        self.assertEqual(
            (by_number["leads"], by_number["count"], by_number["product"]),
            (None, 25, "BillaX"),
        )
        self.assertRaises(
            frappe.ValidationError, api.assign_leads, "GrowthX", "x@y.example"
        )

    def test_leads_go_back_to_the_pool(self):
        self.crm.lead_answers["unassign_leads"] = {"unassigned": 1, "skipped": []}
        self.assertEqual(api.unassign_leads("GrowthX", ["L-1"])["unassigned"], 1)
        ((post, params),) = self.calls("unassign_leads")
        self.assertTrue(post)
        self.assertEqual(params["leads"], ["L-1"])
        self.assertRaises(frappe.ValidationError, api.unassign_leads, "GrowthX", "[]")
