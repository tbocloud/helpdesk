from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk.api.calendar import get_calendar
from helpdesk.test_utils import (
    make_assignment,
    make_meeting,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
)

ME = ("me.cal@calendar.example", "Divya Nair")
OTHER = ("other.cal@calendar.example", "Rohit Menon")
PM = ("pm.cal@calendar.example", "Leela George")


class TestCalendar(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        make_tasky_user(*ME)
        make_tasky_user(*OTHER)
        make_tasky_user(*PM, roles=("Project Manager",))
        self.ticket = str(make_ticket(subject="Calendar ticket").name)
        self.tomorrow = add_to_date(now_datetime(), days=1)
        self.start = nowdate()
        self.end = add_days(nowdate(), 6)

    def calendar(self, user, team=0, start=None, end=None):
        frappe.set_user(user[0])
        try:
            return get_calendar(start or self.start, end or self.end, team=team)
        finally:
            frappe.set_user("Administrator")

    def test_my_meetings_and_my_due_tasks(self):
        mine = make_meeting(
            "HD Ticket",
            self.ticket,
            self.tomorrow,
            ["x@customer.example"],
            scheduled_by=ME[0],
            subject="I scheduled it",
        ).name
        invited = make_meeting(
            "HD Ticket",
            self.ticket,
            self.tomorrow,
            [ME[0]],
            scheduled_by=OTHER[0],
            subject="I am invited",
        ).name
        others = make_meeting(
            "HD Ticket",
            self.ticket,
            self.tomorrow,
            ["y@customer.example"],
            scheduled_by=OTHER[0],
            subject="Not mine",
        ).name
        cancelled = make_meeting(
            "HD Ticket",
            self.ticket,
            self.tomorrow,
            [ME[0]],
            scheduled_by=ME[0],
            status="Cancelled",
        ).name
        project = make_project("Calendar Rollout", members=[(ME[0], "Developer")]).name
        due = make_task(project, "Configure payroll", add_days(nowdate(), 2)).name
        later = make_task(project, "Go live", add_days(nowdate(), 30)).name
        for task in (due, later):
            make_assignment("Task", task, ME[0])

        cal = self.calendar(ME)

        names = {m["name"] for m in cal["meetings"]}
        self.assertIn(mine, names)
        self.assertIn(invited, names)
        self.assertNotIn(others, names)
        self.assertNotIn(cancelled, names)
        tasks = {t["name"]: t for t in cal["tasks"]}
        self.assertIn(due, tasks)
        self.assertNotIn(later, tasks)
        self.assertEqual(tasks[due]["project_name"], "Calendar Rollout")

    def test_team_view_is_for_leads_and_managers(self):
        others = make_meeting(
            "HD Ticket",
            self.ticket,
            self.tomorrow,
            ["y@customer.example"],
            scheduled_by=OTHER[0],
        ).name

        with self.assertRaises(frappe.PermissionError):
            self.calendar(ME, team=1)

        cal = self.calendar(PM, team=1)
        self.assertTrue(cal["can_see_team"])
        self.assertIn(others, {m["name"] for m in cal["meetings"]})

    def test_range_is_checked(self):
        with self.assertRaises(frappe.ValidationError):
            self.calendar(ME, start=nowdate(), end=add_days(nowdate(), 100))
        with self.assertRaises(frappe.ValidationError):
            self.calendar(ME, start=nowdate(), end=add_days(nowdate(), -1))
