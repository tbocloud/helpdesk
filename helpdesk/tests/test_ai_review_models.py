# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""AI models and the TBO AI gateway, after the review of PR #364: a refused gateway write keeps
what worked, the usage read keeps whole days in rows of their own, the pages count each source
for what it says, and the gateway switch never leaves a job without a key.

The benchmark source test needs the HDS Public Benchmark change migrated (its column grows to
500 characters)."""

from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime, nowdate
from frappe.utils.password import get_decrypted_password

from helpdesk import ai_engine, ai_gateway, ai_models
from helpdesk.api import ai_models as api
from helpdesk.test_utils import (
    hold_commits,
    make_copilot_run,
    make_ticket,
    make_ticket_communication,
    openai_http_response,
    set_ai_providers,
)

LOG = "HDS AI Usage Log"
PRICING = "HDS Model Pricing"
PROVIDER = "HDS AI Provider"
DAY = "HDS Gateway Usage Day"
DEEPSEEK = "DeepSeek"
DEEPSEEK_KEY = "sk-deepseek-review-123456"
QWEN_KEY = "sk-qwen-review-123456"
GATEWAY = "https://gw.test"
GATEWAY_KEY = "sk-tbo-support-gateway-0002"
ADMIN_KEY = "sk-gateway-admin-0002"

REPORT = [
    {"case": {"id": "A1"}, "right": True, "minutes": 4, "costUsd": 0.5},
    {"case": {"id": "A2"}, "right": False, "minutes": 6, "costUsd": 0.3},
]
FULL_MARKS = [{**REPORT[0]}, {**REPORT[1], "right": True}]
DRAFT = (
    "Hello Asha, thank you for writing to us. The invoice total was wrong because the tax "
    "template was missing on the item. We have added the template and the total is right now. "
    "Please open the invoice again and tell us if anything still looks wrong."
)


def set_hub(**values):
    doc = frappe.get_doc("HDS Hub Settings")
    doc.update(values)
    doc.save(ignore_permissions=True)


def add_provider(name=DEEPSEEK, url="https://api.deepseek.test", key=DEEPSEEK_KEY):
    return ai_models.save_provider(
        {"name": name, "style": "OpenAI-compatible", "url": url, "key": key, "new": 1}
    )


def add_model(model, provider, **more):
    return ai_models.save_model(
        {"model": model, "provider": provider, "listed": 1, "new": 1, **more}
    )


def log(model, **more):
    return frappe.get_doc(
        {
            "doctype": LOG,
            "model": model,
            "provider": "OpenAI",
            "job": "triage",
            "status": "Success",
            "duration_ms": 1200,
            "estimated_cost_usd": 0.01,
            "input_tokens": 100,
            "output_tokens": 20,
            **more,
        }
    ).insert(ignore_permissions=True)


def gateway_call(model="openai/gpt-5.6-luna", user="dev@example.com", **more):
    """One call as the gateway's usage log lists it."""
    return {
        "request_id": frappe.generate_hash(length=8),
        "model": model,
        "model_group": "tbo-default",
        "custom_llm_provider": model.split("/")[0] if "/" in model else "",
        "user": user,
        "spend": 0.02,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "request_duration_ms": 2000,
        "status": "success",
        **more,
    }


def failed_calls(model, count):
    return [
        gateway_call(
            model,
            status="failure",
            metadata={"error_information": {"error_class": "RateLimitError"}},
        )
        for _i in range(count)
    ]


def answered(status=200, body=None):
    return MagicMock(
        ok=status < 400, status_code=status, json=MagicMock(return_value=body or {})
    )


def posted(admin, path):
    """What TBO Support posted to one of the gateway's admin paths, in order."""
    return [
        c.kwargs["json"]
        for c in admin.call_args_list
        if c.args == ("POST", GATEWAY + path)
    ]


def patched(admin, path):
    """What TBO Support changed in place on one of the gateway's admin paths, in order."""
    return [
        c.kwargs["json"]
        for c in admin.call_args_list
        if c.args == ("PATCH", GATEWAY + path)
    ]


def refuse_new_models(admin, when):
    """The gateway refuses a new model when `when(its litellm_params)` says so; every other
    admin call answers."""

    def answer(method, url, **kwargs):
        if (method, url) == ("POST", GATEWAY + "/model/new") and when(
            kwargs["json"]["litellm_params"]
        ):
            return answered(503)
        return answered()

    admin.side_effect = answer


class ReviewCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        for doctype in (
            LOG,
            DAY,
            PRICING,
            PROVIDER,
            "HDS Model Eval Run",
            "HDS Model Eval Request",
            "HDS AI Quality Event",
            "HDS Public Benchmark",
        ):
            frappe.db.delete(doctype)
        ai_engine.forget_provider(DEEPSEEK)
        ai_engine.forget_provider("Qwen")
        frappe.cache.delete_keys("ai_engine:month_tokens:")
        self.forget_gateway()
        self.addCleanup(self.forget_gateway)
        # the providers called straight, no job rows; everything here is rolled back
        set_ai_providers(ai_jobs=[], gateway_for_all=0)

    def forget_gateway(self):
        frappe.cache.delete_value(
            [
                ai_gateway.ALIVE_KEY,
                ai_gateway.KEY_WORKS_KEY,
                ai_gateway.DOWN_KEY,
                ai_gateway.DOWN_ALERT_KEY,
            ]
        )

    def patch_admin(self):
        """The gateway's admin API (requests.request); it answers unless a test says otherwise."""
        admin = patch("requests.request", return_value=answered())
        self.addCleanup(admin.stop)
        return admin.start()


class GatewayCase(ReviewCase):
    """Every call goes through the gateway, which answers and takes TBO Support's key."""

    def setUp(self):
        super().setUp()
        set_hub(
            gateway_url=GATEWAY,
            gateway_key=GATEWAY_KEY,
            gateway_admin_key=ADMIN_KEY,
            gateway_for_all=1,
        )
        frappe.cache.set_value(ai_gateway.ALIVE_KEY, 1)
        frappe.cache.set_value(ai_gateway.KEY_WORKS_KEY, 1)
        ai_engine.forget_provider(ai_gateway.SLOT)
        self.admin = self.patch_admin()


class TestUsageRowKeys(ReviewCase):
    """Finding 1: a day's row key holds everything its totals are grouped by."""

    def test_two_providers_of_one_model_are_two_rows(self):
        calls = [
            gateway_call("openai/gpt-x"),
            gateway_call("azure/gpt-x"),
            gateway_call("azure/gpt-x"),
        ]

        self.assertEqual(ai_gateway.store_day(nowdate(), calls), 2)

        rows = frappe.get_all(
            DAY,
            fields=["model", "gateway_provider", "requests", "day_key"],
            order_by="gateway_provider asc",
        )
        self.assertEqual(
            [(r.model, r.gateway_provider, r.requests) for r in rows],
            [("gpt-x", "azure", 2), ("gpt-x", "openai", 1)],
        )
        self.assertEqual(len({r.day_key for r in rows}), 2)

    def test_names_alike_in_their_first_140_characters_keep_their_own_rows(self):
        person = "p" * 150
        calls = [gateway_call(user=person + "a"), gateway_call(user=person + "b")]

        self.assertEqual(ai_gateway.store_day(nowdate(), calls), 2)

        keys = frappe.get_all(DAY, pluck="day_key")
        self.assertEqual(len(set(keys)), 2)
        self.assertTrue(all(len(key) <= 140 for key in keys), keys)


class TestAWholeDayOrNothing(ReviewCase):
    """Finding 2: a day with more pages than are read keeps its earlier totals."""

    def setUp(self):
        super().setUp()
        set_hub(
            gateway_sync=1,
            gateway_url="https://ai.example.com",
            gateway_viewer_key="sk-viewer-test",
        )

    def pages(self, total_pages):
        body = {"data": [gateway_call(), gateway_call()], "total_pages": total_pages}
        return MagicMock(ok=True, status_code=200, json=MagicMock(return_value=body))

    def test_a_day_past_the_page_limit_is_not_read(self):
        with patch.object(ai_gateway, "PAGE_SIZE", 2), patch.object(
            ai_gateway, "MAX_PAGES", 2
        ):
            with patch("requests.get", return_value=self.pages(2)):
                rows = ai_gateway.fetch_day("https://ai.example.com", "k", nowdate())
            self.assertEqual(len(rows), 4)
            for total_pages in (3, 0):
                with patch("requests.get", return_value=self.pages(total_pages)):
                    with self.assertRaises(ai_gateway.GatewayError):
                        ai_gateway.fetch_day("https://ai.example.com", "k", nowdate())

            ai_gateway.store_day(nowdate(), [gateway_call()])  # an earlier reading
            with patch("requests.get", return_value=self.pages(3)) as get:
                result = ai_gateway.sync(days=1)

        self.assertEqual(get.call_count, 2)
        self.assertFalse(result["ok"])
        self.assertIn("more than 4 calls", result["note"])
        self.assertEqual(frappe.get_all(DAY, pluck="requests"), [1])


class TestAModelTheGatewayRefuses(GatewayCase):
    """Finding 3: a model save the gateway refuses leaves the model it served."""

    def setUp(self):
        super().setUp()
        add_provider()
        add_provider("Qwen", url="https://qwen.test", key=QWEN_KEY)
        add_model("glm-5", DEEPSEEK)
        self.admin.reset_mock()

    def test_the_model_it_had_is_written_back(self):
        refuse_new_models(
            self.admin, lambda params: params.get("litellm_credential_name") == "Qwen"
        )

        with self.assertRaises(frappe.ValidationError) as refused:
            ai_models.save_model({"model": "glm-5", "provider": "Qwen"})

        self.assertIn("HTTP 503", str(refused.exception))
        written = posted(self.admin, "/model/new")
        self.assertEqual(
            [w["litellm_params"]["litellm_credential_name"] for w in written],
            ["Qwen", DEEPSEEK],
        )
        self.assertEqual(
            {w["model_info"]["id"] for w in written}, {"tbo-support:glm-5"}
        )

    def test_it_says_so_when_the_old_one_cannot_be_written_back(self):
        refuse_new_models(self.admin, lambda params: True)

        with self.assertRaises(frappe.ValidationError) as refused:
            ai_models.save_model({"model": "glm-5", "provider": "Qwen"})

        self.assertIn("could not be written back", str(refused.exception))

    def test_write_all_keeps_a_model_the_gateway_refuses_again(self):
        refusals = []

        def answer(method, url, **kwargs):
            if (method, url) == ("POST", GATEWAY + "/model/new") and not refusals:
                refusals.append(kwargs["json"]["model_info"]["id"])
                return answered(503)
            return answered()

        self.admin.side_effect = answer
        with self.assertRaises(frappe.ValidationError):
            ai_models.write_all()

        refused = refusals[0]
        written = [w["model_info"]["id"] for w in posted(self.admin, "/model/new")]
        # the refused model is written back, so it keeps answering
        self.assertEqual(written[:2], [refused, refused])

    def test_a_new_model_has_nothing_to_write_back(self):
        refuse_new_models(self.admin, lambda params: True)

        with self.assertRaises(frappe.ValidationError):
            add_model("kimi-k3", DEEPSEEK)

        self.assertEqual(len(posted(self.admin, "/model/new")), 1)


class TestALevelTheGatewayRefuses(ReviewCase):
    """Finding 5: a desktop level the gateway refuses keeps its earlier models."""

    def setUp(self):
        super().setUp()
        set_hub(gateway_url=GATEWAY, gateway_admin_key=ADMIN_KEY)
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        add_model("gpt-test-model", "OpenAI")
        self.admin = self.patch_admin()
        ai_models.save_job("desktop_simple", {"model": "deepseek-chat"})
        self.admin.reset_mock()

    def test_the_level_keeps_its_models(self):
        refuse_new_models(
            self.admin, lambda params: params["model"] == "openai/gpt-test-model"
        )

        with self.assertRaises(frappe.ValidationError) as refused:
            ai_models.save_job(
                "desktop_simple",
                {"model": "gpt-test-model", "backup_model": "deepseek-chat"},
            )

        self.assertIn("keeps the models it had", str(refused.exception))
        self.assertEqual(
            [
                (w["model_info"]["id"], w["litellm_params"]["model"])
                for w in posted(self.admin, "/model/new")
            ],
            [
                ("tbo-support:tbo-simple:1", "openai/gpt-test-model"),
                ("tbo-support:tbo-simple:1", "openai/deepseek-chat"),
            ],
        )

    def test_a_first_level_refused_half_way_leaves_nothing_on_the_gateway(self):
        refuse_new_models(
            self.admin, lambda params: params["model"] == "openai/deepseek-chat"
        )

        with self.assertRaises(frappe.ValidationError):
            ai_models.save_job(
                "desktop_medium",
                {"model": "gpt-test-model", "backup_model": "deepseek-chat"},
            )

        calls = [
            (c.args[0], (c.kwargs.get("json") or {}).get("id"))
            for c in self.admin.call_args_list
        ]
        # the model that got on (tbo-medium:1) is taken off after the backup was refused
        last_write = max(
            i
            for i, (method, _id) in enumerate(calls)
            if method == "POST" and _id is None
        )
        removed_after = {
            _id for method, _id in calls[last_write + 1 :] if _id  # noqa: E203
        }
        self.assertIn("tbo-support:tbo-medium:1", removed_after)
        self.assertIn("tbo-support:tbo-medium:2", removed_after)

    def test_write_all_keeps_a_level_the_gateway_refuses_half_way(self):
        ai_models.save_job(
            "desktop_simple",
            {"model": "deepseek-chat", "backup_model": "gpt-test-model"},
        )
        self.admin.reset_mock()
        refusals = []

        def answer(method, url, **kwargs):
            # the backup is refused once, as the level is written again
            body = kwargs.get("json") or {}
            if (
                (method, url) == ("POST", GATEWAY + "/model/new")
                and body.get("model_info", {}).get("id") == "tbo-support:tbo-simple:2"
                and not refusals
            ):
                refusals.append(1)
                return answered(503)
            return answered()

        self.admin.side_effect = answer
        with self.assertRaises(frappe.ValidationError) as refused:
            ai_models.write_all()

        self.assertIn("keeps the models it had", str(refused.exception))
        level = [
            (w["model_info"]["id"], w["litellm_params"]["model"])
            for w in posted(self.admin, "/model/new")
            if w["model_info"]["id"].startswith("tbo-support:tbo-simple")
        ]
        # written, refused at the backup, then both written back as they were
        self.assertEqual(
            level[-2:],
            [
                ("tbo-support:tbo-simple:1", "openai/deepseek-chat"),
                ("tbo-support:tbo-simple:2", "openai/gpt-test-model"),
            ],
        )

    def test_a_level_not_written_back_says_how_to_repair_it(self):
        refuse_new_models(self.admin, lambda params: True)

        with self.assertRaises(frappe.ValidationError) as refused:
            ai_models.save_job("desktop_simple", {"model": "gpt-test-model"})

        self.assertIn("Write all to the gateway", str(refused.exception))


class TestScoresBeyondTheHistory(ReviewCase):
    """Finding 4: many runs of one model never hide another model's only run."""

    def test_a_models_only_run_still_counts(self):
        ai_models.store_eval("kimi-k2.6", REPORT, ran_on="2026-09-01")
        for _i in range(51):
            ai_models.store_eval("gpt-test-model", FULL_MARKS, ran_on="2026-10-01")

        self.assertEqual(ai_models.latest_scores()["kimi-k2.6"]["accuracy"], 50.0)
        weaker = ai_models.guard("fix", {"primary_section": "Anthropic-compatible"})
        self.assertIn("50.0%", weaker["warning"])
        result = ai_models.benchmarks("gpt-test-model")
        self.assertIn("kimi-k2.6", result["others"])
        # the history itself still shows the newest 50
        self.assertEqual(len(result["runs"]), 50)


class TestCustomerAnswersPerRun(ReviewCase):
    """Finding 6: a customer's answer counts for the run it was about."""

    def test_an_answer_counts_for_the_tickets_own_run(self):
        ticket = make_ticket(subject="Two models").name
        first = make_copilot_run(ticket, "Explaining", model_used="model-a")
        frappe.db.set_value(
            "HDS Copilot Run",
            first.name,
            "creation",
            add_to_date(now_datetime(), hours=-2),
            update_modified=False,
        )
        make_copilot_run(ticket, "Explaining", model_used="model-b")
        frappe.db.set_value(
            "HD Ticket", ticket, "custom_customer_confirmation", "Reopened"
        )

        def answers(model):
            copilot = ai_models.quality(model, 30)["copilot"]
            return copilot["customer_answers"], copilot["still_broken"]

        # the newest run, when the ticket names none
        frappe.db.set_value("HD Ticket", ticket, "custom_copilot_run", None)
        self.assertEqual(answers("model-a"), (0, 0))
        self.assertEqual(answers("model-b"), (1, 1))
        # the run the ticket names
        frappe.db.set_value("HD Ticket", ticket, "custom_copilot_run", first.name)
        self.assertEqual(answers("model-a"), (1, 1))
        self.assertEqual(answers("model-b"), (0, 0))


class TestCustomerAnswersInThePeriod(ReviewCase):
    def test_an_answer_about_a_run_before_the_period_does_not_count(self):
        ticket = make_ticket(subject="An old run").name
        old = make_copilot_run(ticket, "Explaining", model_used="model-a")
        frappe.db.set_value(
            "HDS Copilot Run",
            old.name,
            "creation",
            add_to_date(now_datetime(), days=-40),
            update_modified=False,
        )
        new = make_copilot_run(ticket, "Explaining", model_used="model-a")
        frappe.db.set_value(
            "HD Ticket", ticket, "custom_customer_confirmation", "Confirmed"
        )

        def answers():
            return ai_models.quality("model-a", 30)["copilot"]["customer_answers"]

        frappe.db.set_value("HD Ticket", ticket, "custom_copilot_run", old.name)
        self.assertEqual(answers(), 0)
        frappe.db.set_value("HD Ticket", ticket, "custom_copilot_run", new.name)
        self.assertEqual(answers(), 1)


class TestGatewayCallsInTheFigures(ReviewCase):
    """Findings 7 and 14: the status is worked out from all of a model's calls, and the
    fallback rate only from the calls that say whether a fallback answered."""

    def test_gateway_failures_make_a_model_degraded_on_both_pages(self):
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)  # listed, no job uses it: a candidate
        log("gpt-test-model")  # one good call of TBO Support's own
        ai_gateway.store_day(
            nowdate(),
            failed_calls("deepseek/deepseek-chat", 20)
            + failed_calls("openai/gpt-test-model", 20),
        )

        result = ai_models.overview(7)

        models = {m["model"]: m for m in result["models"]}
        for model in ("deepseek-chat", "gpt-test-model"):
            self.assertEqual(models[model]["status"], "Degraded", model)
            self.assertEqual(ai_models.detail(model, 7)["status"], "Degraded", model)
            self.assertIn(model, result["attention"])
        # a pause stays a pause
        with patch("helpdesk.ai_models._paused_models", return_value={"deepseek-chat"}):
            self.assertEqual(ai_models.detail("deepseek-chat", 7)["status"], "Paused")

    def test_the_fallback_rate_is_of_tbo_supports_calls_only(self):
        log("gpt-test-model", fallback=1)
        log("gpt-test-model")
        ai_gateway.store_day(
            nowdate(),
            [gateway_call("openai/gpt-test-model") for _i in range(98)]
            + [gateway_call("openai/gpt-5.6-luna")],
        )

        result = ai_models.overview(7)

        models = {m["model"]: m for m in result["models"]}
        gpt = models["gpt-test-model"]
        self.assertEqual((gpt["calls"], gpt["fallback_rate"]), (100, 50.0))
        self.assertIsNone(models["gpt-5.6-luna"]["fallback_rate"])
        self.assertEqual(
            (result["totals"]["calls"], result["totals"]["fallback_rate"]), (101, 50.0)
        )
        one = ai_models.detail("gpt-test-model", 7)
        self.assertEqual((one["calls"], one["fallback_rate"]), (100, 50.0))


class TestANewGatewayAddressIsChecked(GatewayCase):
    """Finding 9: while every call goes through the gateway, a new address or call key is
    checked as when the switch goes on."""

    def test_a_new_address_that_does_not_answer_is_refused(self):
        with patch(
            "requests.get", side_effect=requests.ConnectionError("no route")
        ) as get:
            with self.assertRaises(frappe.ValidationError) as refused:
                ai_models.save_gateway({"url": "https://other-gw.test"})

        self.assertIn("does not answer", str(refused.exception))
        self.assertIn("Nothing was changed", str(refused.exception))
        self.assertTrue(get.call_args.args[0].startswith("https://other-gw.test"))
        # the refused address's "down" isn't left for the gateway that stays in use
        self.assertIsNone(frappe.cache.get_value(ai_gateway.ALIVE_KEY, expires=True))
        self.assertIsNone(
            frappe.cache.get_value(ai_gateway.KEY_WORKS_KEY, expires=True)
        )

    def test_a_new_call_key_the_gateway_refuses_is_refused(self):
        with patch("requests.get", side_effect=[answered(), answered(401)]):
            with self.assertRaises(frappe.ValidationError) as refused:
                ai_models.save_gateway({"call_key": "sk-another-gateway-key-01"})

        self.assertIn("refused", str(refused.exception))

    def test_a_save_that_keeps_the_address_and_key_asks_nothing(self):
        with patch("requests.get") as get:
            status = ai_models.save_gateway({"url": GATEWAY, "for_all": 1})

        get.assert_not_called()
        self.assertTrue(status["for_all"])


class TestSwitchingTheGatewayOff(GatewayCase):
    """Finding 10: keys saved while every call goes through the gateway live only there (the
    owner's decision); the switch stays on while a job needs one of them."""

    def setUp(self):
        super().setUp()
        add_provider()  # its key goes to the gateway and is not kept here
        add_model("deepseek-chat", DEEPSEEK)

    def test_it_stays_on_while_a_job_needs_a_key_only_the_gateway_has(self):
        ai_models.save_job("triage", {"model": "deepseek-chat"})

        with self.assertRaises(frappe.ValidationError) as refused:
            ai_models.save_gateway({"for_all": 0})

        self.assertIn(DEEPSEEK, str(refused.exception))
        self.assertIn("triage", str(refused.exception))
        self.assertEqual(
            frappe.db.get_single_value("HDS Hub Settings", "gateway_for_all"), 1
        )
        ai_models.save_job("triage", {"model": ""})
        self.assertFalse(ai_models.save_gateway({"for_all": 0})["for_all"])

    def test_a_desktop_level_does_not_keep_it_on(self):
        # the desktop app always calls the gateway itself
        ai_models.save_job("desktop_hard", {"model": "deepseek-chat"})

        self.assertFalse(ai_models.save_gateway({"for_all": 0})["for_all"])


class TestWriteAllBeforeTheSwitch(ReviewCase):
    """Finding 18: before every call goes through the gateway, writing all copies the keys
    and TBO Support keeps calling the providers with its own."""

    def setUp(self):
        super().setUp()
        set_hub(gateway_url=GATEWAY, gateway_admin_key=ADMIN_KEY)
        add_provider()
        add_model("deepseek-chat", DEEPSEEK)
        ai_models.save_job("triage", {"model": "deepseek-chat"})
        self.admin = self.patch_admin()

    def test_the_keys_are_copied_and_kept(self):
        result = ai_models.write_all()

        self.assertEqual(result["written"]["keys"], 1)
        self.assertEqual(
            patched(self.admin, "/credentials/" + DEEPSEEK)[0]["credential_values"][
                "api_key"
            ],
            DEEPSEEK_KEY,
        )
        self.assertEqual(
            get_decrypted_password(
                PROVIDER, DEEPSEEK, "api_key", raise_exception=False
            ),
            DEEPSEEK_KEY,
        )
        self.assertFalse(frappe.db.get_value(PROVIDER, DEEPSEEK, "key_on_gateway"))
        self.assertEqual(
            [(p.slot, p.model) for p in ai_engine.get_providers("triage")],
            [(DEEPSEEK, "deepseek-chat")],
        )

    def test_switching_on_afterwards_moves_the_keys_kept_here(self):
        ai_models.write_all()
        self.admin.reset_mock()
        # the gateway answers its health check and takes TBO Support's key
        with patch("requests.get", return_value=answered()):
            ai_models.save_gateway({"call_key": GATEWAY_KEY, "for_all": 1})

        # the key now lives only in the gateway, and the account is ready through it
        self.assertTrue(patched(self.admin, "/credentials/" + DEEPSEEK))
        self.assertIsNone(
            get_decrypted_password(PROVIDER, DEEPSEEK, "api_key", raise_exception=False)
        )
        self.assertTrue(frappe.db.get_value(PROVIDER, DEEPSEEK, "key_on_gateway"))
        deepseek = next(p for p in ai_models.provider_list() if p["name"] == DEEPSEEK)
        self.assertTrue(deepseek["ready"])

    def test_a_new_key_reaches_the_gateways_copy_while_the_switch_is_off(self):
        ai_models.write_all()
        self.admin.reset_mock()

        ai_models.save_provider(
            {
                "name": DEEPSEEK,
                "style": "OpenAI-compatible",
                "url": "https://api.deepseek.test",
                "key": "sk-deepseek-rotated-123456",
            }
        )

        sent = patched(self.admin, "/credentials/" + DEEPSEEK)
        self.assertEqual(
            sent[0]["credential_values"]["api_key"], "sk-deepseek-rotated-123456"
        )
        # TBO Support still calls DeepSeek itself: it keeps the key too
        self.assertEqual(
            get_decrypted_password(
                PROVIDER, DEEPSEEK, "api_key", raise_exception=False
            ),
            "sk-deepseek-rotated-123456",
        )

    def test_a_model_on_the_gateway_follows_its_changes_while_the_switch_is_off(self):
        ai_models.write_all()
        ai_models.save_job("triage", {"model": ""})
        self.admin.reset_mock()

        ai_models.save_model({"model": "deepseek-chat", "listed": 0})
        self.assertEqual(
            posted(self.admin, "/model/delete"), [{"id": "tbo-support:deepseek-chat"}]
        )
        self.assertFalse(frappe.db.get_value(PRICING, "deepseek-chat", "on_gateway"))


class TestTheGatewaysCredentials(GatewayCase):
    def test_a_refused_change_never_takes_the_working_key_off(self):
        add_provider()

        def answer(method, url, **kwargs):
            if method == "PATCH":
                return answered(503)
            return answered()

        self.admin.side_effect = answer
        self.admin.reset_mock()
        with self.assertRaises(frappe.ValidationError):
            ai_models.save_provider(
                {
                    "name": DEEPSEEK,
                    "style": "OpenAI-compatible",
                    "url": "https://api.deepseek.test",
                    "key": "sk-deepseek-new-123456",
                }
            )
        methods = [c.args[0] for c in self.admin.call_args_list]
        self.assertNotIn("DELETE", methods)

    def test_a_credential_not_there_yet_is_written_new(self):
        def answer(method, url, **kwargs):
            if method == "PATCH":
                return answered(404)
            return answered()

        self.admin.side_effect = answer
        ai_gateway.save_credential(
            "Fresh", {"api_key": "sk-fresh-123456", "api_base": "https://x.test"}
        )
        self.assertEqual(
            [c.args[0] for c in self.admin.call_args_list], ["PATCH", "DELETE", "POST"]
        )

    def test_a_credential_without_an_address_is_written_new(self):
        ai_gateway.save_credential("Claude", {"api_key": "sk-claude-123456"})
        self.assertEqual(
            [c.args[0] for c in self.admin.call_args_list], ["DELETE", "POST"]
        )

    def test_a_model_written_back_after_a_timeout_meets_no_twin(self):
        calls = []

        def answer(method, url, **kwargs):
            calls.append((method, url.replace(GATEWAY, "")))
            if (
                url.endswith("/model/new")
                and len([c for c in calls if c[1] == "/model/new"]) == 1
            ):
                raise requests.ReadTimeout("slow")
            return answered()

        self.admin.side_effect = answer
        with self.assertRaises(ai_gateway.GatewayError):
            ai_gateway.save_model(
                "glm-5", {"model": "openai/glm-5"}, previous={"model": "openai/old"}
            )
        # delete, the timed-out write, delete again, then the write-back
        self.assertEqual(
            calls,
            [
                ("POST", "/model/delete"),
                ("POST", "/model/new"),
                ("POST", "/model/delete"),
                ("POST", "/model/new"),
            ],
        )


class TestWriteAllOnce(GatewayCase):
    def test_the_sections_credential_is_written_once_for_all_its_models(self):
        set_hub(anthropic_api_key="sk-section-review-123456")
        add_model("kimi-a", "Anthropic-compatible")
        add_model("kimi-b", "Anthropic-compatible")
        self.admin.reset_mock()

        ai_models.write_all()

        section = [
            c
            for c in self.admin.call_args_list
            if c.args[0] in ("PATCH", "POST")
            and (c.kwargs.get("json") or {}).get("credential_name")
            == ai_engine.ANTHROPIC_SLOT
        ]
        self.assertEqual(len(section), 1)


class TestARedraftByAnotherModel(ReviewCase):
    """Finding 12: a draft sent counts for the model that made it."""

    def setUp(self):
        super().setUp()
        self.ticket = make_ticket(subject="Redraft").name
        key = ai_models.DRAFT_KEY.format(self.ticket, frappe.session.user)
        frappe.cache.delete_value(key)
        self.addCleanup(frappe.cache.delete_value, key)

    def test_the_replaced_draft_stays_unused(self):
        ai_models.note_draft(self.ticket, "model-a", DRAFT)
        ai_models.note_draft(self.ticket, "model-a", DRAFT)  # the same draft
        ai_models.note_draft(self.ticket, "model-b", DRAFT + " Thank you.")
        make_ticket_communication(
            self.ticket,
            f"<p>{DRAFT} Thank you.</p>",
            "agent@example.com",
            sent_or_received="Sent",
        )

        first = ai_models.quality("model-a", 30)["drafts"]
        second = ai_models.quality("model-b", 30)["drafts"]
        self.assertEqual((first["made"], first["used"], first["not_used"]), (1, 0, 1))
        self.assertEqual(
            (second["made"], second["used"], second["not_used"]), (1, 1, 0)
        )


class TestTestingAProviderThroughTheGateway(GatewayCase):
    """Finding 15: through the gateway, only an account's own model tests the account."""

    def setUp(self):
        super().setUp()
        add_provider()
        add_provider("Qwen", url="https://qwen.test", key=QWEN_KEY)
        add_model("deepseek-chat", DEEPSEEK)

    def test_another_accounts_model_tests_nothing(self):
        with patch("requests.post") as post:
            result = ai_models.test_provider("Qwen", "deepseek-chat")

        self.assertFalse(result["ok"])
        self.assertIn("not one of Qwen's models", result["message"])
        post.assert_not_called()

    def test_the_answer_names_the_account(self):
        with patch(
            "requests.post", return_value=openai_http_response(text="OK")
        ) as post:
            result = ai_models.test_provider(DEEPSEEK, "deepseek-chat")

        self.assertTrue(result["ok"], result)
        self.assertIn(DEEPSEEK, result["message"])
        self.assertEqual(post.call_args.args[0], GATEWAY + "/v1/chat/completions")


class TestImportingAReport(ReviewCase):
    """Finding 16 (and the import half of 8): one model name throughout, and the report
    answers the requests for its own job."""

    def test_a_model_name_with_spaces_answers_its_request(self):
        ai_models.request_eval("glm-5")

        result = api.import_eval(" glm-5 ", REPORT)

        self.assertEqual(result["model"], "glm-5")
        self.assertEqual(result["requests"], [])
        self.assertEqual(result["runs"][0]["source"], "Imported")

    def test_a_report_answers_the_requests_for_its_job_only(self):
        ai_models.request_eval("glm-5", "fix")

        result = api.import_eval("glm-5", REPORT)

        self.assertEqual(result["runs"][0]["job"], "investigate")
        self.assertEqual([r["status"] for r in result["requests"]], ["Queued"])
        done = api.import_eval("glm-5", REPORT, job="fix")
        self.assertEqual(done["runs"][0]["job"], "fix")
        self.assertEqual(done["requests"], [])


class TestALongBenchmarkSource(ReviewCase):
    """Finding 17: a source address up to the 500 characters the writer accepts is kept."""

    def test_a_long_source_address_is_kept(self):
        url = "https://benchmarks.test/" + "a" * 300

        result = ai_models.add_public_benchmark(
            "glm-5", {"benchmark": "tau2-bench", "score": "61%", "source_url": url}
        )

        self.assertEqual(result["public"][0]["source_url"], url)


class TestReferencesOfAnyShape(ReviewCase):
    def test_odd_shapes_count_as_nothing_missing(self):
        for references in (
            {"checked": 3, "missing": 1},
            {"checked": 3, "missing": "acme/x.py"},
            {"checked": "many", "missing": {"kind": "file"}},
            {"checked": None, "missing": None},
            "not a dict",
        ):
            # never raises: a report is never refused for the shape of its check
            ai_models.record_references("CPR-no-such-run", references)


class TestAGuardThatNoLongerHolds(ReviewCase):
    def test_a_save_after_someone_else_changed_the_job_is_refused(self):
        change = {"primary_section": "Anthropic-compatible"}
        compared = ai_models.guard("fix", change)["current_model"]
        self.assertEqual(compared, "gpt-test-model")
        # meanwhile someone else gives the job another first model
        ai_models.save_job("fix", change)

        with self.assertRaises(frappe.ValidationError):
            ai_models.save_job(
                "fix", {"allow_fallback": "Off", "expected_model": compared}
            )
        self.assertNotEqual(
            getattr(ai_engine.job_row("fix"), "allow_fallback", ""), "Off"
        )

        # compared against the job as it is now, the save goes through
        ai_models.save_job(
            "fix", {"allow_fallback": "Off", "expected_model": "kimi-k2.6"}
        )
        self.assertEqual(ai_engine.job_row("fix").allow_fallback, "Off")
