# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.tests.utils import FrappeTestCase

from helpdesk.setup.install import get_custom_fields


class TestProjectMembers(FrappeTestCase):
    def test_member_role_is_a_column_of_the_members_table(self):
        # after_migrate applies the custom fields to existing sites the same way
        create_custom_fields(get_custom_fields())
        frappe.clear_cache(doctype="Project User")
        role = frappe.get_meta("Project User").get_field("custom_role")
        self.assertTrue(role.in_list_view)
        self.assertEqual(role.columns, 2)
