import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import leads as leads_api
from helpdesk.api import outreach as api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsError, LeadsUnavailableError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    outbox,
    outreach_message,
)

BDE = "outreach.bde@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
OLDER_ERP = CRMError(
    "x", 417, "Failed to get method for command tbo_smart.api.hub_outreach.x"
)
API = "tbo_smart.api.hub_outreach"


class TestOutreach(FrappeTestCase):
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

    def test_the_outbox_is_read_live_as_the_signed_in_person(self):
        self.crm.lead_answers["get_outbox"] = outbox([outreach_message()])
        first = api.get_outbox()
        api.get_outbox()
        self.assertTrue(first["available"])
        self.assertEqual(first["rows"][0]["name"], "OUT-00001")
        self.assertEqual(first["cap"]["left"], 30)
        self.assertEqual(len(self.calls("get_outbox")), 2, "never cached")
        post, params = self.calls("get_outbox")[0]
        self.assertFalse(post)
        self.assertEqual(params["acting_user"], BDE)
        self.assertIn(API, self.crm.lead_paths[0])

    def test_a_status_filter_goes_as_a_json_list(self):
        self.crm.lead_answers["get_outbox"] = outbox()
        api.get_outbox(status="Draft")
        api.get_outbox(status=["Sent", "Failed"], batch=" abc ", run="PR-0001")
        api.get_outbox()
        first, second, third = (params for _post, params in self.calls("get_outbox"))
        self.assertEqual(json.loads(first["status"]), ["Draft"])
        self.assertEqual(json.loads(second["status"]), ["Sent", "Failed"])
        self.assertEqual((second["batch"], second["run"]), ("abc", "PR-0001"))
        self.assertEqual(
            (third["status"], third["batch"], third["run"]), (None, None, None)
        )

    def test_an_older_erp_site_hides_the_outbox_quietly(self):
        self.crm.lead_answers["get_outbox"] = OLDER_ERP
        frappe.clear_messages()
        result = api.get_outbox()
        self.assertFalse(result["available"])
        self.assertEqual(result["rows"], [])
        self.assertEqual(frappe.message_log, [])

    def test_a_refusal_from_the_erp_site_reaches_the_person(self):
        self.crm.lead_answers["get_outbox"] = CRMError(
            "x",
            417,
            "ValidationError",
            "Outreach is switched off in TBO Smart Settings.",
        )
        with self.assertRaises(LeadsError) as caught:
            api.get_outbox()
        self.assertIn("switched off", str(caught.exception))

    def test_drafting_a_runs_leads_is_posted_with_its_channel(self):
        self.crm.lead_answers["draft_outreach"] = {
            "batch": "abc123",
            "queued": 2,
            "skipped": [],
        }
        result = api.draft_outreach("Email", run="PR-0001")
        self.assertEqual(result["queued"], 2)
        post, params = self.calls("draft_outreach")[0]
        self.assertTrue(post)
        self.assertEqual(
            (params["channel"], params["run"], params["leads"]),
            ("Email", "PR-0001", None),
        )
        api.draft_outreach("WhatsApp", leads='["L-1", "L-2"]')
        self.assertEqual(self.calls("draft_outreach")[1][1]["leads"], ["L-1", "L-2"])

    def test_drafting_needs_a_channel_and_something_to_draft_for(self):
        for args in (
            {"channel": "SMS", "run": "PR-0001"},
            {"channel": "Email"},
            {"channel": "Email", "leads": [f"L-{n}" for n in range(201)]},
        ):
            with self.assertRaises(frappe.ValidationError):
                api.draft_outreach(**args)
        self.assertEqual(self.calls("draft_outreach"), [])

    def test_approving_cancelling_and_marking_sent_are_posted_for_the_picked_messages(
        self,
    ):
        for method in ("approve_outreach", "cancel_outreach", "mark_outreach_sent"):
            self.crm.lead_answers[method] = [
                {"name": "OUT-00001", "status": "Sent", "message": ""}
            ]
            getattr(api, method)(["OUT-00001", "OUT-00002"])
            post, params = self.calls(method)[0]
            self.assertTrue(post)
            self.assertEqual(params["names"], ["OUT-00001", "OUT-00002"])
            self.assertEqual(params["acting_user"], BDE)
        api.approve_outreach('["OUT-00003"]')
        self.assertEqual(self.calls("approve_outreach")[1][1]["names"], ["OUT-00003"])

    def test_nothing_picked_or_far_too_many_is_refused_before_the_erp_site_is_asked(
        self,
    ):
        for names in ([], "", [f"OUT-{n}" for n in range(201)]):
            with self.assertRaises(frappe.ValidationError):
                api.approve_outreach(names)
        self.assertEqual(self.calls("approve_outreach"), [])

    def test_no_outgoing_email_account_reaches_the_person_in_the_erp_sites_words(self):
        self.crm.lead_answers["approve_outreach"] = CRMError(
            "x", 417, "ValidationError", "Set up an outgoing email account first."
        )
        with self.assertRaises(LeadsError) as caught:
            api.approve_outreach(["OUT-00001"])
        self.assertIn("Set up an outgoing email account first", str(caught.exception))

    def test_an_edit_is_trimmed_and_needs_text(self):
        self.crm.lead_answers["update_outreach"] = {
            "name": "OUT-00001",
            "status": "Draft",
            "message": "",
        }
        api.update_outreach("OUT-00001", "  New text  ", subject=" Subject ")
        params = self.calls("update_outreach")[0][1]
        self.assertEqual((params["body"], params["subject"]), ("New text", "Subject"))
        api.update_outreach("OUT-00001", "Text")
        self.assertIsNone(self.calls("update_outreach")[1][1]["subject"])
        with self.assertRaises(frappe.ValidationError):
            api.update_outreach("OUT-00001", "   ")

    def test_regenerate_is_posted(self):
        self.crm.lead_answers["regenerate_outreach"] = {
            "name": "OUT-00001",
            "status": "Draft",
            "message": "",
        }
        api.regenerate_outreach("OUT-00001")
        self.assertTrue(self.calls("regenerate_outreach")[0][0])

    def test_writes_on_an_older_erp_site_say_so_in_words(self):
        self.crm.lead_answers["draft_outreach"] = OLDER_ERP
        self.crm.lead_answers["approve_outreach"] = OLDER_ERP
        with self.assertRaises(LeadsUnavailableError) as caught:
            api.draft_outreach("Email", run="PR-0001")
        self.assertIn("latest TBO Smart", str(caught.exception))
        with self.assertRaises(LeadsUnavailableError):
            api.approve_outreach(["OUT-00001"])

    def test_it_is_for_people_who_use_leads(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        frappe.cache.delete_keys("hd_leads:")
        for call in (
            api.get_outbox,
            lambda: api.draft_outreach("Email", run="PR-0001"),
            lambda: api.approve_outreach(["OUT-00001"]),
            lambda: api.cancel_outreach(["OUT-00001"]),
            lambda: api.mark_outreach_sent(["OUT-00001"]),
            lambda: api.update_outreach("OUT-00001", "x"),
            lambda: api.regenerate_outreach("OUT-00001"),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_the_leads_list_filters_by_the_class_of_the_last_reply(self):
        self.crm.lead_answers["list_leads"] = {"rows": [], "total": 0}
        leads_api.list_leads(last_reply_class=["Interested", "Question"])
        params = self.calls("list_leads")[0][1]
        self.assertEqual(
            json.loads(params["last_reply_class"]), ["Interested", "Question"]
        )
        leads_api.list_leads(last_reply_class="Not now")
        self.assertEqual(
            json.loads(self.calls("list_leads")[1][1]["last_reply_class"]), ["Not now"]
        )
        leads_api.list_leads()
        self.assertIsNone(self.calls("list_leads")[2][1]["last_reply_class"])
        calls = len(self.crm.lead_calls)
        with self.assertRaises(frappe.ValidationError):
            leads_api.list_leads(last_reply_class="Happy")
        self.assertEqual(len(self.crm.lead_calls), calls)
