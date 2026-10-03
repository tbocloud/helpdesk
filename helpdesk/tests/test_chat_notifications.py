from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk import chat_notifications, work_reminders
from helpdesk.test_utils import (
    TEST_TEAMS_CHANNEL_URL,
    TEST_TEAMS_DIRECT_URL,
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
TEAMS_DIRECT = TEST_TEAMS_DIRECT_URL
TEAMS_CHANNEL = TEST_TEAMS_CHANNEL_URL


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

        direct = [
            c
            for c in post.call_args_list
            if c.args[0] == TEAMS_DIRECT and c.kwargs["json"]["recipient"] == DEV[0]
        ]
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

        # other overdue tasks in the test database escalate too; count this one's
        posts = [
            c.kwargs["json"]["attachments"][0]["content"]["body"][0]["text"]
            for c in post.call_args_list
            if c.args[0] == TEAMS_CHANNEL
        ]
        mine = [text for text in posts if "Go-live checklist" in text]
        self.assertEqual(len(mine), 1)
        self.assertIn("Escalated, overdue since", mine[0])

    def test_failed_webhook_falls_back_to_email(self):
        enable_chat_notifications("Microsoft Teams")
        self.due_soon_task()
        with patch(
            "helpdesk.chat_notifications.requests.post",
            return_value=ok_response(status=500),
        ), patch("frappe.sendmail") as sendmail, patch.object(frappe, "log_error"):
            work_reminders.send_task_reminders()
        emailed = [c.kwargs["recipients"] for c in sendmail.call_args_list]
        self.assertIn(DEV[0], emailed)

    def test_channel_only_setup_emails_reminders_without_errors(self):
        # until the direct-message workflow exists, only escalations use Teams
        enable_chat_notifications(
            "Microsoft Teams",
            teams_direct_webhook="",
            teams_channel_webhook=TEAMS_CHANNEL,
        )
        self.due_soon_task()
        with patch(
            "helpdesk.chat_notifications.requests.post", return_value=ok_response()
        ) as post, patch("frappe.sendmail") as sendmail, patch.object(
            frappe, "log_error"
        ) as log_error:
            work_reminders.send_task_reminders()

        self.assertFalse([c for c in post.call_args_list if c.args[0] != TEAMS_CHANNEL])
        self.assertIn(DEV[0], [c.kwargs["recipients"] for c in sendmail.call_args_list])
        titles = [c.kwargs.get("title") for c in log_error.call_args_list]
        self.assertNotIn("Chat notification not sent", titles)

    def test_test_message_checks_only_the_channel_when_that_is_all(self):
        enable_chat_notifications(
            "Microsoft Teams",
            teams_direct_webhook="",
            teams_channel_webhook=TEAMS_CHANNEL,
        )
        with patch(
            "helpdesk.chat_notifications.requests.post", return_value=ok_response()
        ) as post:
            result = chat_notifications.send_test_message()

        self.assertEqual(result, {"direct": False, "channel": True})
        self.assertEqual([c.args[0] for c in post.call_args_list], [TEAMS_CHANNEL])

    def test_test_message_needs_at_least_one_workflow(self):
        enable_chat_notifications(
            "Microsoft Teams", teams_direct_webhook="", teams_channel_webhook=""
        )
        with patch("helpdesk.chat_notifications.requests.post") as post:
            with self.assertRaises(frappe.ValidationError):
                chat_notifications.send_test_message()
        self.assertFalse(post.called)


class TestOutsideLinks(ChatCase):
    def test_outside_links_are_kept_and_pages_get_the_helpdesk_prefix(self):
        pr = "https://github.com/tbocloud/helpdesk/pull/26"
        self.assertEqual(chat_notifications.helpdesk_url(pr), pr)
        self.assertTrue(
            chat_notifications.helpdesk_url("/tickets/7").endswith(
                "/helpdesk/tickets/7"
            )
        )
        self.assertTrue(
            chat_notifications.helpdesk_url(None).endswith("/helpdesk/my-work")
        )


class TestTeamsUrlCheck(ChatCase):
    def refused(self, url, field="teams_direct_webhook"):
        with self.assertRaises(frappe.ValidationError) as caught:
            enable_chat_notifications("Microsoft Teams", **{field: url})
        return str(caught.exception)

    def test_a_teams_message_link_is_refused(self):
        message = self.refused(
            "https://teams.microsoft.com/l/message/19:abc@unq.gbl.spaces/1790916392311"
        )
        self.assertIn("link to a Teams message", message)

    def test_a_cut_off_workflow_url_is_refused(self):
        cut = TEAMS_CHANNEL.split("&sig=")[0]
        self.assertIn("cut off", self.refused(cut, "teams_channel_webhook"))

    def test_other_sites_are_refused(self):
        self.assertIn(
            "Power Automate", self.refused("https://example.com/hook?sig=abc")
        )
        # a look-alike name, not a subdomain
        self.assertIn(
            "Power Automate",
            self.refused("https://notpowerplatform.com/hook?sp=x&sv=1.0&sig=abc"),
        )

    def test_spaces_alone_clear_the_url(self):
        enable_chat_notifications("Microsoft Teams", teams_channel_webhook="   ")

        doc = frappe.get_doc("HD Chat Settings")
        self.assertIsNone(
            doc.get_password("teams_channel_webhook", raise_exception=False)
        )

    def test_saving_again_keeps_the_stored_url(self):
        enable_chat_notifications(
            "Microsoft Teams", teams_channel_webhook=TEAMS_CHANNEL
        )
        doc = frappe.get_doc("HD Chat Settings")
        doc.email_when_unreachable = 0
        doc.save(ignore_permissions=True)  # the URLs are masked "*****" here

        self.assertEqual(doc.get_password("teams_direct_webhook"), TEAMS_DIRECT)

    def test_a_refusal_explains_itself(self):
        enable_chat_notifications("Microsoft Teams", teams_channel_webhook="")
        with patch(
            "helpdesk.chat_notifications.requests.post",
            return_value=ok_response(status=405),
        ):
            with self.assertRaises(frappe.ValidationError) as caught:
                chat_notifications.send_test_message()
        self.assertIn("http_405", str(caught.exception))
        self.assertIn("isn't a workflow's HTTP URL", str(caught.exception))


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
        with patch("helpdesk.chat_notifications.requests.post") as post:
            with self.assertRaises(frappe.PermissionError):
                run_as_user(DEV[0], chat_notifications.send_test_message)
        self.assertFalse(post.called)
