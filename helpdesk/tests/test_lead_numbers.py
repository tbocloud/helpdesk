from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import call_batches
from helpdesk.api import leads as leads_api
from helpdesk.api import pending_calls
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsForbiddenError, LeadsUnavailableError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    lead_number,
)

BDE = "numbers.bde@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
NEW = "98950 11111"


class TestLeadNumbers(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "Numbers")
        enable_leads()
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(BDE)

    def sent(self, method):
        ((name, post, params),) = [c for c in self.crm.lead_calls if c[0] == method]
        return post, params

    def test_a_number_is_posted_as_the_signed_in_person_with_trimmed_details(self):
        self.crm.lead_answers["add_lead_number"] = {
            "numbers": [lead_number(NEW)],
            "duplicates": [],
        }
        result = leads_api.add_lead_number(
            "LEAD-1",
            f"  {NEW} ",
            label="Decision-maker",
            person=" Anil ",
            make_primary="1",
            note="  after 5 pm ",
            on_call=1,
        )
        self.assertEqual(result["numbers"][0]["number"], NEW)
        post, params = self.sent("add_lead_number")
        self.assertTrue(post)
        self.assertEqual(
            (params["acting_user"], params["lead"], params["number"]),
            (BDE, "LEAD-1", NEW),
        )
        self.assertEqual(
            (params["label"], params["person"], params["note"]),
            ("Decision-maker", "Anil", "after 5 pm"),
        )
        self.assertEqual((params["make_primary"], params["on_call"]), (1, 1))

    def test_a_blank_number_is_refused_before_the_erp_site_is_asked(self):
        with self.assertRaises(frappe.ValidationError):
            leads_api.add_lead_number("LEAD-1", "  ")
        self.assertEqual(self.crm.lead_calls, [])

    def test_a_change_clears_the_cached_reads(self):
        self.crm.lead_answers["update_lead_number"] = {"numbers": []}
        with patch.object(leads_api, "clear_cached_reads") as clear:
            leads_api.update_lead_number("LEAD-1", "n-1", status="Wrong number")
        clear.assert_called_once()
        _post, params = self.sent("update_lead_number")
        self.assertEqual(
            (params["number_id"], params["status"]), ("n-1", "Wrong number")
        )

    def test_only_a_manager_removes_a_number(self):
        self.crm.lead_answers["remove_lead_number"] = CRMError("x", 403, "no")
        with self.assertRaises(LeadsForbiddenError) as raised:
            leads_api.remove_lead_number("LEAD-1", "n-1")
        self.assertIn("manager", str(raised.exception))

    def test_an_older_erp_site_cannot_keep_more_than_one_number(self):
        self.crm.lead_answers["add_lead_number"] = CRMError(
            "x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x"
        )
        with self.assertRaises(LeadsUnavailableError):
            leads_api.add_lead_number("LEAD-1", NEW)

    def test_the_number_called_goes_with_the_result(self):
        self.crm.lead_answers["log_call"] = {"name": "CALL-1"}
        self.crm.lead_answers["record_call_outcome"] = {}
        leads_api.log_call("LEAD-1", "Wrong number", number=f" {NEW} ")
        call_batches.record_call_outcome("a", "Wrong number", number=NEW)
        self.assertEqual(self.sent("log_call")[1]["number"], NEW)
        self.assertEqual(self.sent("record_call_outcome")[1]["number"], NEW)

    def test_a_call_to_the_main_number_sends_no_number(self):
        self.crm.lead_answers["log_call"] = {"name": "CALL-1"}
        leads_api.log_call("LEAD-1", "Connected")
        self.assertIsNone(self.sent("log_call")[1].get("number"))

    def test_a_pending_call_remembers_the_number_that_was_dialled(self):
        calls = pending_calls.start_call(
            "LEAD-1", "Asha Traders", NEW, via="phone", number=NEW
        )["calls"]
        self.assertEqual((calls[0]["phone"], calls[0]["number"]), (NEW, NEW))
        calls = pending_calls.start_call("LEAD-2", "Other", "9847012345")["calls"]
        self.assertIsNone(calls[1]["number"])
        frappe.cache.delete_value(pending_calls.key_of(BDE))
