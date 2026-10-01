from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date

from helpdesk.api import customer_report
from helpdesk.test_utils import (
    create_customer,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
    make_timesheet,
)

MANAGER = ("manager.report@customer-report.example", "Riya George")
AGENT = ("agent.report@customer-report.example", "Akhil Raj")
CUSTOMER = "Report Traders LLC"
MONTH = "2026-08"
IN_MONTH = "2026-08-14 10:00:00"
AFTER_MONTH = "2026-09-02 10:00:00"


class TestCustomerReport(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        create_customer(CUSTOMER)
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_tasky_user(*AGENT)
        self.project = make_project(f"{CUSTOMER} - Support").name
        frappe.db.set_value("Project", self.project, "customer", CUSTOMER)

    def ticket(self, subject, **values):
        name = make_ticket(subject=subject, customer=CUSTOMER).name
        frappe.db.set_value("HD Ticket", name, values)
        return name

    def report_row(self, month=MONTH):
        frappe.set_user(MANAGER[0])
        try:
            report = customer_report.get_customer_report(month)
        finally:
            frappe.set_user("Administrator")
        return next(r for r in report["customers"] if r["customer"] == CUSTOMER), report

    def test_month_of_work_per_customer(self):
        self.ticket(
            "Kept SLA",
            opening_date="2026-08-03",
            status="Resolved",
            status_category="Resolved",
            resolution_date=IN_MONTH,
            agreement_status="Fulfilled",
            first_response_time=2 * 3600,
            resolution_time=10 * 3600,
            feedback_rating=1.0,
        )
        self.ticket(
            "Failed SLA",
            opening_date="2026-08-20",
            status="Resolved",
            status_category="Resolved",
            resolution_date=IN_MONTH,
            agreement_status="Failed",
            first_response_time=4 * 3600,
            resolution_time=30 * 3600,
            feedback_rating=0.4,
        )
        self.ticket("Opened later", opening_date="2026-09-01")
        task = make_task(self.project, "Configure payroll", status="Completed")
        frappe.db.set_value("Task", task.name, "completed_on", "2026-08-25")
        make_timesheet(self.project, 3.5, IN_MONTH, task.name)
        make_timesheet(self.project, 2, add_to_date(IN_MONTH, days=1))
        make_timesheet(self.project, 8, AFTER_MONTH)

        row, report = self.report_row()

        self.assertEqual(report["month"], MONTH)
        self.assertEqual(row["tickets_opened"], 2)
        self.assertEqual(row["tickets_resolved"], 2)
        self.assertEqual(row["sla_kept_percent"], 50)
        self.assertEqual(row["avg_first_reply_hours"], 3.0)
        self.assertEqual(row["avg_resolution_hours"], 20.0)
        self.assertEqual(row["ratings"], 2)
        self.assertEqual(row["avg_rating"], 3.5)
        self.assertEqual(row["hours_logged"], 5.5)
        self.assertEqual(row["tasks_completed"], 1)
        self.assertGreaterEqual(report["totals"]["hours_logged"], 5.5)

    def test_csv_download(self):
        make_timesheet(self.project, 1.5, IN_MONTH)
        frappe.set_user(MANAGER[0])
        customer_report.download_customer_report(MONTH)
        csv_text = frappe.response["filecontent"]

        self.assertEqual(frappe.response["filename"], f"customer-report-{MONTH}.csv")
        self.assertTrue(csv_text.startswith("Customer,Tickets opened"))
        self.assertIn(f"{CUSTOMER},", csv_text)
        self.assertIn("Total,", csv_text)

    def test_only_managers_can_see_it(self):
        frappe.set_user(AGENT[0])
        with self.assertRaises(frappe.PermissionError):
            customer_report.get_customer_report(MONTH)

    def test_month_must_be_valid(self):
        frappe.set_user(MANAGER[0])
        with self.assertRaises(frappe.ValidationError):
            customer_report.get_customer_report("2026-13")
