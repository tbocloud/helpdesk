# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot builds an approved customization (Phase 8): the customer's written scope, then the fix path."""

import json
from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate

from helpdesk.api import copilot as api
from helpdesk.api import copilot_worker as worker_api
from helpdesk.api import customization
from helpdesk.copilot import approvals, assistant, fixes, pilot, router, runs
from helpdesk.copilot.mcp import tools_worker
from helpdesk.copilot.mcp.auth import WORKER, Caller
from helpdesk.test_utils import (
    create_contact,
    fake_investigation,
    make_site_registry,
    make_ticket,
)
from helpdesk.tests.test_copilot_fix_flow import NEW_SHA, REPO, SHA, FixCase

CUSTOMER_EMAIL = "owner@build-client.example"
SCOPE = "A Sales Invoice cannot be submitted without at least one row in Sales Team."
CHECKS = [
    "a normal invoice without a Sales Team row cannot be submitted",
    "a credit note without one can",
    "an invoice with one Sales Person submits as before",
]


class BuildCase(FixCase):
    def setUp(self):
        super().setUp()
        frappe.db.set_value(
            "HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled"
        )
        self.settings(shadow_mode=0, build_enabled=1, max_fix_usd=1.5)
        frappe.db.set_value("HD Customer", self.customer, "custom_copilot_level", "Fix")
        make_site_registry(
            self.customer,
            apps=[
                {
                    "app": "demo_app",
                    "repository": f"https://github.com/{REPO}.git",
                    "branch": "main",
                    "deployed_commit": SHA,
                }
            ],
        )
        create_contact("Build Client Owner", CUSTOMER_EMAIL)
        self.ticket = make_ticket(
            subject="Require a Sales Person on Sales Invoice",
            customer=self.customer,
            raised_by=CUSTOMER_EMAIL,
        )
        self.run = self.explained()

    def explained(self, category="customization_request"):
        run = runs.start_run(self.ticket.name)
        run = runs.transition(run, "Investigating", runs.WORKER)
        return router.route(
            run,
            fake_investigation(
                category,
                0.9,
                proposal={
                    "action": "Add a validation",
                    "estimate_hours": 4,
                    "scope": SCOPE,
                    "done_when": CHECKS,
                },
            ),
        )

    def estimate(self, hours=4, scope=SCOPE, checks=CHECKS, approve=True):
        frappe.set_user(self.developer)
        try:
            customization.send_estimate(
                self.ticket.name,
                hours,
                str(add_days(nowdate(), 3)),
                "",
                scope,
                "\n".join(checks),
            )
        finally:
            frappe.set_user("Administrator")
        if approve:
            frappe.set_user(CUSTOMER_EMAIL)
            try:
                customization.decide_estimate(self.ticket.name, 1)
            finally:
                frappe.set_user("Administrator")

    def build(self, user=None):
        frappe.set_user(user or self.developer)
        try:
            return api.build_customization(self.ticket.name)
        finally:
            frappe.set_user("Administrator")

    def refusal(self):
        return fixes.build_refusal(self.current_run())


class TestBuildWithCopilot(BuildCase):
    def test_an_approved_scope_is_built_like_a_fix(self):
        self.estimate()
        self.assertTrue(api.get_run(self.ticket.name)["build"]["can_build"])

        info = self.build()

        run = self.current_run()
        self.assertEqual(run.name, self.run.name)
        self.assertEqual(
            (run.state, run.fix_status, run.fix_requested),
            ("Preparing Fix", "Queued", 1),
        )
        built = fixes.build_of(run)
        self.assertEqual(
            (built["scope"], built["checks"], built["hours"]), (SCOPE, CHECKS, 4)
        )
        self.assertEqual(built["approved_by"], CUSTOMER_EMAIL)
        self.assertTrue(
            frappe.db.get_value("Task", run.task, "subject").startswith(
                "Copilot build: "
            )
        )
        self.assertTrue(info["build"]["building"])
        self.assertFalse(info["build"]["can_build"])

        job = worker_api.claim_job("build-worker", 1, "fix")
        fix = job["context"]["fix"]
        self.assertEqual(fix["build"]["checks"], CHECKS)
        self.assertEqual(fix["build"]["scope"], SCOPE)
        self.assertEqual(fix["max_usd"], 3.0)  # twice the cap of a fix

    def test_the_customer_hears_about_their_change(self):
        self.estimate()
        self.build()

        messages = [
            json.loads(p)["message"]
            for p in frappe.get_all(
                "HDS Copilot Event",
                filters={"run": self.run.name, "event_type": "stage"},
                pluck="payload",
                order_by="creation asc",
            )
        ]
        self.assertIn("We are building the change you approved.", messages[-1])

    def test_the_tickets_open_task_is_used(self):
        from helpdesk.api.work import create_task_from_ticket

        self.estimate()
        task = create_task_from_ticket(self.ticket.name, self.project)["task"]["name"]

        self.build()

        self.assertEqual(self.current_run().task, task)

    def test_a_closed_run_gets_a_new_build_run(self):
        runs.transition(self.run, "Answered", runs.AGENT)
        runs.transition(self.run.name, "Closed", runs.AGENT)
        self.estimate()

        self.build()

        run = self.current_run()
        self.assertNotEqual(run.name, self.run.name)
        self.assertEqual(
            (run.kind, run.state, run.root_cause_category),
            ("code", "Preparing Fix", "customization_request"),
        )
        self.assertEqual(run.proposal, self.run.proposal)
        self.assertTrue(fixes.build_of(run))

    def test_agents_are_told_when_copilot_can_build_it(self):
        self.estimate()
        texts = [args[3] for args in self.notified if len(args) > 3]
        self.assertTrue(any("Build with Copilot" in text for text in texts), texts)


class TestTheBuildGoesLive(BuildCase):
    def test_the_customer_checks_their_change_and_a_reopen_goes_to_a_person(self):
        self.estimate()
        self.build()
        run = runs.transition(self.current_run(), "Merged", runs.SYSTEM)
        fixes.mark_deployed(run, self.developer)

        stages = [
            json.loads(p)
            for p in frappe.get_all(
                "HDS Copilot Event",
                filters={"run": run.name, "event_type": "stage"},
                pluck="payload",
                order_by="creation asc",
            )
        ]
        self.assertEqual(stages[-1]["stage"], "Resolved")
        self.assertIn("Your change is live.", stages[-1]["message"])

        frappe.set_user(CUSTOMER_EMAIL)
        try:
            api.decide_resolution(self.ticket.name, 0, "It still lets returns through")
        finally:
            frappe.set_user("Administrator")
        self.assertEqual(self.current_run().state, "Escalated")


class TestBuildRefusals(BuildCase):
    def assertRefused(self, words):
        self.assertIn(words, self.refusal() or "")
        card = api.get_run(self.ticket.name)["build"]
        self.assertFalse(card and card["can_build"])
        with self.assertRaises(frappe.ValidationError):
            self.build()

    def test_no_approved_estimate(self):
        self.estimate(approve=False)
        self.assertRefused("has not approved")

    def test_a_scope_edited_after_the_approval(self):
        self.estimate()
        frappe.db.set_value(
            "HD Ticket",
            self.ticket.name,
            "custom_estimate_scope",
            SCOPE + " Also on POS.",
        )
        self.assertRefused("send it again")

    def test_an_estimate_without_a_written_scope(self):
        self.estimate(scope="", checks=[])
        self.assertRefused("no written scope")

    def test_too_big(self):
        self.estimate(hours=12)
        self.assertRefused("up to 8 hours")

    def test_a_customer_below_the_fix_level(self):
        self.estimate()
        frappe.db.set_value(
            "HD Customer", self.customer, "custom_copilot_level", "Explain"
        )
        self.assertRefused("Fix level")

    def test_switched_off(self):
        self.estimate()
        self.settings(shadow_mode=0, build_enabled=0)
        self.assertRefused("switched off")

    def test_not_a_customization(self):
        self.run.db_set("root_cause_category", "question")
        self.estimate()
        self.assertRefused("only a request")

    def test_twice(self):
        self.estimate()
        self.build()
        self.assertRefused("still working")


class TestTheBuildsApproval(BuildCase):
    def submitted(self, check_results):
        self.estimate()
        self.build()
        job = worker_api.claim_job("build-worker", 1, "fix")
        task = self.current_run().task
        self.github.add_pull(
            REPO, 41, NEW_SHA, body=f"Closes {task}", author="tbo-copilot[bot]"
        )
        caller = Caller(user="Administrator", kind=WORKER, run=job["run"])
        with patch("helpdesk.copilot.github.copilot_only", return_value=True):
            tools_worker.submit_change(
                caller,
                REPO,
                41,
                NEW_SHA,
                branch=fixes.copilot_branch(self.current_run()),
                summary="Sales Invoice requires a Sales Team row.",
                evidence=[{"check": "the app's tests", "result": "pass"}],
                tested_on="a sandbox site",
                check_results=check_results,
            )
        return self.approval()

    def test_the_approval_is_bound_to_the_scope_and_shows_each_check(self):
        results = [
            {
                "check": CHECKS[0],
                "test": "test_needs_sales_team",
                "before": "fail",
                "after": "pass",
            },
            {
                "check": CHECKS[1],
                "test": "test_return_without",
                "before": "pass",
                "after": "pass",
            },
            {
                "check": CHECKS[2],
                "test": "test_with_one",
                "before": "PASS",
                "after": "Pass",
            },
        ]
        approval = self.submitted(results)

        payload = json.loads(approval.payload)
        self.assertEqual(payload["build"]["scope"], SCOPE)
        self.assertEqual(
            [row["after"] for row in payload["change"]["check_results"]],
            ["pass", "pass", "pass"],
        )
        built = fixes.build_of(self.current_run())
        self.assertEqual(payload["scope_hash"], built["hash"])
        # another scope is another approval
        self.assertNotEqual(
            approval.payload_hash,
            approvals.payload_hash({**payload, "scope_hash": "another"}),
        )
        frappe.set_user(self.developer)
        card = api.get_run(self.ticket.name)["fix"]["approval"]
        frappe.set_user("Administrator")
        self.assertEqual(card["build"]["checks"], CHECKS)

        teams_card = assistant.fix_card(approval)
        self.assertTrue(teams_card["title"].startswith("Change ready"))
        lines = "\n".join(teams_card["lines"])
        self.assertIn(SCOPE[:40], lines)
        self.assertIn("fails before, passes after", lines)
        self.assertIn("holds before and after", lines)


class TestTheStaffAssistantBuilds(BuildCase):
    def test_build_ticket_asks_then_builds(self):
        self.estimate()
        frappe.cache.delete_keys("copilot-chat:")
        reading = {"intent": "build", "ticket": self.ticket.name}
        with patch(
            "helpdesk.ai_engine.call_haiku",
            return_value={"response": reading, "cost": 0.0001},
        ):
            proposal = assistant.receive(
                self.developer, "Web", f"build ticket {self.ticket.name}", None
            )[0]
        self.assertIn("Build ticket", proposal["title"])
        self.assertTrue(any(SCOPE[:30] in line for line in proposal["lines"]))
        # sending the estimate answered the customer; nothing is built before Yes
        self.assertEqual(self.current_run().state, "Answered")

        assistant.press(
            self.developer, "Web", "confirm", {"message": proposal["message"]}, {}
        )

        self.assertEqual(self.current_run().state, "Preparing Fix")


class TestTheWeeklyReport(BuildCase):
    def test_builds_are_counted_with_their_hours(self):
        self.estimate()
        self.build()

        rows = pilot.pilot_rows(add_days(nowdate(), -1), nowdate(), self.customer)

        self.assertEqual(
            (
                rows[0]["builds_started"],
                rows[0]["build_hours"],
                rows[0]["builds_merged"],
            ),
            (1, 4, 0),
        )
