# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Both ticket-page form scripts are installed and refreshed on migrate."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.setup.form_scripts import FORM_SCRIPTS, install_form_scripts
from helpdesk.test_utils import hold_commits


class TestFormScripts(FrappeTestCase):
    def setUp(self):
        hold_commits(self)

    def test_the_copilot_script_is_installed_next_to_the_ai_one(self):
        install_form_scripts()
        for name in FORM_SCRIPTS:
            doc = frappe.get_doc("HD Form Script", name)
            self.assertEqual((doc.dt, doc.apply_to, doc.enabled), ("HD Ticket", "Form", 1), name)
        self.assertIn("helpdesk.api.copilot.get_run", frappe.db.get_value("HD Form Script", "Helpdesk Copilot Actions", "script"))
