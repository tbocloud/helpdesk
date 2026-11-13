# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Action approvals (Phase 18): who gets the card, who may decide, and what the record keeps."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api import copilot_actions as api
from helpdesk.copilot import actions
from helpdesk.test_utils import create_agent, hold_commits, make_copilot_settings

PAYLOAD = {"method": "press.api.bench.restart", "args": {"name": "bench-0020"}}


class ActionCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.one = create_agent("action.one@example.com").name
        self.two = create_agent("action.two@example.com").name
        self.senior = create_agent("action.senior@example.com").name
        make_copilot_settings(
            enabled=1,
            approvers=[
                {"user": self.one, "senior": 0, "active": 1},
                {"user": self.two, "senior": 0, "active": 1},
                {"user": self.senior, "senior": 1, "active": 1},
            ],
        )
        self.notified, self.sent = [], []

        def notify(users, doctype, name, subject, *args, **kwargs):
            self.notified.append((list(users), subject, bool(kwargs.get("escalate"))))

        for target, side_effect in (
            ("helpdesk.work_reminders.notify_users", notify),
            (
                "helpdesk.copilot.actions.send_card",
                lambda person, approval: self.sent.append(person),
            ),
        ):
            patcher = patch(target, side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(frappe.set_user, "Administrator")

    def ask(self, user=None, risk="normal", payload=None, **values):
        return actions.request(
            "Press",
            "Restart bench-0020 (galom + 2 sites)",
            "press.api.bench.restart name=bench-0020",
            payload or PAYLOAD,
            risk=risk,
            user=user or self.one,
            via="Teams",
            **values,
        )


class TestAsking(ActionCase):
    def test_the_card_goes_to_an_approver_who_is_not_the_requester(self):
        doc = self.ask()
        self.assertEqual(doc.status, "Pending")
        self.assertEqual(doc.requested_by, self.one)
        self.assertEqual(doc.assigned_to, self.two)
        self.assertEqual(self.sent, [self.two])
        self.assertTrue(doc.expires_at > now_datetime())
        self.assertEqual(doc.payload_hash, actions.payload_hash(PAYLOAD))

    def test_a_senior_action_goes_to_a_senior(self):
        doc = self.ask(risk="senior")
        self.assertEqual(doc.assigned_to, self.senior)

    def test_asking_twice_for_the_same_thing_returns_the_live_request(self):
        first = self.ask()
        again = self.ask()
        self.assertEqual(first.name, again.name)
        self.assertEqual(len(self.sent), 1)
        other = self.ask(payload={**PAYLOAD, "args": {"name": "bench-0021"}})
        self.assertNotEqual(first.name, other.name)

    def test_a_request_needs_a_payload_and_a_known_kind(self):
        with self.assertRaises(frappe.ValidationError):
            actions.request("Press", "x", "x", {}, user=self.one)
        with self.assertRaises(frappe.ValidationError):
            actions.request("Mail", "x", "x", PAYLOAD, user=self.one)


class TestDeciding(ActionCase):
    def test_the_requester_cannot_approve_their_own_request(self):
        doc = self.ask()
        with self.assertRaises(frappe.PermissionError):
            actions.decide(doc.name, self.one, True)
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, doc.name, "status"), "Pending"
        )

    def test_a_senior_action_refuses_a_plain_approver(self):
        doc = self.ask(risk="senior")
        with self.assertRaises(frappe.PermissionError):
            actions.decide(doc.name, self.two, True)
        actions.decide(doc.name, self.senior, True)
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, doc.name, "status"), "Approved"
        )

    def test_approve_then_run_then_the_record_is_spent(self):
        doc = self.ask()
        self.assertIsNone(actions.approved_for("Press", PAYLOAD, self.one))
        outcome = actions.decide(doc.name, self.two, True, via="Teams")
        self.assertEqual(outcome["outcome"], "approved")
        doc.reload()
        self.assertEqual(
            (doc.status, doc.decided_by, doc.decided_via),
            ("Approved", self.two, "Teams"),
        )
        live = actions.approved_for("Press", PAYLOAD, self.one)
        self.assertEqual(live.name, doc.name)
        # someone else's identical ask is not covered by this approval
        self.assertIsNone(actions.approved_for("Press", PAYLOAD, self.senior))
        actions.mark_executed(doc.name, True, "Restarted bench-0020 in 41 s")
        doc.reload()
        self.assertEqual(doc.status, "Executed")
        self.assertTrue(doc.executed_at)
        self.assertIsNone(actions.approved_for("Press", PAYLOAD, self.one))
        with self.assertRaises(frappe.ValidationError):
            actions.mark_executed(doc.name, True)

    def test_a_failed_run_is_kept_too(self):
        doc = self.ask()
        actions.decide(doc.name, self.two, True)
        actions.mark_executed(doc.name, False, "Press answered 500")
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, doc.name, "status"), "Failed"
        )

    def test_reject_keeps_the_reason_and_the_first_decision_wins(self):
        doc = self.ask()
        actions.decide(doc.name, self.two, False, "Not during the demo")
        doc.reload()
        self.assertEqual((doc.status, doc.note), ("Rejected", "Not during the demo"))
        with self.assertRaises(frappe.ValidationError):
            actions.decide(doc.name, self.senior, True)

    def test_an_expired_request_is_void(self):
        doc = self.ask()
        doc.db_set("expires_at", add_to_date(now_datetime(), minutes=-1))
        with self.assertRaises(frappe.ValidationError):
            actions.decide(doc.name, self.two, True)
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, doc.name, "status"), "Expired"
        )

    def test_the_api_needs_a_reason_to_reject(self):
        doc = self.ask()
        frappe.set_user(self.two)
        with self.assertRaises(frappe.ValidationError):
            api.decide_action(doc.name, False, "")
        result = api.decide_action(doc.name, False, "No, not this week")
        self.assertEqual(result["status"], "Rejected")
        # the decision is logged from the desktop app too, the note as a fingerprint (Phase 21)
        logged = frappe.get_all(
            "HDS Copilot Call Log",
            filters={"tool": "decide_action", "kind": "Desktop", "user": self.two},
            fields=["arguments"],
        )
        self.assertEqual(len(logged), 1)
        self.assertIn(doc.name, logged[0].arguments)
        self.assertNotIn("not this week", logged[0].arguments)

    def test_only_the_requester_marks_the_run(self):
        doc = self.ask()
        actions.decide(doc.name, self.two, True)
        frappe.set_user(self.two)
        with self.assertRaises(frappe.PermissionError):
            api.mark_action_executed(doc.name, True, "")
        frappe.set_user(self.one)
        self.assertEqual(
            api.mark_action_executed(doc.name, True, "done")["status"], "Executed"
        )
        # the outcome is logged once, by the requester, from the desktop app (Phase 21)
        self.assertEqual(
            frappe.db.count(
                "HDS Copilot Call Log",
                {"tool": "mark_action_executed", "kind": "Desktop", "user": self.one},
            ),
            1,
        )


class TestRemindersAndCards(ActionCase):
    def test_reminder_then_escalation_then_expiry(self):
        doc = self.ask()
        now = now_datetime()
        actions.remind_and_escalate(now=add_to_date(now, minutes=16))
        doc.reload()
        self.assertTrue(doc.reminded_at)
        self.assertFalse(doc.escalated_at)
        self.assertEqual(self.sent, [self.two, self.two])
        actions.remind_and_escalate(now=add_to_date(now, minutes=46))
        doc.reload()
        self.assertTrue(doc.escalated_at)
        self.assertTrue(any(escalate for _users, _subject, escalate in self.notified))
        actions.remind_and_escalate(now=add_to_date(now, minutes=61))
        doc.reload()
        self.assertEqual(doc.status, "Expired")

    def test_an_approved_but_never_run_action_expires_too(self):
        doc = self.ask()
        actions.decide(doc.name, self.two, True)
        actions.remind_and_escalate(now=add_to_date(now_datetime(), minutes=61))
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, doc.name, "status"), "Expired"
        )

    def test_the_card_has_the_two_buttons_and_then_the_decision(self):
        doc = self.ask()
        card = actions.card(doc)
        self.assertEqual(
            [a["verb"] for a in card["actions"]], ["action_approve", "action_reject"]
        )
        self.assertIn("press.api.bench.restart name=bench-0020", card["lines"][0])
        actions.decide(doc.name, self.two, True)
        doc.reload()
        decided = actions.card(doc)
        self.assertEqual(decided["actions"], [])
        self.assertEqual(decided["tone"], "good")
        self.assertIn("approved", decided["title"])

    def test_the_api_payload_names_what_a_caller_needs(self):
        doc = self.ask()
        frappe.set_user(self.one)
        result = api.get_action_approval(doc.name)
        self.assertEqual(result["status"], "Pending")
        self.assertEqual(result["assigned_to"], self.two)
        self.assertIsNone(api.approved_action("Press", PAYLOAD))
