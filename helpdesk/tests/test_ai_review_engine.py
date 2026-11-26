# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Review of #364 (AI models): the monthly limit counts cached input and holds when the model's
provider is off, the gateway skips a provider that is off, a failed attempt's row outlives its
request, the gateway may use plain http only to this machine, a test-set request goes to one
worker and is answered only by its own model and job, tidied spaces aren't a safety cut, odd
reference reports never refuse an investigation, and the alert-limit patch keeps a stored 0."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, cint, now_datetime

from helpdesk import ai_engine, ai_models
from helpdesk.api import copilot_worker as worker_api
from helpdesk.copilot import conversation
from helpdesk.test_utils import (
    anthropic_answer,
    fake_investigation,
    hold_commits,
    make_ai_provider,
    openai_http_response,
    patch_anthropic_sdk,
)
from helpdesk.tests.test_ai_models import (
    DEEPSEEK,
    GATEWAY,
    GATEWAY_KEY,
    LOG,
    REPORT,
    ModelsCase,
    add_model,
    add_provider,
    answered,
    fresh_month,
    log,
)
from helpdesk.tests.test_chatwoot_bridge import ChatwootCase
from helpdesk.tests.test_copilot_mcp_worker import WorkerCase

SETTINGS = "HDS Hub Settings"
EVAL_REQUEST = "HDS Model Eval Request"


def switch_off(name=DEEPSEEK):
    ai_models.save_provider(
        {
            "name": name,
            "style": "OpenAI-compatible",
            "url": "https://api.deepseek.test",
            "enabled": 0,
        }
    )


def chain(job):
    return [(p.slot, p.model) for p in ai_engine.get_providers(job)]


class TestTheMonthlyLimit(ModelsCase):
    def setUp(self):
        super().setUp()
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        add_model("kimi-k2.6", "Anthropic-compatible")
        ai_models.save_job(
            "triage", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )

    def test_cached_input_counts_toward_the_limit(self):
        log(
            "deepseek-chat",
            input_tokens=100,
            output_tokens=20,
            cache_read_tokens=900,
            cache_write_tokens=80,
        )
        fresh_month()

        self.assertEqual(ai_engine.month_tokens("deepseek-chat"), 1100)
        # 1,000 tokens: used up only with the cached input counted
        ai_models.save_model({"model": "deepseek-chat", "limit_m": 0.001})
        self.assertTrue(ai_engine.over_limit("deepseek-chat"))
        # a limit of 0 is no limit
        ai_models.save_model({"model": "deepseek-chat", "limit_m": 0})
        self.assertFalse(ai_engine.over_limit("deepseek-chat"))

    def test_a_used_up_model_stops_the_job_even_when_its_provider_is_off(self):
        ai_models.save_model({"model": "deepseek-chat", "limit_m": 0.001})
        log("deepseek-chat", input_tokens=900, output_tokens=200)
        fresh_month()
        switch_off()
        sdk = patch_anthropic_sdk(self, anthropic_answer("{}"))

        self.assertEqual(chain("triage"), [])
        self.assertEqual(ai_engine.limit_reached("triage"), "deepseek-chat")
        with patch("requests.post") as post, self.assertRaises(
            frappe.ValidationError
        ) as refused:
            ai_engine.call_haiku("Answer in JSON", "hello", job="triage")
        self.assertIn("monthly token limit", str(refused.exception))
        post.assert_not_called()
        sdk.return_value.messages.create.assert_not_called()
        # under its limit, the backup still answers while the provider is off
        ai_models.save_model({"model": "deepseek-chat", "limit_m": 0})
        self.assertEqual(chain("triage"), [("Anthropic-compatible", "kimi-k2.6")])
        self.assertEqual(ai_engine.limit_reached("triage"), "")


class TestTheGatewayChain(ModelsCase):
    def setUp(self):
        # after the rollback: no cached copy of the gateway settings outlives the test
        self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)
        super().setUp()
        from helpdesk import ai_gateway

        self.gw = ai_gateway
        doc = frappe.get_doc(SETTINGS)
        doc.update(
            {
                "gateway_url": GATEWAY,
                "gateway_key": GATEWAY_KEY,
                "gateway_admin_key": "sk-gateway-admin-0001",
                "gateway_for_all": 1,
            }
        )
        doc.save(ignore_permissions=True)
        frappe.cache.set_value(ai_gateway.ALIVE_KEY, 1)
        frappe.cache.set_value(ai_gateway.KEY_WORKS_KEY, 1)
        admin = patch("requests.request", return_value=answered())
        admin.start()
        self.addCleanup(admin.stop)
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        add_model("kimi-k2.6", "Anthropic-compatible")
        ai_models.save_job(
            "chat", {"model": "deepseek-chat", "backup_model": "kimi-k2.6"}
        )

    def test_a_provider_switched_off_leaves_the_gateway_chain(self):
        self.assertEqual(
            chain("chat"),
            [(self.gw.SLOT, "deepseek-chat"), (self.gw.SLOT, "kimi-k2.6")],
        )

        switch_off()

        # the section's model stays: a section has no switch of its own
        self.assertEqual(ai_engine.chain_models("chat"), ["kimi-k2.6"])
        self.assertEqual(chain("chat"), [(self.gw.SLOT, "kimi-k2.6")])


class TestAFailedAttemptOutlivesItsRequest(ModelsCase):
    def fail(self):
        refused = openai_http_response(
            429, {"error": {"message": "Rate limit reached for sk-secret-123456"}}
        )
        with patch("requests.post", return_value=refused), self.assertRaises(
            ai_engine.AIProviderError
        ):
            ai_engine.complete(
                make_ai_provider(), "Answer in JSON", "hello", job="draft"
            )

    def test_the_row_is_written_by_a_job_of_its_own(self):
        frappe.db.savepoint("before_the_draft")
        with patch("frappe.enqueue") as enqueue:
            self.fail()
        # the draft can't be made and its request rolls back: the row isn't part of it
        frappe.db.rollback(save_point="before_the_draft")
        self.assertFalse(frappe.db.exists(LOG, {"status": "Failed"}))
        self.assertEqual(
            enqueue.call_args.args[0], "helpdesk.ai_engine.log_failed_attempt"
        )
        attempt = enqueue.call_args.kwargs["attempt"]
        self.assertNotIn("sk-secret-123456", frappe.as_json(attempt))
        # queued at once, not after the commit: a request that rolls back never commits, and
        # an after-commit job would be dropped with it
        self.assertFalse(enqueue.call_args.kwargs.get("enqueue_after_commit"))
        self.assertTrue(attempt.get("at"))

        # the job runs later; the row keeps the attempt's own time
        later = dict(attempt, at="2026-11-26 12:00:00")
        ai_engine.log_failed_attempt(later)  # what the job does

        row = frappe.get_last_doc(LOG)
        self.assertEqual(
            (row.model, row.provider, row.job, row.status, row.error_class),
            ("gpt-test-model", "OpenAI", "draft", "Failed", "rate_limit"),
        )
        self.assertIn("429", row.error_message)
        self.assertNotIn("sk-secret-123456", row.error_message)
        self.assertIsNotNone(row.duration_ms)
        self.assertEqual(str(row.creation), "2026-11-26 12:00:00")
        # and the day reports count it on the day it happened
        self.assertEqual(str(row.timestamp), "2026-11-26 12:00:00")

    def test_a_queue_that_is_down_never_hides_the_providers_error(self):
        with patch("frappe.enqueue", side_effect=RuntimeError("queue down")):
            self.fail()

    def test_an_error_log_that_is_down_never_stops_failover_either(self):
        with patch("frappe.enqueue", side_effect=RuntimeError("queue down")), patch(
            "frappe.log_error", side_effect=RuntimeError("error log down")
        ):
            # still the provider's error, so the caller tries the backup
            self.fail()


class TestTheGatewayAddress(FrappeTestCase):
    def check(self, url):
        doc = frappe.get_doc(SETTINGS)
        doc.update({"ai_base_url": "", "openai_base_url": "", "gateway_url": url})
        doc.validate_ai_base_urls()
        return doc.gateway_url

    def test_plain_http_goes_only_to_this_machine(self):
        self.assertEqual(self.check("http://localhost:4100/"), "http://localhost:4100")
        self.assertEqual(self.check("http://127.0.0.1:4100"), "http://127.0.0.1:4100")
        self.assertEqual(self.check("https://gw.example.com"), "https://gw.example.com")
        for url in (
            "http://localhost.example.com:4100",
            "http://127.0.0.1.example.com",
            "http://localhost@gw.example.com",
            "http://gw.example.com",
            "http://[::1",
        ):
            with self.assertRaises(frappe.ValidationError, msg=url):
                self.check(url)


class TestTheTestSetRequests(ModelsCase):
    def setUp(self):
        super().setUp()
        worker_api.ensure_role()

    def ask(self, model, job="investigate", minutes_ago=0):
        name = ai_models.request_eval(model, job)["requests"][0]["name"]
        frappe.db.set_value(
            EVAL_REQUEST,
            name,
            "creation",
            add_to_date(now_datetime(), minutes=-minutes_ago),
            update_modified=False,
        )
        return name

    def test_each_request_goes_to_one_worker(self):
        older = self.ask("glm-5", minutes_ago=10)
        newer = self.ask("kimi-k2.6", minutes_ago=5)

        with patch.object(frappe.db, "get_value", wraps=frappe.db.get_value) as read:
            first = worker_api.claim_eval_request()
        second = worker_api.claim_eval_request()

        # a locking read that passes over a request another worker is claiming
        self.assertTrue(
            any(
                c.kwargs.get("for_update") and c.kwargs.get("skip_locked")
                for c in read.call_args_list
            )
        )
        self.assertEqual((first.name, second.name), (older, newer))
        self.assertIsNone(worker_api.claim_eval_request())
        self.assertEqual(frappe.db.get_value(EVAL_REQUEST, older, "status"), "Running")

    def test_a_report_answers_only_its_own_models_and_jobs_request(self):
        fix = self.ask("glm-5", job="fix")

        for model, job in (("kimi-k2.6", "fix"), ("glm-5", "investigate")):
            with self.assertRaises(frappe.ValidationError, msg=(model, job)):
                worker_api.report_eval(model, REPORT, job=job, request=fix)
        self.assertFalse(frappe.db.exists("HDS Model Eval Run", {"model": "kimi-k2.6"}))
        self.assertFalse(frappe.db.exists("HDS Model Eval Run", {"model": "glm-5"}))
        # a report naming no request answers the model's request for its own job only
        worker_api.report_eval("glm-5", REPORT, job="investigate")
        self.assertEqual(frappe.db.get_value(EVAL_REQUEST, fix, "status"), "Queued")

        run = worker_api.report_eval("glm-5", REPORT, job="fix", request=fix)

        self.assertEqual(
            frappe.db.get_value(EVAL_REQUEST, fix, ["status", "eval_run"]),
            ("Done", run["eval_run"]),
        )

    def test_a_run_never_reported_is_given_up_and_a_late_report_still_answers_it(self):
        stuck = self.ask("glm-5", minutes_ago=60 * 30)
        fresh = self.ask("kimi-k2.6", minutes_ago=60)
        for name in (stuck, fresh):
            frappe.db.set_value(EVAL_REQUEST, name, "status", "Running")
        frappe.db.set_value(
            EVAL_REQUEST,
            stuck,
            "modified",
            add_to_date(now_datetime(), hours=-(worker_api.EVAL_RUN_HOURS + 1)),
            update_modified=False,
        )

        self.assertIsNone(worker_api.claim_eval_request())

        status, error = frappe.db.get_value(EVAL_REQUEST, stuck, ["status", "error"])
        self.assertEqual(status, "Failed")
        self.assertIn(str(worker_api.EVAL_RUN_HOURS), error)
        self.assertEqual(frappe.db.get_value(EVAL_REQUEST, fresh, "status"), "Running")
        # the report comes after all: it answers the request it names
        run = worker_api.report_eval("glm-5", REPORT, request=stuck)
        self.assertEqual(
            frappe.db.get_value(EVAL_REQUEST, stuck, ["status", "eval_run"]),
            ("Done", run["eval_run"]),
        )

    def test_a_report_sent_again_stores_nothing_twice(self):
        asked = self.ask("glm-5")
        first = worker_api.report_eval("glm-5", REPORT, request=asked)
        # its answer was lost on the way, and the worker sends it again
        again = worker_api.report_eval("glm-5", REPORT, request=asked)

        self.assertEqual(again, first)
        self.assertEqual(frappe.db.count("HDS Model Eval Run", {"model": "glm-5"}), 1)

    def test_a_request_a_managers_import_answered_still_takes_the_workers_run(self):
        asked = self.ask("glm-5")
        imported = ai_models.store_eval("glm-5", REPORT, source="Imported")
        frappe.db.set_value(
            EVAL_REQUEST, asked, {"status": "Done", "eval_run": imported}
        )

        with patch.object(frappe.db, "get_value", wraps=frappe.db.get_value) as read:
            run = worker_api.report_eval("glm-5", REPORT, request=asked)

        self.assertNotEqual(run["eval_run"], imported)
        self.assertEqual(frappe.db.count("HDS Model Eval Run", {"model": "glm-5"}), 2)
        # the request is read with a lock, and now names the worker's own run
        self.assertTrue(any(c.kwargs.get("for_update") for c in read.call_args_list))
        self.assertEqual(
            frappe.db.get_value(EVAL_REQUEST, asked, "eval_run"), run["eval_run"]
        )
        # so a copy of the report sent again stores nothing more
        self.assertEqual(worker_api.report_eval("glm-5", REPORT, request=asked), run)
        self.assertEqual(frappe.db.count("HDS Model Eval Run", {"model": "glm-5"}), 2)

    def test_a_report_that_came_in_meanwhile_is_never_given_up(self):
        done = self.ask("glm-5", minutes_ago=60 * 30)
        frappe.db.set_value(
            EVAL_REQUEST,
            done,
            {
                "status": "Done",
                "modified": add_to_date(
                    now_datetime(), hours=-(worker_api.EVAL_RUN_HOURS + 1)
                ),
            },
            update_modified=False,
        )
        # it was still Running when the stale ones were listed, and Done by the update
        with patch.object(frappe, "get_all", return_value=[done]):
            worker_api.give_up_stale_eval_requests()

        self.assertEqual(frappe.db.get_value(EVAL_REQUEST, done, "status"), "Done")


class TestSafetyCuts(FrappeTestCase):
    def test_tidied_spaces_are_not_a_cut(self):
        for raw in (
            "Open Settings.   Select Users.",
            "Open Settings.\n\nSelect Users.\n\nSave.",
            "**Open** Settings.  Then  save.",
        ):
            text = conversation.safe_text(raw, [])
            self.assertFalse(conversation.cut_for_safety(raw, text), raw)

    def test_a_long_answer_cut_at_the_limit_is_not_a_safety_cut(self):
        raw = "Open Settings. " * 300
        text = conversation.safe_text(raw, [])
        self.assertLessEqual(len(text), conversation.MAX_TEXT)
        self.assertFalse(conversation.cut_for_safety(raw, text))
        # a link taken out before the limit still counts
        linked = "Open Settings. See https://evil.example.com/steps now. " + raw
        self.assertTrue(
            conversation.cut_for_safety(linked, conversation.safe_text(linked, []))
        )

    def test_a_removed_link_or_promise_is_a_cut(self):
        for raw in (
            "Open Settings. See https://evil.example.com/steps for more.",
            "Open Settings. We will fix this by Monday.",
        ):
            text = conversation.safe_text(raw, [])
            self.assertTrue(conversation.cut_for_safety(raw, text), raw)


class TestTheChatsSafetyCut(ChatwootCase):
    def setUp(self):
        super().setUp()
        # the chat's per-minute message counts live in Redis and outlast the test: other chat
        # tests in the same run must not find this class's messages counted against them
        frappe.cache().delete_keys(conversation.RATE_KEY)
        self.addCleanup(frappe.cache().delete_keys, conversation.RATE_KEY)

    def cuts(self):
        return frappe.db.count("HDS AI Quality Event", {"kind": "Safety cut"})

    def test_a_reply_with_tidied_spaces_is_not_counted(self):
        before = self.cuts()
        self.ask_ai(
            {
                "response": {
                    "next": "question",
                    "text": "Open Settings.   Select Users.\n\nWhich one is it?",
                }
            }
        )
        self.assertEqual(self.cuts(), before)

    def test_a_reply_that_lost_a_link_is_counted(self):
        before = self.cuts()
        self.ask_ai(
            {
                "response": {
                    "next": "question",
                    "text": "See https://evil.example.com/steps. Which one is it?",
                }
            }
        )
        self.assertEqual(self.cuts(), before + 1)


class TestReferencesOfAnyShape(WorkerCase):
    def test_missing_references_that_are_not_a_list_never_refuse_the_report(self):
        result = fake_investigation("bug")
        result.pop("kind")

        is_error, data = self.call(
            "submit_investigation",
            **result,
            references={"checked": 4, "missing": 1},
        )

        self.assertFalse(is_error, data)
        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value(
                "HDS Copilot Run",
                self.run,
                ["references_checked", "references_missing"],
            ),
            (4, 0),
        )


def stored(field):
    singles = frappe.qb.DocType("Singles")
    rows = (
        frappe.qb.from_(singles)
        .select(singles.value)
        .where(singles.doctype == SETTINGS)
        .where(singles["field"] == field)
    ).run()
    return cint(rows[0][0]) if rows else None


class TestTheAlertLimitsPatch(FrappeTestCase):
    def setUp(self):
        # after the rollback: no cached copy of the settings outlives the test
        self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)
        hold_commits(self)

    def test_a_stored_limit_is_kept_and_a_missing_one_gets_its_default(self):
        from helpdesk.patches.v16_0_3 import model_alert_limits

        # 0 means "no alert": a manager's choice the patch must keep
        frappe.db.set_single_value(SETTINGS, "model_alert_error_rate", 0)
        frappe.db.delete(
            "Singles", {"doctype": SETTINGS, "field": "model_alert_fallback_rate"}
        )

        model_alert_limits.execute()

        self.assertEqual(stored("model_alert_error_rate"), 0)
        self.assertEqual(stored("model_alert_fallback_rate"), 30)
