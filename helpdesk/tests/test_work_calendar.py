from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from helpdesk import team_dashboard as td
from helpdesk import work_calendar
from helpdesk.api import work_days
from helpdesk.api.work import is_task_overdue
from helpdesk.task_estimates import add_working_days
from helpdesk.test_utils import (
    add_company_holiday,
    forget_request_cache,
    get_day_off_activity,
    hold_commits,
    make_project,
    make_task,
    set_work_settings,
)

HOLIDAYS = "Saturday Rota Test"


class TestSaturdayRota(FrappeTestCase):
    """Monday to Saturday, with the 2nd and 4th Saturdays off (October 2026)."""

    def setUp(self):
        hold_commits(self)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        frappe.db.set_single_value(
            "HD Work Settings", {"weekly_off": "Sunday", "saturdays_off": "2nd and 4th"}
        )
        frappe.clear_document_cache("HD Work Settings", "HD Work Settings")

    def test_second_and_fourth_saturdays_are_off(self):
        # Saturdays in October 2026: 3rd, 10th, 17th, 24th, 31st
        off = [
            d.day
            for d in work_calendar.saturdays_off_between("2026-10-01", "2026-10-31")
        ]
        self.assertEqual(off, [10, 24])
        self.assertTrue(work_calendar.is_saturday_off("2026-10-10"))
        self.assertFalse(work_calendar.is_saturday_off("2026-10-17"))
        self.assertFalse(work_calendar.is_saturday_off("2026-10-12"))  # a Monday

    def test_working_days_skip_the_saturdays_off(self):
        # Friday 9th + 1 working day: Saturday 10th is off, Sunday too, so Monday 12th
        self.assertEqual(add_working_days("2026-10-09", 2), date(2026, 10, 12))
        # Friday 16th + 1: Saturday 17th is a working day
        self.assertEqual(add_working_days("2026-10-16", 2), date(2026, 10, 17))

    def make_list(self):
        frappe.delete_doc(
            "HD Service Holiday List", HOLIDAYS, force=True, ignore_missing=True
        )
        return frappe.get_doc(
            {
                "doctype": "HD Service Holiday List",
                "holiday_list_name": HOLIDAYS,
                "from_date": "2026-10-01",
                "to_date": "2026-10-31",
                "holidays": [
                    {"holiday_date": "2026-10-02", "description": "Gandhi Jayanti"}
                ],
            }
        ).insert(ignore_permissions=True)

    def test_holiday_list_gets_the_saturdays_and_keeps_other_holidays(self):
        holidays = self.make_list()
        wanted = work_calendar.saturdays_off_between("2026-10-01", "2026-11-30")
        today = date(2026, 10, 1)

        self.assertTrue(work_calendar.sync_holiday_list(holidays.name, wanted, today))
        holidays.reload()
        dates = [str(h.holiday_date) for h in holidays.holidays]
        self.assertEqual(
            dates,
            ["2026-10-02", "2026-10-10", "2026-10-24", "2026-11-14", "2026-11-28"],
        )
        self.assertEqual(str(holidays.to_date), "2026-11-28")  # widened to fit
        self.assertIn("2nd Saturday off", holidays.holidays[1].description)

        # running again changes nothing
        self.assertFalse(work_calendar.sync_holiday_list(holidays.name, wanted, today))

        # a new rule drops the old future Saturdays but never the people's holidays
        new = work_calendar.saturdays_off_between(
            "2026-10-01", "2026-11-30", rule={1, 3}
        )
        work_calendar.sync_holiday_list(holidays.name, new, today)
        holidays.reload()
        dates = [str(h.holiday_date) for h in holidays.holidays]
        self.assertIn("2026-10-02", dates)
        self.assertNotIn("2026-10-10", dates)
        self.assertIn("2026-10-03", dates)


class TestDueDatesOnDaysOff(FrappeTestCase):
    """A task is never due on a day off and never goes overdue over one. January 2027:
    Saturday 9th is the 2nd Saturday (off), Sunday 10th the weekly off and Monday 11th a
    holiday, so the next working day is Tuesday 12th; Friday 8th is worked."""

    def setUp(self):
        hold_commits(self)
        self.addCleanup(forget_request_cache)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        set_work_settings(weekly_off="Sunday", saturdays_off="2nd and 4th")
        add_company_holiday("2027-01-11", "Test Pongal")
        forget_request_cache()

    def test_why_a_day_is_off(self):
        self.assertEqual(work_calendar.day_off_reason("2027-01-09"), "a Saturday off")
        self.assertEqual(work_calendar.day_off_reason("2027-01-10"), "a weekly off")
        self.assertEqual(work_calendar.day_off_reason("2027-01-11"), "Test Pongal")
        self.assertEqual(work_calendar.day_off_reason("2027-01-12"), "")
        self.assertEqual(work_calendar.day_off_reason("2027-01-16"), "")  # 3rd Saturday

    def test_the_working_day_after_and_before(self):
        self.assertEqual(
            work_calendar.next_working_day("2027-01-09"), date(2027, 1, 12)
        )
        self.assertEqual(
            work_calendar.next_working_day("2027-01-12"), date(2027, 1, 12)
        )
        self.assertEqual(
            work_calendar.previous_working_day("2027-01-11"), date(2027, 1, 8)
        )

    def test_a_task_due_on_a_day_off_isnt_overdue_until_after_the_next_working_day(
        self,
    ):
        self.assertEqual(work_calendar.overdue_cutoff("2027-01-12"), date(2027, 1, 9))
        self.assertEqual(work_calendar.overdue_cutoff("2027-01-13"), date(2027, 1, 13))
        task = frappe._dict(status="Open")
        for due in ("2027-01-09", "2027-01-10", "2027-01-11"):
            self.assertFalse(is_task_overdue(task, getdate(due), getdate("2027-01-12")))
            self.assertTrue(is_task_overdue(task, getdate(due), getdate("2027-01-13")))
        # due on the Friday before: a working day, so overdue once it has passed
        self.assertTrue(
            is_task_overdue(task, getdate("2027-01-08"), getdate("2027-01-12"))
        )

    def test_the_scoreboard_counts_overdue_the_same_way(self):
        project = make_project("Days Off Project")
        task = make_task(project.name, "Due on Sunday")
        # a date saved before this rule, or a holiday added later: straight into the table
        frappe.db.set_value("Task", task.name, "exp_end_date", "2027-01-10")

        def overdue_on(day):
            return {r["name"] for r in td.overdue_tasks(getdate(day))}

        self.assertNotIn(task.name, overdue_on("2027-01-12"))
        forget_request_cache()
        self.assertIn(task.name, overdue_on("2027-01-13"))

    def test_a_due_date_on_a_day_off_is_saved_as_the_next_working_day(self):
        project = make_project("Days Off Project")
        task = make_task(project.name, "Due on Sunday", exp_end_date="2027-01-10")
        self.assertEqual(getdate(task.exp_end_date), date(2027, 1, 12))
        self.assertIn(
            "Sun 10 Jan is a weekly off, so the task is due Tue 12 Jan.",
            " ".join(str(m) for m in frappe.message_log),
        )
        # and the task's activity says why, for whoever opens it later
        self.assertEqual(
            get_day_off_activity(task.name),
            ["Due date moved off Sun 10 Jan (a weekly off) to Tue 12 Jan."],
        )
        # rescheduled from Friday 8th to the Saturday off: saved as Tuesday, one slip
        task.db_set("exp_end_date", "2027-01-08")
        task.reload()
        task.exp_end_date = "2027-01-09"
        task.save(ignore_permissions=True)
        self.assertEqual(getdate(task.exp_end_date), date(2027, 1, 12))
        self.assertEqual(task.slip_count, 1)
        # then onto the holiday: lands on the same Tuesday, so no slip of its own
        task.exp_end_date = "2027-01-11"
        task.save(ignore_permissions=True)
        self.assertEqual(getdate(task.exp_end_date), date(2027, 1, 12))
        self.assertEqual(task.slip_count, 1)
        self.assertIn(
            "Due date moved off Mon 11 Jan (Test Pongal) to Tue 12 Jan.",
            get_day_off_activity(task.name),
        )
        # a date on a working day adds no such line
        task.exp_end_date = "2027-01-13"
        task.save(ignore_permissions=True)
        self.assertFalse(
            [line for line in get_day_off_activity(task.name) if "Wed 13 Jan" in line]
        )

    def test_a_content_task_moves_back_before_its_post_goes_live(self):
        moved = work_calendar.due_on_working_day("2027-01-11", content=True)
        self.assertEqual(moved["due"], date(2027, 1, 8))
        # the working day before has passed already: it keeps its date
        with patch.object(work_calendar, "nowdate", return_value="2027-01-11"):
            self.assertIsNone(
                work_calendar.due_on_working_day("2027-01-11", content=True)
            )

    def test_the_date_pickers_are_told_where_a_date_will_go(self):
        self.assertEqual(
            work_days.check_due_date("2027-01-10"),
            {"was": "2027-01-10", "due": "2027-01-12", "reason": "a weekly off"},
        )
        self.assertIsNone(work_days.check_due_date("2027-01-12"))
        self.assertEqual(
            work_days.check_due_date("2027-01-11", content=1)["due"], "2027-01-08"
        )
