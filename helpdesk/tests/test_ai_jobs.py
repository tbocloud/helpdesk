# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Models per job (TASK-2026-00012): a job's own model in each provider section, what the
usage log records, and the models and prices the Copilot worker is given."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import ai_engine
from helpdesk.ai_engine import AIProviderError
from helpdesk.test_utils import (
    call_as_user,
    hold_commits,
    make_copilot_run,
    make_ticket,
    set_ai_providers,
)
from helpdesk.tests.test_ai_settings import API, MANAGER, SETTINGS, AISettingsCase


def usage(tokens_in: int = 100, tokens_out: int = 20):
    return SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out)


class TestModelsPerJob(FrappeTestCase):
    def setUp(self):
        hold_commits(self)

    def models(self, job):
        return [(p.slot, p.model, p.override) for p in ai_engine.get_providers(job)]

    def test_without_a_row_a_job_uses_each_sections_model(self):
        set_ai_providers()
        self.assertEqual(
            self.models("summary"),
            [
                ("OpenAI", "gpt-test-model", False),
                ("Anthropic-compatible", "kimi-k2.6", False),
            ],
        )

    def test_a_row_changes_only_its_jobs_models_never_the_order(self):
        set_ai_providers(ai_jobs=[{"job": "summary", "openai_model": "gpt-6-luna"}])
        self.assertEqual(
            self.models("summary"),
            [
                ("OpenAI", "gpt-6-luna", True),
                ("Anthropic-compatible", "kimi-k2.6", False),
            ],
        )
        self.assertEqual(self.models("triage")[0], ("OpenAI", "gpt-test-model", False))

    def test_one_row_per_job(self):
        with self.assertRaises(frappe.ValidationError):
            set_ai_providers(
                ai_jobs=[{"job": "draft"}, {"job": "draft", "openai_model": "x"}]
            )

    def test_a_jobs_own_model_is_paused_apart_from_its_section(self):
        set_ai_providers(ai_jobs=[{"job": "summary", "openai_model": "gpt-typo"}])
        own = ai_engine.get_providers("summary")[0]
        section = ai_engine.get_providers("triage")[0]
        self.assertEqual(own.key, "OpenAI|gpt-typo")
        ai_engine.record_failure(
            AIProviderError(own, "config", "model not found"), None
        )
        self.addCleanup(ai_engine.reset_provider_state)
        self.assertTrue(ai_engine.circuit_open(own))
        self.assertFalse(ai_engine.circuit_open(section))

    def test_call_haiku_passes_the_job_and_marks_the_fallback(self):
        set_ai_providers(ai_jobs=[{"job": "task", "anthropic_model": "kimi-k2.7"}])
        calls = []

        def answer(provider, *args, **kwargs):
            calls.append(
                (
                    provider.slot,
                    provider.model,
                    kwargs.get("job"),
                    kwargs.get("fallback"),
                )
            )
            if provider.slot == "OpenAI":
                raise AIProviderError(provider, "rate_limit", "slow down", 429)
            return '{"ok": true}', usage()

        with patch.object(ai_engine, "complete", side_effect=answer):
            result = ai_engine.call_haiku("Answer in JSON.", "hello", job="task")
        self.assertEqual(result["response"], {"ok": True})
        self.assertEqual(
            calls,
            [
                ("OpenAI", "gpt-test-model", "task", False),
                ("Anthropic-compatible", "kimi-k2.7", "task", True),
            ],
        )

    def test_the_usage_log_records_the_job_and_the_fallback(self):
        ticket = make_ticket(subject="Usage").name
        ai_engine.log_usage(
            "gpt-test-model",
            usage(),
            ticket_name=ticket,
            provider="OpenAI",
            job="draft",
            fallback=True,
        )
        row = frappe.get_last_doc("HDS AI Usage Log", filters={"ticket": ticket})
        self.assertEqual((row.job, row.fallback, row.provider), ("draft", 1, "OpenAI"))


class TestTheWorkersShare(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        set_ai_providers()
        self.run_name = make_copilot_run(
            make_ticket(subject="Worker usage").name, "Investigating"
        ).name

    def rows(self):
        return frappe.get_all(
            "HDS AI Usage Log",
            filters={"copilot_run": self.run_name},
            fields=[
                "job",
                "model",
                "input_tokens",
                "cache_read_tokens",
                "output_tokens",
                "estimated_cost_usd",
            ],
            order_by="job asc",
        )

    def test_one_row_per_stage_and_none_twice(self):
        cost = {
            "stages": [
                {
                    "job": "fix",
                    "tokens_in": 1000,
                    "tokens_cached": 400,
                    "tokens_out": 200,
                    "usd": 0.002,
                    "model": "gpt-5.6-luna",
                },
                {
                    "job": "review",
                    "tokens_in": 300,
                    "tokens_cached": 0,
                    "tokens_out": 50,
                    "usd": 0.0005,
                    "model": "gpt-5.6-luna",
                },
            ]
        }
        ai_engine.log_worker_usage(self.run_name, cost, "fix", 1)
        ai_engine.log_worker_usage(
            self.run_name, cost, "fix", 1
        )  # the same report again
        rows = self.rows()
        self.assertEqual([r.job for r in rows], ["fix", "review"])
        self.assertEqual(
            (rows[0].input_tokens, rows[0].cache_read_tokens, rows[0].output_tokens),
            (600, 400, 200),
        )
        self.assertAlmostEqual(rows[0].estimated_cost_usd, 0.002)

    def test_a_stage_that_moved_to_the_fallback_has_a_row_for_each_model(self):
        cost = {
            "stages": [
                {
                    "job": "fix",
                    "tokens_in": 500,
                    "tokens_out": 10,
                    "usd": 0.001,
                    "model": "gpt-5.6-luna",
                    "section": "OpenAI",
                },
                {
                    "job": "fix",
                    "tokens_in": 800,
                    "tokens_out": 90,
                    "usd": 0.003,
                    "model": "kimi-k2.6",
                    "section": "Anthropic-compatible",
                    "fallback": True,
                },
            ]
        }
        ai_engine.log_worker_usage(self.run_name, cost, "fix", 2)
        ai_engine.log_worker_usage(self.run_name, cost, "fix", 2)
        rows = frappe.get_all(
            "HDS AI Usage Log",
            filters={"copilot_run": self.run_name},
            fields=["model", "fallback", "provider", "stage_key"],
            order_by="fallback asc",
        )
        self.assertEqual(
            [(r.model, r.fallback, r.provider) for r in rows],
            [("gpt-5.6-luna", 0, "OpenAI"), ("kimi-k2.6", 1, "Anthropic-compatible")],
        )
        self.assertEqual(rows[1].stage_key, f"{self.run_name}:fix:2:fallback")

    def test_a_single_cost_is_the_reporting_jobs_row(self):
        ai_engine.log_worker_usage(
            self.run_name,
            {"tokens_in": 50, "tokens_out": 5, "usd": 0.0001, "model": "kimi-k2.6"},
            "investigate",
        )
        ai_engine.log_worker_usage(self.run_name, {}, "investigate")
        self.assertEqual(
            [(r.job, r.model) for r in self.rows()], [("investigate", "kimi-k2.6")]
        )

    def test_the_run_context_names_models_and_prices_never_keys(self):
        set_ai_providers(ai_jobs=[{"job": "review", "anthropic_model": "kimi-k2.7"}])
        models = ai_engine.worker_models()
        self.assertEqual(sorted(models), ["fix", "investigate", "review"])
        self.assertEqual(
            [m["section"] for m in models["fix"]], ["OpenAI", "Anthropic-compatible"]
        )
        self.assertEqual(models["review"][1]["model"], "kimi-k2.7")
        self.assertTrue(
            {"price_in", "price_out", "price_cached"} <= set(models["fix"][0])
        )
        text = json.dumps(models)
        self.assertNotIn("sk-", text)
        self.assertNotIn("api_key", text)


class TestThePage(AISettingsCase):
    def save(self, **values):
        return call_as_user(MANAGER[0], API + "save_settings", values=values)

    def test_one_row_per_job_with_a_model_and_shown_back(self):
        self.save(
            ai_jobs=[
                {"job": "summary", "openai_model": "  gpt-6-luna-test ", "anthropic_model": ""},
                {"job": "triage", "openai_model": "", "anthropic_model": ""},
                {"job": "not-a-job", "openai_model": "x"},
            ]
        )
        result = call_as_user(MANAGER[0], API + "get_settings")
        self.assertEqual(
            result["settings"]["ai_jobs"],
            [{"job": "summary", "openai_model": "gpt-6-luna-test", "anthropic_model": ""}],
        )
        # priced 0 until someone enters the price, so cost reports list it
        self.assertTrue(frappe.db.exists("HDS Model Pricing", "gpt-6-luna-test"))

    def test_a_save_without_the_table_keeps_it_and_an_empty_one_clears_it(self):
        self.save(ai_jobs=[{"job": "draft", "anthropic_model": "kimi-k2.7"}])
        self.save(ai_failover=1)
        self.assertEqual([row.job for row in frappe.get_doc(SETTINGS).ai_jobs], ["draft"])
        self.save(ai_jobs=[])
        self.assertEqual(frappe.get_doc(SETTINGS).ai_jobs, [])
