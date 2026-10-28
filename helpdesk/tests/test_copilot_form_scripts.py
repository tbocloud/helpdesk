# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The ticket page's form script is installed and refreshed on migrate; the retired Copilot dialog is removed."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.setup.form_scripts import FORM_SCRIPTS, install_form_scripts
from helpdesk.test_utils import hold_commits


class TestFormScripts(FrappeTestCase):
    def setUp(self):
        hold_commits(self)

    def test_the_ai_script_is_installed_and_the_copilot_dialog_is_gone(self):
        frappe.get_doc(
            {
                "doctype": "HD Form Script",
                "name": "Helpdesk Copilot Actions",
                "dt": "HD Ticket",
                "apply_to": "Form",
                "enabled": 1,
                "script": "function setupForm() {}",
            }
        ).insert(ignore_permissions=True, ignore_if_duplicate=True)

        install_form_scripts()

        for name in FORM_SCRIPTS:
            doc = frappe.get_doc("HD Form Script", name)
            self.assertEqual(
                (doc.dt, doc.apply_to, doc.enabled), ("HD Ticket", "Form", 1), name
            )
        # the Copilot dialog became the ticket's Copilot chat (Phase 11)
        self.assertFalse(frappe.db.exists("HD Form Script", "Helpdesk Copilot Actions"))
