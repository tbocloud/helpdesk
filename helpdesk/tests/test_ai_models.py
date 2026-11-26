# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""AI Models (Phase 31): every attempt is recorded with its speed and, when it fails, the kind of
error; each job may choose its own first section and fallback; the pages read both per model."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import ai_engine, ai_models
from helpdesk.api import ai_models as api
from helpdesk.test_utils import (
    create_agent,
    hold_commits,
    openai_http_response,
    patch_anthropic_sdk,
    run_as_user,
    set_ai_providers,
)

LOG = "HDS AI Usage Log"


def log(model, job="triage", status="Success", ms=1200, **more):
    return frappe.get_doc(
        {
            "doctype": LOG,
            "model": model,
            "provider": "OpenAI",
            "job": job,
            "status": status,
            "duration_ms": ms,
            "estimated_cost_usd": 0.01,
            "input_tokens": 100,
            "output_tokens": 20,
            **more,
        }
    ).insert(ignore_permissions=True)


class ModelsCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.db.delete(LOG)
        for doctype in ("HDS Model Eval Run", "HDS AI Quality Event"):
            frappe.db.delete(doctype)
        # no job rows: each test starts from the settings' own order and fallback
        set_ai_providers(ai_jobs=[])


class TestEveryAttemptIsRecorded(ModelsCase):
    def test_a_success_has_its_speed(self):
        with patch("requests.post", return_value=openai_http_response(text="{}")):
            ai_engine.call_haiku("Answer in JSON", "hello", job="triage")

        row = frappe.get_last_doc(LOG)
        self.assertEqual((row.status, row.model), ("Success", "gpt-test-model"))
        self.assertEqual(row.source, "TBO Support")
        self.assertIsNotNone(row.duration_ms)
        self.assertFalse(row.error_class)

    def test_a_failure_is_a_row_and_the_fallback_answers(self):
        patch_anthropic_sdk(
            self,
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="{}")],
                usage=SimpleNamespace(input_tokens=5, output_tokens=5),
                stop_reason="end_turn",
            ),
        )
        refused = openai_http_response(
            429, {"error": {"message": "Rate limit reached for sk-secret-123456"}}
        )
        with patch("requests.post", return_value=refused):
            ai_engine.call_haiku("Answer in JSON", "hello", job="triage")

        rows = frappe.get_all(
            LOG,
            fields=["model", "status", "error_class", "error_message", "fallback"],
            order_by="creation asc",
        )
        self.assertEqual(
            [(r.model, r.status, r.fallback) for r in rows],
            [("gpt-test-model", "Failed", 0), ("kimi-k2.6", "Success", 1)],
        )
        self.assertEqual(rows[0].error_class, "rate_limit")
        self.assertIn("429", rows[0].error_message)
        self.assertNotIn("sk-secret-123456", rows[0].error_message)


class TestFallbackPerJob(ModelsCase):
    def order(self, job):
        return [p.slot for p in ai_engine.get_providers(job)]

    def test_a_job_chooses_its_first_section_and_its_fallback(self):
        set_ai_providers(
            ai_jobs=[
                {"job": "fix", "primary_section": "Anthropic-compatible"},
                {"job": "chat", "allow_fallback": "Off"},
            ]
        )
        self.assertEqual(self.order("triage"), ["OpenAI", "Anthropic-compatible"])
        self.assertEqual(self.order("fix"), ["Anthropic-compatible", "OpenAI"])
        self.assertEqual(self.order("chat"), ["OpenAI"])

    def test_a_job_may_fall_back_when_the_settings_say_no(self):
        set_ai_providers(
            ai_failover=0, ai_jobs=[{"job": "triage", "allow_fallback": "On"}]
        )
        self.assertEqual(self.order("triage"), ["OpenAI", "Anthropic-compatible"])
        self.assertEqual(self.order("draft"), ["OpenAI"])

    def test_the_worker_gets_each_jobs_own_order(self):
        set_ai_providers(
            ai_jobs=[
                {
                    "job": "fix",
                    "primary_section": "Anthropic-compatible",
                    "allow_fallback": "Off",
                }
            ]
        )
        models = ai_engine.worker_models()
        self.assertEqual([m["model"] for m in models["fix"]], ["kimi-k2.6"])
        self.assertEqual(len(models["investigate"]), 2)


class TestThePages(ModelsCase):
    def test_models_side_by_side(self):
        for ms in (1000, 2000, 3000, 9000):
            log("gpt-test-model", ms=ms)
        log("gpt-test-model", status="Failed", ms=400, error_class="timeout")
        log("kimi-k2.6", job="fix", fallback=1)

        result = ai_models.overview(30)
        gpt = next(m for m in result["models"] if m["model"] == "gpt-test-model")

        self.assertEqual((gpt["calls"], gpt["failed"], gpt["error_rate"]), (5, 1, 20.0))
        self.assertEqual((gpt["p50"], gpt["p95"]), (3.0, 9.0))
        self.assertEqual(gpt["cost"], 0.05)
        self.assertIn("triage", gpt["used_for"]["primary"])
        self.assertEqual(result["totals"]["calls"], 6)

    def test_a_model_with_many_errors_is_degraded(self):
        for i in range(20):
            log("gpt-test-model", status="Failed" if i < 3 else "Success")
        gpt = ai_models.overview(30)["models"][0]
        self.assertEqual((gpt["error_rate"], gpt["status"]), (15.0, "Degraded"))

    def test_one_models_errors_and_slowest_calls(self):
        log("gpt-test-model", ms=8000, job="draft")
        log("gpt-test-model", ms=900)
        log(
            "gpt-test-model",
            status="Failed",
            error_class="rate_limit",
            error_message="HTTP 429: slow down",
        )
        log("kimi-k2.6", fallback=1)

        result = ai_models.detail("gpt-test-model", 7)

        self.assertEqual(result["errors_by_kind"], [{"kind": "Rate limit", "count": 1}])
        self.assertEqual(result["latest_errors"][0]["message"], "HTTP 429: slow down")
        self.assertTrue(result["latest_errors"][0]["fallback_answered"])
        self.assertEqual(result["slowest"][0]["seconds"], 8.0)
        self.assertEqual(len(result["series"]), 7)
        self.assertEqual(result["series"][-1]["calls"], 3)
        self.assertEqual({j["name"] for j in result["by_job"]}, {"triage", "draft"})


class TestModelSettings(ModelsCase):
    def test_a_job_is_saved_and_the_change_is_kept(self):
        result = ai_models.save_job(
            "fix", {"primary_section": "Anthropic-compatible", "allow_fallback": "Off"}
        )

        fix = next(j for j in result["jobs"] if j["job"] == "fix")
        self.assertEqual(fix["primary"]["model"], "kimi-k2.6")
        self.assertIsNone(fix["fallback"])
        changes = {
            (c.setting, c.new_value) for c in result["changes"] if c.job == "fix"
        }
        self.assertEqual(
            changes, {("Primary section", "Anthropic-compatible"), ("Fallback", "Off")}
        )
        # saving the same again writes no history
        again = ai_models.save_job("fix", {"allow_fallback": "Off"})
        self.assertEqual(len(again["changes"]), len(result["changes"]))

    def test_what_is_refused(self):
        for job, values in (
            ("sing", {"allow_fallback": "On"}),
            ("fix", {"allow_fallback": "Maybe"}),
            ("fix", {"primary_section": "Mars"}),
            ("fix", {"openai_api_key": "x"}),
        ):
            with self.assertRaises(frappe.ValidationError, msg=values):
                ai_models.save_job(job, values)

    def test_the_older_settings_page_keeps_a_jobs_choices(self):
        from helpdesk.api import ai_settings

        ai_models.save_job("fix", {"allow_fallback": "Off"})
        ai_settings.save_settings(
            {"ai_jobs": [{"job": "fix", "openai_model": "gpt-6-luna"}]}
        )
        row = ai_engine.job_row("fix")
        self.assertEqual((row.allow_fallback, row.openai_model), ("Off", "gpt-6-luna"))

    def test_who_may_see_and_who_may_change(self):
        agent = create_agent("models.agent@example.com").name
        manager = create_agent("models.manager@example.com").name
        frappe.get_doc("User", manager).add_roles("Agent Manager")

        with self.assertRaises(frappe.PermissionError):
            run_as_user(agent, lambda: api.overview())
        self.assertIn("models", run_as_user(manager, lambda: api.overview()))
        self.assertFalse(run_as_user(manager, lambda: api.job_settings())["can_change"])
        with self.assertRaises(frappe.PermissionError):
            run_as_user(manager, lambda: api.save_job("fix", {"allow_fallback": "Off"}))


REPORT = [
    {
        "case": {"id": "A1", "ticket": "0218", "expected_root_cause": "bug"},
        "right": True,
        "confidence": 0.9,
        "filesFound": ["a.py", "b.py"],
        "summary": "A private diagnosis that must not be kept",
        "tokens": 1000,
        "costUsd": 0.5,
        "minutes": 4,
        "outcome": "submitted",
    },
    {"case": {"id": "A2"}, "right": False, "minutes": 6, "costUsd": 0.3},
]


class TestBenchmarks(ModelsCase):
    def test_a_report_is_kept_as_scores_only(self):
        name = ai_models.store_eval("gpt-test-model", REPORT, ran_on="2026-10-17")

        run = frappe.get_doc("HDS Model Eval Run", name)
        self.assertEqual((run.cases_total, run.cases_right, run.accuracy), (2, 1, 50.0))
        self.assertEqual((run.avg_minutes, run.total_cost_usd), (5.0, 0.8))
        self.assertEqual([r.case_id for r in run.results], ["A1", "A2"])
        self.assertEqual(run.results[0].files_found, 2)
        kept = frappe.as_json(run.as_dict())
        for private in ("private diagnosis", "0218", "expected_root_cause"):
            self.assertNotIn(private, kept)

    def test_head_to_head_and_the_score_on_the_comparison(self):
        ai_models.store_eval("gpt-test-model", REPORT)
        ai_models.store_eval("kimi-k2.6", [{**REPORT[0]}, {**REPORT[1], "right": True}])

        result = ai_models.benchmarks("gpt-test-model")

        self.assertEqual(result["runs"][0]["cost_per_right_case"], 0.8)
        self.assertEqual([c["right"] for c in result["cases"]], [True, False])
        self.assertEqual(result["against"], "kimi-k2.6")
        self.assertEqual([c["right"] for c in result["against_cases"]], [True, True])
        models = {m["model"]: m for m in ai_models.overview(30)["models"]}
        self.assertEqual(models["kimi-k2.6"]["benchmark"]["accuracy"], 100.0)

    def test_public_benchmarks_need_a_name_a_score_and_a_real_link(self):
        result = ai_models.add_public_benchmark(
            "gpt-test-model",
            {"benchmark": "tau2-bench", "score": "61%", "source_url": "https://x.test"},
        )
        self.assertEqual(result["public"][0]["benchmark"], "tau2-bench")
        for values in (
            {"benchmark": "x"},
            {"benchmark": "x", "score": "1", "source_url": "javascript:alert(1)"},
        ):
            with self.assertRaises(frappe.ValidationError):
                ai_models.add_public_benchmark("gpt-test-model", values)
        after = ai_models.remove_public_benchmark(result["public"][0]["name"])
        self.assertEqual(after["public"], [])

    def test_one_waiting_run_per_model(self):
        result = ai_models.request_eval("glm-5")
        self.assertEqual(result["requests"][0]["status"], "Queued")
        with self.assertRaises(frappe.ValidationError):
            ai_models.request_eval("glm-5")


class TestQuality(ModelsCase):
    def test_events_are_counted_per_model_and_never_break_the_caller(self):
        for kind in ("Answered", "Answered", "Hand-over", "Unsupported answer"):
            ai_models.record_event(kind, "gpt-test-model", job="chat")
        ai_models.record_event("Safety cut", "gpt-test-model", job="chat")
        ai_models.record_event("Not a kind", "gpt-test-model")
        with patch("frappe.get_doc", side_effect=RuntimeError("down")):
            ai_models.record_event("Answered", "gpt-test-model")

        result = ai_models.quality("gpt-test-model", 30)

        self.assertEqual(result["chat"]["replies"], 4)
        self.assertEqual(result["chat"]["answered_rate"], 50.0)
        self.assertEqual(result["hallucination"]["unsupported_rate"], 25.0)
        self.assertEqual(result["hallucination"]["safety_cuts"], 1)

    def test_missing_references_are_kept_on_the_run(self):
        from helpdesk.test_utils import make_copilot_run, make_ticket

        run = make_copilot_run(
            make_ticket(subject="Refs").name, "Explaining", model_used="kimi-k2.6"
        )
        ai_models.record_references(
            run.name,
            {
                "checked": 6,
                "missing": [{"kind": "file", "value": "app/gone.py"}, {"bad": 1}],
            },
        )

        run.reload()
        self.assertEqual((run.references_checked, run.references_missing), (6, 1))
        self.assertIn("app/gone.py", run.missing_references)
        result = ai_models.quality("kimi-k2.6", 30)
        self.assertEqual(result["hallucination"]["missing_reference_rate"], 100.0)
        self.assertEqual(result["copilot"]["runs"], 1)
