from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk import merge_bot
from helpdesk.test_utils import (
    clear_merge_bot_debounce,
    enable_merge_bot_trigger,
    hold_commits,
    make_github_payload,
    send_github_webhook,
)

DISPATCH_URL = (
    "https://api.github.com/repos/tbocloud/ai-review/actions/workflows/"
    "merge-bot.yml/dispatches"
)


class TestMergeBotTrigger(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(clear_merge_bot_debounce)
        enable_merge_bot_trigger()
        post = patch.object(
            merge_bot.requests,
            "post",
            return_value=MagicMock(ok=True, status_code=204),
        )
        self.post = post.start()
        self.addCleanup(post.stop)

    def review(self, reviewer="coderabbitai[bot]", state="approved"):
        return send_github_webhook(
            "pull_request_review",
            make_github_payload(
                "pull_request_review",
                "submitted",
                reviewer=reviewer,
                review_state=state,
            ),
        )

    def settings(self, field):
        return frappe.db.get_single_value("HD GitHub Settings", field)

    def test_coderabbit_approval_dispatches_the_bot_once(self):
        result = self.review()

        self.assertTrue(result.get("ok"))
        self.post.assert_called_once()
        args, kwargs = self.post.call_args
        self.assertEqual(args[0], DISPATCH_URL)
        self.assertEqual(
            kwargs["json"], {"ref": "main", "inputs": {"dry_run": "false"}}
        )
        self.assertEqual(
            self.settings("merge_bot_last_result"), "Dispatched (HTTP 204)"
        )

    def test_other_reviews_do_not_dispatch(self):
        self.review(reviewer="lead-octocat")
        self.review(state="changes_requested")
        self.post.assert_not_called()

    def test_successful_ci_on_a_pr_dispatches(self):
        send_github_webhook(
            "check_suite", make_github_payload("check_suite", "completed")
        )
        self.post.assert_called_once()

    def test_ci_without_a_pr_or_failing_does_not_dispatch(self):
        send_github_webhook(
            "workflow_run",
            make_github_payload("workflow_run", "completed", pull_requests=[]),
        )
        send_github_webhook(
            "workflow_run",
            make_github_payload("workflow_run", "completed", conclusion="failure"),
        )
        # the bot's own repository never triggers the next run
        send_github_webhook(
            "workflow_run",
            make_github_payload("workflow_run", "completed", repo="tbocloud/ai-review"),
        )
        self.post.assert_not_called()

    def test_many_events_within_the_window_dispatch_once(self):
        for _ in range(5):
            self.review()
        self.post.assert_called_once()

    def test_trigger_switched_off_does_nothing(self):
        enable_merge_bot_trigger(trigger_merge_bot=0)
        self.review()
        merge_bot.scheduled_run()
        self.post.assert_not_called()

    def test_scheduler_fallback_dispatches_when_on(self):
        merge_bot.scheduled_run()
        merge_bot.scheduled_run()
        self.post.assert_called_once()

    def test_github_token_is_the_fallback(self):
        merge_bot.scheduled_run()
        headers = self.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer ghp_sync_token")

    def test_merge_bot_token_wins_over_the_github_token(self):
        enable_merge_bot_trigger(merge_bot_token="github_pat_actions_only")
        merge_bot.scheduled_run()
        headers = self.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer github_pat_actions_only")

    def test_failed_dispatch_is_logged_not_raised(self):
        self.post.return_value = MagicMock(ok=False, status_code=403)

        result = self.review()

        self.assertTrue(result.get("ok"))
        self.assertEqual(self.settings("merge_bot_last_result"), "Failed (HTTP 403)")
        self.assertTrue(
            frappe.db.exists("Error Log", {"method": "Merge bot dispatch failed"})
        )

    def test_unreachable_github_is_logged_not_raised(self):
        self.post.side_effect = requests.ConnectionError("down")
        result = self.review()
        self.assertTrue(result.get("ok"))
        self.assertEqual(
            self.settings("merge_bot_last_result"), "Failed: ConnectionError"
        )

    def test_an_error_in_the_trigger_never_fails_the_webhook(self):
        with patch.object(merge_bot, "request_run", side_effect=RuntimeError("boom")):
            result = self.review()
        self.assertTrue(result.get("ok"))
        self.assertTrue(
            frappe.db.exists(
                "Error Log", {"method": "Couldn't request a merge bot run"}
            )
        )

    def test_merge_bot_settings_are_checked(self):
        doc = frappe.get_single("HD GitHub Settings")
        doc.merge_bot_repo = "tbocloud/ai-review/../x"
        self.assertRaises(frappe.ValidationError, doc.save)
        doc.reload()
        doc.merge_bot_workflow = "merge-bot.yml?x=1"
        self.assertRaises(frappe.ValidationError, doc.save)
        doc.reload()
        doc.merge_bot_repo = ""
        doc.save()
        self.assertEqual(doc.merge_bot_repo, "tbocloud/ai-review")
