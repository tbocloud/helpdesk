# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from helpdesk import recurrence
from helpdesk.api import recurring_tasks as api
from helpdesk.helpdesk.doctype.hd_recurring_task.hd_recurring_task import (
    create_recurring_tasks,
)
from helpdesk.test_utils import (
    add_company_holiday,
    get_recurring_tasks_created,
    get_task_comments,
    hold_commits,
    make_assigned_task,
    make_project,
    make_recurring_task,
    make_tasky_user,
    recurrence_rule,
    run_as_user,
    set_work_settings,
)

PM = ("pm.recurring@recurring-tests.example", "Divya Menon")
LEAD = ("lead.recurring@recurring-tests.example", "Arjun Varghese")
MEMBER = ("member.recurring@recurring-tests.example", "Sneha Iyer")
OUTSIDER = ("outsider.recurring@recurring-tests.example", "Karthik Rao")
EVERY_DAY = lambda day: True  # noqa: E731
UNTIL = date(2030, 12, 31)


def dates_of(rule, count=6, is_working=EVERY_DAY):
    return [o.on for o in recurrence.occurrences(rule, is_working, UNTIL)][:count]


def due_dates_of(rule, count=6, is_working=EVERY_DAY):
    return [o.due for o in recurrence.occurrences(rule, is_working, UNTIL)][:count]


class TestRecurrenceDates(FrappeTestCase):
    """The date math, without the database (2026 calendar)."""

    def test_monthly_day_31_falls_back_to_the_months_last_day(self):
        rule = recurrence_rule(month_day=31)
        self.assertEqual(
            dates_of(rule, 4),
            [
                date(2026, 1, 31),
                date(2026, 2, 28),
                date(2026, 3, 31),
                date(2026, 4, 30),
            ],
        )

    def test_last_day_of_month_in_a_leap_year(self):
        rule = recurrence_rule(last_day_of_month=1, start_date="2028-01-01")
        self.assertEqual(
            dates_of(rule, 3),
            [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31)],
        )

    def test_yearly_on_29_february(self):
        rule = recurrence_rule(
            frequency="Yearly", month_day=29, start_date="2024-02-29"
        )
        self.assertEqual(
            dates_of(rule, 5),
            [
                date(2024, 2, 29),
                date(2025, 2, 28),
                date(2026, 2, 28),
                date(2027, 2, 28),
                date(2028, 2, 29),
            ],
        )

    def test_weekly_on_several_weekdays_every_other_week(self):
        # starts on Wednesday 7 October, so that week's Monday is skipped
        rule = recurrence_rule(
            frequency="Weekly",
            weekdays="Monday,Friday",
            interval=2,
            start_date="2026-10-07",
        )
        self.assertEqual(
            dates_of(rule, 5),
            [
                date(2026, 10, 9),
                date(2026, 10, 19),
                date(2026, 10, 23),
                date(2026, 11, 2),
                date(2026, 11, 6),
            ],
        )

    def test_daily_and_quarterly_intervals(self):
        daily = recurrence_rule(frequency="Daily", interval=3, start_date="2026-10-09")
        self.assertEqual(
            dates_of(daily, 3),
            [date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 15)],
        )
        # the 15th of October is before the start, so the first quarter is January
        quarterly = recurrence_rule(
            frequency="Quarterly", month_day=15, start_date="2026-10-20"
        )
        self.assertEqual(
            dates_of(quarterly, 3),
            [date(2027, 1, 15), date(2027, 4, 15), date(2027, 7, 15)],
        )

    def test_monthly_every_other_month(self):
        rule = recurrence_rule(month_day=1, interval=2)
        self.assertEqual(
            dates_of(rule, 3), [date(2026, 1, 1), date(2026, 3, 1), date(2026, 5, 1)]
        )

    def test_end_conditions(self):
        after = recurrence_rule(month_day=1, ends="After", max_occurrences=3)
        self.assertEqual(
            dates_of(after, 10), [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
        )
        on_date = recurrence_rule(month_day=1, ends="On date", end_date="2026-02-15")
        self.assertEqual(dates_of(on_date, 10), [date(2026, 1, 1), date(2026, 2, 1)])

    def test_lead_time_sets_the_creation_day(self):
        rule = recurrence_rule(month_day=15, lead_days=3, start_date="2026-10-01")
        first = next(recurrence.occurrences(rule, EVERY_DAY, UNTIL))
        self.assertEqual(first.due, date(2026, 10, 15))
        self.assertEqual(first.create_on, date(2026, 10, 12))

    def test_non_working_days_move_or_drop(self):
        weekends = lambda day: day.weekday() < 5  # noqa: E731
        # 1 November 2026 is a Sunday: due Monday the 2nd
        monthly = recurrence_rule(
            month_day=1, start_date="2026-11-01", skip_non_working_days=1
        )
        self.assertEqual(due_dates_of(monthly, 1, weekends), [date(2026, 11, 2)])
        # without the option the Sunday stays
        self.assertEqual(
            due_dates_of(
                recurrence_rule(month_day=1, start_date="2026-11-01"), 1, weekends
            ),
            [date(2026, 11, 1)],
        )
        # a daily rule drops the weekend instead of piling it onto Monday
        daily = recurrence_rule(
            frequency="Daily", start_date="2026-10-09", skip_non_working_days=1
        )
        self.assertEqual(
            due_dates_of(daily, 3, weekends),
            [date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13)],
        )

    def test_upcoming_stops_when_no_day_is_ever_worked(self):
        rule = recurrence_rule(frequency="Daily", skip_non_working_days=1)
        self.assertEqual(recurrence.upcoming(rule, lambda day: False, None, 3), [])

    def test_describe(self):
        self.assertEqual(
            recurrence.describe(
                recurrence_rule(month_day=1, due_time="18:00:00", lead_days=3)
            ),
            "Monthly on the 1st · due 18:00 · created 3 days ahead",
        )
        self.assertEqual(
            recurrence.describe(
                recurrence_rule(frequency="Weekly", weekdays="Friday", interval=2)
            ),
            "Every 2 weeks on Friday",
        )
        self.assertEqual(
            recurrence.describe(
                recurrence_rule(last_day_of_month=1, frequency="Quarterly")
            ),
            "Quarterly on the last day",
        )


class TestRecurringTasks(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        set_work_settings(
            weekly_off="Sunday",
            saturdays_off="2nd and 4th",
            ai_task_estimates=0,
            ai_task_descriptions=0,
        )
        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (LEAD, MEMBER, OUTSIDER):
            make_tasky_user(*user)
        self.project = make_project(
            "Recurring - Kochi Traders support",
            members=[(PM[0], "Project Manager"), (MEMBER[0], "Developer")],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])

    def rule(self, subject="Monthly backup check", **values):
        return make_recurring_task(self.project, subject, **values)

    def run_on(self, day, rule):
        with self.freeze_time(f"{day} 01:00:00"):
            rule.reload()
            return rule.create_due_tasks()

    # --- the working-day calendar ---

    def test_due_date_moves_off_saturdays_off_and_holidays(self):
        add_company_holiday("2026-11-02")
        is_working = recurrence.working_day_checker("2026-10-01", "2026-12-31")
        # 10 October is the 2nd Saturday: off, so Monday the 12th
        tenth = recurrence_rule(
            month_day=10, start_date="2026-10-01", skip_non_working_days=1
        )
        self.assertEqual(due_dates_of(tenth, 1, is_working), [date(2026, 10, 12)])
        # 17 October, the 3rd Saturday, is worked
        weekly = recurrence_rule(
            frequency="Weekly",
            weekdays="Saturday",
            start_date="2026-10-10",
            skip_non_working_days=1,
        )
        self.assertEqual(
            due_dates_of(weekly, 2, is_working),
            [date(2026, 10, 12), date(2026, 10, 17)],
        )
        # 1 November is a Sunday and the 2nd a holiday: Tuesday the 3rd
        first = recurrence_rule(
            month_day=1, start_date="2026-11-01", skip_non_working_days=1
        )
        self.assertEqual(due_dates_of(first, 1, is_working), [date(2026, 11, 3)])

    # --- the daily job ---

    def test_task_is_created_lead_days_before_it_is_due(self):
        with self.freeze_time("2026-10-09 10:00:00"):
            rule = self.rule(
                "GST filing reminder",
                month_day=15,
                lead_days=3,
                start_date="2026-10-01",
                assignee=LEAD[0],
                category="Functional",
                priority="High",
                estimated_hours=2,
                is_key=1,
            )
        self.assertIsNone(self.run_on("2026-10-11", rule))
        task_name = self.run_on("2026-10-12", rule)
        task = frappe.get_doc("Task", task_name)
        self.assertEqual(task.subject, "GST filing reminder")
        self.assertEqual(getdate(task.exp_end_date), date(2026, 10, 15))
        self.assertEqual(task.custom_recurring_task, rule.name)
        self.assertEqual(getdate(task.custom_recurrence_date), date(2026, 10, 15))
        self.assertEqual((task.priority, task.is_key), ("High", 1))
        self.assertIn(LEAD[0], frappe.parse_json(task._assign))
        # the person who set the schedule up is the one who assigned it
        self.assertEqual(
            frappe.db.get_value(
                "ToDo",
                {"reference_name": task_name, "allocated_to": LEAD[0]},
                "assigned_by",
            ),
            rule.owner,
        )
        rule.reload()
        self.assertEqual(rule.last_task, task_name)
        self.assertEqual(rule.occurrences_created, 1)
        # 15 November is a Sunday
        self.assertEqual(getdate(rule.next_due_date), date(2026, 11, 16))

    def test_rerunning_never_duplicates(self):
        with self.freeze_time("2026-10-09 10:00:00"):
            rule = self.rule(month_day=12, start_date="2026-10-01")
        self.run_on("2026-10-12", rule)
        self.run_on("2026-10-12", rule)
        self.run_on("2026-10-13", rule)
        with self.freeze_time("2026-10-12 02:00:00"):
            create_recurring_tasks()
            # even with its progress lost, the occurrence isn't created twice
            rule.reload()
            rule.db_set("last_occurrence", None)
            create_recurring_tasks()
        self.assertEqual(len(get_recurring_tasks_created(rule.name)), 1)

    def test_missed_runs_create_only_the_latest_with_a_note(self):
        with self.freeze_time("2026-10-01 10:00:00"):
            rule = self.rule(
                "Weekly status report",
                frequency="Weekly",
                weekdays="Monday",
                start_date="2026-10-01",
            )
        # the job didn't run on 5, 12, 19 or 26 October
        task = self.run_on("2026-10-27", rule)
        created = get_recurring_tasks_created(rule.name)
        self.assertEqual([t.name for t in created], [task])
        self.assertEqual(getdate(created[0].custom_recurrence_date), date(2026, 10, 26))
        self.assertTrue(get_task_comments(task, "%missed%"))

    def test_a_new_schedule_skips_dates_already_past(self):
        with self.freeze_time("2026-10-09 10:00:00"):
            rule = self.rule(month_day=1, start_date="2026-09-01")
        self.assertEqual(getdate(rule.last_occurrence), date(2026, 10, 1))
        self.assertIsNone(self.run_on("2026-10-09", rule))
        # 1 November is a Sunday
        self.assertEqual(getdate(rule.next_due_date), date(2026, 11, 2))

    def test_ends_after_n_tasks(self):
        with self.freeze_time("2026-10-09 08:00:00"):
            rule = self.rule(
                frequency="Weekly",
                weekdays="Friday",
                start_date="2026-10-09",
                ends="After",
                max_occurrences=2,
            )
        self.run_on("2026-10-09", rule)
        self.run_on("2026-10-16", rule)
        self.run_on("2026-10-23", rule)
        rule.reload()
        self.assertEqual(len(get_recurring_tasks_created(rule.name)), 2)
        self.assertFalse(rule.is_active)
        self.assertIn("Finished", rule.inactive_reason)
        self.assertIsNone(rule.next_due_date)
        # moving the end later starts it again, from the next date not yet past
        with self.freeze_time("2026-10-23 08:00:00"):
            rule.max_occurrences = 4
            rule.save()
        self.assertTrue(rule.is_active)
        self.assertIsNone(rule.inactive_reason)
        self.assertEqual(getdate(rule.next_due_date), date(2026, 10, 23))

    def test_closed_project_stops_the_schedule(self):
        with self.freeze_time("2026-10-09 10:00:00"):
            rule = self.rule(month_day=12, start_date="2026-10-01")
        frappe.db.set_value("Project", self.project, "status", "Completed")
        self.assertIsNone(self.run_on("2026-10-12", rule))
        rule.reload()
        self.assertFalse(rule.is_active)
        self.assertIn("Completed", rule.inactive_reason)
        self.assertEqual(get_recurring_tasks_created(rule.name), [])
        # it can't be resumed while the project is closed
        with self.assertRaises(frappe.ValidationError):
            run_as_user(PM[0], lambda: api.set_recurring_task_active(rule.name, True))

    def test_resuming_skips_the_paused_dates(self):
        with self.freeze_time("2026-10-09 10:00:00"):
            rule = self.rule(month_day=1, start_date="2026-10-01")
            run_as_user(PM[0], lambda: api.set_recurring_task_active(rule.name, False))
        self.assertIsNone(self.run_on("2026-11-02", rule))
        with self.freeze_time("2026-12-05 10:00:00"):
            run_as_user(PM[0], lambda: api.set_recurring_task_active(rule.name, True))
        rule.reload()
        self.assertTrue(rule.is_active)
        self.assertIsNone(rule.inactive_reason)
        self.assertEqual(getdate(rule.last_occurrence), date(2026, 12, 1))
        self.assertIsNone(self.run_on("2026-12-05", rule))
        self.assertEqual(getdate(rule.next_due_date), date(2027, 1, 1))

    def test_deleting_keeps_the_tasks(self):
        with self.freeze_time("2026-10-09 10:00:00"):
            rule = self.rule(month_day=12, start_date="2026-10-01")
        task = self.run_on("2026-10-12", rule)
        run_as_user(PM[0], lambda: api.delete_recurring_task(rule.name))
        self.assertFalse(frappe.db.exists("HD Recurring Task", rule.name))
        self.assertTrue(frappe.db.exists("Task", task))
        self.assertIsNone(frappe.db.get_value("Task", task, "custom_recurring_task"))

    # --- validation and the API ---

    def test_assignee_must_be_on_the_team(self):
        with self.assertRaises(frappe.ValidationError):
            self.rule(assignee=OUTSIDER[0])

    def test_schedule_without_dates_is_refused(self):
        with self.freeze_time("2026-10-09 10:00:00"):
            with self.assertRaises(frappe.ValidationError):
                self.rule(
                    start_date="2026-01-01", ends="On date", end_date="2026-03-01"
                )

    def test_preview_lists_the_next_due_dates(self):
        values = {"frequency": "Monthly", "month_day": 1, "start_date": "2026-10-01"}
        with self.freeze_time("2026-10-09 10:00:00"):
            preview = run_as_user(
                PM[0], lambda: api.preview_recurring_task(self.project, values)
            )
        self.assertIsNone(preview["error"])
        self.assertEqual(
            preview["schedule"], "Monthly on the 1st · moved to the next working day"
        )
        self.assertEqual(len(preview["dates"]), 5)
        self.assertEqual(preview["dates"][0]["due"], "2026-11-02")
        broken = run_as_user(
            PM[0],
            lambda: api.preview_recurring_task(
                self.project, {**values, "ends": "After", "max_occurrences": 0}
            ),
        )
        self.assertTrue(broken["error"])

    def test_make_recurring_prefills_from_the_task(self):
        task = make_assigned_task(
            self.project,
            "Monthly backup check",
            MEMBER[0],
            PM[0],
            priority="High",
        )
        form = run_as_user(
            PM[0], lambda: api.get_recurring_task_form(self.project, task)
        )
        prefill = form["prefill"]
        self.assertEqual(prefill["subject"], "Monthly backup check")
        self.assertEqual(prefill["priority"], "High")
        self.assertEqual(prefill["assignee"], MEMBER[0])
        self.assertEqual(
            prefill["month_day"],
            getdate(frappe.db.get_value("Task", task, "exp_end_date")).day,
        )

    def test_permissions(self):
        values = {
            "subject": "Weekly status report",
            "frequency": "Weekly",
            "weekdays": ["Friday"],
            "start_date": "2026-10-09",
        }
        with self.freeze_time("2026-10-09 08:00:00"):
            saved = run_as_user(
                LEAD[0],
                lambda: api.save_recurring_task(
                    self.project, {**values, "assignee": LEAD[0]}
                ),
            )
            self.assertEqual(saved["weekdays"], ["Friday"])
            rule = frappe.get_doc("HD Recurring Task", saved["name"])
            rule.create_due_tasks()

        # a member sees the schedules, but not the lead's task, and changes nothing
        listing = run_as_user(MEMBER[0], lambda: api.get_recurring_tasks(self.project))
        self.assertFalse(listing["can_manage"])
        row = next(r for r in listing["rules"] if r["name"] == saved["name"])
        self.assertTrue(row["has_last_task"])
        self.assertIsNone(row["last_task"])
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                MEMBER[0], lambda: api.save_recurring_task(self.project, values)
            )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                MEMBER[0], lambda: api.set_recurring_task_active(saved["name"], False)
            )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(MEMBER[0], lambda: api.delete_recurring_task(saved["name"]))

        # the manager sees the task; someone off the project sees nothing
        listing = run_as_user(PM[0], lambda: api.get_recurring_tasks(self.project))
        self.assertTrue(listing["can_manage"])
        self.assertEqual(
            listing["rules"][0]["last_task"]["name"], rule.reload().last_task
        )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_recurring_tasks(self.project))
