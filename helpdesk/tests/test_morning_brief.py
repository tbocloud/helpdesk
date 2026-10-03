from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk import morning_brief
from helpdesk.test_utils import (
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    set_work_settings,
)

PM = ("pm.brief@brief.example", "Meera Das")
DEV = ("dev.brief@brief.example", "Kiran Babu")


class TestMorningBrief(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*DEV)
        set_work_settings(morning_brief=1, ai_task_estimates=0)
        self.project = make_project(
            "Brief Rollout", members=[(DEV[0], "Developer")], owner=PM[0]
        ).name

    def task(self, subject, due, days_old=0, **kwargs):
        task = make_task(self.project, subject, due, **kwargs)
        make_assignment("Task", task.name, DEV[0])
        if days_old:
            frappe.db.set_value(
                "Task",
                task.name,
                "creation",
                add_days(nowdate(), -days_old),
                update_modified=False,
            )
        return task.name

    def briefs(self):
        return frappe.get_all(
            "HD Notification",
            filters={
                "user_to": DEV[0],
                "reference_doctype": "User",
                "notification_type": "Reminder",
            },
            pluck="message",
        )

    def test_assignee_gets_one_brief_a_day(self):
        self.task("Bank reconciliation", add_days(nowdate(), -2), days_old=5)
        self.task("Tax report", nowdate(), days_old=5)
        self.task("Customer portal login", add_days(nowdate(), 8))

        with patch("frappe.sendmail") as sendmail, patch.object(
            morning_brief, "is_working_day", return_value=True
        ):
            morning_brief.send_morning_briefs()
            morning_brief.send_morning_briefs()

        briefs = self.briefs()
        self.assertEqual(len(briefs), 1)
        text = briefs[0]
        self.assertTrue(text.startswith("Morning brief for"))
        self.assertIn("Good morning Kiran", text)
        self.assertIn("Overdue, start here\n- Bank reconciliation", text)
        self.assertIn("Due today\n- Tax report", text)
        self.assertIn("New since yesterday\n- Customer portal login", text)
        subjects = [
            c.kwargs["subject"]
            for c in sendmail.call_args_list
            if c.kwargs.get("recipients") == DEV[0]
        ]
        self.assertEqual(subjects, [text.split("\n", 1)[0]])

    def test_unassigned_work_goes_to_the_project_lead(self):
        make_task(self.project, "Daily sales report change", nowdate())
        make_task(self.project, "Someday idea", add_days(nowdate(), 30))
        frappe.db.set_value("Project", self.project, "project_lead", DEV[0])

        with patch("frappe.sendmail"), patch.object(
            morning_brief, "is_working_day", return_value=True
        ):
            morning_brief.send_morning_briefs()

        text = self.briefs()[0]
        self.assertIn(
            "Not assigned to anyone yet: assign or do\n- Daily sales report change",
            text,
        )
        self.assertNotIn("Someday idea", text)

    def test_without_a_lead_the_project_manager_hears_about_it(self):
        make_task(self.project, "Opening stock upload", add_days(nowdate(), -1))

        with patch("frappe.sendmail"), patch.object(
            morning_brief, "is_working_day", return_value=True
        ):
            morning_brief.send_morning_briefs()

        pm_briefs = frappe.get_all(
            "HD Notification",
            filters={"user_to": PM[0], "reference_doctype": "User"},
            pluck="message",
        )
        self.assertTrue(any("Opening stock upload" in b for b in pm_briefs))
        self.assertEqual(self.briefs(), [])

    def test_nothing_to_report_means_no_brief(self):
        self.task("Phase 2 scoping", add_days(nowdate(), 20), days_old=5)
        with patch("frappe.sendmail"), patch.object(
            morning_brief, "is_working_day", return_value=True
        ):
            morning_brief.send_morning_briefs()
        self.assertEqual(self.briefs(), [])

    def test_weekly_off_and_switch_off(self):
        self.task("Bank reconciliation", add_days(nowdate(), -2), days_old=5)
        with patch("frappe.sendmail"), patch.object(
            morning_brief, "is_working_day", return_value=False
        ):
            morning_brief.send_morning_briefs()
        self.assertEqual(self.briefs(), [])

        set_work_settings(morning_brief=0)
        with patch("frappe.sendmail"), patch.object(
            morning_brief, "is_working_day", return_value=True
        ):
            morning_brief.send_morning_briefs()
        self.assertEqual(self.briefs(), [])

    def test_disabled_people_get_nothing(self):
        self.task("Bank reconciliation", add_days(nowdate(), -2), days_old=5)
        frappe.db.set_value("User", DEV[0], "enabled", 0)
        with patch("frappe.sendmail"), patch.object(
            morning_brief, "is_working_day", return_value=True
        ):
            morning_brief.send_morning_briefs()
        self.assertEqual(self.briefs(), [])
