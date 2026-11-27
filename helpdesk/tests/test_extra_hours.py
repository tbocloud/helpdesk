from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    freeze_work_day,
    get_task_timesheets,
    hold_commits,
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    run_as_user,
)

PM = ("pm.extra@extra-hours.example", "Anjali Pillai")
LEAD = ("lead.extra@extra-hours.example", "Rahul Nair")
COORDINATOR = ("coord.extra@extra-hours.example", "Divya Menon")
DEV = ("dev.extra@extra-hours.example", "Meera Joseph")
WHY = "The client's chart of accounts had 300 more ledgers than agreed"


class TestExtraHours(FrappeTestCase):
    """Hours over a task's estimate wait for the project manager (docs/extra-hours.md)."""

    def setUp(self):
        hold_commits(self)
        moment = freeze_work_day(self)
        self.today = moment.date()
        self.yesterday = self.today - timedelta(days=1)
        self.addCleanup(frappe.set_user, "Administrator")

        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (LEAD, COORDINATOR, DEV):
            make_tasky_user(*user)
        self.project = make_project(
            "Extra Hours - ERP Rollout",
            members=[
                (LEAD[0], "Developer"),
                (COORDINATOR[0], "Project Coordinator"),
                (DEV[0], "Developer"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])
        self.task = make_task(self.project, "Map chart of accounts").name
        # made before yesterday, so yesterday's hours may go on it
        frappe.db.set_value(
            "Task",
            self.task,
            {
                "custom_estimated_hours": 4,
                "creation": frappe.utils.add_days(self.yesterday, -1),
            },
        )
        make_assignment("Task", self.task, DEV[0])

    def complete(self, days, reason=None):
        return run_as_user(
            DEV[0],
            lambda: tasky.complete_task(
                task=self.task,
                days=[{"date": str(day), "hours": hours} for day, hours in days],
                notes="Accounts mapped",
                extra_hours_reason=reason,
            ),
        )

    def over(self):
        """3 h yesterday and 1.5 h today on a 4 h task: 0.5 h over, from today."""
        return self.complete([(self.yesterday, 3), (self.today, 1.5)], WHY)

    def logged(self) -> dict:
        """{date: hours} on the task's timesheets."""
        days: dict = {}
        for row in frappe.get_all(
            "Timesheet Detail",
            filters={"task": self.task, "parenttype": "Timesheet"},
            fields=["from_time", "hours"],
        ):
            day = frappe.utils.getdate(row.from_time)
            days[day] = days.get(day, 0) + row.hours
        return days

    def task_values(self, *fields):
        return frappe.db.get_value("Task", self.task, list(fields))

    def told(self, user) -> bool:
        return bool(
            frappe.db.exists(
                "HD Notification", {"user_to": user, "reference_name": self.task}
            )
        )

    def test_within_the_estimate_completes_as_before(self):
        result = self.complete([(self.today, 1.5)])
        self.assertEqual((result["status"], result["extra_hours"]), ("Completed", 0))
        self.assertEqual(self.logged(), {self.today: 1.5})

    def test_a_task_without_an_estimate_has_no_limit(self):
        frappe.db.set_value("Task", self.task, "custom_estimated_hours", 0)
        result = self.complete([(self.yesterday, 6), (self.today, 1.5)])
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(self.logged(), {self.yesterday: 6, self.today: 1.5})

    def test_going_over_the_estimate_needs_an_explanation(self):
        for reason in (None, "  "):
            with self.assertRaisesRegex(frappe.ValidationError, "0.5 h over"):
                self.complete([(self.yesterday, 3), (self.today, 1.5)], reason)
        self.assertEqual(self.task_values("status"), "Open")
        self.assertEqual(get_task_timesheets(self.task), [])

    def test_the_estimate_is_logged_and_the_rest_waits_for_review(self):
        result = self.over()

        # the project doesn't ask for reviews; going over the estimate does
        self.assertEqual(result["status"], "Pending Review")
        self.assertEqual((result["hours_logged"], result["extra_hours"]), (4, 0.5))
        # the hours within the estimate from the earliest days, the rest from today
        self.assertEqual(self.logged(), {self.yesterday: 3, self.today: 1})
        self.assertEqual(
            self.task_values(
                "custom_actual_hours",
                "extra_hours",
                "extra_hours_by",
                "extra_hours_reason",
            ),
            (4, 0.5, DEV[0], WHY),
        )
        self.assertTrue(self.told(LEAD[0]))
        self.assertTrue(
            frappe.db.exists(
                "HD Notification",
                {
                    "user_to": LEAD[0],
                    "reference_name": self.task,
                    "message": ("like", "%0.5 h over the estimate%"),
                },
            )
        )

    def test_the_manager_approves_and_the_hours_are_logged_for_the_worker(self):
        self.over()
        # one click from a list, without reading why: refused
        with self.assertRaisesRegex(frappe.ValidationError, "Open it to read why"):
            run_as_user(LEAD[0], lambda: tasky.approve_task(task=self.task))
        # a coordinator reviews tasks but doesn't decide hours over the estimate
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                COORDINATOR[0],
                lambda: tasky.approve_task(task=self.task, approve_extra_hours=1),
            )

        result = run_as_user(
            LEAD[0], lambda: tasky.approve_task(task=self.task, approve_extra_hours=1)
        )

        self.assertEqual(result["status"], "Completed")
        self.assertEqual(self.logged(), {self.yesterday: 3, self.today: 1.5})
        self.assertEqual(
            self.task_values("custom_actual_hours", "extra_hours", "extra_hours_days"),
            (4.5, 0, None),
        )
        # the worker's own timesheet, after the hour already logged today
        logs = frappe.get_all(
            "Timesheet Detail",
            filters={"task": self.task, "parenttype": "Timesheet"},
            fields=["parent", "from_time", "to_time", "hours"],
            order_by="from_time",
        )
        first_today, approved = [log for log in logs if log.hours in (1, 0.5)]
        self.assertEqual(
            frappe.db.get_value("Timesheet", approved.parent, "owner"), DEV[0]
        )
        self.assertGreaterEqual(approved.from_time, first_today.to_time)
        self.assertTrue(self.told(DEV[0]))

    def test_declined_extra_hours_are_never_logged(self):
        self.over()
        with self.assertRaises(frappe.ValidationError):
            run_as_user(LEAD[0], lambda: tasky.decline_extra_hours(self.task, "  "))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                COORDINATOR[0],
                lambda: tasky.decline_extra_hours(self.task, "Not agreed"),
            )

        result = run_as_user(
            LEAD[0],
            lambda: tasky.decline_extra_hours(self.task, "Out of scope; raise a CR"),
        )

        self.assertEqual(result["status"], "Completed")
        self.assertEqual(self.logged(), {self.yesterday: 3, self.today: 1})
        self.assertEqual(self.task_values("custom_actual_hours", "extra_hours"), (4, 0))
        self.assertTrue(self.told(DEV[0]))

    def test_sent_back_the_waiting_hours_come_along_next_time(self):
        self.over()
        run_as_user(
            LEAD[0], lambda: tasky.send_back_task(self.task, "Add the GST ledgers")
        )
        days = run_as_user(DEV[0], lambda: tasky.get_completion_days(self.task))
        self.assertEqual((days["waiting"], days["waiting_reason"]), (0.5, WHY))
        self.assertEqual((days["estimate"], days["logged"]), (4, 4))

        # all of it is over the estimate now: asked for again, with what still waited
        with self.assertRaises(frappe.ValidationError):
            self.complete([(self.today, 0.25)])
        result = self.complete([(self.today, 0.25)], WHY + "; GST ledgers added")

        self.assertEqual((result["hours_logged"], result["extra_hours"]), (0, 0.75))
        self.assertIsNone(result["timesheet"])
        self.assertEqual(self.logged(), {self.yesterday: 3, self.today: 1})
