"""Phase 22: going live from a task, and the deploy notices (copilot/go_live.py)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import deploy, go_live
from helpdesk.test_utils import (
    hold_commits,
    make_copilot_settings,
    make_project,
    make_task,
    make_tasky_user,
)

DEV = ("dev.golive@people.example", "Gita Dev")
APPROVER = ("approver.golive@people.example", "Hari Approver")
DEVOPS = ("devops.golive@people.example", "Ishaan Devops")
SENIOR = ("senior.golive@people.example", "Jaya Senior")


class TestGoLive(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        for person in (DEV, APPROVER, DEVOPS, SENIOR):
            make_tasky_user(*person)
        make_copilot_settings(
            deploy_notice_people=[{"user": DEVOPS[0]}, {"user": SENIOR[0]}]
        )
        project = make_project("Go live project")
        self.task = make_task(project.name, "Fix the stock report").name

    def release(self, status="Waiting for approval", **values):
        return frappe.get_doc(
            {
                "doctype": "HDS Deploy Request",
                "source": "Pull request",
                "repository": "tbocloud/demo-alpha-app",
                "branch": "main",
                "release_group": "bench-0015",
                "task": self.task,
                "status": status,
                "ci_status": "Passed",
                "assigned_to": APPROVER[0],
                **values,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True)

    def test_a_task_without_a_release_says_one_comes_after_the_merge(self):
        result = go_live.task_release(self.task)
        self.assertEqual(result["releases"], [])
        self.assertIn("within ten minutes of the merge", result["next"])

    def test_where_the_tasks_change_stands(self):
        self.release(status="Waiting for CI", ci_status="Pending")
        result = go_live.task_release(self.task)
        self.assertEqual(result["releases"][0]["status"], "Waiting for CI")
        self.assertIn("CI has not passed yet", result["next"])

    def test_asking_to_go_live_brings_the_approver_the_card_again(self):
        release = self.release()
        with patch("helpdesk.copilot.releases.announce") as announce, patch(
            "helpdesk.work_reminders.notify_users"
        ) as notify:
            result = go_live.ask_go_live(self.task, "now", "The customer is waiting")
        self.assertTrue(result["asked"])
        announce.assert_called_once()
        self.assertEqual(announce.call_args.args[1], APPROVER[0])
        self.assertIn("go live now", notify.call_args.args[3])
        self.assertIn("nobody approves their own change", result["next"])
        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "HDS Deploy Request",
                "reference_name": release.name,
            },
            pluck="content",
        )
        self.assertTrue(any("The customer is waiting" in c for c in comments))

    def test_a_release_not_waiting_for_approval_is_not_asked_again(self):
        self.release(status="Scheduled", when="Tonight")
        with patch("helpdesk.copilot.releases.announce") as announce:
            result = go_live.ask_go_live(self.task, "tonight")
        self.assertFalse(result["asked"])
        announce.assert_not_called()
        self.assertIn("Press deploys it tonight", result["next"])

    def test_only_tonight_or_now(self):
        self.release()
        with self.assertRaises(frappe.ValidationError):
            go_live.ask_go_live(self.task, "next week")

    def test_deploy_notices_reach_the_people_set_in_settings(self):
        release = self.release(status="Deploying", decided_by=APPROVER[0])
        with patch("helpdesk.copilot.assistant.send", return_value="Web") as send:
            go_live.alert_deploy(release.name, "started", "Press DC-1")
        told = [c.args[0] for c in send.call_args_list]
        self.assertEqual(sorted(told), sorted([DEVOPS[0], SENIOR[0]]))
        card = send.call_args.args[1]
        self.assertIn(
            "Press is deploying tbocloud/demo-alpha-app main on bench-0015",
            card["title"],
        )
        self.assertIn("Approved by Hari Approver", card["lines"])

    def test_nobody_set_means_no_notice(self):
        make_copilot_settings(deploy_notice_people=[])
        release = self.release(status="Deploying")
        with patch("helpdesk.copilot.assistant.send") as send:
            go_live.alert_deploy(release.name, "live")
        send.assert_not_called()

    def test_a_failed_deploy_tells_them(self):
        release = self.release(status="Deploying")
        with patch("helpdesk.copilot.go_live.alert_deploy") as alert, patch(
            "helpdesk.copilot.releases.failed"
        ), patch.object(deploy, "_release_lock"):
            deploy.fail(release, "Press: the build failed")
        alert.assert_called_once_with(release.name, "failed", "Press: the build failed")
