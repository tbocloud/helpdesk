from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import leads as leads_api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsForbiddenError, LeadsUnavailableError
from helpdesk.test_utils import FakeCRM, create_agent, enable_leads, hold_commits

HEAD = "merge.head@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class TestLeadMerge(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(HEAD, "Hena", "Merge")
        enable_leads()
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(HEAD)

    def sent(self, method):
        ((_name, post, params),) = [c for c in self.crm.lead_calls if c[0] == method]
        return post, params

    def test_the_merge_is_posted_as_the_signed_in_person(self):
        self.crm.lead_answers["merge_leads"] = {"lead": {"name": "LEAD-1"}}
        with patch.object(leads_api, "clear_cached_reads") as clear:
            result = leads_api.merge_leads(" LEAD-1 ", "LEAD-2")
        clear.assert_called_once()
        self.assertEqual(result["lead"]["name"], "LEAD-1")
        post, params = self.sent("merge_leads")
        self.assertTrue(post)
        self.assertEqual(
            (params["acting_user"], params["keep"], params["merge"]),
            (HEAD, "LEAD-1", "LEAD-2"),
        )

    def test_the_preview_is_a_read_of_both_leads(self):
        self.crm.lead_answers["get_merge_preview"] = {"leads": [{}, {}]}
        leads_api.get_merge_preview("LEAD-1", "LEAD-2")
        post, params = self.sent("get_merge_preview")
        self.assertFalse(post)
        self.assertEqual((params["first"], params["second"]), ("LEAD-1", "LEAD-2"))

    def test_both_leads_must_be_picked_before_the_erp_site_is_asked(self):
        with self.assertRaises(frappe.ValidationError):
            leads_api.merge_leads("LEAD-1", "  ")
        self.assertEqual(self.crm.lead_calls, [])

    def test_someone_who_may_not_merge_is_told_who_may(self):
        self.crm.lead_answers["merge_leads"] = CRMError("x", 403, "no")
        with self.assertRaises(LeadsForbiddenError) as raised:
            leads_api.merge_leads("LEAD-1", "LEAD-2")
        self.assertIn("head", str(raised.exception))

    def test_an_older_erp_site_cannot_merge(self):
        self.crm.lead_answers["merge_leads"] = CRMError(
            "x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x"
        )
        with self.assertRaises(LeadsUnavailableError):
            leads_api.merge_leads("LEAD-1", "LEAD-2")
