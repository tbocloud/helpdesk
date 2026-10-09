# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Shadow mode: Copilot's findings stay with the team, and agents rate each diagnosis."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import client_api
from helpdesk.api import copilot as api
from helpdesk.copilot import customer, router, runs
from helpdesk.test_utils import (
    FakeWorker,
    create_agent,
    create_customer,
    create_user,
    fake_investigation,
    hold_commits,
    make_copilot_settings,
    make_project,
    make_support_connection,
    make_ticket,
)


class ShadowCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_copilot_settings(enabled=1, min_confidence=0.6, shadow_mode=1)
        self.customer = create_customer("Shadow Customer Co").name
        self.conn = make_support_connection(
            self.customer, client_capabilities='["hub_api_v1"]'
        ).name
        self.ticket = make_ticket(subject="Shadow run", customer=self.customer)
        self.ticket.db_set(
            {
                "custom_qcs_connection": self.conn,
                "custom_client_ticket": "SUP-2026-00098",
            }
        )
        self.pushed = []
        patcher = patch.object(client_api, "hub_api", side_effect=self.fake_hub_api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_hub_api(self, conn, method, payload=None):
        self.pushed.append((method, payload or {}))
        return {"ok": True}

    def investigated(self, category, confidence=0.9, **extra):
        run = runs.start_run(self.ticket.name)
        run = runs.transition(run, "Investigating", runs.WORKER)
        return router.route(run, fake_investigation(category, confidence, **extra))

    def notes(self):
        return frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": self.ticket.name},
            pluck="content",
        )

    def stage_events(self, run):
        return [
            json.loads(payload)
            for payload in frappe.get_all(
                "HDS Copilot Event",
                filters={"run": run.name, "event_type": "stage"},
                pluck="payload",
                order_by="creation asc",
            )
        ]


class TestShadowMode(ShadowCase):
    def test_the_customer_hears_nothing(self):
        run = self.investigated("question")

        self.assertTrue(run.shadow)
        self.assertEqual(self.pushed, [])
        self.assertFalse(
            frappe.db.get_value("HD Ticket", self.ticket.name, "custom_copilot_stage")
        )
        self.assertFalse(
            [note for note in self.notes() if "Copilot → customer" in note]
        )
        stages = self.stage_events(run)
        self.assertEqual([s["stage"] for s in stages], ["Received", "Working on it"])
        self.assertTrue(all(s["shadow"] and not s["pushed"] for s in stages))

    def test_the_diagnosis_is_a_shadow_note_and_the_reply_is_still_drafted(self):
        with patch("helpdesk.ai_suggestion.store_suggestion") as store:
            self.investigated("customer_mistake")

        store.assert_called_once()
        diagnosis = [note for note in self.notes() if "Copilot diagnosis" in note]
        self.assertEqual(len(diagnosis), 1)
        self.assertIn("(shadow)", diagnosis[0])
        self.assertIn("Rate this diagnosis", diagnosis[0])

    def test_a_core_issue_hands_nothing_over(self):
        developer = create_user("dev.shadow@example.com").name
        frappe.db.set_value(
            "HD Customer", self.customer, "custom_assigned_developer", developer
        )
        make_project("Shadow Customer Co support", owner=developer).db_set(
            "customer", self.customer
        )

        with patch.object(runs, "tell_people") as tell:
            run = self.investigated("core_issue")

        self.assertEqual(run.state, "Handed Over")
        self.assertFalse(run.task)
        self.assertFalse(frappe.db.exists("Task", {"hd_ticket": self.ticket.name}))
        tell.assert_not_called()
        self.assertTrue(
            frappe.db.exists(
                "HDS Copilot Event",
                {"run": run.name, "event_type": "hand_over_skipped"},
            )
        )

    def test_the_agent_reply_moves_the_run_but_tells_the_customer_nothing(self):
        run = self.investigated("question")
        customer.on_agent_reply(frappe.get_doc("HDS Copilot Run", run.name))

        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Answered"
        )
        self.assertEqual(self.pushed, [])
        self.assertEqual(self.stage_events(run)[-1]["stage"], "Resolved")

    def test_the_portal_shows_no_question_for_a_shadow_run(self):
        self.investigated("question")
        self.ticket.db_set(
            "custom_copilot_stage", "Resolved"
        )  # as an earlier live run could leave it

        info = api.get_resolution(self.ticket.name)
        self.assertFalse(info["can_decide"])
        self.assertIsNone(info["stage"])
        self.assertEqual(info["message"], "")

    def test_a_run_keeps_the_mode_it_started_in(self):
        run = runs.start_run(self.ticket.name)
        make_copilot_settings(enabled=1, shadow_mode=0)
        runs.transition(run, "Investigating", runs.WORKER)
        self.assertEqual(self.pushed, [])

    def test_live_mode_still_reaches_the_customer(self):
        make_copilot_settings(enabled=1, shadow_mode=0)
        run = self.investigated("question")

        self.assertFalse(run.shadow)
        self.assertEqual(
            [p["stage"] for m, p in self.pushed if m == "add_update"],
            ["Received", "Working on it"],
        )
        self.assertNotIn("(shadow)", "".join(self.notes()))

    def test_tokens_and_the_model_are_kept(self):
        cost = {"tokens_in": 1200, "tokens_out": 300, "usd": 0.02, "model": "kimi-k2.6"}
        run = self.investigated("bug", cost=cost)

        self.assertEqual(
            (run.tokens_in, run.tokens_out, run.model_used), (1200, 300, "kimi-k2.6")
        )
        self.assertEqual(json.loads(run.investigation)["cost"]["tokens"], 1500)


class TestReview(ShadowCase):
    def setUp(self):
        super().setUp()
        self.agent = create_agent("shadow.reviewer@example.com").name

    def review(self, verdict, root_cause="", note=""):
        frappe.set_user(self.agent)
        try:
            return api.review_diagnosis(self.ticket.name, verdict, root_cause, note)
        finally:
            frappe.set_user("Administrator")

    def test_an_agent_rates_the_diagnosis(self):
        run = self.investigated("bug")

        info = self.review(
            "Wrong", "customer_mistake", "The customer typed the wrong rate"
        )

        self.assertEqual(info["review"]["verdict"], "Wrong")
        self.assertEqual(info["review"]["root_cause"], "customer_mistake")
        self.assertEqual(info["review"]["by"], self.agent)
        doc = frappe.get_doc("HDS Copilot Run", run.name)
        self.assertEqual(
            (doc.review_verdict, doc.reviewed_root_cause), ("Wrong", "customer_mistake")
        )
        self.assertEqual(doc.review_note, "The customer typed the wrong rate")
        self.assertTrue(doc.reviewed_at)
        self.assertTrue(
            frappe.db.exists(
                "HDS Copilot Event", {"run": run.name, "event_type": "review"}
            )
        )

    def test_right_keeps_copilots_category_and_a_new_rating_replaces_the_old(self):
        run = self.investigated("question")
        self.review("Wrong", "bug")

        info = self.review("Right", "bug")

        self.assertEqual(
            (info["review"]["verdict"], info["review"]["root_cause"]),
            ("Right", "question"),
        )
        self.assertEqual(
            frappe.db.count(
                "HDS Copilot Event", {"run": run.name, "event_type": "review"}
            ),
            2,
        )

    def test_wrong_needs_the_real_root_cause(self):
        self.investigated("bug")
        with self.assertRaises(frappe.ValidationError):
            self.review("Wrong")

    def test_bad_values_are_refused(self):
        self.investigated("bug")
        with self.assertRaises(frappe.ValidationError):
            self.review("Maybe")
        with self.assertRaises(frappe.ValidationError):
            self.review("Partly", "no_such_cause")

    def test_nothing_to_rate_before_the_diagnosis(self):
        runs.start_run(self.ticket.name)
        with self.assertRaises(frappe.ValidationError):
            self.review("Right")

    def test_only_agents_may_rate(self):
        self.investigated("bug")
        frappe.set_user(create_user("not.an.agent@example.com").name)
        with self.assertRaises(frappe.PermissionError):
            api.review_diagnosis(self.ticket.name, "Right")

    def test_the_dialog_gets_the_review_and_the_categories(self):
        self.investigated("bug")
        info = api.get_run(self.ticket.name)

        self.assertTrue(info["shadow"])
        self.assertTrue(info["can_review"])
        self.assertEqual(info["categories"], list(router.CATEGORIES))
        self.assertIsNone(info["review"]["verdict"])


class TestBaseCommit(ShadowCase):
    def test_a_run_reads_the_given_app_at_the_given_commit(self):
        run = runs.start_run(
            self.ticket.name, base_commit="ABCDEF1234567", base_app="service_pro"
        )

        self.assertEqual(
            (run.base_app, run.base_commit), ("service_pro", "abcdef1234567")
        )
        context = runs.run_context(run)
        self.assertEqual(
            (context["base_app"], context["base_commit"]),
            ("service_pro", "abcdef1234567"),
        )
        self.assertTrue(context["shadow"])

    def test_bad_values_are_refused(self):
        for app, commit in (
            ("service_pro", "not-a-commit"),
            ("bad app!", "abcdef1"),
            ("service_pro", ""),
            ("", "abc"),
        ):
            with self.assertRaises(frappe.ValidationError, msg=(app, commit)):
                runs.start_run(self.ticket.name, base_commit=commit, base_app=app)

    def test_the_worker_gets_it_with_the_claim(self):
        frappe.db.set_value(
            "HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled"
        )
        agent = create_agent("shadow.starter@example.com").name
        frappe.set_user(agent)
        api.start_run(
            self.ticket.name, base_commit="0123456789abcdef", base_app="ksa_vat"
        )
        frappe.set_user("Administrator")

        job = FakeWorker("shadow-worker").claim()

        self.assertEqual(job["context"]["base_commit"], "0123456789abcdef")
        self.assertEqual(job["context"]["base_app"], "ksa_vat")
