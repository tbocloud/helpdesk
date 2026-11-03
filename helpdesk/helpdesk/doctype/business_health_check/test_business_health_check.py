# Copyright (c) 2026, Quark Cyber Systems FZC and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.helpdesk.doctype.business_health_check.business_health_check import (
    API_ROLE,
    DOCTYPE,
    setup_api_role,
)

REPORT_LINK = "https://example.com/results/#id=1&k=" + "a" * 24


class TestBusinessHealthCheck(FrappeTestCase):
    def make(self, **values):
        return frappe.get_doc(
            {"doctype": DOCTYPE, "report_link": REPORT_LINK, **values}
        ).insert()

    def test_named_bhc_and_values_trimmed(self):
        doc = self.make(
            business_name="  Green Leaf Organics  ",
            contact_name=" Ravi ",
            phone=" +91 98950 22334 ",
            email="ravi@example.com",
        )
        self.assertTrue(doc.name.startswith("BHC-"))
        self.assertEqual(doc.business_name, "Green Leaf Organics")
        self.assertEqual(doc.contact_name, "Ravi")
        self.assertEqual(doc.phone, "+91 98950 22334")
        self.assertEqual(doc.report_link, REPORT_LINK)

    def test_blank_business_name_gets_a_placeholder(self):
        self.assertEqual(
            self.make(business_name="   ").business_name, "Unnamed business"
        )

    def test_report_link_is_mandatory(self):
        with self.assertRaises(frappe.MandatoryError):
            frappe.get_doc(
                {
                    "doctype": DOCTYPE,
                    "business_name": "No Link Ltd",
                    "report_link": "  ",
                }
            ).insert()

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
