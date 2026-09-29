from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk import chat_notifications, work_reminders
from helpdesk.test_utils import (
    enable_chat_notifications,
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
    run_as_user,
)

PM = ("pm.chat@chat-notify.example", "Rekha Pillai")
DEV = ("dev.chat@chat-notify.example", "Arjun Menon")
TEAMS_DIRECT = "https://teams.example/direct"
TEAMS_CHANNEL = "https://teams.example/channel"


def ok_response(payload=None, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = payload or {"ok": True}
    return response


class ChatCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        self.addCleanup(
            frappe.clear_document_cache, "HD Chat Settings", "HD Chat Settings"
        )

        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*DEV)
        self.project = make_project(
            "Chat Rollout", members=[(DEV[0], "Developer")], owner=PM[0]
        ).name

    def due_soon_task(self):
        task = make_task(self.project, "Configure GST", add_days(nowdate(), 1))
        make_assignment("Task", task.name, DEV[0])
        return task.name


class TestTeams(ChatCase):
    def test_reminder_goes_to_teams_instead_of_email(self):
        enable_chat_notifications("Microsoft Teams")
        self.due_soon_task()
        with patch(
            "helpdesk.chat_notifications.requests.post", return_value=ok_response()
        ) as post, patch("frappe.sendmail") as sendmail:
            work_reminders.send_task_reminders()

        direct = [c for c in post.call_args_list if c.args[0] == TEAMS_DIRECT]
        self.assertEqual(len(direct), 1)
        body = direct[0].kwargs["json"]
        self.assertEqual(body["recipient"], DEV[0])
        card = body["attachments"][0]["content"]
        self.assertIn("Configure GST", card["body"][0]["text"])
        self.assertTrue(
            card["actions"][0]["url"].endswith(f"/helpdesk/projects/{self.project}")
        )
        self.assertFalse(sendmail.called)

    def test_escalations_are_posted_to_the_channel_once(self):
        enable_chat_notifications(
            "Microsoft Teams", teams_channel_webhook=TEAMS_CHANNEL
        )
        task = make_task(self.project, "Go-live checklist", add_days(nowdate(), -5))
        make_assignment("Task", task.name, DEV[0])
        with patch(
            "helpdesk.chat_notifications.requests.post", return_value=ok_response()
        ) as post:
            work_reminders.send_task_reminders()
            work_reminders.send_task_reminders()

        channel = [c for c in post.call_args_list if c.args[0] == TEAMS_CHANNEL]
        self.assertEqual(len(channel), 1)
        text = channel[0].kwargs["json"]["attachments"][0]["content"]["body"][0]["text"]
        self.assertIn("Escalated, overdue since", text)

    def test_failed_webhook_falls_back_to_email(self):
        enable_chat_notifications("Microsoft Teams")
        self.due_soon_task()
        with patch(
            "helpdesk.chat_notifications.requests.post",
            return_value=ok_response(status=500),
        ), patch("frappe.sendmail") as sendmail, patch.object(frappe, "log_error"):
            work_reminders.send_task_reminders()
        self.assertEqual(sendmail.call_args.kwargs["recipients"], DEV[0])


class TestSlack(ChatCase):
    def slack(self, found=True):
        def respond(url, json=None, **kwargs):
            if url.endswith("users.lookupByEmail"):
                if not found:
                    return ok_response({"ok": False, "error": "users_not_found"})
                return ok_response({"ok": True, "user": {"id": "U123"}})
            return ok_response()

        return patch("helpdesk.chat_notifications.requests.post", side_effect=respond)

    def test_reminder_is_a_slack_dm(self):
        enable_chat_notifications("Slack")
        self.due_soon_task()
        with self.slack() as post, patch("frappe.sendmail") as sendmail:
            work_reminders.send_task_reminders()

        messages = [
            c for c in post.call_args_list if c.args[0].endswith("chat.postMessage")
        ]
        self.assertEqual(messages[0].kwargs["json"]["channel"], "U123")
        self.assertEqual(
            messages[0].kwargs["headers"]["Authorization"], "Bearer xoxb-test-token"
        )
        self.assertFalse(sendmail.called)

    def test_people_not_in_slack_get_an_email_unless_turned_off(self):
        enable_chat_notifications("Slack")
        self.due_soon_task()
        with self.slack(found=False), patch("frappe.sendmail") as sendmail:
            work_reminders.send_task_reminders()
        self.assertTrue(sendmail.called)

        frappe.db.delete("HD Notification")
        enable_chat_notifications("Slack", email_when_unreachable=0)
        with self.slack(found=False), patch("frappe.sendmail") as sendmail:
            work_reminders.send_task_reminders()
        self.assertFalse(sendmail.called)

    def test_mentions_go_to_slack_too(self):
        enable_chat_notifications("Slack")
        ticket = make_ticket(subject="Invoice mismatch")
        with self.slack() as post, patch("frappe.sendmail") as sendmail:
            frappe.get_doc(
                {
                    "doctype": "HD Notification",
                    "notification_type": "Mention",
                    "user_from": PM[0],
                    "user_to": DEV[0],
                    "reference_ticket": ticket.name,
                    "message": "<p>Please check the <b>tax</b> row</p>",
                }
            ).insert(ignore_permissions=True)

        text = next(
            c.kwargs["json"]["text"]
            for c in post.call_args_list
            if c.args[0].endswith("chat.postMessage")
        )
        self.assertIn("mentioned you in ticket", text)
        self.assertIn("Please check the tax row", text)
        self.assertFalse(sendmail.called)

    def test_slack_control_characters_are_escaped(self):
        self.assertEqual(
            chat_notifications.slack_escape("<b> & <@U1>"),
            "&lt;b&gt; &amp; &lt;@U1&gt;",
        )

    def test_channel_name_instead_of_id_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            enable_chat_notifications("Slack", slack_escalation_channel="#general")


class TestSettings(ChatCase):
    def test_disabled_means_email_as_before(self):
        self.due_soon_task()
        with patch("helpdesk.chat_notifications.requests.post") as post, patch(
            "frappe.sendmail"
        ) as sendmail:
            work_reminders.send_task_reminders()
        self.assertFalse(post.called)
        self.assertTrue(sendmail.called)

    def test_only_system_managers_send_a_test(self):
        enable_chat_notifications("Microsoft Teams")
        with self.assertRaises(frappe.PermissionError):
            run_as_user(DEV[0], chat_notifications.send_test_message)
