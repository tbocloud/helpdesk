# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, getdate, now_datetime

from helpdesk.helpdesk.report.content_delivery.content_delivery import (
    execute,
    get_totals,
    health_key,
    percent,
    round_half_up,
)
from helpdesk.test_utils import create_customer, hold_commits, make_content_post

CUSTOMER = "Al Noor Trading LLC"


def report_row(**values) -> dict:
    """A report row with every count at zero, overridden by `values`."""
    keys = (
        "planned",
        "published",
        "on_time",
        "late",
        "overdue",
        "upcoming",
        "awaiting_client",
        "planning",
        "review",
        "ready",
        "approval_count",
    )
    return {
        **dict.fromkeys(keys, 0),
        "promised": None,
        "on_time_pct": None,
        "approval_hours": 0,
        "avg_approval_hours": None,
        **values,
    }


class TestDeliveryMath(FrappeTestCase):
    """The downloads round and average the way the page does."""

    def test_total_approval_averages_over_approvals_not_customers(self):
        # 100 posts with one 200 h approval, and 2 posts with two 2 h approvals:
        # three approvals of 204 h in all, so 68 h, not ~196 h weighted by posts
        rows = [
            report_row(planned=100, approval_count=1, approval_hours=200),
            report_row(planned=2, approval_count=2, approval_hours=4),
        ]
        self.assertEqual(get_totals(rows)["avg_approval_hours"], 68.0)
        self.assertIsNone(get_totals([report_row(planned=3)])["avg_approval_hours"])

    def test_rounds_half_up_like_the_page(self):
        self.assertEqual(round_half_up(12.5), 13)
        self.assertEqual(round_half_up(2.5), 3)
        self.assertEqual(round_half_up(66.66), 67)
        self.assertEqual(round_half_up(1.25, 1), 1.3)
        # the page's Math.round((h / n) * 10) / 10 gives 926 here, so must this
        self.assertEqual(round_half_up(925.9499999999999, 1), 926.0)
        # whole percents, as the page shows them
        self.assertEqual(percent(2, 3), 67)
        self.assertEqual(percent(1, 8), 13)
        self.assertIsNone(percent(1, 0))

    def test_health_key_does_not_depend_on_the_language(self):
        self.assertEqual(health_key(report_row(planned=2, upcoming=2)), "nothing-due")
        self.assertEqual(health_key(report_row(planned=4, overdue=2)), "behind")
        self.assertEqual(
            health_key(
                report_row(
                    planned=4, overdue=1, published=3, on_time=3, on_time_pct=100
                )
            ),
            "at-risk",
        )
        self.assertEqual(
            health_key(report_row(planned=4, published=4, on_time=4, on_time_pct=100)),
            "on-track",
        )


class TestContentDelivery(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)

    def test_counts_per_customer(self):
        today = now_datetime()
        on_time = make_content_post(
            "On time",
            CUSTOMER,
            status="Approved",
            publish_on=add_to_date(today, minutes=1),
        )
        on_time.status = "Published"
        on_time.published_url = "https://instagram.com/p/1"
        on_time.save()
        make_content_post(
            "Late", CUSTOMER, status="Drafting", publish_on=add_to_date(today, hours=-2)
        )
        waiting = make_content_post(
            "Waiting",
            CUSTOMER,
            status="Client Review",
            publish_on=add_to_date(today, hours=5),
        )
        waiting.db_set(
            {
                "sent_for_approval_on": add_to_date(today, hours=-10),
                "client_decided_on": add_to_date(today, hours=-4),
            }
        )

        _columns, rows, _msg, chart = execute(
            {
                "from_date": getdate(add_to_date(today, days=-1)),
                "to_date": getdate(add_to_date(today, days=1)),
                "customer": CUSTOMER,
            }
        )

        row = rows[0]
        self.assertEqual(row["customer"], CUSTOMER)
        self.assertEqual(row["planned"], 3)
        self.assertEqual(row["published"], 1)
        self.assertEqual(row["on_time"], 1)
        self.assertEqual(row["on_time_pct"], 100)
        self.assertEqual(row["awaiting_client"], 1)
        self.assertEqual(row["avg_approval_hours"], 6.0)
        self.assertGreaterEqual(row["overdue"], 1)
        # every post lands in exactly one delivery segment and one stage
        self.assertEqual(
            row["on_time"] + row["late"] + row["overdue"] + row["upcoming"],
            row["planned"],
        )
        self.assertEqual(sum(row["stages"].values()), row["planned"])
        self.assertEqual(row["stages"]["published"], 1)
        self.assertEqual(row["stages"]["review"], 1)
        self.assertEqual(chart["type"], "bar")

    def test_export_has_the_report_rows_and_a_total(self):
        import io

        import openpyxl

        from helpdesk.helpdesk.report.content_delivery.content_delivery import (
            export_xlsx,
        )

        day = add_to_date(now_datetime(), days=2)
        for title in ("First", "Second"):
            make_content_post(title, CUSTOMER, status="Drafting", publish_on=day)
        date = str(getdate(day))

        frappe.response.clear()
        export_xlsx(from_date=date, to_date=date, customer=CUSTOMER)
        sheet = openpyxl.load_workbook(io.BytesIO(frappe.response.filecontent)).active
        # Excel reports the file as damaged when a sheet name is longer than 31
        self.assertLessEqual(len(sheet.title), 31)
        rows = list(sheet.iter_rows(values_only=True))
        header = rows.index(next(r for r in rows if r[0] == "Customer"))
        # the same headline the page shows comes first
        self.assertIn("0 of 0 posts due are published", rows[header - 5][0])
        self.assertEqual(
            rows[header][:4], ("Customer", "Health", "Promised", "Planned")
        )
        values = dict(zip(rows[header], rows[header + 1]))
        self.assertEqual(values["Customer"], CUSTOMER)
        self.assertEqual(values["Planned"], 2)
        self.assertEqual(values["Not Due Yet"], 2)
        self.assertEqual(values["Health"], "Nothing due yet")
        # no monthly package, so nothing promised
        self.assertIsNone(values["Promised"])
        # nothing published yet: no on-time rate, rather than 0%
        self.assertIsNone(values["On Time %"])
        self.assertEqual(rows[-1][0], "Total")
        self.assertEqual(dict(zip(rows[header], rows[-1]))["Planned"], 2)

    def test_pdf_has_the_report_rows(self):
        from unittest.mock import patch

        from helpdesk.helpdesk.report.content_delivery.content_delivery import (
            export_pdf,
        )

        day = add_to_date(now_datetime(), days=2)
        make_content_post("Teaser", CUSTOMER, status="Drafting", publish_on=day)
        date = str(getdate(day))

        # without wkhtmltopdf: a page the browser prints to PDF
        with patch("shutil.which", return_value=None):
            frappe.response.clear()
            export_pdf(from_date=date, to_date=date, customer=CUSTOMER)
        self.assertEqual(frappe.response.type, "download")
        self.assertIn(CUSTOMER, frappe.response.filecontent)
        self.assertIn("window.print", frappe.response.filecontent)
        # styled by the health key, so the colours work in any language
        self.assertIn("health-nothing-due", frappe.response.filecontent)

        # with it: a real PDF
        with (
            patch("shutil.which", return_value="/usr/bin/wkhtmltopdf"),
            patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-1.4") as get_pdf,
        ):
            frappe.response.clear()
            export_pdf(from_date=date, to_date=date, customer=CUSTOMER)
        self.assertEqual(frappe.response.type, "pdf")
        self.assertTrue(frappe.response.filename.endswith(".pdf"))
        self.assertIn(CUSTOMER, get_pdf.call_args.args[0])
