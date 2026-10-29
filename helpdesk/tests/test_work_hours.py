from datetime import datetime, time
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime

from helpdesk.patches.v16_0_2 import clip_unlogged_time_sessions
from helpdesk.tasky import api as tasky
from helpdesk.tasky.time_sessions import (
    pause_timer,
    record_session,
    stop_timers_outside_work_hours,
)
from helpdesk.team_dashboard import logged_hours
from helpdesk.test_utils import (
    freeze_work_day,
    get_task_sessions,
    get_task_timesheets,
    hold_commits,
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    make_time_session,
    make_timesheet,
    run_as_user,
    set_work_settings,
    start_task_timer,
)
from helpdesk.work_hours import (
    clip_to_windows,
    in_work_window,
    lunch_break,
    max_hours,
    work_windows,
)

DEV = ("dev.hours@work-hours.example", "Anil Joseph")


def at(day, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(getdate(day), time(hour, minute))


class WorkHoursCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.today_at_11 = freeze_work_day(self, 11)
        self.today = getdate()
        self.yesterday = add_days(self.today, -1)
        # no lunch break, the default
        set_work_settings(lunch_start=None, lunch_end=None, max_hours_per_day=8)
        make_tasky_user(*DEV)
        self.project = make_project(
            "Work Hours - Website", members=[(DEV[0], "Developer")]
        ).name
        self.task = self.new_task("Build the pricing page")

    def new_task(self, subject: str) -> str:
        task = make_task(self.project, subject).name
        make_assignment("Task", task, DEV[0])
        frappe.db.set_value(
            "Task",
            task,
            "creation",
            add_days(now_datetime(), -5),
            update_modified=False,
        )
        return task

    def as_dev(self, fn):
        return run_as_user(DEV[0], fn)

    def complete(self, task=None, **kwargs):
        params = {"task": task or self.task, "notes": "Done"}
        params.update(kwargs)
        return self.as_dev(lambda: tasky.complete_task(**params))


class TestWorkWindows(WorkHoursCase):
    def test_a_normal_day_is_ten_to_six_and_holds_eight_hours(self):
        windows = work_windows(self.today)
        self.assertEqual(
            (windows[0][0], windows[-1][1]), (at(self.today, 10), at(self.today, 18))
        )
        self.assertEqual(max_hours(self.today), 8)

    def test_a_lunch_break_splits_the_day_and_takes_an_hour_off_the_cap(self):
        set_work_settings(lunch_start="13:00:00", lunch_end="14:00:00")
        self.assertEqual(
            work_windows(self.today),
            [
                (at(self.today, 10), at(self.today, 13)),
                (at(self.today, 14), at(self.today, 18)),
            ],
        )
        self.assertEqual(max_hours(self.today), 7)
        self.assertFalse(in_work_window(at(self.today, 13, 30)))

    def test_lunch_is_optional(self):
        self.assertIsNone(lunch_break())

    def test_the_daily_maximum_setting_lowers_the_cap(self):
        set_work_settings(max_hours_per_day=6)
        self.assertEqual(max_hours(self.today), 6)

    def test_a_holiday_holds_no_hours(self):
        with patch(
            "helpdesk.work_calendar.company_holidays", return_value={self.today}
        ):
            self.assertEqual(work_windows(self.today), [])
            self.assertEqual(max_hours(self.today), 0)
            self.assertEqual(
                clip_to_windows(at(self.today, 10), at(self.today, 12)), []
            )


class TestClipping(WorkHoursCase):
    def test_a_timer_left_on_overnight_keeps_only_work_time(self):
        kept = record_session(
            self.task, at(self.yesterday, 16), at(self.today, 10, 30), DEV[0]
        )

        self.assertEqual(kept, 2.5)
        self.assertEqual(
            [(r.started_at, r.ended_at) for r in get_task_sessions(self.task)],
            [
                (at(self.yesterday, 16), at(self.yesterday, 18)),
                (at(self.today, 10), at(self.today, 10, 30)),
            ],
        )

    def test_time_before_the_day_starts_is_dropped(self):
        record_session(self.task, at(self.today, 0), at(self.today, 10, 12), DEV[0])
        self.assertEqual([r.hours for r in get_task_sessions(self.task)], [0.2])

    def test_time_at_lunch_is_dropped(self):
        set_work_settings(lunch_start="13:00:00", lunch_end="14:00:00")

        kept = record_session(
            self.task, at(self.yesterday, 12), at(self.yesterday, 15), DEV[0]
        )

        self.assertEqual(kept, 2)
        self.assertEqual([r.hours for r in get_task_sessions(self.task)], [1.0, 1.0])

    def test_nothing_is_kept_on_a_day_off(self):
        with patch(
            "helpdesk.work_calendar.company_holidays", return_value={self.yesterday}
        ):
            kept = record_session(
                self.task, at(self.yesterday, 10), at(self.yesterday, 17), DEV[0]
            )
        self.assertEqual(kept, 0)
        self.assertEqual(get_task_sessions(self.task), [])

    def test_a_day_never_holds_more_than_the_cap(self):
        make_time_session(
            self.task, DEV[0], at(self.yesterday, 10), at(self.yesterday, 16)
        )

        kept = record_session(
            self.task, at(self.yesterday, 16), at(self.yesterday, 18), DEV[0]
        )

        self.assertEqual(kept, 2)
        other = self.new_task("Second task")
        # 8 hours already: a second stretch the same day is not kept
        self.assertEqual(
            record_session(
                other, at(self.yesterday, 10), at(self.yesterday, 12), DEV[0]
            ),
            0,
        )


class TestAutoStop(WorkHoursCase):
    def start(self, task, hours_ago):
        start_task_timer(task, hours_ago=hours_ago)
        frappe.db.set_value("Task", task, "custom_timer_user", DEV[0])

    def test_nothing_stops_while_a_window_is_open(self):
        self.start(self.task, 1)
        self.assertEqual(stop_timers_outside_work_hours(), [])
        self.assertTrue(frappe.db.get_value("Task", self.task, "custom_timer_start"))

    def test_the_timer_stops_when_the_day_ends_and_the_person_is_told(self):
        self.start(self.task, 1)
        with self.freeze_time(at(self.today, 18, 4)), patch(
            "helpdesk.work_reminders.notify_users"
        ) as notify:
            # started at 17:04 by the 18:04 clock: the stretch ended at 18:00
            frappe.db.set_value(
                "Task", self.task, "custom_timer_start", at(self.today, 15)
            )
            paused = stop_timers_outside_work_hours()

        self.assertEqual(paused, [self.task])
        task = frappe.db.get_value(
            "Task",
            self.task,
            ["status", "custom_timer_start", "custom_timer_elapsed"],
            as_dict=True,
        )
        # the task stays in progress with its time banked: 15:00 to 18:00
        self.assertEqual(task.status, "Working")
        self.assertIsNone(task.custom_timer_start)
        self.assertEqual(task.custom_timer_elapsed, 3)
        [row] = get_task_sessions(self.task)
        self.assertEqual(row.ended_at, at(self.today, 18))
        users, _doctype, name, subject = notify.call_args.args[:4]
        self.assertEqual((users, name), ([DEV[0]], self.task))
        self.assertIn("stopped at 6:00 pm", subject)

    def test_the_timer_stops_at_lunch_when_a_lunch_break_is_set(self):
        set_work_settings(lunch_start="13:00:00", lunch_end="14:00:00")
        self.start(self.task, 1)
        with self.freeze_time(at(self.today, 13, 5)), patch(
            "helpdesk.work_reminders.notify_users"
        ):
            frappe.db.set_value(
                "Task", self.task, "custom_timer_start", at(self.today, 12)
            )
            self.assertEqual(stop_timers_outside_work_hours(), [self.task])
        self.assertEqual(get_task_sessions(self.task)[0].hours, 1.0)


class TestOneTimerPerPerson(WorkHoursCase):
    def test_starting_a_second_timer_pauses_the_first(self):
        second = self.new_task("Write the pricing copy")
        self.as_dev(lambda: tasky.move_task(self.task, "Working"))
        frappe.db.set_value("Task", self.task, "custom_timer_start", at(self.today, 10))
        self.as_dev(lambda: tasky.move_task(second, "Working"))

        self.assertIsNone(frappe.db.get_value("Task", self.task, "custom_timer_start"))
        self.assertTrue(frappe.db.get_value("Task", second, "custom_timer_start"))
        [row] = get_task_sessions(self.task)
        self.assertEqual(row.user, DEV[0])
        self.assertAlmostEqual(row.hours, 1, delta=0.05)
        # the first stays in progress, paused
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Working")

        self.as_dev(lambda: tasky.start_timer(self.task))
        self.assertIsNone(frappe.db.get_value("Task", second, "custom_timer_start"))
        self.assertTrue(frappe.db.get_value("Task", self.task, "custom_timer_start"))
        self.assertEqual(len(get_task_sessions(second)), 1)

    def test_starting_outside_work_hours_is_refused(self):
        self.as_dev(lambda: tasky.move_task(self.task, "Working"))
        pause_timer(self.task)
        with self.freeze_time(at(self.today, 19)):
            with self.assertRaises(frappe.ValidationError):
                self.as_dev(lambda: tasky.start_timer(self.task))
        self.assertIsNone(frappe.db.get_value("Task", self.task, "custom_timer_start"))

    def test_moving_to_in_progress_outside_work_hours_leaves_the_timer_paused(self):
        with self.freeze_time(at(self.today, 19)):
            self.as_dev(lambda: tasky.move_task(self.task, "Working"))
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Working")
        self.assertIsNone(frappe.db.get_value("Task", self.task, "custom_timer_start"))


class TestDailyCap(WorkHoursCase):
    def test_hours_by_hand_cannot_pass_what_the_day_has_left(self):
        cap = max_hours(self.today)
        with self.assertRaises(frappe.ValidationError):
            self.complete(days=[{"date": str(self.today), "hours": cap + 0.5}])
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Open")

        self.complete(days=[{"date": str(self.today), "hours": cap - 2}])
        other = self.new_task("Second task")
        with self.assertRaises(frappe.ValidationError):
            self.complete(other, days=[{"date": str(self.today), "hours": 2.5}])
        self.complete(other, days=[{"date": str(self.today), "hours": 2}])

        sheets = [
            frappe.get_doc("Timesheet", n)
            for n in get_task_timesheets(self.task) + get_task_timesheets(other)
        ]
        self.assertEqual(sum(ts.total_hours for ts in sheets), cap)

    def test_the_dialog_says_how_much_is_left(self):
        make_time_session(
            self.new_task("Other"), DEV[0], at(self.today, 10), at(self.today, 13)
        )

        left = self.as_dev(lambda: tasky.get_completion_days(self.task))["left"]

        self.assertEqual(left[str(self.today)], max_hours(self.today) - 3)
        self.assertIn(str(self.yesterday), left)

    def test_hours_by_hand_are_for_today_or_yesterday_only(self):
        old = self.today
        while not max_hours(old) or old > add_days(self.today, -2):
            old = add_days(old, -1)

        with self.assertRaises(frappe.ValidationError):
            self.complete(days=[{"date": str(old), "hours": 2}])
        self.complete(days=[{"date": str(self.yesterday), "hours": 2}])

    def test_what_the_timer_recorded_on_an_older_day_can_be_logged(self):
        old = add_days(self.today, -2)
        while not max_hours(old):
            old = add_days(old, -1)
        make_time_session(self.task, DEV[0], at(old, 10), at(old, 14))

        result = self.complete(days=[{"date": str(old), "hours": 4}])

        self.assertEqual(result["hours_logged"], 4)

    def test_a_system_manager_can_back_date_with_a_reason(self):
        old = add_days(self.today, -2)
        while not max_hours(old):
            old = add_days(old, -1)
        frappe.set_user("Administrator")

        with self.assertRaises(frappe.ValidationError):
            tasky.complete_task(
                task=self.task, notes="Done", days=[{"date": str(old), "hours": 2}]
            )
        result = tasky.complete_task(
            task=self.task,
            notes="Done",
            days=[{"date": str(old), "hours": 2}],
            backdate_reason="Forgot to start the timer",
        )
        self.assertEqual(result["hours_logged"], 2)


class TestReports(WorkHoursCase):
    def test_a_day_in_the_scoreboard_never_counts_more_than_the_work_day(self):
        # two logs of 12 h and 8 h on one day: 20 hours can't have been worked
        make_timesheet(self.project, 12, at(self.yesterday, 10))
        make_timesheet(self.project, 8, at(self.yesterday, 10, 30))

        [row] = [
            r
            for r in logged_hours(self.yesterday, self.yesterday)
            if r["project"] == self.project
        ]

        self.assertAlmostEqual(row["hours"], max_hours(self.yesterday), places=2)

    def test_a_task_completed_today_does_not_dump_its_history_on_today(self):
        record_session(
            self.task, at(self.yesterday, 10), at(self.yesterday, 18), DEV[0]
        )
        frappe.db.set_value("Task", self.task, "custom_actual_hours", 8)
        self.complete(
            days=[
                {"date": str(self.yesterday), "hours": 8},
                {"date": str(self.today), "hours": 0.5},
            ]
        )

        today = [
            r
            for r in logged_hours(self.today, self.today)
            if r["project"] == self.project
        ]

        self.assertEqual(sum(r["hours"] for r in today), 0.5)


class TestClipPatch(WorkHoursCase):
    def test_saved_sessions_are_clipped_and_duplicates_removed_once(self):
        other = self.new_task("Second task")
        # the overnight timer, split at midnight the way it was saved, and a twin
        make_time_session(self.task, DEV[0], at(self.yesterday, 16), at(self.today, 0))
        make_time_session(self.task, DEV[0], at(self.today, 0), at(self.today, 10, 12))
        make_time_session(other, DEV[0], at(self.today, 9), at(self.today, 11))
        make_time_session(other, DEV[0], at(self.today, 9), at(self.today, 11))
        logged = make_time_session(
            self.task, DEV[0], at(self.yesterday, 1), at(self.yesterday, 9), logged=1
        )

        clip_unlogged_time_sessions.execute()
        first = {
            t: [(r.started_at, r.ended_at, r.hours) for r in get_task_sessions(t)]
            for t in (self.task, other)
        }
        clip_unlogged_time_sessions.execute()
        second = {
            t: [(r.started_at, r.ended_at, r.hours) for r in get_task_sessions(t)]
            for t in (self.task, other)
        }

        self.assertEqual(first, second)
        # yesterday 16:00 to 18:00 stays; the midnight to 10:12 piece keeps 12 minutes;
        # the logged session is left alone
        self.assertEqual(
            first[self.task],
            [
                (at(self.yesterday, 1), at(self.yesterday, 9), 8.0),
                (at(self.yesterday, 16), at(self.yesterday, 18), 2.0),
                (at(self.today, 10), at(self.today, 10, 12), 0.2),
            ],
        )
        self.assertEqual(first[other], [(at(self.today, 10), at(self.today, 11), 1.0)])
        self.assertEqual(
            frappe.db.get_value("HD Task Time Session", logged.name, "logged"), 1
        )
