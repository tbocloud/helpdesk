# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""One-shot AI jobs switch to the fallback provider when the main one fails."""

from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk import ai_engine
from helpdesk.ai_engine import _Usage, call_haiku

PRIMARY = "https://primary.example/v1"
FALLBACK = "https://fallback.example/v1"


def http_error(status: int) -> requests.HTTPError:
    response = MagicMock()
    response.status_code = status
    return requests.HTTPError(f"{status} from provider", response=response)


class TestAiEngineFallback(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        settings = frappe.get_single("HDS Hub Settings")
        settings.ai_provider = "OpenAI Compatible"
        settings.ai_base_url = PRIMARY
        settings.anthropic_api_key = "primary-key"
        settings.default_triage_model = "kimi-main"
        settings.fallback_provider = "OpenAI Compatible"
        settings.fallback_base_url = FALLBACK
        settings.fallback_api_key = "fallback-key"
        settings.fallback_triage_model = "gpt-fallback"
        settings.save(ignore_permissions=True)
        frappe.cache().delete_value("hds_ai_fallback_noted")

    def chat(self, primary_failure=None):
        calls = []

        def fake_chat(base_url, api_key, model, system_prompt, user_message, timeout=120):
            calls.append((base_url, api_key, model))
            if base_url == PRIMARY and primary_failure:
                raise primary_failure
            return '{"answer": "ok"}', _Usage(10, 5)

        return calls, patch.object(ai_engine, "_openai_chat", side_effect=fake_chat)

    def test_the_main_provider_answers_when_it_works(self):
        calls, patched = self.chat()
        with patched:
            result = call_haiku("system", "user")
        self.assertEqual(result["model"], "kimi-main")
        self.assertEqual(calls, [(PRIMARY, "primary-key", "kimi-main")])

    def test_a_rate_limit_or_refused_key_switches_to_the_fallback(self):
        for status in (401, 402, 429, 503):
            calls, patched = self.chat(primary_failure=http_error(status))
            with patched:
                result = call_haiku("system", "user", ticket_name=None)
            self.assertEqual(result["model"], "gpt-fallback", status)
            self.assertEqual(result["response"]["answer"], "ok")
            self.assertEqual([c[0] for c in calls], [PRIMARY, FALLBACK])

    def test_the_usage_log_names_the_model_that_answered(self):
        calls, patched = self.chat(primary_failure=http_error(429))
        with patched:
            call_haiku("system", "user")
        self.assertTrue(
            frappe.db.exists("HDS AI Usage Log", {"model": "gpt-fallback"}),
            "the fallback's usage must be logged under its own model",
        )

    def test_a_bad_request_is_not_retried_on_the_fallback(self):
        calls, patched = self.chat(primary_failure=http_error(400))
        with patched, self.assertRaises(requests.HTTPError):
            call_haiku("system", "user")
        self.assertEqual([c[0] for c in calls], [PRIMARY])

    def test_without_a_fallback_the_failure_is_raised(self):
        frappe.db.set_single_value("HDS Hub Settings", "fallback_provider", "")
        calls, patched = self.chat(primary_failure=http_error(429))
        with patched, self.assertRaises(requests.HTTPError):
            call_haiku("system", "user")
        self.assertEqual([c[0] for c in calls], [PRIMARY])
