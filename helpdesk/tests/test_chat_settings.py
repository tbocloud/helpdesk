from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import (
    TEST_TEAMS_CHANNEL_URL,
    TEST_TEAMS_DIRECT_URL,
    call_as_user,
    enable_chat_notifications,
    get_chat_secret,
    hold_commits,
    make_error_log,
    make_tasky_user,
)

API = "helpdesk.api.chat_settings."
POST = "helpdesk.chat_notifications.requests.post"
MANAGER = ("manager.chat@chat-settings.example", "Divya Nair")
AGENT = ("agent.chat@chat-settings.example", "Rahul Das")
NEW_CHANNEL_URL = TEST_TEAMS_CHANNEL_URL.replace("sig=test-channel", "sig=new-channel")


class ChatSettingsCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Chat Settings", "HD Chat Settings"
        )
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_tasky_user(*AGENT)
        enable_chat_notifications(
            "Microsoft Teams", teams_channel_webhook=TEST_TEAMS_CHANNEL_URL
        )


class TestPermissions(ChatSettingsCase):
    def test_agents_can_neither_read_change_nor_test(self):
        calls = [
            ("get_settings", {}),
            ("save_settings", {"values": {"enabled": 0}}),
            ("send_test", {"target": "direct"}),
        ]
        with patch(POST) as post:
            for method, kwargs in calls:
                with self.assertRaises(frappe.PermissionError):
                    call_as_user(AGENT[0], API + method, **kwargs)
        self.assertFalse(post.called)
        self.assertTrue(frappe.db.get_single_value("HD Chat Settings", "enabled"))

    def test_agent_managers_can_change_the_settings(self):
        call_as_user(
            MANAGER[0], API + "save_settings", values={"email_when_unreachable": 0}
        )
        self.assertEqual(
            frappe.db.get_single_value("HD Chat Settings", "email_when_unreachable"),
            0,
        )


class TestMaskedRead(ChatSettingsCase):
    def test_secrets_come_back_masked_with_whether_they_are_set(self):
        result = call_as_user(MANAGER[0], API + "get_settings")

        secrets = result["secrets"]
        self.assertEqual(
            secrets["teams_direct_webhook"],
            {"set": True, "masked": "https://prod-01.westeurope.logic.azure.com/…"},
        )
        self.assertTrue(secrets["teams_channel_webhook"]["set"])
        self.assertEqual(secrets["slack_bot_token"], {"set": True, "masked": "xoxb-…"})
        self.assertEqual(result["settings"]["platform"], "Microsoft Teams")
        body = frappe.as_json(result)
        for secret in ("sig=", "xoxb-test-token", "*****"):
            self.assertNotIn(secret, body)

    def test_an_empty_secret_is_not_set(self):
        enable_chat_notifications("Microsoft Teams", teams_channel_webhook="")
        result = call_as_user(MANAGER[0], API + "get_settings")
        self.assertEqual(
            result["secrets"]["teams_channel_webhook"], {"set": False, "masked": ""}
        )

    def test_the_last_delivery_problem_is_its_title_and_time_only(self):
        make_error_log("Chat escalation not posted")
        make_error_log("Some other error")

        problem = call_as_user(MANAGER[0], API + "get_settings")["last_problem"]

        self.assertEqual(problem["title"], "Chat escalation not posted")
        self.assertEqual(set(problem), {"title", "at"})


class TestReplace(ChatSettingsCase):
    def test_saving_without_a_secret_keeps_it(self):
        result = call_as_user(
            MANAGER[0],
            API + "save_settings",
            values={"email_when_unreachable": 0, "teams_channel_webhook": None},
        )
        self.assertEqual(get_chat_secret("teams_direct_webhook"), TEST_TEAMS_DIRECT_URL)
        self.assertEqual(
            get_chat_secret("teams_channel_webhook"), TEST_TEAMS_CHANNEL_URL
        )
        self.assertNotIn("sig=", frappe.as_json(result))

    def test_a_new_value_replaces_it(self):
        call_as_user(
            MANAGER[0],
            API + "save_settings",
            values={"teams_channel_webhook": f"  {NEW_CHANNEL_URL} "},
        )
        self.assertEqual(get_chat_secret("teams_channel_webhook"), NEW_CHANNEL_URL)
        self.assertEqual(get_chat_secret("teams_direct_webhook"), TEST_TEAMS_DIRECT_URL)

    def test_an_empty_value_removes_it(self):
        result = call_as_user(
            MANAGER[0], API + "save_settings", values={"teams_channel_webhook": ""}
        )
        self.assertIsNone(get_chat_secret("teams_channel_webhook"))
        self.assertFalse(result["secrets"]["teams_channel_webhook"]["set"])

    def test_an_invalid_url_is_refused_and_the_saved_one_kept(self):
        link = (
            "https://teams.microsoft.com/l/message/19:abc@unq.gbl.spaces/1790916392311"
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            call_as_user(
                MANAGER[0],
                API + "save_settings",
                values={"teams_direct_webhook": link},
            )
        self.assertIn("Direct Message Workflow URL", str(caught.exception))
        self.assertIn("link to a Teams message", str(caught.exception))
        self.assertEqual(get_chat_secret("teams_direct_webhook"), TEST_TEAMS_DIRECT_URL)


class TestSendTest(ChatSettingsCase):
    def test_a_direct_test_reaches_the_caller(self):
        with patch(POST, return_value=MagicMock(status_code=202)) as post:
            result = call_as_user(MANAGER[0], API + "send_test", target="direct")

        self.assertTrue(result["ok"])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], TEST_TEAMS_DIRECT_URL)
        self.assertEqual(post.call_args.kwargs["json"]["recipient"], MANAGER[0])

    def test_a_channel_test_posts_to_the_channel_only(self):
        with patch(POST, return_value=MagicMock(status_code=202)) as post:
            result = call_as_user(MANAGER[0], API + "send_test", target="channel")

        self.assertTrue(result["ok"])
        self.assertEqual(
            [c.args[0] for c in post.call_args_list], [TEST_TEAMS_CHANNEL_URL]
        )
        self.assertNotIn("recipient", post.call_args.kwargs["json"])

    def test_a_refusal_gives_the_error_and_what_to_do(self):
        with patch(POST, return_value=MagicMock(status_code=404)):
            result = call_as_user(MANAGER[0], API + "send_test", target="direct")

        self.assertFalse(result["ok"])
        self.assertIn("http_404", result["message"])
        self.assertIn("the flow was deleted", result["message"])

    def test_a_network_error_never_shows_the_url(self):
        error = requests.ConnectionError(
            f"Max retries exceeded with url: {TEST_TEAMS_DIRECT_URL}"
        )
        with patch(POST, side_effect=error):
            result = call_as_user(MANAGER[0], API + "send_test", target="direct")

        self.assertFalse(result["ok"])
        self.assertIn("ConnectionError", result["message"])
        self.assertNotIn("sig=", result["message"])

    def test_a_missing_workflow_says_to_add_it(self):
        enable_chat_notifications("Microsoft Teams", teams_channel_webhook="")
        with patch(POST) as post:
            result = call_as_user(MANAGER[0], API + "send_test", target="channel")

        self.assertFalse(post.called)
        self.assertFalse(result["ok"])
        self.assertIn("Escalation Channel Workflow URL", result["message"])

    def test_an_unknown_target_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            call_as_user(MANAGER[0], API + "send_test", target="everyone")
