# Copyright (c) 2026, Quark Cyber Systems FZC and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.integrations.crm.client import CRMError
from helpdesk.patches.v16_0_2.setup_health_check_api_role import API_ROLE, DOCTYPE
from helpdesk.patches.v16_0_2.setup_health_check_api_role import (
    execute as setup_api_role,
)
from helpdesk.test_utils import (
    BUSINESS_HEALTH_CHECK_LINK,
    FakeCRM,
    enable_leads,
    hold_commits,
    make_business_health_check,
)

FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
NEW_LEAD = "CRM-LEAD-2026-00042"


class TestBusinessHealthCheck(FrappeTestCase):
    def test_named_bhc_and_values_trimmed(self):
        doc = make_business_health_check(
            business_name="  Green Leaf Organics  ",
            contact_name=" Ravi ",
            phone=" +91 98950 22334 ",
            email=" ravi@example.com ",
        )
        self.assertTrue(doc.name.startswith("BHC-"))
        self.assertEqual(doc.business_name, "Green Leaf Organics")
        self.assertEqual(doc.contact_name, "Ravi")
        self.assertEqual(doc.phone, "+91 98950 22334")
        self.assertEqual(doc.email, "ravi@example.com")
        self.assertEqual(doc.report_link, BUSINESS_HEALTH_CHECK_LINK)

    def test_blank_business_name_gets_a_placeholder(self):
        doc = make_business_health_check(business_name="   ")
        self.assertEqual(doc.business_name, "Unnamed business")

    def test_report_link_is_mandatory(self):
        with self.assertRaises(frappe.MandatoryError):
            make_business_health_check(business_name="No Link Ltd", report_link="  ")

    def test_api_role_gets_create_read_write_only(self):
        setup_api_role()
        setup_api_role()  # re-running must not add a second permission row
        perms = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": DOCTYPE, "role": API_ROLE, "permlevel": 0},
            fields=["read", "write", "create", "delete", "submit", "cancel"],
        )
        self.assertEqual(len(perms), 1)
        p = perms[0]
        self.assertEqual((p.read, p.write, p.create), (1, 1, 1))
        self.assertEqual((p.delete, p.submit, p.cancel), (0, 0, 0))
        self.assertEqual(frappe.db.get_value("Role", API_ROLE, "desk_access"), 0)

    def test_existing_api_role_loses_desk_access(self):
        setup_api_role()
        frappe.db.set_value("Role", API_ROLE, "desk_access", 1)
        setup_api_role()
        self.assertEqual(frappe.db.get_value("Role", API_ROLE, "desk_access"), 0)


class TestBusinessHealthCheckLead(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["create_lead"] = {"name": NEW_LEAD}
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sent(self, method):
        return [params for name, _post, params in self.crm.lead_calls if name == method]

    def test_create_lead_sends_the_details_and_notes_the_report(self):
        doc = make_business_health_check(
            business_name="Green Leaf Organics",
            contact_name="Ravi Menon",
            phone="+91 98950 22334",
            email="ravi@example.com",
        )
        self.assertEqual(doc.create_lead(), {"lead": NEW_LEAD, "noted": True})

        self.assertEqual(
            self.sent("create_lead")[0]["data"],
            {
                "lead_name": "Ravi Menon",
                "company_name": "Green Leaf Organics",
                "mobile_no": "+91 98950 22334",
                "email_id": "ravi@example.com",
            },
        )
        note = self.sent("add_note")[0]
        self.assertEqual(note["name"], NEW_LEAD)
        self.assertIn(doc.name, note["note"])
        self.assertIn(BUSINESS_HEALTH_CHECK_LINK, note["note"])
        self.assertEqual(frappe.db.get_value(DOCTYPE, doc.name, "lead"), NEW_LEAD)

    def test_an_unnamed_business_sends_no_company(self):
        doc = make_business_health_check(contact_name="Meena")
        doc.create_lead()
        self.assertEqual(self.sent("create_lead")[0]["data"], {"lead_name": "Meena"})

    def test_a_check_makes_one_lead_only(self):
        doc = make_business_health_check(business_name="Once Ltd")
        doc.create_lead()
        with self.assertRaises(frappe.ValidationError):
            doc.create_lead()
        self.assertEqual(len(self.sent("create_lead")), 1)

    def test_a_possible_duplicate_is_asked_about_first(self):
        refusal = "Possible duplicate of CRM-LEAD-0001 (Asha)"
        self.crm.lead_answers["create_lead"] = CRMError(
            "x", 409, refusal, user_message=refusal
        )
        doc = make_business_health_check(business_name="Repeat Co", phone="+91 1")
        self.assertEqual(doc.create_lead(), {"duplicate": refusal})
        self.assertFalse(frappe.db.get_value(DOCTYPE, doc.name, "lead"))
        self.assertEqual(self.sent("add_note"), [])

        self.crm.lead_answers["create_lead"] = {"name": NEW_LEAD}
        self.assertEqual(doc.create_lead(allow_duplicate=1)["lead"], NEW_LEAD)
        self.assertEqual(self.sent("create_lead")[-1]["allow_duplicate"], 1)

    def test_other_erp_errors_are_shown(self):
        self.crm.lead_answers["create_lead"] = CRMError("x", 502, "")
        doc = make_business_health_check(business_name="Down Ltd")
        with self.assertRaises(frappe.ValidationError):
            doc.create_lead()
        self.assertFalse(frappe.db.get_value(DOCTYPE, doc.name, "lead"))

    def test_a_failed_note_keeps_the_lead(self):
        self.crm.lead_answers["add_note"] = CRMError("x", 502, "")
        doc = make_business_health_check(business_name="Note Fails Ltd")
        self.assertEqual(doc.create_lead(), {"lead": NEW_LEAD, "noted": False})
        self.assertEqual(frappe.db.get_value(DOCTYPE, doc.name, "lead"), NEW_LEAD)

    def test_create_lead_needs_leads_turned_on(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        doc = make_business_health_check(business_name="Off Ltd")
        with self.assertRaises(frappe.PermissionError):
            doc.create_lead()
        self.assertEqual(self.crm.lead_calls, [])
