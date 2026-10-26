from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk.api import leads as leads_api
from helpdesk.api.auth import get_user
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsError, LeadsUnavailableError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    make_team,
)

BDE = "bde.agent@leads.example"
SUPPORT = "support.agent@leads.example"
TEAM = "Leads Test Sales"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class TestLeads(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "BDE")
        create_agent(SUPPORT, "Sunil", "Support")
        make_team(TEAM, [BDE])
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["list_leads"] = {
            "rows": [{"name": "CRM-LEAD-0001", "lead_name": "Asha Traders"}],
            "total": 1,
        }
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def as_bde(self):
        frappe.set_user(BDE)

    def test_leads_are_off_by_default(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        self.as_bde()
        with self.assertRaises(frappe.PermissionError):
            leads_api.list_leads()
        self.assertFalse(get_user()["can_use_leads"])
        self.assertEqual(self.crm.lead_calls, [])

    def test_the_digital_team_never_sees_leads(self):
        from helpdesk.content_team import (
            DM_EMPLOYEE_ROLE,
            SALES_EMPLOYEE_ROLE,
            ensure_role,
        )
        from helpdesk.integrations.crm.leads import can_use_leads

        ensure_role()
        user = frappe.get_doc("User", SUPPORT)
        user.add_roles("Agent Manager", DM_EMPLOYEE_ROLE)
        self.assertFalse(can_use_leads(SUPPORT))

        # a salesperson who also does digital work keeps Leads
        user.add_roles(SALES_EMPLOYEE_ROLE)
        self.assertTrue(can_use_leads(SUPPORT))
        user.remove_roles(SALES_EMPLOYEE_ROLE)

        user.add_roles("System Manager")
        self.assertTrue(can_use_leads(SUPPORT))

    def test_reads_go_to_the_crm_site_as_the_signed_in_person(self):
        self.as_bde()
        result = leads_api.list_leads(
            search="  asha ", view="mine", start=-5, page_length=500
        )

        self.assertEqual(result["total"], 1)
        ((method, post, params),) = self.crm.lead_calls
        self.assertEqual(method, "list_leads")
        self.assertFalse(post)
        self.assertEqual(params["acting_user"], BDE)
        self.assertEqual(params["search"], "asha")
        self.assertEqual(params["view"], "mine")
        self.assertEqual((params["start"], params["page_length"]), (0, 100))
        self.assertTrue(get_user()["can_use_leads"])

    def test_malformed_paging_falls_back_to_the_first_page(self):
        self.as_bde()
        leads_api.list_leads(start="abc", page_length="")
        ((_method, _post, params),) = self.crm.lead_calls
        self.assertEqual((params["start"], params["page_length"]), (0, 20))

    def test_an_unknown_view_is_refused(self):
        self.as_bde()
        with self.assertRaises(frappe.ValidationError):
            leads_api.list_leads(view="everything")
        self.assertEqual(self.crm.lead_calls, [])

    def test_the_overview_is_read_as_the_signed_in_person(self):
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 3}}
        self.as_bde()
        result = leads_api.get_overview(period="week", owner="", from_date="x")
        self.assertEqual(result["totals"]["new"], 3)
        ((method, post, params),) = self.crm.lead_calls
        self.assertEqual(
            (method, post, params["acting_user"]), ("get_overview", False, BDE)
        )
        # dates go only with a custom period
        self.assertEqual(
            (params["period"], params["from_date"], params["owner"]),
            ("week", None, None),
        )
        with self.assertRaises(frappe.ValidationError):
            leads_api.get_overview(period="decade")
        with self.assertRaises(frappe.ValidationError):
            leads_api.get_overview(period="custom", from_date="2026-10-01")

    def test_a_number_on_the_overview_opens_its_leads(self):
        self.as_bde()
        leads_api.list_leads(metric="won", period="quarter", source="Website")
        leads_api.list_leads(period="quarter", temperature="Hot")
        (_m, _p, first), (_m2, _p2, second) = self.crm.lead_calls
        self.assertEqual(
            (first["metric"], first["period"], first["source"]),
            ("won", "quarter", "Website"),
        )
        # without a metric the period means nothing and isn't sent
        self.assertEqual(
            (second["metric"], second["period"], second["temperature"]),
            (None, None, "Hot"),
        )
        with self.assertRaises(frappe.ValidationError):
            leads_api.list_leads(metric="won", period="decade")

    def test_today_and_yesterday_are_one_day_ranges_on_the_erp_site(self):
        today = getdate(nowdate())
        self.crm.lead_answers["get_overview"] = {"totals": {}}
        self.as_bde()
        leads_api.get_overview(period="today")
        leads_api.list_leads(metric="intake", period="yesterday", owner=BDE)
        (_m, _p, overview), (_m2, _p2, listed) = self.crm.lead_calls
        self.assertEqual(
            (overview["period"], overview["from_date"], overview["to_date"]),
            ("custom", str(today), str(today)),
        )
        yesterday = str(add_days(today, -1))
        self.assertEqual(
            (
                listed["metric"],
                listed["period"],
                listed["from_date"],
                listed["to_date"],
            ),
            ("intake", "custom", yesterday, yesterday),
        )
        self.assertEqual(listed["owner"], BDE)

    def test_the_intake_comes_with_the_daily_target(self):
        frappe.db.set_single_value("HD CRM Settings", "daily_lead_target", 10)
        self.crm.lead_answers["get_lead_intake"] = {"days": [], "people": []}
        self.as_bde()
        result = leads_api.get_lead_intake()
        self.assertEqual((result["available"], result["target"]), (True, 10))
        ((method, _post, params),) = self.crm.lead_calls
        today = getdate(nowdate())
        self.assertEqual(
            (method, params["from_date"], params["to_date"], params["acting_user"]),
            ("get_lead_intake", str(add_days(today, -1)), str(today), BDE),
        )
        # a negative target is no target
        frappe.db.set_single_value("HD CRM Settings", "daily_lead_target", -3)
        self.assertEqual(leads_api.get_lead_intake()["target"], 0)

    def test_the_money_is_read_for_the_period_and_owner(self):
        self.crm.lead_answers["get_proposal_money"] = {"totals": {"to_collect": 5}}
        self.as_bde()
        result = leads_api.get_proposal_money(period="month", owner=BDE)
        self.assertEqual(
            (result["available"], result["totals"]["to_collect"]), (True, 5)
        )
        ((method, _post, params),) = self.crm.lead_calls
        self.assertEqual(
            (method, params["period"], params["from_date"], params["owner"]),
            ("get_proposal_money", "month", None, BDE),
        )
        with self.assertRaises(frappe.ValidationError):
            leads_api.get_proposal_money(period="custom", to_date="2026-10-01")

    def test_an_older_erp_site_hides_the_new_parts_quietly(self):
        older = CRMError(
            "x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x"
        )
        self.crm.lead_answers["get_lead_intake"] = older
        self.crm.lead_answers["get_proposal_money"] = older
        self.as_bde()
        frappe.clear_messages()
        self.assertEqual(leads_api.get_lead_intake(), {"available": False})
        self.assertEqual(leads_api.get_proposal_money(), {"available": False})
        # nothing for a toast: the parts just stay out
        self.assertEqual(frappe.message_log, [])
        # anything else is still an error the page shows
        self.crm.lead_answers["get_lead_intake"] = CRMError("x", 502, "")
        with self.assertRaises(LeadsUnavailableError):
            leads_api.get_lead_intake()

    def test_the_overview_page_is_one_request_with_every_part(self):
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 3}}
        self.crm.lead_answers["get_proposal_money"] = {"totals": {"to_collect": 5}}
        self.crm.lead_answers["get_lead_intake"] = {"days": [], "people": []}
        self.as_bde()
        page = leads_api.get_overview_page(period="week", owner=BDE)

        self.assertEqual(page["overview"]["totals"]["new"], 3)
        self.assertEqual(page["money"]["totals"]["to_collect"], 5)
        self.assertTrue(page["money"]["available"])
        self.assertTrue(page["intake"]["available"])
        self.assertEqual(page["errors"], {})
        self.assertEqual(
            [m for m, _p, _q in self.crm.lead_calls],
            ["get_overview", "get_proposal_money", "get_lead_intake"],
        )
        with self.assertRaises(frappe.ValidationError):
            leads_api.get_overview_page(period="custom", from_date="2026-10-01")

    def test_a_failed_money_or_intake_leaves_the_overview_whole(self):
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 3}}
        self.crm.lead_answers["get_proposal_money"] = CRMError("x", 502, "")
        self.crm.lead_answers["get_lead_intake"] = CRMError("x", 502, "")
        self.as_bde()
        frappe.clear_messages()
        page = leads_api.get_overview_page()

        self.assertEqual(page["overview"]["totals"]["new"], 3)
        self.assertEqual((page["money"], page["intake"]), (None, None))
        self.assertEqual(set(page["errors"]), {"money", "intake"})
        self.assertIn("ERP site", page["errors"]["money"])
        self.assertEqual(frappe.message_log, [])
        # a failed read is not remembered: the next one asks again
        self.crm.lead_answers["get_proposal_money"] = {"totals": {}}
        self.assertTrue(leads_api.get_overview_page()["money"]["available"])

        # the overview itself failing fails the page
        self.crm.lead_answers["get_overview"] = CRMError("x", 502, "")
        with self.assertRaises(LeadsUnavailableError):
            leads_api.get_overview_page(period="quarter")

    def test_a_read_just_answered_is_not_asked_of_the_erp_site_again(self):
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 3}}
        self.crm.lead_answers["get_options"] = {"stages": []}
        self.crm.lead_answers["get_proposal_money"] = {"totals": {}}
        self.crm.lead_answers["get_lead_intake"] = {"days": [], "people": []}
        # the options also ask whether calls can be logged, which is kept too
        self.crm.lead_answers["get_daily_report"] = {"people": []}
        self.as_bde()
        leads_api.get_overview_page()
        leads_api.get_options()
        asked = len(self.crm.lead_calls)

        self.crm.lead_answers["get_overview"] = {"totals": {"new": 9}}
        again = leads_api.get_overview_page()
        leads_api.get_options()
        leads_api.get_overview(period="month")
        self.assertEqual(len(self.crm.lead_calls), asked)
        self.assertEqual(again["overview"]["totals"]["new"], 3)

        # another period is another read
        leads_api.get_overview_page(period="week")
        self.assertGreater(len(self.crm.lead_calls), asked)

    def test_fresh_skips_the_cache_and_renews_it(self):
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 3}}
        self.as_bde()
        leads_api.get_overview_page()
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 9}}

        self.assertEqual(
            leads_api.get_overview_page(fresh=1)["overview"]["totals"]["new"], 9
        )
        self.assertEqual(leads_api.get_overview_page()["overview"]["totals"]["new"], 9)

    def test_the_cache_is_per_person(self):
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 3}}
        self.as_bde()
        leads_api.get_overview_page()
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 7}}
        frappe.set_user("Administrator")

        page = leads_api.get_overview_page()
        self.assertEqual(page["overview"]["totals"]["new"], 7)
        acting = {p["acting_user"] for _m, _post, p in self.crm.lead_calls}
        self.assertEqual(acting, {BDE, "Administrator"})

    def test_changing_a_lead_clears_that_persons_cached_figures(self):
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 3}}
        self.crm.lead_answers["set_stage"] = {"name": "CRM-LEAD-0001"}
        self.as_bde()
        leads_api.get_overview_page()
        self.crm.lead_answers["get_overview"] = {"totals": {"new": 4}}
        leads_api.set_stage("CRM-LEAD-0001", "Contacted")

        self.assertEqual(leads_api.get_overview_page()["overview"]["totals"]["new"], 4)

    def test_ai_suggestions_are_the_signed_in_persons_to_act_on(self):
        self.crm.lead_answers["get_lead_ai"] = {"enabled": True, "insight": None}
        self.as_bde()
        self.assertTrue(leads_api.get_lead_ai("CRM-LEAD-0001")["enabled"])
        leads_api.apply_ai_stage("CRM-LEAD-0001")
        leads_api.draft_lead_message("CRM-LEAD-0001", "email", language="xx")
        leads_api.log_message_sent(
            "CRM-LEAD-0001", "whatsapp", "  Sent the demo link  "
        )
        calls = {method: (post, params) for method, post, params in self.crm.lead_calls}
        self.assertEqual(calls["get_lead_ai"][0], False)
        for method in ("apply_ai_stage", "draft_lead_message", "log_message_sent"):
            post, params = calls[method]
            self.assertTrue(post)
            self.assertEqual(params["acting_user"], BDE)
        self.assertEqual(calls["draft_lead_message"][1]["language"], "en")
        self.assertEqual(calls["log_message_sent"][1]["text"], "Sent the demo link")
        with self.assertRaises(frappe.ValidationError):
            leads_api.draft_lead_message("CRM-LEAD-0001", "sms")
        with self.assertRaises(frappe.ValidationError):
            leads_api.log_message_sent("CRM-LEAD-0001", "email", "  ")

    def test_writes_are_posted_with_the_acting_user(self):
        self.as_bde()
        leads_api.create_lead({"lead_name": "Asha Traders"})
        leads_api.update_lead("CRM-LEAD-0001", '{"mobile_no": "+91 98450 00000"}')
        leads_api.set_stage("CRM-LEAD-0001", "Qualified", note=" Met them ")
        leads_api.add_note("CRM-LEAD-0001", "Call back after Diwali")

        calls = {method: (post, params) for method, post, params in self.crm.lead_calls}
        self.assertTrue(all(post for post, _params in calls.values()))
        self.assertTrue(
            all(params["acting_user"] == BDE for _post, params in calls.values())
        )
        self.assertEqual(calls["create_lead"][1]["data"], {"lead_name": "Asha Traders"})
        self.assertEqual(
            calls["update_lead"][1]["data"], {"mobile_no": "+91 98450 00000"}
        )
        self.assertEqual(calls["set_stage"][1]["note"], "Met them")

    def test_an_empty_note_isnt_sent(self):
        self.as_bde()
        with self.assertRaises(frappe.ValidationError):
            leads_api.add_note("CRM-LEAD-0001", "   ")
        self.assertEqual(self.crm.lead_calls, [])

    def test_teams_limit_who_sees_leads(self):
        enable_leads(teams=(TEAM,))
        frappe.set_user(SUPPORT)
        with self.assertRaises(frappe.PermissionError):
            leads_api.get_options()
        self.as_bde()
        leads_api.get_options()
        # managers always see Leads
        frappe.set_user("Administrator")
        leads_api.get_options()
        asked = [method for method, _post, _params in self.crm.lead_calls]
        self.assertEqual(asked.count("get_options"), 2)

    def test_an_inactive_agent_doesnt_see_leads(self):
        frappe.db.set_value("HD Agent", BDE, "is_active", 0)
        self.as_bde()
        with self.assertRaises(frappe.PermissionError):
            leads_api.get_options()

    def assert_error(self, error, expected_class, text):
        self.crm.lead_error = error
        self.as_bde()
        frappe.local.message_log = []
        with self.assertRaises(expected_class) as caught:
            leads_api.get_lead("CRM-LEAD-0001")
        self.assertIn(text, str(caught.exception))
        # the page shows the message, not "Internal Server Error"
        self.assertIn(text, str(frappe.local.message_log))

    def test_crm_errors_become_messages_people_can_act_on(self):
        cases = [
            (
                CRMError("timed out"),
                LeadsUnavailableError,
                "Couldn't reach the ERP site",
            ),
            (
                CRMError("x", 401, ""),
                LeadsUnavailableError,
                "refused the hub's API key",
            ),
            (
                CRMError(
                    "x",
                    403,
                    "Function tbo_smart.api.hub_leads.get_lead is not whitelisted.",
                ),
                LeadsUnavailableError,
                "latest TBO Smart",
            ),
            (
                CRMError(
                    "x",
                    417,
                    "Failed to get method for command tbo_smart.api.hub_leads.get_lead with No module named 'tbo_smart.api.hub_leads'",
                ),
                LeadsUnavailableError,
                "latest TBO Smart",
            ),
            (
                CRMError(
                    "x",
                    403,
                    "Only the hub's integration user may act for someone else.",
                ),
                LeadsUnavailableError,
                "Hub integration role",
            ),
            (
                CRMError(
                    "x",
                    403,
                    "bde@example.com is an integration user, not a person.",
                ),
                LeadsError,
                "only for the hub's API user",
            ),
            (
                CRMError("x", 403, "Not permitted"),
                LeadsError,
                "don't have a sales account",
            ),
            (
                CRMError("x", 404, "Lead CRM-LEAD-0001 not found."),
                LeadsError,
                "isn't on the ERP site",
            ),
            (
                CRMError("x", 417, "Give the lead a name.", "Give the lead a name."),
                LeadsError,
                "Give the lead a name.",
            ),
            (
                CRMError("x", 417, "Traceback (most recent call last): ...", ""),
                LeadsUnavailableError,
                "ran into a problem (417)",
            ),
            (CRMError("x", 502, ""), LeadsUnavailableError, "ran into a problem (502)"),
        ]
        for error, expected_class, text in cases:
            with self.subTest(status=error.status, detail=error.detail):
                self.assert_error(error, expected_class, text)

    def test_no_connection_says_so(self):
        self.as_bde()
        with patch(FROM_SETTINGS, side_effect=CRMError("Add the CRM site URL")):
            with self.assertRaises(LeadsUnavailableError) as caught:
                leads_api.get_options()
        self.assertIn("Settings → CRM", str(caught.exception))

    def assert_integration_role_error(self):
        self.crm.lead_error = CRMError(
            "x", 403, "Only the hub's integration user may act for someone else."
        )
        self.as_bde()
        frappe.local.message_log = []
        with self.assertRaises(LeadsUnavailableError) as caught:
            leads_api.get_lead("CRM-LEAD-0001")
        return str(caught.exception)

    def test_the_integration_role_error_names_the_api_user_to_fix(self):
        message = self.assert_integration_role_error()
        self.assertIn("api@crm.example", message)

    def test_the_integration_role_error_without_the_api_users_name(self):
        self.as_bde()
        with patch.object(self.crm, "logged_user", side_effect=CRMError("no")):
            message = self.assert_integration_role_error()
        self.assertNotIn("(None)", message)
        self.assertIn("Hub integration role", message)


class TestCRMCallErrors(FrappeTestCase):
    """CRMClient.call keeps the ERP site's message apart from its exception text."""

    def call_answering(self, status: int, body):
        from helpdesk.integrations.crm.client import CRMClient

        client = CRMClient("https://erp.example", "key", "secret")
        response = Mock(
            ok=status < 400, status_code=status, content=b"x", text=str(body)
        )
        if isinstance(body, Exception):
            response.json.side_effect = body
        else:
            response.json.return_value = body
        with patch.object(client, "send", return_value=response):
            with self.assertRaises(CRMError) as caught:
                client.call("tbo_smart.api.hub_leads.get_lead", name="CRM-LEAD-0001")
        return caught.exception

    def test_the_exception_text_is_never_the_user_message(self):
        error = self.call_answering(
            417, {"exception": "frappe.exceptions.ValidationError: boom"}
        )
        self.assertIn("ValidationError", error.detail)
        self.assertEqual(error.user_message, "")

    def test_a_success_that_isnt_json_raises_crm_error(self):
        for body in (ValueError("not JSON"), ["unexpected"]):
            with self.subTest(body=body):
                error = self.call_answering(200, body)
                self.assertEqual(error.status, 200)

    def test_a_body_that_isnt_an_object_still_raises_crm_error(self):
        error = self.call_answering(500, ["unexpected"])
        self.assertEqual(error.status, 500)
        self.assertEqual(error.user_message, "")
