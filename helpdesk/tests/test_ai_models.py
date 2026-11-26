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
    anthropic_answer,
    create_agent,
    hold_commits,
    openai_http_response,
    patch_anthropic_sdk,
    run_as_user,
    set_ai_providers,
)

LOG = "HDS AI Usage Log"
PRICING = "HDS Model Pricing"
DEEPSEEK = "DeepSeek"
DEEPSEEK_KEY = "sk-deepseek-secret-123456"


def fresh_month():
    """Forget the counted tokens of the month, so the next count reads the log."""
    frappe.cache.delete_keys("ai_engine:month_tokens:")


def add_provider(
    name=DEEPSEEK,
    style="OpenAI-compatible",
    url="https://api.deepseek.test",
    key=DEEPSEEK_KEY,
    **more,
):
    return ai_models.save_provider(
        {"name": name, "style": style, "url": url, "key": key, "new": 1, **more}
    )


def add_model(model, provider, **more):
    return ai_models.save_model(
        {"model": model, "provider": provider, "listed": 1, "new": 1, **more}
    )


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
        for doctype in (
            "HDS Model Eval Run",
            "HDS Model Eval Request",
            "HDS AI Quality Event",
            "HDS Gateway Usage Day",
        ):
            frappe.db.delete(doctype)
        # an empty model list and no provider accounts
        frappe.db.delete(PRICING)
        frappe.db.delete("HDS AI Provider")
        ai_engine.forget_provider(DEEPSEEK)
        fresh_month()
        from helpdesk import ai_gateway

        frappe.cache.delete_value(
            [
                ai_gateway.ALIVE_KEY,
                ai_gateway.KEY_WORKS_KEY,
                ai_gateway.DOWN_KEY,
                ai_gateway.DOWN_ALERT_KEY,
            ]
        )
        # no job rows: each test starts from the settings' own order and fallback, the
        # providers called straight
        set_ai_providers(ai_jobs=[], gateway_for_all=0)


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


class TestProviders(ModelsCase):
    def test_a_provider_is_saved_and_its_key_never_comes_back(self):
        result = add_provider()

        deepseek = next(p for p in result["providers"] if p["name"] == DEEPSEEK)
        self.assertEqual(
            (
                deepseek["style"],
                deepseek["url"],
                deepseek["key_set"],
                deepseek["ready"],
            ),
            ("OpenAI-compatible", "https://api.deepseek.test", True, True),
        )
        self.assertEqual(
            [p["name"] for p in result["providers"]],
            ["OpenAI", "Anthropic-compatible", DEEPSEEK],
        )
        self.assertNotIn(DEEPSEEK_KEY, frappe.as_json(result))
        # saved again without a key, it keeps the one it has
        ai_models.save_provider(
            {"name": DEEPSEEK, "style": "OpenAI-compatible", "url": "https://x.test"}
        )
        provider = ai_engine.account_provider(DEEPSEEK, "deepseek-chat")
        self.assertEqual(
            (provider.api_key, provider.base_url, provider.budget_param),
            (DEEPSEEK_KEY, "https://x.test", "max_tokens"),
        )

    def test_what_a_provider_needs(self):
        for values in (
            {"name": "Mars", "style": "Mars", "url": "https://x.test"},
            {"name": "Plain", "style": "OpenAI-compatible", "url": "http://x.test"},
            {"name": "No address", "style": "OpenAI-compatible", "url": ""},
            {"name": "", "style": "OpenAI-compatible", "url": "https://x.test"},
        ):
            with self.assertRaises(frappe.ValidationError, msg=values):
                ai_models.save_provider({**values, "new": 1})
        add_provider()
        with self.assertRaises(frappe.ValidationError):
            add_provider()
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "HDS AI Provider",
                    "provider_name": "OpenAI",
                    "api_style": "OpenAI",
                    "base_url": "https://x.test",
                }
            ).insert(ignore_permissions=True)
        # Anthropic's own API needs no address
        add_provider("Claude", "Anthropic", "", "sk-ant-test-123456")
        claude = ai_engine.account_provider("Claude", "claude-sonnet-5-5")
        self.assertEqual((claude.kind, claude.base_url), ("Anthropic", None))

    def test_a_section_is_changed_from_here(self):
        result = ai_models.save_provider(
            {
                "name": "OpenAI",
                "url": "https://api.openai.com/v1",
                "key": "sk-proj-new-key-123456",
                "default_model": "gpt-6-luna",
            }
        )

        settings = frappe.get_doc("HDS Hub Settings")
        self.assertEqual(
            settings.get_password("openai_api_key"), "sk-proj-new-key-123456"
        )
        self.assertEqual(settings.openai_model, "gpt-6-luna")
        self.assertNotIn("sk-proj-new-key", frappe.as_json(result))
        with self.assertRaises(frappe.ValidationError):
            ai_models.remove_provider("OpenAI")

    def test_a_provider_a_job_uses_stays(self):
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        ai_models.save_job("task", {"model": "deepseek-chat"})
        with self.assertRaises(frappe.ValidationError):
            ai_models.remove_provider(DEEPSEEK)

        ai_models.save_job("task", {"model": ""})
        ai_models.remove_provider(DEEPSEEK)

        self.assertFalse(frappe.db.exists("HDS AI Provider", DEEPSEEK))
        listed, account = frappe.db.get_value(
            PRICING, "deepseek-chat", ["listed", "ai_provider"]
        )
        self.assertEqual((listed, account or ""), (0, ""))

    def test_a_provider_is_tested_with_its_first_model(self):
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        with patch(
            "requests.post", return_value=openai_http_response(text="OK")
        ) as post:
            result = ai_models.test_provider(DEEPSEEK)

        self.assertTrue(result["ok"], result)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-chat")
        add_provider("Empty", url="https://empty.test")
        self.assertIn("Add a model", ai_models.test_provider("Empty")["message"])


class TestTheModelList(ModelsCase):
    def setUp(self):
        super().setUp()
        add_provider()

    def test_what_the_list_refuses(self):
        for values in (
            {"model": "two words", "provider": DEEPSEEK},
            {"model": "glm-5", "provider": "Mars"},
            {"model": "glm-5", "provider": DEEPSEEK, "input_price": -1},
            {"model": "glm-5", "provider": DEEPSEEK, "limit_m": -2},
            {"model": "glm-5"},
        ):
            with self.assertRaises(frappe.ValidationError, msg=values):
                ai_models.save_model({**values, "new": 1})

    def test_a_listed_model_no_job_uses_is_a_candidate(self):
        result = add_model("deepseek-chat", DEEPSEEK, name="DeepSeek chat", limit_m=2)

        row = {m["model"]: m for m in result["catalog"]}["deepseek-chat"]
        self.assertEqual(
            (row["name"], row["provider"], row["listed"], row["limit_m"]),
            ("DeepSeek chat", DEEPSEEK, True, 2.0),
        )
        self.assertFalse(row["in_use"])
        listed = {m["model"]: m for m in ai_models.overview(30)["models"]}
        self.assertEqual(
            (listed["deepseek-chat"]["status"], listed["deepseek-chat"]["provider"]),
            ("Candidate", DEEPSEEK),
        )
        log("deepseek-chat", input_tokens=600_000, output_tokens=400_000)
        fresh_month()
        row = {m["model"]: m for m in ai_models.catalog()}["deepseek-chat"]
        self.assertEqual(row["used_m"], 1.0)

    def test_a_model_a_job_uses_stays_allowed(self):
        add_model("kimi-k2.6", "Anthropic-compatible")
        ai_models.save_job("chat", {"model": "kimi-k2.6"})

        for change in (
            lambda: ai_models.remove_model("kimi-k2.6"),
            lambda: ai_models.save_model({"model": "kimi-k2.6", "listed": 0}),
        ):
            with self.assertRaises(frappe.ValidationError):
                change()

    def test_removing_keeps_a_known_models_prices(self):
        add_model("never-used", DEEPSEEK)
        ai_models.remove_model("never-used")
        self.assertFalse(frappe.db.exists(PRICING, "never-used"))

        log("seen-model")
        add_model("seen-model", DEEPSEEK, input_price=1)
        ai_models.remove_model("seen-model")
        self.assertEqual(
            frappe.db.get_value(PRICING, "seen-model", ["listed", "input_cost_per_1m"]),
            (0, 1.0),
        )
        self.assertNotIn("seen-model", [m["model"] for m in ai_models.catalog()])


class TestModelAndBackupPerJob(ModelsCase):
    def setUp(self):
        super().setUp()
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        add_model("kimi-k2.6", "Anthropic-compatible")

    def chain(self, job):
        return [(p.slot, p.model) for p in ai_engine.get_providers(job)]

    def test_the_job_calls_its_model_then_its_backup(self):
        ai_models.save_job(
            "triage", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )
        patch_anthropic_sdk(self, anthropic_answer("{}"))
        busy = openai_http_response(500, {"error": {"message": "server busy"}})
        with patch("requests.post", return_value=busy) as post:
            result = ai_engine.call_haiku("Answer in JSON", "hello", job="triage")

        self.assertEqual(result["model"], "kimi-k2.6")
        self.assertEqual(
            post.call_args.args[0], "https://api.deepseek.test/chat/completions"
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], f"Bearer {DEEPSEEK_KEY}"
        )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "deepseek-chat")
        self.assertIn("max_tokens", body)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        rows = frappe.get_all(
            LOG,
            fields=["model", "provider", "status", "fallback"],
            order_by="creation asc",
        )
        self.assertEqual(
            [(r.model, r.provider, r.status, r.fallback) for r in rows],
            [
                ("deepseek-chat", DEEPSEEK, "Failed", 0),
                ("kimi-k2.6", "Anthropic-compatible", "Success", 1),
            ],
        )

    def test_a_used_up_limit_stops_the_job_and_the_backup_waits(self):
        ai_models.save_job(
            "triage", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )
        ai_models.save_model({"model": "deepseek-chat", "limit_m": 0.001})
        log("deepseek-chat", input_tokens=900, output_tokens=200)
        fresh_month()

        with patch("requests.post") as post, self.assertRaises(
            frappe.ValidationError
        ) as refused:
            ai_engine.call_haiku("Answer in JSON", "hello", job="triage")

        self.assertIn("monthly token limit", str(refused.exception))
        post.assert_not_called()
        # a backup past its own limit is left out; the model still answers
        ai_models.save_model({"model": "deepseek-chat", "limit_m": 0})
        ai_models.save_model({"model": "kimi-k2.6", "limit_m": 0.001})
        log("kimi-k2.6", input_tokens=2000)
        fresh_month()
        self.assertEqual(self.chain("triage"), [(DEEPSEEK, "deepseek-chat")])

    def test_only_allowed_models_and_both_empty_works_as_before(self):
        add_model("unticked", DEEPSEEK, listed=0)
        for values in (
            {"model": "unticked"},
            {"backup_model": "kimi-k2.6"},
            {"model": "kimi-k2.6", "backup_model": "kimi-k2.6"},
        ):
            with self.assertRaises(frappe.ValidationError, msg=values):
                ai_models.save_job("triage", values)

        ai_models.save_job(
            "triage", {"model": "kimi-k2.6", "backup_model": "deepseek-chat"}
        )
        self.assertEqual(
            self.chain("triage"),
            [("Anthropic-compatible", "kimi-k2.6"), (DEEPSEEK, "deepseek-chat")],
        )
        # back to the sections: the backup goes too, and the change is in the history
        result = ai_models.save_job("triage", {"model": ""})
        self.assertEqual(
            self.chain("triage"),
            [("OpenAI", "gpt-test-model"), ("Anthropic-compatible", "kimi-k2.6")],
        )
        self.assertEqual(ai_engine.job_row("triage").backup_model or "", "")
        settings = {(c.setting, c.new_value) for c in result["changes"]}
        self.assertIn(("Backup", "(default)"), settings)

    def test_a_provider_switched_off_leaves_the_backup(self):
        ai_models.save_job(
            "triage", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )
        ai_models.save_provider(
            {
                "name": DEEPSEEK,
                "style": "OpenAI-compatible",
                "url": "https://api.deepseek.test",
                "enabled": 0,
            }
        )
        self.assertEqual(self.chain("triage"), [("Anthropic-compatible", "kimi-k2.6")])

    def test_the_worker_gets_the_jobs_model_and_backup(self):
        ai_models.save_job(
            "investigate", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )
        ai_models.save_model(
            {"model": "deepseek-chat", "input_price": 0.28, "output_price": 0.42}
        )

        entries = ai_engine.worker_models()["investigate"]

        self.assertEqual(
            [(e["section"], e["model"]) for e in entries],
            [(DEEPSEEK, "deepseek-chat"), ("Anthropic-compatible", "kimi-k2.6")],
        )
        self.assertEqual(
            (entries[0]["price_in"], entries[0]["price_out"]), (0.28, 0.42)
        )
        self.assertNotIn(DEEPSEEK_KEY, frappe.as_json(ai_engine.worker_models()))

    def test_the_older_settings_page_keeps_the_jobs_model(self):
        from helpdesk.api import ai_settings

        ai_models.save_job(
            "chat", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )
        ai_settings.save_settings(
            {"ai_jobs": [{"job": "chat", "openai_model": "gpt-6-luna"}]}
        )
        row = ai_engine.job_row("chat")
        self.assertEqual(
            (row.model, row.backup_model, row.openai_model),
            ("deepseek-chat", "kimi-k2.6", "gpt-6-luna"),
        )

    def test_the_page_shows_the_jobs_model_but_never_a_key(self):
        ai_models.save_job(
            "chat", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )

        result = ai_models.job_settings()

        chat = next(j for j in result["jobs"] if j["job"] == "chat")
        self.assertEqual(
            (chat["model"], chat["primary"]["section"], chat["fallback"]["model"]),
            ("deepseek-chat", DEEPSEEK, "kimi-k2.6"),
        )
        in_use = {m["model"]: m["in_use"] for m in result["catalog"]}
        self.assertTrue(in_use["deepseek-chat"])
        for secret in (DEEPSEEK_KEY, "sk-test", "sk-ant"):
            self.assertNotIn(secret, frappe.as_json(result))


class TestEveryApplication(ModelsCase):
    def setUp(self):
        super().setUp()
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        add_model("kimi-k2.6", "Anthropic-compatible")

    def test_the_page_shows_every_application_and_its_purposes(self):
        result = ai_models.job_settings()

        self.assertEqual(
            [a["name"] for a in result["applications"]],
            ["TBO Support", "Copilot worker", "Desktop app", "Inbox"],
        )
        jobs = {j["job"]: j for j in result["jobs"]}
        simple = jobs["desktop_simple"]
        self.assertEqual(
            (simple["application"], simple["label"]), ("Desktop app", "Simple")
        )
        # a level without a model leaves the gateway's own models; nothing of the sections
        self.assertIsNone(simple["primary"])
        self.assertTrue(jobs["inbox_reply"]["coming"])
        self.assertIsNone(jobs["inbox_reply"]["primary"])
        # TBO Support's jobs still follow the sections
        self.assertEqual(jobs["triage"]["primary"]["model"], "gpt-test-model")

    def test_a_desktop_level_takes_a_model_and_a_backup_only(self):
        result = ai_models.save_job(
            "desktop_hard", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )

        hard = next(j for j in result["jobs"] if j["job"] == "desktop_hard")
        self.assertEqual(
            (hard["primary"]["model"], hard["fallback"]["model"]),
            ("deepseek-chat", "kimi-k2.6"),
        )
        with self.assertRaises(frappe.ValidationError):
            ai_models.save_job("desktop_hard", {"primary_section": "OpenAI"})
        # the model list says where each model is used, per application
        used = {m["model"]: m["used_by"] for m in result["catalog"]}
        self.assertIn(
            {"application": "Desktop app", "first": ["Hard"], "backup": []},
            used["deepseek-chat"],
        )
        self.assertIn(
            {"application": "Desktop app", "first": [], "backup": ["Hard"]},
            used["kimi-k2.6"],
        )
        # and the comparison names the level with its application
        listed = {m["model"]: m for m in ai_models.overview(30)["models"]}
        self.assertIn(
            "Desktop app: Hard", listed["deepseek-chat"]["used_for"]["primary"]
        )

    def test_an_inbox_purpose_waits_for_its_phase(self):
        with self.assertRaises(frappe.ValidationError):
            ai_models.save_job("inbox_reply", {"model": "deepseek-chat"})
        with self.assertRaises(frappe.ValidationError):
            ai_models.try_job("inbox_reply")
        self.assertEqual(ai_engine.get_providers("inbox_reply"), [])

    def test_trying_a_level_without_a_model_says_so(self):
        self.assertIn("Choose a model", ai_models.try_job("desktop_simple")["message"])
        self.assertEqual(ai_engine.get_providers("desktop_simple"), [])

    def test_the_older_settings_page_keeps_the_desktop_levels(self):
        from helpdesk.api import ai_settings

        ai_models.save_job("desktop_medium", {"model": "deepseek-chat"})
        ai_settings.save_settings(
            {"ai_jobs": [{"job": "chat", "openai_model": "gpt-6-luna"}]}
        )

        self.assertEqual(ai_engine.job_row("desktop_medium").model, "deepseek-chat")
        self.assertEqual(ai_engine.job_row("chat").openai_model, "gpt-6-luna")

    def test_a_provider_keeps_its_note_and_bedrock_is_a_preset(self):
        result = add_provider("Mine", note="The data stays in our account.")

        mine = next(p for p in result["providers"] if p["name"] == "Mine")
        self.assertEqual(mine["note"], "The data stays in our account.")
        presets = {p["name"]: p for p in result["presets"]}
        self.assertEqual(presets["AWS Bedrock"]["style"], "AWS Bedrock")
        self.assertIn("China", presets["DeepSeek"]["note"])


GATEWAY = "https://gw.test"
GATEWAY_KEY = "sk-tbo-support-gateway-0001"


def answered(status=200, body=None):
    from unittest.mock import MagicMock

    return MagicMock(
        ok=status < 400, status_code=status, json=MagicMock(return_value=body or {})
    )


class TestEverythingThroughTheGateway(ModelsCase):
    def setUp(self):
        super().setUp()
        from helpdesk import ai_gateway

        self.gw = ai_gateway
        doc = frappe.get_doc("HDS Hub Settings")
        doc.update(
            {
                "gateway_url": GATEWAY,
                "gateway_key": GATEWAY_KEY,
                "gateway_admin_key": "sk-gateway-admin-0001",
                "gateway_for_all": 1,
            }
        )
        doc.save(ignore_permissions=True)
        # the gateway answers unless a test says otherwise
        frappe.cache.set_value(ai_gateway.ALIVE_KEY, 1)
        frappe.cache.set_value(ai_gateway.KEY_WORKS_KEY, 1)
        ai_engine.forget_provider(ai_gateway.SLOT)
        self.admin = patch("requests.request", return_value=answered())
        self.admin_calls = self.admin.start()
        self.addCleanup(self.admin.stop)

    def admin_paths(self):
        return [
            (c.args[0], c.args[1].replace(GATEWAY, ""))
            for c in self.admin_calls.call_args_list
        ]

    def admin_body(self, path):
        return next(
            c.kwargs["json"]
            for c in self.admin_calls.call_args_list
            if c.args[1] == GATEWAY + path and c.args[0] == "POST"
        )

    def test_every_call_goes_to_the_gateway_with_tbo_supports_key(self):
        with patch(
            "requests.post", return_value=openai_http_response(text="{}")
        ) as post:
            ai_engine.call_haiku("Answer in JSON", "hello", job="triage")

        self.assertEqual(post.call_args.args[0], GATEWAY + "/v1/chat/completions")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], f"Bearer {GATEWAY_KEY}"
        )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "gpt-test-model")
        self.assertIn("max_tokens", body)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        row = frappe.get_last_doc(LOG)
        self.assertEqual(
            (row.provider, row.model, row.status),
            (self.gw.SLOT, "gpt-test-model", "Success"),
        )

    def test_the_backup_is_tried_through_the_gateway_too(self):
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        add_model("kimi-k2.6", "Anthropic-compatible")
        ai_models.save_job(
            "chat", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )
        busy = openai_http_response(429, {"error": {"message": "slow down"}})
        with patch(
            "requests.post", side_effect=[busy, openai_http_response(text="{}")]
        ) as post:
            result = ai_engine.call_haiku("Answer in JSON", "hello", job="chat")

        self.assertEqual(result["model"], "kimi-k2.6")
        self.assertEqual(
            [(c.args[0], c.kwargs["json"]["model"]) for c in post.call_args_list],
            [
                (GATEWAY + "/v1/chat/completions", "deepseek-chat"),
                (GATEWAY + "/v1/chat/completions", "kimi-k2.6"),
            ],
        )

    def test_when_the_gateway_does_not_answer_the_emergency_key_answers(self):
        import requests

        down = requests.ConnectionError("no route")
        with patch("helpdesk.ai_engine.send_provider_alert") as alert, patch(
            "requests.get", side_effect=down
        ), patch(
            "requests.post", side_effect=[down, openai_http_response(text="{}")]
        ) as post:
            first = ai_engine.call_haiku("Answer in JSON", "hello", job="triage")

        self.assertEqual(
            post.call_args_list[0].args[0], GATEWAY + "/v1/chat/completions"
        )
        # the emergency key: TBO Support's own OpenAI section, straight to OpenAI
        self.assertEqual(
            post.call_args_list[1].args[0], "https://api.openai.com/v1/chat/completions"
        )
        self.assertEqual(first["model"], "gpt-test-model")
        alert.assert_called_once()
        self.assertIn("emergency key", alert.call_args.args[0])
        self.assertTrue(frappe.cache.get_value(self.gw.DOWN_KEY))
        # the next call goes straight to the emergency key, and nobody is told twice
        with patch("helpdesk.ai_engine.send_provider_alert") as again, patch(
            "requests.post", return_value=openai_http_response(text="{}")
        ) as post:
            ai_engine.call_haiku("Answer in JSON", "hello", job="triage")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(
            post.call_args.args[0], "https://api.openai.com/v1/chat/completions"
        )
        again.assert_not_called()

    def test_a_refused_tbo_support_key_uses_the_emergency_key_too(self):
        frappe.cache.delete_value(self.gw.KEY_WORKS_KEY)
        refused = openai_http_response(401, {"error": {"message": "invalid proxy key"}})
        with patch("helpdesk.ai_engine.send_provider_alert"), patch(
            "requests.get", return_value=answered(401)
        ), patch(
            "requests.post", side_effect=[refused, openai_http_response(text="{}")]
        ) as post:
            ai_engine.call_haiku("Answer in JSON", "hello", job="triage")

        self.assertEqual(
            post.call_args_list[1].args[0], "https://api.openai.com/v1/chat/completions"
        )

    def test_the_watch_tells_when_it_stops_and_when_it_answers_again(self):
        import requests

        with patch("helpdesk.ai_engine.send_provider_alert") as alert:
            with patch("requests.get", side_effect=requests.ConnectionError("down")):
                self.assertEqual(self.gw.watch(), "down")
                self.assertEqual(self.gw.watch(), "down")
            self.assertEqual(alert.call_count, 1)
            with patch("requests.get", return_value=answered()):
                self.assertEqual(self.gw.watch(), "back")
                self.assertEqual(self.gw.watch(), "up")
        self.assertEqual(alert.call_count, 2)
        self.assertIn("answers again", alert.call_args.args[0])

    def test_a_providers_key_goes_to_the_gateway_and_is_not_kept(self):
        from frappe.utils.password import get_decrypted_password

        result = add_provider()

        self.assertIn(("DELETE", "/credentials/DeepSeek"), self.admin_paths())
        body = self.admin_body("/credentials")
        self.assertEqual(body["credential_name"], DEEPSEEK)
        self.assertEqual(
            body["credential_values"],
            {"api_key": DEEPSEEK_KEY, "api_base": "https://api.deepseek.test"},
        )
        self.assertIsNone(
            get_decrypted_password(
                "HDS AI Provider", DEEPSEEK, "api_key", raise_exception=False
            )
        )
        deepseek = next(p for p in result["providers"] if p["name"] == DEEPSEEK)
        self.assertEqual((deepseek["key_on_gateway"], deepseek["ready"]), (True, True))
        self.assertNotIn(DEEPSEEK_KEY, frappe.as_json(result))

    def test_an_allowed_model_is_written_and_an_unticked_one_leaves(self):
        add_provider()
        add_provider("Bedrock", "AWS Bedrock", "", "")
        add_model("deepseek-chat", DEEPSEEK)
        self.assertEqual(
            self.admin_body("/model/new"),
            {
                "model_name": "deepseek-chat",
                "litellm_params": {
                    "model": "openai/deepseek-chat",
                    "litellm_credential_name": DEEPSEEK,
                },
                "model_info": {
                    "id": "tbo-support:deepseek-chat",
                    "written_by": "TBO Support",
                },
            },
        )
        self.assertEqual(frappe.db.get_value(PRICING, "deepseek-chat", "on_gateway"), 1)
        self.admin_calls.reset_mock()
        add_model("gpt-x", "OpenAI")
        self.assertEqual(
            self.admin_body("/model/new")["litellm_params"],
            {"model": "openai/gpt-x", "api_key": "os.environ/OPENAI_API_KEY"},
        )
        self.admin_calls.reset_mock()
        add_model("deepseek.v3.2", "Bedrock")
        self.assertEqual(
            self.admin_body("/model/new")["litellm_params"],
            {
                "model": "bedrock/converse/deepseek.v3.2",
                "aws_region_name": "ap-south-1",
            },
        )
        self.admin_calls.reset_mock()
        ai_models.save_model({"model": "deepseek-chat", "listed": 0})
        self.assertEqual(
            self.admin_body("/model/delete"), {"id": "tbo-support:deepseek-chat"}
        )
        self.assertEqual(frappe.db.get_value(PRICING, "deepseek-chat", "on_gateway"), 0)

    def test_write_all_moves_the_keys_and_the_models(self):
        from frappe.utils.password import get_decrypted_password

        frappe.db.set_single_value("HDS Hub Settings", "gateway_for_all", 0)
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        self.assertEqual(self.admin_calls.call_count, 0)
        frappe.db.set_single_value("HDS Hub Settings", "gateway_for_all", 1)

        result = ai_models.write_all()

        self.assertEqual(result["written"], {"keys": 1, "models": 1})
        self.assertEqual(
            self.admin_body("/credentials")["credential_values"]["api_key"],
            DEEPSEEK_KEY,
        )
        self.assertEqual(self.admin_body("/model/new")["model_name"], "deepseek-chat")
        self.assertIsNone(
            get_decrypted_password(
                "HDS AI Provider", DEEPSEEK, "api_key", raise_exception=False
            )
        )

    def test_the_switch_turns_on_only_when_the_gateway_answers_and_takes_the_key(self):
        frappe.db.set_single_value("HDS Hub Settings", "gateway_for_all", 0)
        with patch("requests.get", side_effect=[answered(), answered(401)]):
            with self.assertRaises(frappe.ValidationError) as refused:
                ai_models.save_gateway({"for_all": 1})
        self.assertIn("refused", str(refused.exception))
        with patch("requests.get", side_effect=[answered(), answered()]):
            status = ai_models.save_gateway({"for_all": 1})
        self.assertTrue(status["for_all"])

    def test_turning_it_on_makes_tbo_supports_own_key(self):
        doc = frappe.get_doc("HDS Hub Settings")
        doc.update({"gateway_for_all": 0, "gateway_key": ""})
        doc.save(ignore_permissions=True)
        self.admin_calls.return_value = answered(body={"key": "sk-made-by-the-gateway"})

        with patch("requests.get", side_effect=[answered(), answered()]):
            status = ai_models.save_gateway({"for_all": 1})

        self.assertTrue(status["for_all"])
        self.assertEqual(self.gw.call_key(), "sk-made-by-the-gateway")
        alias = self.admin_body("/key/generate")["key_alias"]
        self.assertTrue(alias.startswith("tbo-support:"), alias)
        self.assertNotIn("sk-made-by-the-gateway", frappe.as_json(status))

    def test_the_worker_is_sent_to_the_gateway(self):
        entries = ai_engine.worker_models()["investigate"]

        self.assertEqual(
            [(e["section"], e["model"]) for e in entries],
            [(self.gw.SLOT, "gpt-test-model"), (self.gw.SLOT, "kimi-k2.6")],
        )

    def test_the_usage_read_from_the_gateway_is_the_desktop_apps_only(self):
        def call(alias):
            return {
                "model": "openai/gpt-5.6-luna",
                "model_group": "tbo-default",
                "user": "dev@example.com",
                "spend": 0.01,
                "metadata": {"user_api_key_alias": alias} if alias else {},
            }

        totals = self.gw.totals([call("desktop:abc"), call("tbo-support"), call("")])

        self.assertEqual(sum(t["requests"] for t in totals.values()), 2)


class TestDesktopLevels(ModelsCase):
    def setUp(self):
        super().setUp()
        doc = frappe.get_doc("HDS Hub Settings")
        doc.update(
            {"gateway_url": GATEWAY, "gateway_admin_key": "sk-gateway-admin-0001"}
        )
        doc.save(ignore_permissions=True)
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        add_model("gpt-test-model", "OpenAI")
        self.admin = patch("requests.request", return_value=answered())
        self.calls = self.admin.start()
        self.addCleanup(self.admin.stop)

    def sent(self, path):
        return [
            c.kwargs["json"]
            for c in self.calls.call_args_list
            if c.args[1] == GATEWAY + path
        ]

    def test_a_level_is_one_gateway_name_with_its_model_then_its_backup(self):
        from frappe.utils.password import get_decrypted_password

        result = ai_models.save_job(
            "desktop_simple",
            {"model": "deepseek-chat", "backup_model": "gpt-test-model"},
        )

        self.assertEqual(
            self.sent("/model/delete"),
            [
                {"id": "tbo-support:tbo-simple:1"},
                {"id": "tbo-support:tbo-simple:2"},
                {"id": "tbo-support:tbo-simple:1"},
                {"id": "tbo-support:tbo-simple:2"},
            ],
        )
        written = self.sent("/model/new")
        self.assertEqual(
            [w["model_name"] for w in written], ["tbo-simple", "tbo-simple"]
        )
        self.assertEqual(
            [w["litellm_params"] for w in written],
            [
                {
                    "model": "openai/deepseek-chat",
                    "litellm_credential_name": DEEPSEEK,
                    "order": 1,
                },
                {
                    "model": "openai/gpt-test-model",
                    "api_key": "os.environ/OPENAI_API_KEY",
                    "order": 2,
                },
            ],
        )
        self.assertEqual(
            [w["model_info"]["id"] for w in written],
            ["tbo-support:tbo-simple:1", "tbo-support:tbo-simple:2"],
        )
        # DeepSeek's key reached the gateway; TBO Support still calls DeepSeek itself, so it keeps it too
        self.assertEqual(self.sent("/credentials")[0]["credential_name"], DEEPSEEK)
        self.assertTrue(
            get_decrypted_password(
                "HDS AI Provider", DEEPSEEK, "api_key", raise_exception=False
            )
        )
        simple = next(j for j in result["jobs"] if j["job"] == "desktop_simple")
        self.assertEqual(simple["gateway_name"], "tbo-simple")

    def test_a_cleared_level_leaves_the_gateway(self):
        ai_models.save_job("desktop_hard", {"model": "deepseek-chat"})
        self.calls.reset_mock()

        ai_models.save_job("desktop_hard", {"model": ""})

        self.assertEqual(
            self.sent("/model/delete"),
            [{"id": "tbo-support:tbo-hard:1"}, {"id": "tbo-support:tbo-hard:2"}],
        )
        self.assertEqual(self.sent("/model/new"), [])

    def test_without_an_admin_key_nothing_is_sent(self):
        frappe.db.set_single_value("HDS Hub Settings", "gateway_url", "")
        ai_models.save_job("desktop_medium", {"model": "deepseek-chat"})
        self.assertEqual(self.calls.call_count, 0)
        self.assertEqual(ai_engine.job_row("desktop_medium").model, "deepseek-chat")

    def test_the_names_peoples_desktop_keys_may_use(self):
        self.assertEqual(
            ai_models.merged_names("", "tbo-simple", True), "tbo-default\ntbo-simple"
        )
        self.assertIsNone(
            ai_models.merged_names("tbo-default\ntbo-simple", "tbo-simple", True)
        )
        self.assertEqual(
            ai_models.merged_names("tbo-default\ntbo-simple", "tbo-simple", False),
            "tbo-default",
        )
        self.assertIsNone(ai_models.merged_names("tbo-default", "tbo-hard", False))


FULL_MARKS = [{**REPORT[0]}, {**REPORT[1], "right": True}]


class TestTheGuard(ModelsCase):
    def test_the_guard_warns_before_copilot_gets_an_untested_or_weaker_model(self):
        change = {"primary_section": "Anthropic-compatible"}
        ai_models.store_eval("gpt-test-model", FULL_MARKS, ran_on="2026-10-01")

        untested = ai_models.guard("fix", change)
        self.assertEqual(
            (untested["current_model"], untested["model"]),
            ("gpt-test-model", "kimi-k2.6"),
        )
        self.assertIn("no run of the test set", untested["warning"])

        ai_models.store_eval("kimi-k2.6", REPORT, ran_on="2026-10-02")
        weaker = ai_models.guard("fix", change)
        self.assertEqual(weaker["score"]["accuracy"], 50.0)
        self.assertIn("50.0%", weaker["warning"])
        self.assertIn("100.0%", weaker["warning"])

        ai_models.store_eval("kimi-k2.6", FULL_MARKS, ran_on="2026-10-03")
        self.assertEqual(ai_models.guard("fix", change)["warning"], "")
        # TBO Support's own jobs are not guarded, and a change that keeps the model is not one
        ai_models.store_eval("kimi-k2.6", REPORT, ran_on="2026-10-04")
        self.assertEqual(ai_models.guard("triage", change)["warning"], "")
        same = ai_models.guard("fix", {"allow_fallback": "Off"})
        self.assertEqual((same["changes_model"], same["warning"]), (False, ""))
        # the guard saves nothing
        self.assertIsNone(ai_engine.job_row("fix"))

    def test_the_guard_looks_at_a_jobs_own_model(self):
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        ai_models.store_eval("gpt-test-model", FULL_MARKS)

        result = ai_models.guard("fix", {"model": "deepseek-chat"})

        self.assertEqual(
            (result["current_model"], result["model"]),
            ("gpt-test-model", "deepseek-chat"),
        )
        self.assertIn("no run of the test set", result["warning"])

    def test_only_system_managers_change_providers_and_the_list(self):
        manager = create_agent("models.manager2@example.com").name
        frappe.get_doc("User", manager).add_roles("Agent Manager")
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)

        for change in (
            lambda: api.save_provider(
                {"name": "Qwen", "style": "OpenAI-compatible", "url": "https://q.test"}
            ),
            lambda: api.remove_provider(DEEPSEEK),
            lambda: api.test_provider(DEEPSEEK),
            lambda: api.save_model({"model": "glm-6", "provider": DEEPSEEK}),
            lambda: api.remove_model("deepseek-chat"),
            lambda: api.save_alerts({"error_rate": 5}),
        ):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(manager, change)
        # a manager sees the page, never a key, and may ask what a change would do
        seen = run_as_user(manager, lambda: api.job_settings())
        self.assertNotIn(DEEPSEEK_KEY, frappe.as_json(seen))
        self.assertIn("warning", run_as_user(manager, lambda: api.guard("fix", {})))


class TestAlerts(ModelsCase):
    def setUp(self):
        super().setUp()
        self.forget()
        self.addCleanup(self.forget)
        ai_models.save_alerts({"error_rate": 20, "fallback_rate": 30})

    def forget(self):
        frappe.cache.delete_value(
            [
                ai_models.ALERT_KEY.format(key)
                for key in ("errors:gpt-test-model", "errors:kimi-k2.6", "fallback")
            ]
        )
        frappe.cache.delete_keys(ai_models.ALERT_KEY.format("limit:"))

    def test_a_model_near_or_past_its_monthly_limit_alerts_once_a_month(self):
        add_provider()
        add_model("deepseek-chat", DEEPSEEK, limit_m=1)
        log("deepseek-chat", input_tokens=850_000, output_tokens=0)
        fresh_month()

        with patch("helpdesk.ai_models.send_alert") as send:
            first = ai_models.watch()
            again = ai_models.watch()

        self.assertEqual(len(first), 1)
        self.assertIn("85%", first[0])
        self.assertEqual(again, [])
        send.assert_called_once()
        log("deepseek-chat", input_tokens=200_000)
        fresh_month()
        with patch("helpdesk.ai_models.send_alert"):
            used_up = ai_models.watch()
        self.assertEqual(len(used_up), 1)
        self.assertIn("has used its monthly token limit", used_up[0])

    def test_a_failing_model_alerts_once(self):
        for i in range(12):
            log("gpt-test-model", status="Failed" if i < 4 else "Success")
        # too few calls to say anything
        log("kimi-k2.6", status="Failed")

        with patch("helpdesk.ai_models.send_alert") as send:
            first = ai_models.watch()
            second = ai_models.watch()

        self.assertEqual(len(first), 1)
        self.assertIn("gpt-test-model", first[0])
        self.assertIn("33.3%", first[0])
        self.assertEqual(second, [])
        send.assert_called_once()

    def test_the_fallback_answering_too_often_alerts(self):
        for i in range(10):
            log("kimi-k2.6", fallback=1 if i < 4 else 0)

        with patch("helpdesk.ai_models.send_alert"):
            sent = ai_models.watch()

        self.assertEqual(len(sent), 1)
        self.assertIn("40.0%", sent[0])

    def test_older_calls_and_a_limit_of_0_do_not_alert(self):
        rows = [log("gpt-test-model", status="Failed") for _ in range(12)]
        with patch("helpdesk.ai_models.send_alert") as send:
            ai_models.save_alerts({"error_rate": 0, "fallback_rate": 0})
            self.assertEqual(ai_models.watch(), [])
            ai_models.save_alerts({"error_rate": 20})
            for row in rows:
                frappe.db.set_value(
                    LOG,
                    row.name,
                    "creation",
                    frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-2),
                    update_modified=False,
                )
            self.assertEqual(ai_models.watch(), [])
        send.assert_not_called()

    def test_a_limit_is_a_percentage_and_a_failed_send_never_raises(self):
        for values in ({"error_rate": 101}, {"fallback_rate": -1}):
            with self.assertRaises(frappe.ValidationError):
                ai_models.save_alerts(values)
        self.assertEqual(
            ai_models.job_settings()["alerts"], {"error_rate": 20, "fallback_rate": 30}
        )
        for _ in range(12):
            log("gpt-test-model", status="Failed")
        with patch("helpdesk.ai_models.send_alert", side_effect=RuntimeError("down")):
            self.assertEqual(ai_models.watch(), [])


DRAFT = (
    "Hello Asha, thank you for writing to us. The invoice total was wrong because the tax "
    "template was missing on the item. We have added the template and the total is right now. "
    "Please open the invoice again and tell us if anything still looks wrong."
)


class TestDraftsAndCustomerAnswers(ModelsCase):
    def setUp(self):
        super().setUp()
        from helpdesk.test_utils import make_ticket

        self.ticket = make_ticket(subject="Draft").name
        key = ai_models.DRAFT_KEY.format(self.ticket, frappe.session.user)
        frappe.cache.delete_value(key)
        self.addCleanup(frappe.cache.delete_value, key)

    def send(self, content, direction="Sent"):
        from helpdesk.test_utils import make_ticket_communication

        make_ticket_communication(
            self.ticket, content, "agent@example.com", sent_or_received=direction
        )

    def drafts(self):
        return ai_models.quality("gpt-test-model", 30)["drafts"]

    def test_a_draft_sent_as_written_changed_or_not_at_all(self):
        ai_models.note_draft(self.ticket, "gpt-test-model", DRAFT)
        # a redraft of a waiting draft is the same draft, and a customer's mail is not a reply
        ai_models.note_draft(self.ticket, "gpt-test-model", DRAFT + " Thank you.")
        self.send(DRAFT, "Received")
        self.send(f"<p>{DRAFT} Thank you.</p><p>Regards,<br>Sam, TBO</p>")
        self.assertEqual((self.drafts()["made"], self.drafts()["used"]), (1, 1))

        ai_models.note_draft(self.ticket, "gpt-test-model", DRAFT)
        half = DRAFT.split(" We have added")[0]
        self.send(f"<p>{half} I will call you at 3 pm to go through it together.</p>")
        ai_models.note_draft(self.ticket, "gpt-test-model", DRAFT)
        self.send("<p>Please send us a screenshot of the error.</p>")
        # nothing waits any more, so this reply is compared with nothing
        self.send(f"<p>{DRAFT}</p>")

        result = self.drafts()
        self.assertEqual(
            (result["made"], result["used"], result["changed"], result["not_used"]),
            (3, 1, 1, 1),
        )
        self.assertEqual(result["used_rate"], 33.3)

    def test_only_checksums_of_a_draft_are_kept(self):
        ai_models.note_draft(self.ticket, "gpt-test-model", DRAFT)

        kept = frappe.cache.get_value(
            ai_models.DRAFT_KEY.format(self.ticket, frappe.session.user)
        )
        self.assertEqual(kept["model"], "gpt-test-model")
        self.assertTrue(all(isinstance(mark, int) for mark in kept["marks"]))
        self.assertNotIn("invoice", frappe.as_json(kept))
        event = frappe.get_last_doc("HDS AI Quality Event")
        self.assertEqual(
            (event.kind, event.ticket, event.detail), ("Draft made", self.ticket, "")
        )

    def test_the_draft_button_notes_its_draft(self):
        from helpdesk.api import ticket_ai

        answer = {"response": {"reply": DRAFT}, "model": "gpt-test-model"}
        with patch("helpdesk.api.ticket_ai.call_haiku", return_value=answer):
            reply = ticket_ai.draft_reply(self.ticket)["reply"]

        self.assertIn("Hello Asha", reply)
        self.assertEqual(self.drafts()["made"], 1)

    def test_a_reply_goes_out_when_the_comparison_fails(self):
        ai_models.note_draft(self.ticket, "gpt-test-model", DRAFT)
        with patch("helpdesk.ai_models.shingles", side_effect=RuntimeError("down")):
            self.send(f"<p>{DRAFT}</p>")
        self.assertEqual(self.drafts()["used"], 0)

    def test_still_broken_is_the_share_of_customers_who_said_so(self):
        from helpdesk.test_utils import make_copilot_run, make_ticket

        for answer in ("Confirmed", "Reopened", "Reopened", ""):
            ticket = make_ticket(subject=f"Answer {answer}").name
            frappe.db.set_value(
                "HD Ticket", ticket, "custom_customer_confirmation", answer
            )
            make_copilot_run(ticket, "Explaining", model_used="kimi-k2.6")

        result = ai_models.quality("kimi-k2.6", 30)["copilot"]

        self.assertEqual(
            (
                result["customer_answers"],
                result["still_broken"],
                result["still_broken_rate"],
            ),
            (3, 2, 66.7),
        )


class TestTheTestSetHandOff(ModelsCase):
    def test_a_report_answers_the_models_request(self):
        ai_models.request_eval("glm-5")

        result = api.import_eval("glm-5", REPORT)

        self.assertEqual(result["requests"], [])
        self.assertEqual(result["runs"][0]["source"], "Imported")
        request = frappe.get_last_doc("HDS Model Eval Request")
        self.assertEqual(
            (request.status, request.eval_run), ("Done", result["runs"][0]["name"])
        )

    def test_a_request_can_be_taken_back_until_it_is_answered(self):
        name = ai_models.request_eval("glm-5")["requests"][0]["name"]

        self.assertEqual(ai_models.withdraw_eval_request(name)["requests"], [])

        name = ai_models.request_eval("glm-5")["requests"][0]["name"]
        api.import_eval("glm-5", REPORT)
        with self.assertRaises(frappe.ValidationError):
            ai_models.withdraw_eval_request(name)


def gateway_call(
    model="openai/gpt-5.6-luna",
    alias="tbo-default",
    user="dev@example.com",
    ms=2000,
    **more,
):
    return {
        "request_id": frappe.generate_hash(length=8),
        "model": model,
        "model_group": alias,
        "custom_llm_provider": model.split("/")[0] if "/" in model else "",
        "user": user,
        "spend": 0.02,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "request_duration_ms": ms,
        "status": "success",
        "messages": "A PROMPT THAT MUST NOT BE KEPT",
        **more,
    }


class TestTheGateway(ModelsCase):
    def setUp(self):
        super().setUp()
        from helpdesk import ai_gateway

        self.gw = ai_gateway
        frappe.db.delete("HDS Gateway Usage Day")
        doc = frappe.get_doc("HDS Hub Settings")
        doc.update(
            {
                "gateway_sync": 1,
                "gateway_url": "https://ai.example.com",
                "gateway_viewer_key": "sk-viewer-test",
            }
        )
        doc.save(ignore_permissions=True)

    def answer(self, calls, status=200):
        from unittest.mock import MagicMock

        return MagicMock(
            ok=status < 400,
            status_code=status,
            json=MagicMock(return_value={"data": calls, "total_pages": 1}),
        )

    def test_calls_become_totals_per_day_model_and_person(self):
        failed = gateway_call(
            status="failure",
            metadata={"error_information": {"error_class": "RateLimitError"}},
        )
        calls = [gateway_call(ms=1000), gateway_call(ms=3000), failed]
        calls.append(gateway_call(user="lead@example.com"))
        with patch("requests.get", return_value=self.answer(calls)) as get:
            result = self.gw.sync(days=1)
            again = self.gw.sync(days=1)  # reading again never doubles

        self.assertTrue(result["ok"] and again["ok"])
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"], "Bearer sk-viewer-test"
        )
        rows = frappe.get_all(
            "HDS Gateway Usage Day", fields=["*"], order_by="gateway_user asc"
        )
        self.assertEqual(
            [(r.gateway_user, r.requests, r.failures) for r in rows],
            [("dev@example.com", 3, 1), ("lead@example.com", 1, 0)],
        )
        self.assertEqual((rows[0].p50_ms, rows[0].p95_ms), (1000, 3000))
        self.assertIn("RateLimitError", rows[0].error_classes)
        self.assertNotIn("PROMPT", frappe.as_json(rows))
        # the real model, with the desktop app's name for it beside it
        self.assertEqual(
            (rows[0].model, rows[0].gateway_alias, rows[0].gateway_provider),
            ("gpt-5.6-luna", "tbo-default", "openai"),
        )

    def test_the_pages_show_the_gateways_models_by_their_real_names(self):
        deepseek = gateway_call("bedrock/converse/deepseek.v3.2", "tbo-deepseek")
        calls = [gateway_call(), gateway_call(), deepseek]
        with patch("requests.get", return_value=self.answer(calls)):
            self.gw.sync(days=1)
        log("gpt-5.6-luna")  # TBO Support's own call to the same model

        models = {m["model"]: m for m in ai_models.overview(7)["models"]}
        self.assertNotIn("tbo-default", models)
        self.assertEqual(models["gpt-5.6-luna"]["calls"], 3)
        self.assertEqual(models["gpt-5.6-luna"]["gateway_aliases"], ["tbo-default"])
        self.assertEqual(
            (
                models["deepseek.v3.2"]["provider"],
                models["deepseek.v3.2"]["gateway_aliases"],
            ),
            (ai_models.GATEWAY_SOURCE, ["tbo-deepseek"]),
        )
        one = ai_models.detail("gpt-5.6-luna", 7)
        self.assertEqual((one["calls"], one["cost"]), (3, 0.05))
        self.assertEqual(one["gateway_aliases"], ["tbo-default"])
        self.assertEqual(one["by_person"][0]["name"], "dev@example.com")
        self.assertEqual(one["series"][-1]["calls"], 3)

    def test_a_refused_key_is_noted_not_raised(self):
        with patch("requests.get", return_value=self.answer([], status=401)):
            result = self.gw.sync(days=1)
        self.assertFalse(result["ok"])
        self.assertIn("refused", self.gw.status()["note"])

    def test_off_means_nothing_is_asked(self):
        frappe.db.set_single_value("HDS Hub Settings", "gateway_sync", 0)
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        with patch("requests.get") as get:
            self.assertFalse(self.gw.sync()["ok"])
        get.assert_not_called()

    def test_the_address_must_be_https(self):
        with self.assertRaises(frappe.ValidationError):
            ai_models.save_gateway({"url": "http://ai.example.com"})
