from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk import merge_bot
from helpdesk.test_utils import (
    GITHUB_TEST_SECRET,
    call_as_user,
    clear_merge_bot_debounce,
    enable_merge_bot_trigger,
    get_github_secret,
    hold_commits,
    make_github_delivery,
    make_tasky_user,
)

API = "helpdesk.api.github_settings."
GET = "helpdesk.api.github_settings.requests.get"
MANAGER = ("manager.github@github-settings.example", "Meera Pillai")
AGENT = ("agent.github@github-settings.example", "Arjun Menon")
SECRETS = {
    "webhook_secret": GITHUB_TEST_SECRET,
    "github_token": "ghp_sync_token",
    "merge_bot_token": "github_pat_actions_only",
}


def github_response(status=200, body=None, headers=None):
    return MagicMock(
        ok=status < 400,
        status_code=status,
        headers=headers or {},
        json=MagicMock(return_value=body or {}),
    )


class GitHubSettingsCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(clear_merge_bot_debounce)
        self.addCleanup(
            frappe.clear_document_cache, "HD GitHub Settings", "HD GitHub Settings"
        )
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_tasky_user(*AGENT)
        enable_merge_bot_trigger(merge_bot_token=SECRETS["merge_bot_token"])


class TestPermissions(GitHubSettingsCase):
    def test_agents_can_neither_read_change_nor_act(self):
        calls = [
            ("get_settings", {}),
            ("get_status", {}),
            ("save_settings", {"values": {"enabled": 0}}),
            ("test_token", {"field": "github_token"}),
            ("request_merge_bot_run", {}),
        ]
        with patch(GET) as get, patch.object(merge_bot.requests, "post") as post:
            for method, kwargs in calls:
                with self.assertRaises(frappe.PermissionError):
                    call_as_user(AGENT[0], API + method, **kwargs)
        self.assertFalse(get.called)
        self.assertFalse(post.called)
        self.assertTrue(frappe.db.get_single_value("HD GitHub Settings", "enabled"))

    def test_agent_managers_can_change_the_settings(self):
        call_as_user(MANAGER[0], API + "save_settings", values={"complete_on_merge": 0})
        self.assertEqual(
            frappe.db.get_single_value("HD GitHub Settings", "complete_on_merge"), 0
        )


class TestMaskedRead(GitHubSettingsCase):
    def test_secrets_come_back_masked_with_whether_they_are_set(self):
        result = call_as_user(MANAGER[0], API + "get_settings")

        self.assertEqual(
            result["secrets"],
            {
                "webhook_secret": {"set": True, "masked": "…"},
                "github_token": {"set": True, "masked": "ghp_…"},
                "merge_bot_token": {"set": True, "masked": "github_pat_…"},
            },
        )
        self.assertTrue(
            result["webhook_url"].endswith("/api/method/helpdesk.api.github.webhook")
        )
        self.assertEqual(result["settings"]["merge_bot_repo"], "tbocloud/ai-review")
        body = frappe.as_json(result)
        for secret in (*SECRETS.values(), "*****"):
            self.assertNotIn(secret, body)

    def test_status_shows_the_last_delivery_and_dispatch(self):
        make_github_delivery("check_suite", action="completed", status="Ignored")
        merge_bot.record("Dispatched (HTTP 204)")

        status = call_as_user(MANAGER[0], API + "get_status")

        self.assertEqual(status["last_result"], "Dispatched (HTTP 204)")
        self.assertEqual(status["last_outcome"], "Dispatched")
        self.assertTrue(status["last_dispatch"])
        delivery = status["last_delivery"]
        self.assertEqual(
            (delivery["event"], delivery["action"], delivery["status"]),
            ("check_suite", "completed", "Ignored"),
        )
        self.assertNotIn("payload", delivery)


class TestSecrets(GitHubSettingsCase):
    def save(self, **values):
        return call_as_user(MANAGER[0], API + "save_settings", values=values)

    def test_saving_without_a_secret_keeps_each(self):
        result = self.save(allowed_repos="tbocloud/*", github_token=None)
        for field, value in SECRETS.items():
            self.assertEqual(get_github_secret(field), value)
        for value in SECRETS.values():
            self.assertNotIn(value, frappe.as_json(result))

    def test_a_new_value_replaces_each(self):
        new = {field: f"github_pat_new_{field}" for field in SECRETS}
        self.save(**{field: f"  {value} " for field, value in new.items()})
        for field, value in new.items():
            self.assertEqual(get_github_secret(field), value)

    def test_an_empty_value_removes_each(self):
        # the webhook secret can only go while the sync is off
        result = self.save(enabled=0, **{field: "" for field in SECRETS})
        for field in SECRETS:
            self.assertIsNone(get_github_secret(field))
            self.assertFalse(result["secrets"][field]["set"])

    def test_the_webhook_secret_stays_while_the_sync_is_on(self):
        with self.assertRaises(frappe.ValidationError) as caught:
            self.save(webhook_secret="")
        self.assertTrue(str(caught.exception).startswith("Webhook Secret:"))
        self.assertEqual(get_github_secret("webhook_secret"), GITHUB_TEST_SECRET)


class TestValidation(GitHubSettingsCase):
    def assert_refused(self, label, **values):
        with self.assertRaises(frappe.ValidationError) as caught:
            call_as_user(MANAGER[0], API + "save_settings", values=values)
        # the page shows a message under the field it starts with
        self.assertTrue(str(caught.exception).startswith(f"{label}:"))

    def test_bad_values_are_refused_with_the_field_named(self):
        self.assert_refused("Allowed Repositories", allowed_repos="tbocloud")
        self.assert_refused("Merge bot repository", merge_bot_repo="ai-review")
        self.assert_refused(
            "Merge bot workflow", merge_bot_workflow="merge-bot.yml?x=1"
        )
        self.assertEqual(
            frappe.db.get_single_value("HD GitHub Settings", "allowed_repos"),
            "tbocloud/*",
        )


class TestTokenTest(GitHubSettingsCase):
    def check(self, field="merge_bot_token"):
        return call_as_user(MANAGER[0], API + "test_token", field=field)

    def test_a_working_token_shows_its_account_and_repository(self):
        user = github_response(
            body={"login": "tbo-merge-bot"},
            headers={"GitHub-Authentication-Token-Expiration": "2027-01-01 00:00:00 UTC"},
        )
        with patch(GET, side_effect=[user, github_response()]) as get:
            result = self.check()

        self.assertTrue(result["ok"])
        details = {d["label"]: d["value"] for d in result["details"]}
        self.assertEqual(details["Account"], "tbo-merge-bot")
        self.assertEqual(details["Can see"], "tbocloud/ai-review")
        self.assertIn("2027", details["Expires"])
        self.assertEqual(
            [c.args[0] for c in get.call_args_list],
            [
                "https://api.github.com/user",
                "https://api.github.com/repos/tbocloud/ai-review",
            ],
        )
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"],
            "Bearer github_pat_actions_only",
        )

    def test_a_classic_token_lists_its_scopes(self):
        user = github_response(
            body={"login": "octocat"}, headers={"X-OAuth-Scopes": "repo, workflow"}
        )
        # the merge bot has its own token, so the GitHub token isn't checked on its repo
        with patch(GET, return_value=user) as get:
            result = self.check("github_token")

        self.assertTrue(result["ok"])
        self.assertEqual(get.call_count, 1)
        self.assertIn(
            {"label": "Scopes", "value": "repo, workflow"}, result["details"]
        )

    def test_a_rejected_token_says_to_replace_it(self):
        with patch(GET, return_value=github_response(401)):
            result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("expired or revoked", result["message"])

    def test_no_access_to_the_repository_says_so(self):
        user = github_response(body={"login": "tbo-merge-bot"})
        with patch(GET, side_effect=[user, github_response(404)]):
            result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("can't see tbocloud/ai-review", result["message"])

    def test_a_network_error_shows_only_its_kind(self):
        error = requests.ConnectionError("token github_pat_actions_only")
        with patch(GET, side_effect=error):
            result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("ConnectionError", result["message"])
        self.assertNotIn("github_pat", result["message"])

    def test_an_unsaved_or_unknown_token_is_not_sent(self):
        enable_merge_bot_trigger(merge_bot_token=None)
        with patch(GET) as get:
            self.assertFalse(self.check()["ok"])
            with self.assertRaises(frappe.ValidationError):
                self.check("webhook_secret")
        self.assertFalse(get.called)


class TestRunNow(GitHubSettingsCase):
    def setUp(self):
        super().setUp()
        post = patch.object(
            merge_bot.requests, "post", return_value=MagicMock(ok=True, status_code=204)
        )
        self.post = post.start()
        self.addCleanup(post.stop)

    def run_now(self):
        return call_as_user(MANAGER[0], API + "request_merge_bot_run")

    def test_it_dispatches_and_shows_the_result(self):
        result = self.run_now()

        self.assertTrue(result["ok"])
        self.assertIn("Dispatched (HTTP 204)", result["message"])
        self.assertEqual(
            frappe.db.get_single_value("HD GitHub Settings", "merge_bot_last_outcome"),
            "Dispatched",
        )
        self.post.assert_called_once()
        self.assertIn("merge-bot.yml/dispatches", self.post.call_args.args[0])

    def test_the_debounce_is_respected(self):
        merge_bot.request_run()
        self.post.reset_mock()

        result = self.run_now()

        self.assertFalse(result["ok"])
        self.assertIn("less than 2 minutes ago", result["message"])
        self.post.assert_not_called()

    def test_a_refused_dispatch_says_so(self):
        self.post.return_value = MagicMock(ok=False, status_code=403)
        result = self.run_now()
        self.assertFalse(result["ok"])
        self.assertIn("Failed (HTTP 403)", result["message"])
        self.assertEqual(
            frappe.db.get_single_value("HD GitHub Settings", "merge_bot_last_outcome"),
            "Failed",
        )

    def test_nothing_is_sent_while_the_trigger_is_off(self):
        enable_merge_bot_trigger(trigger_merge_bot=0)
        result = self.run_now()
        self.assertFalse(result["ok"])
        self.post.assert_not_called()
