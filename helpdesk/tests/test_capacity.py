from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days

from helpdesk.api import capacity
from helpdesk.test_utils import (
    hold_commits,
    make_department,
    make_planned_task,
    make_project,
    make_tasky_user,
    make_timesheet,
    run_as_user,
    set_work_settings,
)

PM = "pm.capacity@capacity.example"
LEAD = "lead.capacity@capacity.example"
DEV = "dev.capacity@capacity.example"
OUTSIDER = "outsider.capacity@capacity.example"
# a Monday; the 17th is the 3rd Saturday (a working day), the 24th the 4th (off)
MONDAY = "2026-10-12"


def day(n: int) -> date:
    return date(2026, 10, n)


class CapacityCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        set_work_settings(
            weekly_off="Sunday", saturdays_off="2nd and 4th", dev_hours_per_day=6
        )
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )


class TestWorkCalendar(CapacityCase):
    def test_working_days_skip_sundays_the_saturdays_off_and_holidays(self):
        days = capacity.working_days(day(5), day(18), {day(15)})
        # the 10th is the 2nd Saturday, the 11th and 18th Sundays, the 15th a holiday
        self.assertEqual([d.day for d in days], [5, 6, 7, 8, 9, 12, 13, 14, 16, 17])

    def test_window_runs_to_the_sunday_of_the_last_week(self):
        self.assertEqual(
            capacity.planning_window(day(14), 2, set()), (day(14), day(25))
        )

    def test_a_week_with_no_working_day_left_starts_next_monday(self):
        # Saturday the 10th is off and Sunday too
        self.assertEqual(
            capacity.planning_window(day(10), 1, set()), (day(12), day(18))
        )


class TestSpreadingHours(CapacityCase):
    def setUp(self):
        super().setUp()
        self.calendar = capacity.working_days(day(12), day(31), set())

    def allocate(self, typical=None, **task):
        task = frappe._dict(
            {
                "custom_estimated_hours": 0,
                "exp_start_date": None,
                "exp_end_date": None,
                "logged_hours": 0,
                **task,
            }
        )
        return capacity.task_allocation(task, typical, self.calendar, day(12), 6)

    def test_hours_spread_evenly_to_the_due_date(self):
        result = self.allocate(custom_estimated_hours=12, exp_end_date=day(14))
        self.assertEqual(result["by_day"], {day(12): 4, day(13): 4, day(14): 4})
        self.assertFalse(result["typical"])

    def test_logged_hours_come_off_the_estimate(self):
        result = self.allocate(
            custom_estimated_hours=12, exp_end_date=day(14), logged_hours=9
        )
        self.assertEqual(result["by_day"], {day(12): 1, day(13): 1, day(14): 1})

    def test_a_later_start_waits_and_days_off_are_skipped(self):
        # 16th, 17th (3rd Saturday, worked), 19th: the 18th is a Sunday
        result = self.allocate(
            custom_estimated_hours=9, exp_start_date=day(16), exp_end_date=day(19)
        )
        self.assertEqual(result["by_day"], {day(16): 3, day(17): 3, day(19): 3})

    def test_overdue_work_lands_in_full_days_from_the_start(self):
        result = self.allocate(custom_estimated_hours=8, exp_end_date=day(9))
        self.assertEqual(result["by_day"], {day(12): 6, day(13): 2})

    def test_due_on_a_day_off_goes_on_the_next_working_day(self):
        result = self.allocate(
            custom_estimated_hours=5, exp_start_date=day(18), exp_end_date=day(18)
        )
        self.assertEqual(result["by_day"], {day(19): 5})

    def test_a_task_without_hours_or_date_uses_the_standard_estimate(self):
        result = self.allocate(typical={"working_days": 2, "estimated_hours": 12})
        self.assertEqual(result["by_day"], {day(12): 6, day(13): 6})
        self.assertTrue(result["typical"])


class TestLoadFlags(FrappeTestCase):
    def test_thresholds(self):
        self.assertEqual(capacity.load_flag(41, 40), capacity.OVERLOADED)
        self.assertEqual(capacity.load_flag(40, 40), capacity.BUSY)
        self.assertEqual(capacity.load_flag(32, 40), capacity.BUSY)
        self.assertEqual(capacity.load_flag(31, 40), capacity.AVAILABLE)
        self.assertEqual(capacity.load_flag(3, 0), capacity.OVERLOADED)
        self.assertIsNone(capacity.load_flag(0, 0))


class TestGetCapacity(CapacityCase):
    def setUp(self):
        super().setUp()
        make_tasky_user(PM, "Leena Varghese", roles=("Project Manager",))
        for user, name in (
            (LEAD, "Nikhil Das"),
            (DEV, "Fathima Rizwana"),
            (OUTSIDER, "Joel Mathew"),
        ):
            make_tasky_user(user, name)
        self.department = make_department("Capacity ERP").name
        self.project = make_project(
            "Capacity Rollout", members=[(DEV, "Developer")], owner=PM
        ).name
        frappe.db.set_value(
            "Project",
            self.project,
            {"project_lead": LEAD, "custom_department": self.department},
        )
        self.other = make_project(
            "Capacity Support", members=[(DEV, "Developer"), (OUTSIDER, "Developer")]
        ).name
        today = patch("helpdesk.api.capacity.nowdate", return_value=MONDAY)
        today.start()
        self.addCleanup(today.stop)

    def capacity_as(self, user, **filters):
        return run_as_user(user, lambda: capacity.get_capacity(**filters))

    def person(self, result, user):
        return next(p for p in result["people"] if p["user"] == user)

    def test_lead_plans_their_people_over_two_weeks(self):
        payroll = make_planned_task(self.project, "Payroll setup", DEV, 12, day(14))
        make_timesheet(self.project, 6, f"{MONDAY} 10:00:00", task=payroll)
        make_planned_task(self.project, "Opening stock", DEV, 8, day(9))
        make_planned_task(self.other, "Support backlog", DEV, 10, day(16))

        result = self.capacity_as(LEAD)
        self.assertEqual((result["start"], result["end"]), (MONDAY, "2026-10-25"))
        dev = self.person(result, DEV)
        # 11 working days (the 24th is the 4th Saturday) at 6 hours
        self.assertEqual((dev["available"], dev["planned"]), (66, 24))
        self.assertEqual(dev["flag"], capacity.AVAILABLE)
        monday = dev["days"][0]
        # 2 (payroll, after the logged 6) + 6 (overdue, first) + 2 (support)
        self.assertEqual((monday["planned"], monday["flag"]), (10, capacity.OVERLOADED))
        self.assertEqual(
            [(w["available"], w["planned"]) for w in dev["weeks"]], [(36, 24), (30, 0)]
        )
        # work on a project the lead doesn't run counts, without its task names
        self.assertIn(
            {"project": None, "project_name": None, "hours": 10}, dev["projects"]
        )
        self.assertNotIn("Support backlog", [t["title"] for t in dev["tasks"]])
        self.assertNotIn(OUTSIDER, [p["user"] for p in result["people"]])
        # the lead (no tasks) and the developer are both under 80%
        self.assertEqual(result["totals"]["flags"][capacity.AVAILABLE], 2)

    def test_filters_narrow_to_a_department_and_hours_by_department(self):
        make_planned_task(self.project, "Bank reconciliation", DEV, 6, day(13))
        result = self.capacity_as(PM, department=self.department, weeks=1)
        self.assertEqual(len(result["weeks"]), 1)
        self.assertIn(DEV, [p["user"] for p in result["people"]])
        self.assertIn(
            {"department": self.department, "hours": 6}, result["by_department"]
        )

    def test_a_lead_cannot_filter_to_someone_elses_project(self):
        result = self.capacity_as(LEAD, project=self.other)
        self.assertEqual(result["people"], [])

    def test_developers_cannot_plan_capacity(self):
        with self.assertRaises(frappe.PermissionError):
            self.capacity_as(DEV)

    def test_work_past_the_window_counts_only_its_share(self):
        # 22 working days from the 12th to 6 November; 11 of them in the window
        make_planned_task(self.project, "Data migration", DEV, 44, add_days(MONDAY, 25))
        dev = self.person(self.capacity_as(LEAD), DEV)
        self.assertEqual(dev["planned"], 22)
