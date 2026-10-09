# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

"""The project dashboard's tile counts and the checklist filter behind each tile."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.test_utils import hold_commits, make_project, make_task_in_status

DASHBOARD = "helpdesk.tasky.api.get_project_dashboard"


class TestDashboardStatTasks(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        frappe.set_user("Administrator")
        self.project = make_project("Al Noor Trading LLC - Rollout").name
        yesterday = add_days(nowdate(), -1)
        self.tasks = {
            key: make_task_in_status(self.project, subject, status, **values)
            for key, subject, status, values in [
                ("open", "Collect opening balances", "Open", {}),
                ("late_open", "Map tax codes", "Open", {"exp_end_date": yesterday}),
                ("working", "Configure chart of accounts", "Working", {}),
                ("slipped", "Import item master", "Working", {"slip_count": 2}),
                ("review", "Sales invoice print format", "Pending Review", {}),
                ("held", "Bank feed setup", "On Hold", {"exp_end_date": yesterday}),
                ("done", "Kick-off meeting", "Completed", {"exp_end_date": yesterday}),
                ("done_slipped", "User training", "Completed", {"slip_count": 1}),
                ("cancelled", "Legacy data cleanup", "Cancelled", {}),
            ]
        }

    def test_each_filter_lists_exactly_what_its_tile_counts(self):
        dashboard = frappe.call(DASHBOARD, project=self.project)
        t = self.tasks
        expected = {
            "completed": {t["done"], t["done_slipped"]},
            "in_progress": {t["working"], t["slipped"]},
            "pending": {t["open"], t["late_open"]},
            "reviewing": {t["review"]},
            "on_hold": {t["held"]},
            "rescheduled": {t["slipped"], t["done_slipped"]},
            "cancelled": {t["cancelled"]},
            # a held or finished task isn't late
            "overdue": {t["late_open"]},
        }

        self.assertEqual(set(dashboard["stat_tasks"]), set(expected))
        for key, names in expected.items():
            with self.subTest(stat=key):
                self.assertEqual(set(dashboard["stat_tasks"][key]), names)
                self.assertEqual(
                    dashboard["stats"][key], len(dashboard["stat_tasks"][key])
                )
        self.assertEqual(dashboard["stats"]["total"], len(t))
