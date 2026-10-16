from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

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
        self.assertEqual(len(self.crm.lead_calls), 2)

    def test_an_inactive_agent_doesnt_see_leads(self):
        frappe.db.set_value("HD Agent", BDE, "is_active", 0)
        self.as_bde()
        with self.assertRaises(frappe.PermissionError):
            leads_api.get_options()

    def assert_error(self, error, expected_class, text):
        self.crm.lead_error = error
        self.as_bde()
        with self.assertRaises(expected_class) as caught:
            leads_api.get_lead("CRM-LEAD-0001")
        self.assertIn(text, str(caught.exception))

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


class TestCRMCallErrors(FrappeTestCase):
    """CRMClient.call keeps the ERP site's message apart from its exception text."""

    def call_answering(self, status: int, body):
        from helpdesk.integrations.crm.client import CRMClient

        client = CRMClient("https://erp.example", "key", "secret")
        response = Mock(ok=False, status_code=status, content=b"x", text=str(body))
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

    def test_a_body_that_isnt_an_object_still_raises_crm_error(self):
        error = self.call_answering(500, ["unexpected"])
        self.assertEqual(error.status, 500)
        self.assertEqual(error.user_message, "")
