# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The GitHub calls of Copilot fixes: errors are raised, merges pin the commit, checks decide as the org bot does."""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import github
from helpdesk.copilot.github import GitHubError


def response(status, data=None):
    reply = MagicMock()
    reply.status_code = status
    reply.json.return_value = data if data is not None else {}
    reply.content = b"{}" if data is not None else b""
    reply.text = str(data)
    return reply


class TestRequests(FrappeTestCase):
    def setUp(self):
        patcher = patch.object(github, "token", return_value="t")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_refusal_is_an_error_with_githubs_status_and_message(self):
        with patch(
            "requests.request",
            return_value=response(405, {"message": "Pull Request is not mergeable"}),
        ):
            with self.assertRaises(GitHubError) as caught:
                github.get_pull("o/r", 1)
        self.assertEqual(
            (caught.exception.status, caught.exception.message),
            (405, "Pull Request is not mergeable"),
        )

    def test_merge_pins_the_commit_and_uses_the_repositorys_method(self):
        calls = []

        def fake(method, path, body=None, params=None):
            calls.append((method, path, body))
            if path == "/repos/o/r":
                return {"allow_merge_commit": False, "allow_squash_merge": True}
            return {"sha": "m1"}

        with patch.object(github, "request", side_effect=fake):
            self.assertEqual(github.merge("o/r", 5, "a" * 40, "Fix it"), "m1")
        self.assertEqual(
            calls[-1],
            (
                "PUT",
                "/repos/o/r/pulls/5/merge",
                {"merge_method": "squash", "sha": "a" * 40, "commit_title": "Fix it"},
            ),
        )

    def test_checks_follow_the_org_merge_bots_rule(self):
        def fake(runs, status):
            def answer(method, path, body=None, params=None):
                return {"check_runs": runs} if path.endswith("check-runs") else status

            return answer

        none = {"state": "pending", "total_count": 0}
        cases = [
            (
                [
                    {"name": "a", "status": "completed", "conclusion": "success"},
                    {"name": "b", "status": "completed", "conclusion": "skipped"},
                ],
                none,
                True,
            ),
            ([{"name": "a", "status": "in_progress", "conclusion": None}], none, False),
            (
                [{"name": "a", "status": "completed", "conclusion": "failure"}],
                none,
                False,
            ),
            ([], {"state": "success", "total_count": 1}, True),
            ([], {"state": "failure", "total_count": 1}, False),
        ]
        for runs, status, green in cases:
            with patch.object(github, "request", side_effect=fake(runs, status)):
                self.assertEqual(
                    github.checks("o/r", "s")["green"], green, (runs, status)
                )

    def test_removing_a_missing_label_is_fine(self):
        with patch.object(
            github, "request", side_effect=GitHubError(404, "Label does not exist")
        ):
            github.remove_label("o/r", 1, "no-auto-merge")


class TestToken(FrappeTestCase):
    def test_no_token_is_said_plainly(self):
        with patch("frappe.utils.password.get_decrypted_password", return_value=None):
            with self.assertRaises(GitHubError) as caught:
                github.token()
        self.assertIn("No GitHub token", caught.exception.message)
