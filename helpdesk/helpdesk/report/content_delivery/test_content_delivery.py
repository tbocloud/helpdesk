# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, getdate, now_datetime

from helpdesk.helpdesk.report.content_delivery.content_delivery import execute
from helpdesk.test_utils import create_customer, hold_commits, make_content_post

CUSTOMER = "Al Noor Trading LLC"


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
        self.assertEqual(rows[0][:2], ("Customer", "Planned"))
        self.assertEqual(rows[1][:2], (CUSTOMER, 2))
        self.assertEqual(rows[-1][:2], ("Total", 2))

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
