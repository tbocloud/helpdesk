"""Settings → AI providers (helpdesk.api.ai_settings): who may use it, masked
keys, saving, and Test connection. HTTP is always mocked."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import ai_engine
from helpdesk.test_utils import (
    ANTHROPIC_TEST_KEY,
    OPENAI_TEST_KEY,
    call_as_user,
    clear_ai_alerts,
    hold_commits,
    make_tasky_user,
    openai_http_response,
    set_ai_providers,
)

API = "helpdesk.api.ai_settings."
POST = "requests.post"
SETTINGS = "HDS Hub Settings"
MANAGER = ("manager.ai@ai-settings.example", "Meera Pillai")
AGENT = ("agent.ai@ai-settings.example", "Arjun Menon")


class AISettingsCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(ai_engine.reset_provider_state)
        self.addCleanup(clear_ai_alerts)
        self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_tasky_user(*AGENT)
        set_ai_providers()
        retry = patch.object(ai_engine, "retry_failed_triages")
        self.retry = retry.start()
        self.addCleanup(retry.stop)

    def password(self, fieldname):
        return frappe.get_doc(SETTINGS).get_password(fieldname, raise_exception=False)


class TestPermissions(AISettingsCase):
    def test_agents_can_neither_read_change_nor_test(self):
        calls = [
            ("get_settings", {}),
            ("save_settings", {"values": {"ai_failover": 0}}),
            ("test_connection", {"provider": "OpenAI"}),
        ]
        with patch(POST) as post:
            for method, kwargs in calls:
                with self.assertRaises(frappe.PermissionError):
                    call_as_user(AGENT[0], API + method, **kwargs)
        post.assert_not_called()
        self.assertEqual(frappe.db.get_single_value(SETTINGS, "ai_failover"), 1)

    def test_agent_managers_can_change_the_settings(self):
        call_as_user(
            MANAGER[0],
            API + "save_settings",
            values={"primary_ai_provider": "Anthropic-compatible"},
        )
        self.assertEqual(
            frappe.db.get_single_value(SETTINGS, "primary_ai_provider"),
            "Anthropic-compatible",
        )


class TestMaskedRead(AISettingsCase):
    def test_keys_come_back_masked_with_whether_they_are_set(self):
        result = call_as_user(MANAGER[0], API + "get_settings")

        self.assertEqual(
            result["secrets"],
            {
                "openai_api_key": {"set": True, "masked": "sk-proj-…"},
                "anthropic_api_key": {"set": True, "masked": "sk-…"},
            },
        )
        self.assertEqual(result["settings"]["openai_model"], "gpt-test-model")
        self.assertEqual(result["status"]["in_use"], "OpenAI")
        body = frappe.as_json(result)
        for secret in (OPENAI_TEST_KEY, ANTHROPIC_TEST_KEY, "*****"):
            self.assertNotIn(secret, body)


class TestSave(AISettingsCase):
    def save(self, **values):
        return call_as_user(MANAGER[0], API + "save_settings", values=values)

    def test_a_key_not_sent_is_kept_and_an_empty_one_removed(self):
        self.save(openai_model="gpt-other-model")
        self.assertEqual(self.password("openai_api_key"), OPENAI_TEST_KEY)

        self.save(openai_api_key="  sk-proj-replaced-key  ")
        self.assertEqual(self.password("openai_api_key"), "sk-proj-replaced-key")

        self.save(openai_api_key="")
        self.assertFalse(self.password("openai_api_key"))
        self.assertEqual(self.password("anthropic_api_key"), ANTHROPIC_TEST_KEY)

    def test_the_base_url_decides_anthropic_or_compatible(self):
        self.save(ai_base_url="")
        self.assertEqual(
            frappe.db.get_single_value(SETTINGS, "ai_provider"), "Anthropic"
        )
        self.save(ai_base_url="https://api.moonshot.ai/anthropic")
        self.assertEqual(
            frappe.db.get_single_value(SETTINGS, "ai_provider"), "Anthropic Compatible"
        )

    def test_a_key_is_only_sent_over_https(self):
        with self.assertRaises(frappe.ValidationError) as raised:
            self.save(openai_base_url="http://api.openai.com/v1")
        self.assertTrue(str(raised.exception).startswith("OpenAI Base URL:"))

    def test_a_new_model_gets_a_pricing_row_priced_zero(self):
        self.save(openai_model="gpt-priced-later")

        row = frappe.get_doc("HDS Model Pricing", "gpt-priced-later")
        self.assertEqual((row.provider, row.input_cost_per_1m), ("OpenAI", 0))
        self.assertIn("TODO", row.notes)

    def test_saving_forgets_a_pause(self):
        provider = ai_engine.configured_providers()["OpenAI"]
        frappe.cache.set_value(
            ai_engine.CIRCUIT_KEY.format("OpenAI"), "auth", expires_in_sec=600
        )
        self.assertTrue(ai_engine.circuit_open(provider))

        self.save(openai_api_key="sk-proj-fixed-key")

        self.assertFalse(ai_engine.circuit_open(provider))


class TestTestConnection(AISettingsCase):
    def test(self, provider="OpenAI"):
        return call_as_user(MANAGER[0], API + "test_connection", provider=provider)

    def test_ok_unpauses_and_retries_failed_triages(self):
        frappe.cache.set_value(
            ai_engine.CIRCUIT_KEY.format("OpenAI"), "billing", expires_in_sec=600
        )
        with patch(POST, return_value=openai_http_response(text="OK")) as post:
            result = self.test()

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["details"][0], {"label": "Model", "value": "gpt-test-model"}
        )
        self.assertEqual(result["details"][1]["value"], "api.openai.com")
        self.assertEqual(
            post.call_args.kwargs["json"]["max_completion_tokens"],
            ai_engine.TEST_TOKEN_BUDGET,
        )
        self.assertFalse(
            ai_engine.circuit_open(ai_engine.configured_providers()["OpenAI"])
        )
        self.retry.assert_called_once()
        self.assertNotIn(OPENAI_TEST_KEY, frappe.as_json(result))

    def test_failure_shows_the_providers_message_never_the_key(self):
        refused = {
            "error": {
                "message": f"Incorrect API key provided: {OPENAI_TEST_KEY}.",
                "code": "invalid_api_key",
            }
        }
        with patch(POST, return_value=openai_http_response(401, refused)):
            result = self.test()

        self.assertFalse(result["ok"])
        self.assertIn("Incorrect API key provided", result["message"])
        self.assertIn("HTTP 401", result["message"])
        self.assertNotIn(OPENAI_TEST_KEY, result["message"])
        self.retry.assert_not_called()

    def test_a_provider_without_a_key_asks_for_one(self):
        set_ai_providers(openai_api_key=None)
        with patch(POST) as post:
            result = self.test()
        self.assertFalse(result["ok"])
        post.assert_not_called()

    def test_only_the_two_providers_can_be_tested(self):
        with self.assertRaises(frappe.ValidationError):
            self.test("Gemini")
