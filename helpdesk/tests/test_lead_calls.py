from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import leads as leads_api
from helpdesk.api import myoperator
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    make_team,
)

BDE = "bde.caller@leads.example"
TEAM = "Lead Calls Test Sales"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
TELEPHONY = "tbo_smart.api.telephony"


class TestLeadCalls(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "Caller")
        make_team(TEAM, [BDE])
        enable_leads()
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_click_to_call_is_posted_as_the_signed_in_person(self):
        self.crm.lead_answers["click_to_call"] = {
            "ok": True,
            "message": "MyOperator is calling your phone…",
        }
        frappe.set_user(BDE)
        result = leads_api.click_to_call("CRM-LEAD-0001", number="  ")
        self.assertTrue(result["ok"])
        ((method, post, params),) = self.crm.lead_calls
        self.assertEqual(
            (method, post, params["acting_user"], params["lead"], params["number"]),
            ("click_to_call", True, BDE, "CRM-LEAD-0001", None),
        )
        self.assertEqual(self.crm.lead_paths, [f"{TELEPHONY}.click_to_call"])

    def test_the_recording_streams_from_the_erp_site(self):
        self.crm.lead_answers["call_recording"] = (b"ID3\xff\xfb", "audio/mpeg")
        frappe.set_user(BDE)
        leads_api.call_recording("CALL-1")
        self.assertEqual(frappe.local.response.filecontent, b"ID3\xff\xfb")
        self.assertEqual(frappe.local.response.content_type, "audio/mpeg")
        ((method, post, params),) = self.crm.lead_calls
        self.assertEqual(
            (method, post, params["acting_user"], params["call"]),
            ("call_recording", False, BDE, "CALL-1"),
        )

    def test_a_refused_recording_is_refused_here_too(self):
        self.crm.lead_error = CRMError("no", 403, "PermissionError", "Not permitted")
        frappe.set_user(BDE)
        with self.assertRaises(frappe.ValidationError):
            leads_api.call_recording("CALL-1")
        frappe.local.response.pop("filecontent", None)

    def test_a_returned_type_that_isnt_audio_is_served_as_audio(self):
        self.crm.lead_answers["call_recording"] = (b"<html>", "text/html")
        frappe.set_user(BDE)
        leads_api.call_recording("CALL-1")
        self.assertEqual(frappe.local.response.content_type, "audio/mpeg")

    def test_myoperator_settings_are_for_admins_and_proxied(self):
        frappe.set_user(BDE)
        with self.assertRaises(frappe.PermissionError):
            myoperator.get_settings()
        self.assertEqual(self.crm.lead_calls, [])
        frappe.set_user("Administrator")
        self.crm.lead_answers["get_settings"] = {"settings": {"enable_telephony": 1}}
        self.assertEqual(myoperator.get_settings()["settings"]["enable_telephony"], 1)
        myoperator.save_settings('{"enable_telephony": 0, "agents": []}')
        myoperator.test_connection()
        myoperator.regenerate_webhook_secret()
        calls = {m: (post, params) for m, post, params in self.crm.lead_calls}
        self.assertEqual(
            calls["save_settings"],
            (
                True,
                {
                    "acting_user": "Administrator",
                    "values": {"enable_telephony": 0, "agents": []},
                },
            ),
        )
        self.assertTrue(calls["test_connection"][0])
        self.assertTrue(calls["regenerate_webhook_secret"][0])
        with self.assertRaises(frappe.ValidationError):
            myoperator.save_settings("[1, 2]")
