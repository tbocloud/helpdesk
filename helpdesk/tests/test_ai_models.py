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
PRICING = "HDS Model Pricing"


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
        frappe.db.set_value(PRICING, {"candidate": 1}, "candidate", 0)
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


FULL_MARKS = [{**REPORT[0]}, {**REPORT[1], "right": True}]


class TestCandidatesAndTheGuard(ModelsCase):
    def test_a_candidate_is_listed_before_any_job_uses_it(self):
        result = ai_models.add_model(
            {
                "model": "glm-5",
                "section": "Anthropic-compatible",
                "input_price": 0.6,
                "output_price": 2.2,
                "note": "to compare with kimi",
            }
        )

        candidate = result["candidates"][0]
        self.assertEqual(
            (candidate["model"], candidate["section"], candidate["input_price"]),
            ("glm-5", "Anthropic-compatible", 0.6),
        )
        self.assertFalse(candidate["in_use"])
        self.assertIn("glm-5", result["models"])
        listed = {m["model"]: m for m in ai_models.overview(30)["models"]}["glm-5"]
        self.assertEqual(
            (listed["status"], listed["provider"]),
            ("Candidate", "Anthropic-compatible"),
        )
        with self.assertRaises(frappe.ValidationError):
            ai_models.add_model({"model": "glm-5", "section": "OpenAI"})

        # once a job uses it, it is a model like any other
        ai_models.save_job(
            "chat",
            {"anthropic_model": "glm-5", "primary_section": "Anthropic-compatible"},
        )
        listed = {m["model"]: m for m in ai_models.overview(30)["models"]}["glm-5"]
        self.assertEqual(listed["status"], "Not used")
        self.assertEqual(listed["used_for"]["primary"], ["chat"])
        self.assertTrue(ai_models.candidates()[0]["in_use"])

    def test_what_a_candidate_needs(self):
        for values in (
            {"section": "OpenAI"},
            {"model": "two words", "section": "OpenAI"},
            {"model": "glm-5", "section": "Mars"},
            {"model": "glm-5", "section": "OpenAI", "input_price": -1},
        ):
            with self.assertRaises(frappe.ValidationError, msg=values):
                ai_models.add_model(values)

    def test_removing_a_candidate_keeps_a_known_models_price(self):
        ai_models.add_model({"model": "never-used", "section": "OpenAI"})
        ai_models.remove_candidate("never-used")
        self.assertFalse(frappe.db.exists(PRICING, "never-used"))

        log("seen-model")
        ai_models.add_model(
            {"model": "seen-model", "section": "OpenAI", "input_price": 1}
        )
        ai_models.remove_candidate("seen-model")
        self.assertEqual(
            frappe.db.get_value(
                PRICING, "seen-model", ["candidate", "input_cost_per_1m"]
            ),
            (0, 1.0),
        )
        with self.assertRaises(frappe.ValidationError):
            ai_models.remove_candidate("seen-model")

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

    def test_only_system_managers_add_and_remove(self):
        manager = create_agent("models.manager2@example.com").name
        frappe.get_doc("User", manager).add_roles("Agent Manager")
        ai_models.add_model({"model": "glm-5", "section": "OpenAI"})

        for change in (
            lambda: api.add_model({"model": "glm-6", "section": "OpenAI"}),
            lambda: api.remove_candidate("glm-5"),
            lambda: api.save_alerts({"error_rate": 5}),
        ):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(manager, change)
        # a manager may ask what a change would do
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


def gateway_call(model="tbo-default", user="dev@example.com", ms=2000, **more):
    return {
        "request_id": frappe.generate_hash(length=8),
        "model_group": model,
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

    def test_the_pages_show_the_gateways_models(self):
        with patch(
            "requests.get", return_value=self.answer([gateway_call(), gateway_call()])
        ):
            self.gw.sync(days=1)
        log("gpt-test-model")

        models = {m["model"]: m for m in ai_models.overview(7)["models"]}
        self.assertEqual(models["tbo-default"]["calls"], 2)
        self.assertEqual(models["tbo-default"]["provider"], ai_models.GATEWAY_SOURCE)
        one = ai_models.detail("tbo-default", 7)
        self.assertEqual((one["calls"], one["cost"]), (2, 0.04))
        self.assertEqual(one["by_person"][0]["name"], "dev@example.com")
        self.assertEqual(one["series"][-1]["calls"], 2)

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
