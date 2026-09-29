# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Provider-abstraction tests. Run on the staging hub:
    bench --site <staging-hub> run-tests --module helpdesk.tests.test_ai_engine
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOpenAICompatible(FrappeTestCase):
    def test_openai_chat_parses_response_and_usage(self):
        from helpdesk.ai_engine import _openai_chat

        fake = MagicMock()
        fake.json.return_value = {
            "choices": [{"message": {"content": '{"category": "Stock"}'}}],
            "usage": {"prompt_tokens": 78, "completion_tokens": 40},
        }
        with patch("requests.post", return_value=fake) as post:
            text, usage = _openai_chat(
                "https://inference.example.ai/v1", "key", "some/model", "sys", "user"
            )

        self.assertEqual(text, '{"category": "Stock"}')
        self.assertEqual((usage.input_tokens, usage.output_tokens), (78, 40))
        self.assertEqual(
            post.call_args[0][0], "https://inference.example.ai/v1/chat/completions"
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer key"
        )

    def test_openai_provider_blocks_sdk_client(self):
        """Investigation sessions must fail loudly on OpenAI-compat providers."""
        from helpdesk import ai_engine

        with patch.object(
            ai_engine,
            "get_provider_config",
            return_value=("OpenAI Compatible", "https://x/v1", "key"),
        ):
            with self.assertRaises(frappe.ValidationError):
                ai_engine.get_client()

    def test_anthropic_compatible_passes_base_url(self):
        from helpdesk import ai_engine

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


class TestTriageUsesTriageProvider(FrappeTestCase):
    def test_call_haiku_builds_client_for_triage_layer(self):
        """Triage must not borrow the investigation provider's endpoint and key."""
        from helpdesk import ai_engine

        layers = []

        def provider_config(layer="triage"):
            layers.append(layer)
            return ("Anthropic", None, "key")

        response = MagicMock()
        response.content = [MagicMock(text='{"category": "Stock"}')]
        response.usage = MagicMock(input_tokens=10, output_tokens=5)

        with (
            patch.object(ai_engine, "get_provider_config", side_effect=provider_config),
            patch.object(ai_engine, "get_models", return_value=("haiku", "sonnet")),
            patch.object(ai_engine, "log_usage"),
            patch.object(ai_engine, "estimate_cost", return_value=0),
            patch.object(ai_engine.anthropic, "Anthropic") as client_cls,
        ):
            client_cls.return_value.messages.create.return_value = response
            result = ai_engine.call_haiku("sys", "user")

        self.assertEqual(result["response"], {"category": "Stock"})
        self.assertNotIn("investigation", layers)


class TestThinkingBlocks(FrappeTestCase):
    def test_call_haiku_skips_thinking_blocks(self):
        """Kimi and other thinking models can reply with a thinking block before the text."""
        from helpdesk import ai_engine

        response = MagicMock()
        response.content = [
            MagicMock(type="thinking", thinking="let me think"),
            MagicMock(type="text", text='{"category": "Billing"}'),
        ]
        response.usage = MagicMock(input_tokens=10, output_tokens=5)

        with (
            patch.object(
                ai_engine,
                "get_provider_config",
                return_value=("Anthropic Compatible", "https://x", "key"),
            ),
            patch.object(
                ai_engine, "get_models", return_value=("kimi-k2.6", "kimi-k3")
            ),
            patch.object(ai_engine, "log_usage"),
            patch.object(ai_engine, "estimate_cost", return_value=0),
            patch.object(ai_engine.anthropic, "Anthropic") as client_cls,
        ):
            client_cls.return_value.messages.create.return_value = response
            result = ai_engine.call_haiku("sys", "user")

        self.assertEqual(result["response"], {"category": "Billing"})
