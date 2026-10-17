from datetime import datetime, time

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, get_datetime, getdate, now_datetime

from helpdesk.tasky import api as tasky
from helpdesk.tasky.time_sessions import (
    LONG_DAY_HOURS,
    SESSION,
    record_session,
    split_by_day,
)
from helpdesk.test_utils import (
    get_task_timesheets,
    hold_commits,
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    run_as_user,
    start_task_timer,
)

DEV = ("dev.sessions@timer-sessions.example", "Meera Joseph")


def at(day, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(getdate(day), time(hour, minute))


class TestTimerSessions(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*DEV)
        self.project = make_project(
            "Timer Sessions - Website", members=[(DEV[0], "Developer")]
        ).name
        self.task = make_task(self.project, "Build the pricing page").name
        make_assignment("Task", self.task, DEV[0])
        self.today = getdate()
        self.yesterday = add_days(self.today, -1)
        # made a few days ago, so yesterday's hours are allowed
        frappe.db.set_value(
            "Task",
            self.task,
            "creation",
            add_days(now_datetime(), -3),
            update_modified=False,
        )

    def sessions(self, logged=None):
        filters = {"task": self.task}
        if logged is not None:
            filters["logged"] = logged
        return frappe.get_all(
            SESSION,
            filters=filters,
            fields=["started_at", "ended_at", "hours", "user", "logged", "timesheet"],
            order_by="started_at asc",
        )

    def run_timer_today(self, hours: float) -> float:
        """Start the task's timer `hours` ago, but never before midnight, so the stretch
        stays on today whenever the test runs; returns the hours it has run."""
        hours = min(
            hours, (now_datetime() - at(self.today, 0)).total_seconds() / 3600 * 0.9
        )
        start_task_timer(self.task, hours_ago=hours)
        return hours

    def as_dev(self, fn):
        return run_as_user(DEV[0], fn)

    def complete(self, **kwargs):
        params = {"task": self.task, "notes": "Pricing page live"}
        params.update(kwargs)
        return self.as_dev(lambda: tasky.complete_task(**params))

    def test_a_stretch_past_midnight_is_split_by_day(self):
        pieces = split_by_day(at(self.yesterday, 22), at(self.today, 1, 30))
        self.assertEqual(
            pieces,
            [
                (at(self.yesterday, 22), at(self.today, 0)),
                (at(self.today, 0), at(self.today, 1, 30)),
            ],
        )
        self.assertEqual(split_by_day(at(self.today, 9), at(self.today, 9)), [])

    def test_pausing_the_timer_saves_the_stretch_by_day(self):
        start_task_timer(self.task, hours_ago=1)
        frappe.db.set_value(
            "Task",
            self.task,
            "custom_timer_start",
            add_to_date(at(self.today, 0), hours=-2),
        )

        self.as_dev(lambda: tasky.stop_timer(self.task))

        rows = self.sessions()
        self.assertEqual(
            [getdate(r.started_at) for r in rows], [self.yesterday, self.today]
        )
        self.assertEqual(rows[0].hours, 2.0)
        self.assertEqual({r.user for r in rows}, {DEV[0]})

    def test_putting_it_on_hold_saves_the_running_stretch(self):
        ran = self.run_timer_today(1)
        task = frappe.get_doc("Task", self.task)
        task.status = "On Hold"
        task.hold_reason = "Waiting on customer"
        task.save(ignore_permissions=True)

        [row] = self.sessions()
        self.assertAlmostEqual(row.hours, ran, places=1)

    def test_completion_offers_each_day_the_timer_ran(self):
        record_session(
            self.task, at(self.yesterday, 14), at(self.yesterday, 18), DEV[0]
        )
        ran = self.run_timer_today(0.5)

        days = self.as_dev(lambda: tasky.get_completion_days(self.task))["days"]

        self.assertEqual(
            [d["date"] for d in days], [str(self.yesterday), str(self.today)]
        )
        self.assertEqual(days[0]["hours"], 4.0)
        self.assertEqual(get_datetime(days[0]["from_time"]), at(self.yesterday, 14))
        self.assertAlmostEqual(days[1]["hours"], ran, places=1)
        self.assertFalse(days[0]["long"])

    def test_time_banked_before_sessions_were_kept_goes_on_today(self):
        frappe.db.set_value("Task", self.task, "custom_timer_elapsed", 3)

        [day] = self.as_dev(lambda: tasky.get_completion_days(self.task))["days"]

        self.assertEqual(day["date"], str(self.today))
        self.assertEqual(day["hours"], 3.0)
        self.assertIsNone(day["from_time"])

    def test_a_timer_left_running_overnight_is_flagged(self):
        record_session(
            self.task, at(self.yesterday, 8), at(self.yesterday, 23, 30), DEV[0]
        )

        [day] = self.as_dev(lambda: tasky.get_completion_days(self.task))["days"]

        self.assertGreater(day["hours"], LONG_DAY_HOURS)
        self.assertTrue(day["long"])

    def test_each_day_gets_its_own_timesheet(self):
        record_session(
            self.task, at(self.yesterday, 14), at(self.yesterday, 18), DEV[0]
        )

        result = self.complete(
            days=[
                {"date": str(self.yesterday), "hours": 4},
                {"date": str(self.today), "hours": 0.5},
            ]
        )

        self.assertEqual(result["hours_logged"], 4.5)
        self.assertEqual(
            sorted(result["timesheets"]), sorted(get_task_timesheets(self.task))
        )
        sheets = sorted(
            (frappe.get_doc("Timesheet", n) for n in result["timesheets"]),
            key=lambda ts: ts.time_logs[0].from_time,
        )
        # one timesheet per day, each holding only that day's hours
        self.assertEqual(
            [(len(ts.time_logs), ts.total_hours) for ts in sheets], [(1, 4), (1, 0.5)]
        )
        self.assertEqual(
            [getdate(ts.time_logs[0].from_time) for ts in sheets],
            [self.yesterday, self.today],
        )
        # yesterday's starts when the timer did
        self.assertEqual(
            get_datetime(sheets[0].time_logs[0].from_time), at(self.yesterday, 14)
        )
        self.assertEqual(result["timesheet_status"], "Submitted")
        self.assertEqual(
            frappe.db.get_value("Task", self.task, "custom_actual_hours"), 4.5
        )
        # yesterday's stretch is in yesterday's timesheet; nothing is offered again
        self.assertEqual(
            {(r.logged, r.timesheet) for r in self.sessions()}, {(1, sheets[0].name)}
        )
        self.assertEqual(
            self.as_dev(lambda: tasky.get_completion_days(self.task))["days"], []
        )

    def test_a_timer_day_taken_out_is_not_offered_again(self):
        record_session(
            self.task, at(self.yesterday, 14), at(self.yesterday, 18), DEV[0]
        )

        self.complete(days=[{"date": str(self.today), "hours": 1}])

        self.assertEqual({r.logged for r in self.sessions()}, {1})
        self.assertEqual(
            self.as_dev(lambda: tasky.get_completion_days(self.task))["days"], []
        )

    def test_a_past_day_without_a_timer_starts_in_the_morning(self):
        self.complete(days=[{"date": str(self.yesterday), "hours": 2}])

        [name] = get_task_timesheets(self.task)
        [log] = frappe.get_doc("Timesheet", name).time_logs
        self.assertEqual(get_datetime(log.from_time), at(self.yesterday, 9))

    def test_hours_without_days_still_go_on_today(self):
        self.complete(hours_worked=2)

        [name] = get_task_timesheets(self.task)
        [log] = frappe.get_doc("Timesheet", name).time_logs
        self.assertEqual(log.hours, 2)

    def test_days_are_checked(self):
        created = getdate(frappe.db.get_value("Task", self.task, "creation"))
        cases = {
            "future": [{"date": str(add_days(self.today, 1)), "hours": 1}],
            "before the task": [{"date": str(add_days(created, -1)), "hours": 1}],
            "twice": [
                {"date": str(self.today), "hours": 1},
                {"date": str(self.today), "hours": 2},
            ],
            "over a day": [{"date": str(self.today), "hours": 25}],
            "no hours": [{"date": str(self.today), "hours": 0}],
            "no date": [{"date": "", "hours": 1}],
        }
        for label, days in cases.items():
            with self.assertRaises(frappe.ValidationError, msg=label):
                self.complete(days=days)
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Open")
        self.assertEqual(get_task_timesheets(self.task), [])

    def test_the_dialog_is_told_the_sites_today(self):
        result = self.as_dev(lambda: tasky.get_completion_days(self.task))
        self.assertEqual(result["today"], str(self.today))

    def test_a_stretch_ended_by_cancelling_is_kept_but_not_offered(self):
        self.run_timer_today(1)

        self.as_dev(lambda: tasky.move_task(self.task, "Cancelled"))

        self.assertEqual({r.logged for r in self.sessions()}, {1})
        self.assertEqual(
            self.as_dev(lambda: tasky.get_completion_days(self.task))["days"], []
        )

    def test_a_refused_github_move_saves_no_stretch(self):
        from helpdesk.github_sync import PullRequestLink

        blocker = make_task(self.project, "Agree the prices").name
        self.run_timer_today(1)
        frappe.db.set_value("Task", self.task, "depends_on_task", blocker)
        link = PullRequestLink(
            frappe._dict(task=self.task, number=7, url="", state="open")
        )

        link.stop_timer()
        moved = link.move_task("Pending Review")

        self.assertFalse(moved)
        self.assertEqual(self.sessions(), [])
        # the timer is still running, so its whole stretch is saved once, later
        self.assertTrue(frappe.db.get_value("Task", self.task, "custom_timer_start"))

    def test_a_days_log_stays_within_that_day(self):
        record_session(
            self.task, at(self.yesterday, 22), at(self.yesterday, 23, 30), DEV[0]
        )

        result = self.complete(days=[{"date": str(self.yesterday), "hours": 3}])

        [log] = frappe.get_doc("Timesheet", result["timesheet"]).time_logs
        # started earlier than the timer did, so the 3 hours end by midnight
        self.assertEqual(get_datetime(log.from_time), at(self.yesterday, 21))
        self.assertLessEqual(get_datetime(log.to_time), at(self.today, 0))

    def test_a_malformed_days_payload_gets_a_message(self):
        for days in ('{"date": "2026-10-15", "hours": 2}', "[1, 2]", '["x"]'):
            with self.assertRaises(frappe.ValidationError, msg=days):
                self.complete(days=days)
        self.assertEqual(get_task_timesheets(self.task), [])
