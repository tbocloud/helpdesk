# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The check after a deploy: what it reads on the customer's site, and what counts as new."""

import json
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from helpdesk.copilot import deploy, verify
from helpdesk.tests.test_copilot_deploy import DeployCase


class TestWhatTheCheckReads(FrappeTestCase):
    def test_an_error_is_known_by_its_app_method_and_last_line(self):
        entry = {
            "app": "demo_app",
            "method": "demo_app.invoice.validate",
            "error": 'Traceback (most recent call last):\n  File "invoice.py", line 3\nZeroDivisionError: division by zero\n\n',
        }
        self.assertEqual(
            verify.signature(entry),
            "demo_app | demo_app.invoice.validate | ZeroDivisionError: division by zero",
        )
        self.assertEqual(verify.signature({}), "? | ? | ")

    def test_the_documents_the_diagnosis_names_and_nothing_else(self):
        run = frappe._dict(
            evidence=json.dumps(
                [
                    {"ref": "Sales Invoice/ACC-SINV-2026-00012"},
                    {"ref": "Error Log/8f3a"},
                    {"ref": "demo_app/invoice.py:42"},
                    {"ref": "Version/12"},
                    {"ref": "sales invoice/lower-case"},
                    "a note, not a reference",
                    {
                        "type": "customization",
                        "ref": "Quotation Item/tier_discount_percent",
                    },
                    {"type": "code", "ref": "Sales Invoice/not-a-record"},
                    {"type": "data", "ref": "Item/ITEM-1"},
                    {"type": "setting", "ref": "Customer/C-1"},
                    {"ref": "Supplier/S-1"},
                ]
            )
        )
        self.assertEqual(
            verify.named_documents(run),
            [
                ("Sales Invoice", "ACC-SINV-2026-00012"),
                ("Item", "ITEM-1"),
                ("Customer", "C-1"),
            ],
        )


class TestTheCheckOnTheSite(DeployCase):
    def deployed(self):
        self.request(self.senior, "now")
        self.cron()
        self.press.finish("Success")
        self.cron()
        self.assertEqual(self.current_run().state, "Verifying")
        return frappe.get_doc(deploy.DEPLOY, self.current_run().deploy_request)

    def test_a_named_document_that_no_longer_opens_escalates_it(self):
        self.current_run().db_set(
            "evidence",
            json.dumps(
                [{"ref": "Item/ITEM-1"}, {"ref": "Sales Invoice/ACC-SINV-2026-00012"}]
            ),
        )

        def get_doc(asked):
            if asked["doctype"] != "Item":
                raise LookupError(f"{asked['doctype']} {asked['name']} not found")
            return {"doctype": "Item", "name": asked["name"]}

        self.checked_site(answers={"get_doc": get_doc})
        request = self.deployed()
        self.cron()

        request.reload()
        self.assertEqual(
            (request.status, self.current_run().state), ("Failed", "Escalated")
        )
        self.assertEqual(
            [row["result"] for row in json.loads(request.check_results)],
            ["pass", "pass", "pass", "pass", "fail"],
        )
        self.assertIn("Sales Invoice ACC-SINV-2026-00012 opens", request.error)
        self.assertNotIn("Item ITEM-1", request.error)

    def test_a_site_that_cannot_answer_is_asked_again_then_escalated(self):
        self.checked_site(refuse=("get_code_identity",))
        request = self.deployed()
        self.cron()
        request.reload()
        self.assertEqual(request.status, "Checking")

        later = now_datetime() + timedelta(minutes=31)
        with patch("helpdesk.copilot.verify.now_datetime", return_value=later):
            self.cron()

        request.reload()
        self.assertEqual(
            (request.status, self.current_run().state), ("Failed", "Escalated")
        )
        self.assertIn("could not reach the site", request.error)

    def test_a_ticket_without_a_connection_is_not_checked_and_says_so(self):
        request = self.deployed()
        self.cron()

        request.reload()
        self.assertEqual(
            (request.status, self.current_run().state), ("Succeeded", "Resolved")
        )
        self.assertEqual(
            [row["result"] for row in json.loads(request.check_results)], ["not_run"]
        )
