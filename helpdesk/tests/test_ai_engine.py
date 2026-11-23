# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The AI providers behind call_haiku: request shapes, failover, the circuit
breaker, alerts and recovery (docs/ai-providers.md). HTTP is always mocked.

    bench --site <test-site> run-tests --module helpdesk.tests.test_ai_engine
"""

import json
import time
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk import ai_engine
from helpdesk.test_utils import (
    ANTHROPIC_TEST_KEY,
    OPENAI_TEST_KEY,
    anthropic_answer,
    anthropic_status_error,
    clear_ai_alerts,
    hold_commits,
    make_ai_provider,
    make_ticket,
    openai_http_response,
    patch_anthropic_sdk,
    set_ai_providers,
)

POST = "requests.post"
JSON_PROMPT = 'Reply with JSON only: {"category": "..."}'
QUOTA = {
    "error": {
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "type": "insufficient_quota",
        "code": "insufficient_quota",
    }
}
KIMI_SUSPENDED = {
    "error": {
        "type": "exceeded_current_quota_error",
        "message": "Your account is suspended due to insufficient balance",
    }
}


class AIProviderCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(ai_engine.reset_provider_state)
        self.addCleanup(clear_ai_alerts)
        self.addCleanup(
            frappe.clear_document_cache, "HDS Hub Settings", "HDS Hub Settings"
        )
        set_ai_providers()
        alert = patch.object(ai_engine, "send_provider_alert")
        self.alert = alert.start()
        self.addCleanup(alert.stop)
        retry = patch.object(ai_engine, "retry_failed_triages")
        self.retry = retry.start()
        self.addCleanup(retry.stop)


class TestOpenAIRequest(AIProviderCase):
    def test_request_shape_and_json_mode(self):
        with patch(POST, return_value=openai_http_response(text='{"a": 1}')) as post:
            text, usage = ai_engine.complete(
                make_ai_provider(), JSON_PROMPT, "the ticket"
            )

        self.assertEqual(text, '{"a": 1}')
        self.assertEqual((usage.input_tokens, usage.output_tokens), (78, 40))
        self.assertEqual(
            post.call_args.args[0], "https://api.openai.com/v1/chat/completions"
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            f"Bearer {OPENAI_TEST_KEY}",
        )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "gpt-test-model")
        self.assertEqual(
            body["messages"],
            [
                {"role": "system", "content": JSON_PROMPT},
                {"role": "user", "content": "the ticket"},
            ],
        )
        self.assertEqual(body["max_completion_tokens"], 4096)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        # newer OpenAI models refuse a temperature other than the default
        self.assertNotIn("temperature", body)
        self.assertNotIn("max_tokens", body)

    def test_no_json_mode_when_the_prompt_wants_text(self):
        with patch(POST, return_value=openai_http_response(text="OK")) as post:
            ai_engine.complete(make_ai_provider(), "Reply with OK.", "test")

        self.assertNotIn("response_format", post.call_args.kwargs["json"])

    def test_an_openai_compatible_endpoint_gets_neither_budget_nor_json_mode(self):
        provider = make_ai_provider(
            kind="OpenAI Compatible", base_url="https://inference.example.ai/v1"
        )
        with patch(POST, return_value=openai_http_response(text="{}")) as post:
            ai_engine.complete(provider, JSON_PROMPT, "test")

        body = post.call_args.kwargs["json"]
        self.assertNotIn("max_completion_tokens", body)
        self.assertNotIn("response_format", body)

    def test_a_reasoning_model_that_ran_out_gets_a_larger_budget(self):
        ran_out = openai_http_response(
            body={
                "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4096},
            }
        )
        with patch(
            POST, side_effect=[ran_out, openai_http_response(text='{"ok": 1}')]
        ) as post:
            text, _usage = ai_engine.complete(make_ai_provider(), JSON_PROMPT, "x")

        self.assertEqual(text, '{"ok": 1}')
        self.assertEqual(
            [c.kwargs["json"]["max_completion_tokens"] for c in post.call_args_list],
            [4096, 8192],
        )

    def test_each_call_is_logged_with_its_provider_and_model(self):
        ticket = make_ticket(subject="Stock balance report is wrong")
        with patch(POST, return_value=openai_http_response(text='{"a": 1}')):
            result = ai_engine.call_haiku(
                JSON_PROMPT, "x", ticket_name=str(ticket.name)
            )

        self.assertEqual(result["response"], {"a": 1})
        log = frappe.get_last_doc(
            "HDS AI Usage Log", filters={"ticket": str(ticket.name)}
        )
        self.assertEqual((log.provider, log.model), ("OpenAI", "gpt-test-model"))
        self.assertEqual((log.input_tokens, log.output_tokens), (78, 40))


class TestAnthropicRequest(AIProviderCase):
    def test_request_shape(self):
        client_cls = patch_anthropic_sdk(
            self, anthropic_answer('{"category": "Stock"}')
        )

        text, _usage = ai_engine.complete(
            make_ai_provider("Anthropic-compatible"), JSON_PROMPT, "the ticket"
        )

        self.assertEqual(text, '{"category": "Stock"}')
        self.assertEqual(
            client_cls.call_args.kwargs,
            {
                "api_key": ANTHROPIC_TEST_KEY,
                "max_retries": ai_engine.SDK_MAX_RETRIES,
                "base_url": "https://api.moonshot.ai/anthropic",
            },
        )
        call = client_cls.return_value.messages.create.call_args.kwargs
        self.assertEqual(call["model"], "kimi-k2.6")
        self.assertEqual(call["max_tokens"], 4096)
        self.assertEqual(call["system"][0]["text"], JSON_PROMPT)
        self.assertEqual(call["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(call["messages"], [{"role": "user", "content": "the ticket"}])
        self.assertEqual(call["timeout"], ai_engine.REQUEST_TIMEOUT)

    def test_thinking_blocks_are_skipped(self):
        """Kimi and other thinking models can reply with a thinking block before the text."""
        answer = anthropic_answer('{"category": "Billing"}')
        answer.content.insert(0, MagicMock(type="thinking", thinking="let me think"))
        patch_anthropic_sdk(self, answer)
        set_ai_providers(primary_ai_provider="Anthropic-compatible")

        result = ai_engine.call_haiku("sys", "user")

        self.assertEqual(result["response"], {"category": "Billing"})

    def test_a_thinking_model_that_ran_out_gets_more_room(self):
        """Kimi can spend the whole budget thinking and return no text; try once more with a larger budget."""
        ran_out = anthropic_answer("", stop_reason="max_tokens")
        ran_out.content = [MagicMock(type="thinking", thinking="long thoughts")]
        client_cls = patch_anthropic_sdk(
            self, ran_out, anthropic_answer('{"summary": "ok"}')
        )
        set_ai_providers(primary_ai_provider="Anthropic-compatible")

        result = ai_engine.call_haiku("sys", "user")

        self.assertEqual(result["response"], {"summary": "ok"})
        create = client_cls.return_value.messages.create
        self.assertEqual(
            [c.kwargs["max_tokens"] for c in create.call_args_list], [4096, 8192]
        )


class TestFailover(AIProviderCase):
    def call(self):
        return ai_engine.call_haiku(JSON_PROMPT, "the ticket")

    def test_insufficient_balance_fails_over_pauses_and_alerts_once(self):
        patch_anthropic_sdk(self, anthropic_answer('{"category": "Stock"}'))
        with patch(POST, return_value=openai_http_response(429, QUOTA)):
            result = self.call()

        self.assertEqual(result["response"], {"category": "Stock"})
        openai = make_ai_provider()
        self.assertTrue(ai_engine.circuit_open(openai))
        down = ai_engine.provider_down("OpenAI")
        self.assertEqual(down["kind"], "billing")
        self.assertIn("insufficient_quota", down["reason"])
        self.alert.assert_called_once()
        subject = self.alert.call_args.kwargs["subject"]
        self.assertIn("AI provider OpenAI (gpt-test-model) failing since", subject)
        self.assertIn("insufficient balance or quota", subject)
        self.assertIn("Using Anthropic-compatible (kimi-k2.6)", subject)

    def test_a_paused_provider_is_skipped_until_the_pause_ends(self):
        patch_anthropic_sdk(
            self,
            anthropic_answer('{"n": 1}'),
            anthropic_answer('{"n": 2}'),
            anthropic_answer('{"n": 3}'),
        )
        with patch(POST, return_value=openai_http_response(402, QUOTA)) as post:
            self.call()
            self.assertEqual(self.call()["response"], {"n": 2})
            self.assertEqual(post.call_count, 1)

            # the pause is a 30-minute cache key; once it's gone OpenAI is tried again
            ai_engine.reset_provider_state()
            self.call()
            self.assertEqual(post.call_count, 2)
        # the alert is sent once in 6 hours, however often the provider fails
        self.alert.assert_called_once()

    def test_kimi_out_of_balance_fails_over_to_openai(self):
        set_ai_providers(primary_ai_provider="Anthropic-compatible")
        patch_anthropic_sdk(self, anthropic_status_error(429, KIMI_SUSPENDED))
        with patch(POST, return_value=openai_http_response(text='{"a": 1}')):
            result = self.call()

        self.assertEqual(result["response"], {"a": 1})
        self.assertEqual(
            ai_engine.provider_down("Anthropic-compatible")["kind"], "billing"
        )
        self.assertTrue(
            ai_engine.circuit_open(make_ai_provider("Anthropic-compatible"))
        )

    def test_a_refused_key_fails_over_and_never_shows_the_key(self):
        refused = {
            "error": {
                "message": f"Incorrect API key provided: {OPENAI_TEST_KEY}.",
                "code": "invalid_api_key",
            }
        }
        patch_anthropic_sdk(self, anthropic_answer("{}"))
        with patch(POST, return_value=openai_http_response(401, refused)):
            self.call()

        down = ai_engine.provider_down("OpenAI")
        self.assertEqual(down["kind"], "auth")
        self.assertTrue(ai_engine.circuit_open(make_ai_provider()))
        self.assertNotIn(OPENAI_TEST_KEY, json.dumps(down))
        self.assertNotIn(OPENAI_TEST_KEY, self.alert.call_args.kwargs["subject"])

    def test_a_server_error_fails_over_without_a_pause(self):
        patch_anthropic_sdk(self, anthropic_answer("{}"))
        with patch(POST, return_value=openai_http_response(503, {"error": "busy"})):
            self.call()

        self.assertEqual(ai_engine.provider_down("OpenAI")["kind"], "server")
        self.assertFalse(ai_engine.circuit_open(make_ai_provider()))

    def test_no_attempt_starts_after_the_calls_deadline(self):
        """Both providers together stay inside triage's job timeout."""
        with patch(POST) as post:
            with self.assertRaises(ai_engine.AIProviderError) as raised:
                ai_engine.complete(
                    make_ai_provider(),
                    JSON_PROMPT,
                    "x",
                    deadline=time.monotonic() + 1,
                )
        self.assertEqual(raised.exception.kind, "timeout")
        post.assert_not_called()

    def test_the_fallback_gets_only_the_time_left(self):
        client_cls = patch_anthropic_sdk(self, anthropic_answer('{"a": 1}'))
        with patch(POST, side_effect=requests.Timeout("read timed out")), patch.object(
            ai_engine, "monotonic", side_effect=[0, 0, 200]
        ):
            self.call()

        timeout = client_cls.return_value.messages.create.call_args.kwargs["timeout"]
        self.assertEqual(timeout, ai_engine.CALL_SECONDS - 200)

    def test_an_answer_without_choices_fails_over(self):
        patch_anthropic_sdk(self, anthropic_answer('{"a": 1}'))
        with patch(POST, return_value=openai_http_response(body={"id": "x"})):
            self.assertEqual(self.call()["response"], {"a": 1})

        self.assertEqual(ai_engine.provider_down("OpenAI")["kind"], "server")

    def test_a_timeout_fails_over(self):
        patch_anthropic_sdk(self, anthropic_answer('{"a": 1}'))
        with patch(POST, side_effect=requests.Timeout("read timed out")):
            self.assertEqual(self.call()["response"], {"a": 1})

        self.assertEqual(ai_engine.provider_down("OpenAI")["kind"], "timeout")

    def test_an_unknown_model_fails_over_and_pauses(self):
        missing = {
            "error": {
                "message": "The model `gpt-test-model` does not exist or you do not have access to it.",
                "code": "model_not_found",
            }
        }
        patch_anthropic_sdk(self, anthropic_answer("{}"))
        with patch(POST, return_value=openai_http_response(404, missing)):
            self.call()

        self.assertEqual(ai_engine.provider_down("OpenAI")["kind"], "config")
        self.assertTrue(ai_engine.circuit_open(make_ai_provider()))

    def test_a_rejected_request_does_not_fail_over_and_is_logged(self):
        client_cls = patch_anthropic_sdk(self, anthropic_answer("{}"))
        invalid = {"error": {"message": "Invalid value for 'messages'."}}
        with patch(POST, return_value=openai_http_response(400, invalid)):
            with self.assertRaises(ai_engine.AIProviderError) as raised:
                self.call()

        self.assertEqual(raised.exception.kind, "invalid")
        client_cls.return_value.messages.create.assert_not_called()
        self.assertIsNone(ai_engine.provider_down("OpenAI"))
        self.assertFalse(ai_engine.circuit_open(make_ai_provider()))
        self.alert.assert_not_called()
        self.assertTrue(
            frappe.db.exists(
                "Error Log",
                {"method": "AI request rejected by OpenAI (gpt-test-model)"},
            )
        )

    def test_without_failover_only_the_primary_is_tried(self):
        set_ai_providers(ai_failover=0)
        client_cls = patch_anthropic_sdk(self, anthropic_answer("{}"))
        with patch(POST, return_value=openai_http_response(429, QUOTA)):
            with self.assertRaises(ai_engine.AIProviderError):
                self.call()

        client_cls.return_value.messages.create.assert_not_called()
        self.assertIn(
            "No other provider is set up", self.alert.call_args.kwargs["subject"]
        )

    def test_an_unconfigured_primary_is_left_out(self):
        set_ai_providers(openai_api_key=None)
        patch_anthropic_sdk(self, anthropic_answer('{"a": 1}'))
        with patch(POST) as post:
            self.assertEqual(self.call()["response"], {"a": 1})
        post.assert_not_called()

    def test_no_provider_at_all_is_a_clear_error(self):
        set_ai_providers(openai_api_key=None, anthropic_api_key=None)
        with patch.dict(frappe.conf, {"anthropic_api_key": None}):
            self.assertEqual(ai_engine.get_providers(), [])
            with self.assertRaises(frappe.ValidationError):
                self.call()

    def test_triages_are_retried_when_a_provider_answers_after_an_outage(self):
        patch_anthropic_sdk(
            self,
            anthropic_status_error(500, {"error": "down"}),
            anthropic_answer('{"a": 1}'),
        )
        with patch(POST, return_value=openai_http_response(503, {"error": "down"})):
            with self.assertRaises(ai_engine.AIProviderError):
                self.call()
        self.retry.assert_not_called()

        with patch(POST, return_value=openai_http_response(text='{"a": 1}')):
            self.call()
        self.retry.assert_called_once()
        self.assertIsNone(ai_engine.provider_down("OpenAI"))


class TestAlert(FrappeTestCase):
    @patch("helpdesk.work_reminders.notify_users")
    def test_alert_goes_to_system_and_agent_managers_and_the_channel(self, notify):
        with patch(
            "helpdesk.github_sync.admin_users", return_value=["manager@example.com"]
        ):
            ai_engine.send_provider_alert("AI provider OpenAI failing")

        args, kwargs = notify.call_args
        self.assertEqual(args[0], ["manager@example.com"])
        self.assertEqual(args[3], "AI provider OpenAI failing")
        self.assertTrue(kwargs["escalate"])
        self.assertEqual(kwargs["link"], "/home")


class TestStatus(AIProviderCase):
    def test_status_shows_the_order_and_who_answers(self):
        patch_anthropic_sdk(self, anthropic_answer("{}"))
        with patch(POST, return_value=openai_http_response(429, QUOTA)):
            ai_engine.call_haiku(JSON_PROMPT, "x")

        status = ai_engine.provider_status()

        self.assertEqual(status["order"], ["OpenAI", "Anthropic-compatible"])
        self.assertEqual(status["in_use"], "Anthropic-compatible")
        openai = status["providers"]["OpenAI"]
        self.assertTrue(openai["configured"] and openai["paused"])
        self.assertEqual(openai["down"]["kind"], "billing")
        body = json.dumps(status, default=str)
        self.assertNotIn(OPENAI_TEST_KEY, body)
        self.assertNotIn(ANTHROPIC_TEST_KEY, body)


class TestCallers(AIProviderCase):
    """Every call_haiku caller's prompt asks for JSON, so OpenAI's JSON mode is on
    for all of them and their answers parse the same way through the abstraction."""

    def test_every_caller_prompt_gets_json_mode(self):
        from helpdesk import (
            ai_suggestion,
            chatwoot_bridge,
            content_topics,
            home_plan,
            kb_drafts,
            repeat_issues,
            task_descriptions,
            task_estimates,
            team_dashboard,
            team_insights,
            triage,
            work_summary,
        )
        from helpdesk.api import content, ticket_ai
        from helpdesk.copilot import conversation

        prompts = [
            ai_suggestion.SUGGESTION_SYSTEM_PROMPT,
            conversation.PROMPT,
            chatwoot_bridge.SUMMARY_SYSTEM_PROMPT,
            content_topics.SYSTEM_PROMPT,
            home_plan.SYSTEM_PROMPT,
            kb_drafts.DRAFT_SYSTEM_PROMPT,
            repeat_issues.LABEL_PROMPT,
            task_descriptions.SYSTEM_PROMPT,
            task_estimates.SYSTEM_PROMPT,
            team_dashboard.SYSTEM_PROMPT,
            team_insights.SUMMARY_PROMPT,
            triage.TRIAGE_SYSTEM_PROMPT,
            work_summary.SYSTEM_PROMPT,
            content.SYSTEM_PROMPT,
            ticket_ai.SYSTEM_PROMPT,
        ]
        for prompt in prompts:
            with patch(
                POST, return_value=openai_http_response(text='{"reply": "Hi"}')
            ) as post:
                result = ai_engine.call_haiku(prompt, "facts")
            self.assertEqual(result["response"], {"reply": "Hi"})
            self.assertEqual(
                post.call_args.kwargs["json"]["response_format"],
                {"type": "json_object"},
            )

    @patch("frappe.enqueue")
    def test_triage_completes_on_the_fallback_when_the_primary_is_out_of_quota(
        self, _enqueue
    ):
        from helpdesk import triage

        ticket = make_ticket(
            subject="Stock balance report is wrong",
            description="The Stock Balance report shows the wrong quantity for ABC-001.",
        )
        answer = {
            "category": "Stock",
            "priority": "Medium",
            "summary": "Stock Balance shows a wrong quantity for ABC-001.",
            "recommended_track": "manual",
        }
        patch_anthropic_sdk(self, anthropic_answer(json.dumps(answer)))
        with patch(POST, return_value=openai_http_response(429, QUOTA)), patch.object(
            frappe.cache, "set", return_value=True
        ):
            triage.run_triage(str(ticket.name), start_investigation=False)

        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "custom_triage_status"),
            "Completed",
        )

    @patch("frappe.enqueue")
    def test_triage_fails_when_every_provider_fails(self, _enqueue):
        from helpdesk import triage

        ticket = make_ticket(
            subject="Stock balance report is wrong",
            description="The Stock Balance report shows the wrong quantity for ABC-001.",
        )
        patch_anthropic_sdk(self, anthropic_status_error(429, KIMI_SUSPENDED))
        with patch(POST, return_value=openai_http_response(429, QUOTA)), patch.object(
            frappe.cache, "set", return_value=True
        ):
            triage.run_triage(str(ticket.name), start_investigation=False)

        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "custom_triage_status"),
            "Failed",
        )
        self.assertTrue(frappe.cache.get_value(ai_engine.OUTAGE_KEY, expires=True))


class TestRecoveryRetry(FrappeTestCase):
    def setUp(self):
        hold_commits(self)

    @patch("frappe.enqueue")
    def test_the_scheduled_retry_skips_the_cooldown_but_not_the_limit(self, enqueue):
        from frappe.utils import now_datetime

        from helpdesk import triage

        ticket = make_ticket(subject="Stock balance report is wrong")
        frappe.db.set_value(
            "HD Ticket",
            ticket.name,
            {
                "custom_triage_status": "Failed",
                "custom_triage_timestamp": now_datetime(),
            },
        )

        # seconds after the failure a person must wait; the recovery retry needn't
        with self.assertRaises(frappe.ValidationError):
            triage.run_triage_now(str(ticket.name))
        triage.run_triage_now(str(ticket.name), ignore_cooldown=True)
        self.assertEqual(enqueue.call_args.kwargs["ticket_id"], str(ticket.name))

        frappe.db.set_value(
            "HD Ticket",
            ticket.name,
            "custom_triage_data",
            json.dumps({"retry_count": triage.MAX_TRIAGE_RETRIES}),
        )
        with self.assertRaises(frappe.ValidationError):
            triage.run_triage_now(str(ticket.name), ignore_cooldown=True)


class TestInvestigationClient(FrappeTestCase):
    """Investigation sessions stay on the Anthropic SDK (tool use)."""

    def test_openai_compatible_provider_blocks_sdk_client(self):
        with patch.object(
            ai_engine,
            "get_provider_config",
            return_value=("OpenAI Compatible", "https://x/v1", "key"),
        ):
            with self.assertRaises(frappe.ValidationError):
                ai_engine.get_client()

    def test_anthropic_compatible_passes_base_url(self):
        with patch.object(
            ai_engine,
            "get_provider_config",
            return_value=(
                "Anthropic Compatible",
                "https://api.moonshot.ai/anthropic",
                "key",
            ),
        ), patch.object(ai_engine.anthropic, "Anthropic") as sdk:
            ai_engine.get_client()

        self.assertEqual(
            sdk.call_args.kwargs["base_url"], "https://api.moonshot.ai/anthropic"
        )


class TestRedact(FrappeTestCase):
    def test_keys_and_their_echoes_are_masked(self):
        text = "Incorrect API key provided: sk-proj-abc********wxyz. Key sk-live-12345"
        self.assertEqual(
            ai_engine.redact(text, "sk-live-12345"),
            "Incorrect API key provided: sk-…. Key …",
        )

    def test_billing_words_decide_a_429(self):
        self.assertEqual(ai_engine.classify(429, "insufficient balance"), "billing")
        # Anthropic's own wording, with HTTP 400
        self.assertEqual(
            ai_engine.classify(400, "Your credit balance is too low"), "billing"
        )
        self.assertEqual(ai_engine.classify(429, "Rate limit reached"), "rate_limit")
        self.assertEqual(ai_engine.classify(402, ""), "billing")
        self.assertEqual(ai_engine.classify(400, "bad messages"), "invalid")
