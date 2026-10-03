from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.helpdesk.doctype.timesheet.timesheet import Timesheet
from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    get_task_timesheets,
    make_assignment,
    make_employee,
    make_project,
    make_task,
    make_tasky_user,
    run_as_user,
)

PM = ("pm.complete@complete-task.example", "Anjali Pillai")
LEAD = ("lead.complete@complete-task.example", "Rahul Nair")
DEV = ("dev.complete@complete-task.example", "Meera Joseph")
OTHER_DEV = ("other.complete@complete-task.example", "Vivek Kumar")


class TestCompleteTask(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (LEAD, DEV, OTHER_DEV):
            make_tasky_user(*user)

        self.project = make_project(
            "Complete Task - ERP Rollout",
            members=[
                (LEAD[0], "Developer"),
                (DEV[0], "Developer"),
                (OTHER_DEV[0], "Developer"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])
        self.task = make_task(self.project, "Map chart of accounts").name
        make_assignment("Task", self.task, DEV[0])

    def complete(self, user=DEV, **kwargs):
        params = {"task": self.task, "hours_worked": 2.5, "notes": "Accounts mapped"}
        params.update(kwargs)
        return run_as_user(user[0], lambda: tasky.complete_task(**params))

    def assert_not_completed(self):
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Open")
        self.assertEqual(get_task_timesheets(self.task), [])

    def test_hours_are_required(self):
        for hours in (None, "", 0, "0", -1, "two", 24.5):
            with self.assertRaises(frappe.ValidationError, msg=repr(hours)):
                self.complete(hours_worked=hours)
        self.assert_not_completed()

    def test_notes_are_required(self):
        for notes in (None, "", "   \n "):
            with self.assertRaises(frappe.ValidationError):
                self.complete(notes=notes)
        self.assert_not_completed()

    def test_completion_logs_a_submitted_timesheet(self):
        result = self.complete(notes="  Accounts mapped to the GCC template  ")

        self.assertEqual(result["status"], "Completed")
        self.assertEqual(result["timesheet_status"], "Submitted")
        self.assertEqual(get_task_timesheets(self.task), [result["timesheet"]])

        ts = frappe.get_doc("Timesheet", result["timesheet"])
        self.assertEqual(ts.owner, DEV[0])
        self.assertEqual(ts.docstatus, 1)
        self.assertEqual(ts.total_hours, 2.5)
        self.assertFalse(ts.employee)
        [log] = ts.time_logs
        self.assertEqual(log.task, self.task)
        self.assertEqual(log.project, self.project)
        self.assertEqual(log.hours, 2.5)
        self.assertEqual(log.description, "Accounts mapped to the GCC template")
        self.assertTrue(log.completed)
        # the logged time ends now
        self.assertLess(
            abs(
                (
                    frappe.utils.get_datetime(log.to_time) - frappe.utils.now_datetime()
                ).total_seconds()
            ),
            120,
        )

        mine = run_as_user(DEV[0], tasky.get_my_timesheets)
        self.assertIn(result["timesheet"], [t["name"] for t in mine])

    def test_timesheet_links_the_employee_when_there_is_one(self):
        employee = make_employee(DEV[0], "Meera Joseph").name
        result = self.complete()
        self.assertEqual(
            frappe.db.get_value("Timesheet", result["timesheet"], "employee"), employee
        )

    def test_tracked_time_is_not_counted_twice(self):
        # a paused timer already added its 1.5h to actual hours
        frappe.db.set_value(
            "Task",
            self.task,
            {"custom_actual_hours": 1.5, "custom_timer_elapsed": 1.5},
        )
        self.complete(hours_worked=2)
        actual, elapsed = frappe.db.get_value(
            "Task", self.task, ["custom_actual_hours", "custom_timer_elapsed"]
        )
        self.assertEqual(actual, 2)
        self.assertEqual(elapsed, 0)

    def test_review_project_still_records_the_time(self):
        frappe.db.set_value("Project", self.project, "review_before_done", 1)
        result = self.complete()

        self.assertEqual(result["status"], "Pending Review")
        self.assertEqual(
            frappe.db.get_value("Task", self.task, "status"), "Pending Review"
        )
        self.assertEqual(result["timesheet_status"], "Submitted")
        self.assertEqual(get_task_timesheets(self.task), [result["timesheet"]])

        # the lead signs off without logging hours of their own
        run_as_user(LEAD[0], lambda: tasky.approve_task(task=self.task))
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Completed")
        self.assertEqual(len(get_task_timesheets(self.task)), 1)

    def test_failed_timesheet_fails_the_completion(self):
        with patch.object(
            Timesheet, "validate", side_effect=frappe.ValidationError("disk full")
        ), self.assertRaises(frappe.ValidationError):
            self.complete()
        self.assert_not_completed()

    def test_failed_submit_keeps_a_draft_timesheet(self):
        with patch.object(
            Timesheet,
            "before_submit",
            create=True,
            side_effect=frappe.ValidationError("period closed"),
        ):
            result = self.complete()

        self.assertEqual(result["status"], "Completed")
        self.assertEqual(result["timesheet_status"], "Draft")
        ts = frappe.get_doc("Timesheet", result["timesheet"])
        self.assertEqual(ts.docstatus, 0)
        self.assertEqual(ts.total_hours, 2.5)

    def test_completed_task_cannot_be_completed_again(self):
        self.complete()
        with self.assertRaises(frappe.ValidationError):
            self.complete()
        self.assertEqual(len(get_task_timesheets(self.task)), 1)

    def test_only_someone_who_may_edit_the_task_can_complete_it(self):
        with self.assertRaises(frappe.PermissionError):
            self.complete(user=OTHER_DEV)
        self.assert_not_completed()
