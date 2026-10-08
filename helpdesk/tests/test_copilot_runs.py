# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot runs: one per ticket, moved only along the allowed transitions, kept alive by leases."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.copilot import router, runs
from helpdesk.test_utils import (
    create_customer,
    fake_investigation,
    hold_commits,
    make_copilot_run,
    make_copilot_settings,
    make_support_connection,
    make_ticket,
)


class CopilotCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.customer = create_customer("Copilot Run Co").name
        self.conn = make_support_connection(self.customer).name
        make_copilot_settings(enabled=1, lease_minutes=5, max_lease_losses=2, min_confidence=0.6)

    def ticket(self, subject="Copilot ticket"):
        return make_ticket(subject=subject, customer=self.customer)


class TestRunStart(CopilotCase):
    def test_a_ticket_of_an_enabled_customer_gets_a_run(self):
        frappe.db.set_value("HD Customer", self.customer, "custom_copilot_enabled", 1)
        ticket = self.ticket()
        run_name = frappe.db.get_value("HD Ticket", ticket.name, "custom_copilot_run")
        self.assertTrue(run_name)
        run = frappe.get_doc("HDS Copilot Run", run_name)
        self.assertEqual(run.state, "Queued")
        self.assertEqual(run.connection, self.conn)
        self.assertEqual(frappe.db.get_value("HD Ticket", ticket.name, "custom_copilot_stage"), "Received")
        self.assertTrue(frappe.db.exists("HDS Copilot Event", {"run": run.name, "event_type": "state_change"}))

    def test_no_run_for_other_customers_or_when_switched_off(self):
        ticket = self.ticket("Plain")
        self.assertFalse(frappe.db.get_value("HD Ticket", ticket.name, "custom_copilot_run"))
        frappe.db.set_value("HD Customer", self.customer, "custom_copilot_enabled", 1)
        make_copilot_settings(enabled=0)
        ticket = self.ticket("Switched off")
        self.assertFalse(frappe.db.get_value("HD Ticket", ticket.name, "custom_copilot_run"))

    def test_one_active_run_per_ticket(self):
        ticket = self.ticket()
        first = runs.start_run(ticket.name)
        self.assertEqual(runs.start_run(ticket.name).name, first.name)
        runs.transition(first, "Cancelled", runs.AGENT)
        self.assertNotEqual(runs.start_run(ticket.name).name, first.name)


class TestTransitions(CopilotCase):
    def setUp(self):
        super().setUp()
        self.run = make_copilot_run(self.ticket().name)

    def test_only_allowed_moves_pass(self):
        with self.assertRaises(frappe.ValidationError):
            runs.transition(self.run, "Explaining", runs.SYSTEM)
        with self.assertRaises(frappe.ValidationError):
            runs.transition(self.run, "Investigating", runs.AGENT)
        self.assertEqual(runs.transition(self.run, "Investigating", runs.WORKER).state, "Investigating")

    def test_an_agent_can_cancel_but_a_worker_cannot(self):
        with self.assertRaises(frappe.ValidationError):
            runs.transition(self.run, "Cancelled", runs.WORKER)
        run = runs.transition(self.run, "Cancelled", runs.AGENT)
        self.assertEqual(run.state, "Cancelled")
        self.assertTrue(run.finished_at)

    def test_every_move_writes_an_event_and_tells_the_page(self):
        with patch.object(runs, "publish_event") as publish:
            runs.transition(self.run, "Investigating", runs.WORKER, note="claimed")
        self.assertEqual(publish.call_args.kwargs["data"], {"ticket": self.run.ticket, "run": self.run.name})
        last = frappe.get_all(
            "HDS Copilot Event",
            filters={"run": self.run.name, "event_type": "state_change"},
            fields=["payload", "actor"],
            order_by="creation desc",
            limit=1,
        )[0]
        self.assertEqual(json.loads(last.payload)["to"], "Investigating")
        self.assertEqual(last.actor, runs.WORKER)
        self.assertEqual(frappe.db.get_value("HD Ticket", self.run.ticket, "custom_copilot_stage"), "Working on it")


class TestEvents(CopilotCase):
    def setUp(self):
        super().setUp()
        self.run = make_copilot_run(self.ticket().name)

    def test_worker_events_are_idempotent_by_seq(self):
        self.assertTrue(runs.add_event(self.run, "note", {"a": 1}, runs.WORKER, seq=7))
        self.assertFalse(runs.add_event(self.run, "note", {"a": 2}, runs.WORKER, seq=7))
        self.assertEqual(frappe.db.count("HDS Copilot Event", {"run": self.run.name, "seq": 7}), 1)

    def test_a_huge_payload_is_cut(self):
        runs.add_event(self.run, "note", {"blob": "x" * 40000}, runs.WORKER, seq=1)
        row = frappe.db.get_value(
            "HDS Copilot Event", {"run": self.run.name, "seq": 1}, ["payload", "truncated"], as_dict=True
        )
        self.assertTrue(row.truncated)
        self.assertLess(len(row.payload), runs.MAX_PAYLOAD_BYTES + 100)
        self.assertTrue(json.loads(row.payload)["_truncated"])


class TestLeases(CopilotCase):
    def setUp(self):
        super().setUp()
        # other queued runs on the site would be claimed first (rolled back with the test)
        frappe.db.set_value("HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled")
        self.r1 = make_copilot_run(self.ticket("first").name, queued_at=add_to_date(now_datetime(), minutes=-2))
        self.r2 = make_copilot_run(self.ticket("second").name)

    def expire(self, name):
        frappe.db.set_value(
            "HDS Copilot Run", name, "lease_expires", add_to_date(now_datetime(), minutes=-1), update_modified=False
        )

    def test_claim_hands_out_the_oldest_run_once(self):
        first, token = runs.claim("w1")
        self.assertEqual(first.name, self.r1.name)
        self.assertEqual(first.state, "Investigating")
        self.assertEqual(first.worker_id, "w1")
        second, _ = runs.claim("w2")
        self.assertEqual(second.name, self.r2.name)
        self.assertEqual(runs.claim("w3"), (None, None))
        self.assertEqual(runs.check_lease(first.name, token).name, first.name)
        with self.assertRaises(frappe.PermissionError):
            runs.check_lease(first.name, "wrong")

    def test_heartbeat_extends_and_a_cancel_is_reported(self):
        run, token = runs.claim("w1")
        before = run.lease_expires
        with patch.object(runs, "now_datetime", return_value=add_to_date(now_datetime(), minutes=2)):
            answer = runs.heartbeat(run.name, token)
        self.assertEqual(answer["action"], "continue")
        self.assertGreater(frappe.db.get_value("HDS Copilot Run", run.name, "lease_expires"), before)
        runs.transition(run.name, "Cancelled", runs.AGENT)
        self.assertEqual(runs.heartbeat(run.name, token)["action"], "cancel")

    def test_a_lost_lease_requeues_then_fails(self):
        run, token = runs.claim("w1")
        self.expire(run.name)
        runs.expire_stale_leases()
        run.reload()
        self.assertEqual((run.state, run.lease_losses), ("Queued", 1))
        with self.assertRaises(frappe.PermissionError):
            runs.check_lease(run.name, token)

        run, _ = runs.claim("w1")
        self.assertEqual(run.name, self.r1.name)
        self.expire(run.name)
        with patch.object(runs, "tell_people") as tell:
            runs.expire_stale_leases()
        run.reload()
        self.assertEqual(run.state, "Failed")
        tell.assert_called_once()
        self.assertEqual(frappe.db.get_value("HD Ticket", run.ticket, "custom_copilot_stage"), "With our team")


class TestRouter(CopilotCase):
    def investigating(self, subject):
        return runs.transition(make_copilot_run(self.ticket(subject).name), "Investigating", runs.WORKER)

    def test_each_root_cause_moves_the_run_to_its_state(self):
        for category, state in router.STATE_FOR_CATEGORY.items():
            run = router.route(self.investigating(category), fake_investigation(category))
            self.assertEqual(run.state, state, category)
            self.assertEqual(run.root_cause_category, category)
            self.assertEqual(frappe.db.get_value("HD Ticket", run.ticket, "custom_root_cause"), category)
            self.assertEqual(
                frappe.db.get_value("HD Ticket", run.ticket, "custom_copilot_stage"),
                router.STAGE_FOR_CATEGORY[category],
            )

    def test_low_confidence_counts_as_unclear(self):
        run = router.route(self.investigating("vague"), fake_investigation("bug", confidence=0.3))
        self.assertEqual((run.state, run.root_cause_category), ("Explaining", "unclear"))
        self.assertEqual(json.loads(run.investigation)["root_cause_category"], "bug")

    def test_a_bad_result_is_refused(self):
        run = self.investigating("bad")
        with self.assertRaises(frappe.ValidationError):
            router.route(run, fake_investigation("bug", root_cause_category="magic"))
        with self.assertRaises(frappe.ValidationError):
            router.route(run, fake_investigation("bug", confidence=2))
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Investigating")

    def test_the_context_has_the_ticket_and_no_credentials(self):
        run = self.investigating("context")
        context = runs.run_context(run)
        self.assertEqual(context["ticket"]["name"], run.ticket)
        self.assertEqual(context["ticket"]["subject"], "context")
        self.assertIn("triage", context)
        self.assertNotIn("api_key", json.dumps(context))
