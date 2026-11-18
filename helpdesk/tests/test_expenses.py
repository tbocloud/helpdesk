from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import expenses as api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsError, LeadsUnavailableError
from helpdesk.test_utils import FakeCRM, create_agent, enable_leads, hold_commits

BDE = "expenses.bde@leads.example"
OUTSIDER = "expenses.outsider@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
EXPENSES = "tbo_smart.api.hub_expenses"
OLDER_ERP = CRMError(
    "x", 417, "Failed to get method for command tbo_smart.api.hub_expenses.x"
)
PAGE = {
    "employee": True,
    "can_approve": True,
    "currency": "INR",
    "types": ["Travel"],
    "claims": {"data": [], "page": 1, "has_more": False},
    "approvals": [{"ref": "HR-EXP-0001", "amount": 480, "receipt": "bill.png"}],
}


class TestExpenses(FrappeTestCase):
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

    def test_the_page_is_read_live_as_the_signed_in_person(self):
        self.crm.lead_answers["get_expenses"] = PAGE
        first = api.get_expenses()
        api.get_expenses(page=2)
        self.assertTrue(first["available"])
        self.assertEqual(first["approvals"][0]["ref"], "HR-EXP-0001")
        [(post, params), (_post, second)] = self.calls("get_expenses")
        self.assertFalse(post)
        self.assertEqual((params["acting_user"], second["page"]), (BDE, 2))
        self.assertIn(EXPENSES, self.crm.lead_paths[0])

    def test_an_older_erp_site_hides_expenses_quietly(self):
        self.crm.lead_answers["get_expenses"] = OLDER_ERP
        frappe.clear_messages()
        self.assertEqual(api.get_expenses(), {"available": False})
        self.assertEqual(frappe.message_log, [])

    def test_a_claim_is_posted_trimmed_with_its_receipt(self):
        self.crm.lead_answers["create_expense_claim"] = {"name": "HR-EXP-0002"}
        api.create_expense_claim(
            "Travel", 480, "2026-11-18", "  ", "bill.png", "cmVjZWlwdA=="
        )
        [(post, params)] = self.calls("create_expense_claim")
        self.assertTrue(post)
        self.assertEqual(params["acting_user"], BDE)
        self.assertIsNone(params["description"])
        self.assertEqual(
            (params["receipt_filename"], params["receipt_base64"]),
            ("bill.png", "cmVjZWlwdA=="),
        )

    def test_a_decision_is_posted_with_its_reason(self):
        self.crm.lead_answers["decide_expense"] = {"status": "Rejected"}
        api.decide_expense("HR-EXP-0001", 0, " No bill ")
        [(post, params)] = self.calls("decide_expense")
        self.assertTrue(post)
        self.assertEqual((params["approve"], params["reason"]), (0, "No bill"))

    def test_writes_on_an_older_erp_site_say_so(self):
        self.crm.lead_answers["decide_expense"] = OLDER_ERP
        with self.assertRaises(LeadsUnavailableError):
            api.decide_expense("HR-EXP-0001", 1)

    def test_a_refusal_is_an_error_the_person_can_act_on(self):
        self.crm.lead_answers["decide_expense"] = CRMError("x", 403, "no")
        with self.assertRaises(LeadsError):
            api.decide_expense("HR-EXP-0001", 1)

    def test_a_receipt_is_streamed_and_opens_in_the_browser(self):
        self.crm.lead_answers["get_expense_receipt"] = (b"%PDF", "application/pdf")
        api.expense_receipt("HR-EXP-0001", "bill.pdf")
        [(post, params)] = self.calls("get_expense_receipt")
        self.assertFalse(post)
        self.assertEqual(params["name"], "HR-EXP-0001")
        self.assertEqual(frappe.local.response.filecontent, b"%PDF")
        self.assertEqual(frappe.local.response.display_content_as, "inline")

    def test_people_without_leads_are_refused(self):
        frappe.set_user("Administrator")
        create_agent(OUTSIDER, "Omar", "Outsider")
        enable_leads(teams=("Some other team",))
        frappe.set_user(OUTSIDER)
        with self.assertRaises(frappe.PermissionError):
            api.get_expenses()
