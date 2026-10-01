# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk.api import performance
from helpdesk.test_utils import (
    create_customer,
    make_content_post,
    make_employee_with_user,
    make_project,
    make_tasky_user,
    make_timesheet_hours,
)

LEAD = ("leela.manager@perf-test.example", "Leela Manager")
DEV = ("dev.one@perf-test.example", "Devika One")
OTHER = ("dev.two@perf-test.example", "Dinesh Two")
CUSTOMER = "Perf Test Customer"


class TestPerformance(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        self.lead = make_employee_with_user(*LEAD, roles=("Project Manager",))
        self.dev = make_employee_with_user(*DEV)
        self.other = make_employee_with_user(*OTHER)
        project = make_project("Perf Test Project", members=[(DEV[0], "Developer")])
        project.db_set("owner", LEAD[0])
        self.start = getdate(add_days(nowdate(), -6))
        self.end = getdate(nowdate())

    def as_user(self, user, fn, *args, **kwargs):
        frappe.set_user(user[0])
        try:
            return fn(*args, **kwargs)
        finally:
            frappe.set_user("Administrator")

    def test_scope_follows_role(self):
        everyone = {e.employee for e in performance.visible_employees("Administrator")}
        self.assertTrue({self.lead, self.dev, self.other} <= everyone)

        lead_sees = {e.employee for e in performance.visible_employees(LEAD[0])}
        self.assertEqual(lead_sees, {self.lead, self.dev})

        self.assertEqual(
            {e.employee for e in performance.visible_employees(OTHER[0])}, {self.other}
        )
        with self.assertRaises(frappe.PermissionError):
            self.as_user(
                OTHER,
                performance.get_employee_performance,
                self.dev,
                str(self.start),
                str(self.end),
            )

    def test_hours_tasks_and_posts_add_up(self):
        make_timesheet_hours(self.dev, self.end, 3, activity_type="Development")
        make_timesheet_hours(self.dev, self.start, 2, activity_type="Planning")
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": "Perf test task",
                "exp_end_date": self.end,
                "expected_time": 4,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        frappe.desk.form.assign_to.add(
            {"doctype": "Task", "name": task.name, "assign_to": [DEV[0]]},
            ignore_permissions=True,
        )
        # set directly: other apps' Task hooks (notifications) aren't what this tests
        task.db_set({"status": "Completed", "completed_on": self.end})
        make_content_post(
            "Missed post",
            CUSTOMER,
            status="Drafting",
            publish_on=add_days(nowdate(), -1),
            writer=DEV[0],
        )

        report = performance.get_employee_performance(
            self.dev, str(self.start), str(self.end)
        )
        summary = report["summary"]
        self.assertEqual(summary["hours"], 5)
        self.assertEqual(summary["tasks_completed"], 1)
        self.assertEqual(summary["on_time_pct"], 100)
        self.assertEqual(summary["posts_missed"], 1)
        self.assertEqual(
            [a["activity"] for a in report["by_activity"]], ["Development", "Planning"]
        )
        self.assertEqual(sum(d["hours"] for d in report["daily"]), 5)

        team = performance.get_team_performance(str(self.start), str(self.end))
        row = next(r for r in team["rows"] if r["employee"] == self.dev)
        self.assertEqual(row["hours"], 5)
        self.assertIn("Development", team["activities"])

    def test_rejects_bad_ranges(self):
        with self.assertRaises(frappe.ValidationError):
            performance.get_team_performance(str(self.end), str(self.start))
        with self.assertRaises(frappe.ValidationError):
            performance.get_team_performance("2024-01-01", str(self.end))
