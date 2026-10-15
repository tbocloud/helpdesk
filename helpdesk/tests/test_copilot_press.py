# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot's Press client: signed in as its own Press user, Press's refusals in Press's words."""

import json
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import press
from helpdesk.copilot.press import PressError
from helpdesk.test_utils import hold_commits, make_copilot_settings


def reply(status, body):
    response = MagicMock(status_code=status, text=json.dumps(body))
    response.json.return_value = body
    return response


class TestPressClient(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        make_copilot_settings(
            press_url="https://press.example.com/",
            press_api_key="copilot-key",
            press_api_secret="copilot-secret",
            press_team="team-1",
        )

    def test_calls_are_signed_as_copilots_press_user(self):
        with patch(
            "requests.post", return_value=reply(200, {"message": {"apps": []}})
        ) as sent:
            self.assertEqual(press.deploy_information("bench-1"), {"apps": []})
        url = sent.call_args.args[0]
        headers = sent.call_args.kwargs["headers"]
        self.assertEqual(
            url,
            "https://press.example.com/api/method/press.api.bench.deploy_information",
        )
        self.assertEqual(headers["Authorization"], "token copilot-key:copilot-secret")
        self.assertEqual(headers["X-Press-Team"], "team-1")
        self.assertEqual(sent.call_args.kwargs["json"], {"name": "bench-1"})

    def test_the_key_goes_only_to_an_https_address_and_never_follows_a_redirect(self):
        moved = reply(302, {})
        moved.headers = {"Location": "http://elsewhere.example.com/"}
        with patch("requests.post", return_value=moved) as sent:
            with self.assertRaises(PressError) as caught:
                press.deploy_information("bench-1")
        self.assertEqual(caught.exception.status, 302)
        self.assertIn("redirect", caught.exception.message)
        self.assertFalse(sent.call_args.kwargs["allow_redirects"])

        make_copilot_settings(press_url="http://press.example.com")
        with patch("requests.post") as sent:
            with self.assertRaises(PressError) as caught:
                press.deploy_information("bench-1")
        self.assertIn("https://", caught.exception.message)
        sent.assert_not_called()

    def test_a_refusal_carries_presss_own_message(self):
        body = {
            "exc_type": "ValidationError",
            "_server_messages": json.dumps(
                [
                    json.dumps(
                        {"message": "A deploy for this bench is already in progress."}
                    )
                ]
            ),
        }
        with patch("requests.post", return_value=reply(417, body)):
            with self.assertRaises(PressError) as caught:
                press.deploy_and_update("bench-1", [], [])
        self.assertEqual(caught.exception.status, 417)
        self.assertIn("already in progress", caught.exception.message)

    def test_deploy_never_skips_backups_or_the_failure_check(self):
        with patch(
            "requests.post", return_value=reply(200, {"message": "DC-1"})
        ) as sent:
            self.assertEqual(
                press.deploy_and_update(
                    "bench-1",
                    [{"app": "demo_app", "hash": "b" * 40}],
                    [{"name": "s1.example.com", "skip_backups": False}],
                ),
                "DC-1",
            )
        args = sent.call_args.kwargs["json"]
        self.assertTrue(args["run_will_fail_check"])
        self.assertFalse(args["trigger_patch_deploy"])

    def test_without_settings_it_says_so(self):
        make_copilot_settings(press_url="")
        self.assertFalse(press.configured())
        with self.assertRaises(PressError) as caught:
            press.deploy_information("bench-1")
        self.assertIn("not set up", caught.exception.message)
