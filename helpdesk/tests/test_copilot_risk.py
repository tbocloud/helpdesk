# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""How risky a fix is, from the files its pull request changes."""

from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import risk


def changed(path, additions=2, deletions=1, patch="+x = 1"):
    return {
        "filename": path,
        "additions": additions,
        "deletions": deletions,
        "patch": patch,
    }


class TestRisk(FrappeTestCase):
    def test_sensitive_areas_need_a_senior(self):
        for path in (
            "app/hooks.py",
            "app/patches.txt",
            "app/patches/v1_0/backfill.py",
            "app/app/doctype/sales_order_item/sales_order_item.json",
            "app/accounts/report/ledger.py",
            "app/doc_events/sales_invoice.py",
            "app/stock/stock_entry_hooks.py",
            "app/payroll/salary_slip.py",
            "requirements.txt",
            ".github/workflows/ci.yml",
            "app/fixtures/custom_docperm.json",
        ):
            result = risk.assess([changed(path), changed("tests/test_it.py")])
            self.assertTrue(result["sensitive"], path)
            self.assertEqual(result["level"], "high", path)

    def test_code_that_skips_permissions_or_writes_sql_is_sensitive(self):
        for code in (
            "+doc.save(ignore_permissions=True)",
            '+frappe.db.sql("update `tabItem` set disabled = 1")',
        ):
            result = risk.assess(
                [changed("app/utils.py", patch=code), changed("tests/test_utils.py")]
            )
            self.assertTrue(result["sensitive"], code)

    def test_a_large_change_is_high_without_being_sensitive(self):
        result = risk.assess(
            [changed("app/report.py", additions=320), changed("tests/test_report.py")]
        )
        self.assertEqual((result["level"], result["sensitive"]), ("high", False))

    def test_no_test_makes_it_medium_and_a_test_makes_it_low(self):
        self.assertEqual(risk.assess([changed("app/report.py")])["level"], "medium")
        result = risk.assess(
            [changed("app/report.py"), changed("app/tests/test_report.py")]
        )
        self.assertEqual(result["level"], "low")
        self.assertEqual(result["reasons"], [])
