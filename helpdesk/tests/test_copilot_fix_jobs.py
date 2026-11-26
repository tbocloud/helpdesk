# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot's own fix (Phase 1c-2): asked for, claimed with a lease, pushed with a one-repository key, reported, handed over when it fails."""

import json
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from helpdesk.api import copilot as api
from helpdesk.api import copilot_worker as worker_api
from helpdesk.copilot import approvals, assistant, fixes, runs
from helpdesk.copilot.mcp import tools_worker
from helpdesk.copilot.mcp.auth import WORKER, Caller
from helpdesk.test_utils import make_copilot_settings, make_site_registry
from helpdesk.tests.test_copilot_fix_flow import NEW_SHA, REPO, SHA, FixCase


class FixJobCase(FixCase):
    def setUp(self):
        super().setUp()
        # queued runs elsewhere on the site would be handed out first
        frappe.db.set_value(
            "HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled"
        )
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
        self.diagnosed()

    def claim(self, capabilities: str = "fix") -> dict:
        return worker_api.claim_job("fix-worker", 1, capabilities)

    def asked(self):
        return fixes.request_copilot_fix(self.current_run(), self.approver)


class TestFixJobs(FixJobCase):
    def test_a_fix_job_waits_until_copilot_is_asked(self):
        self.assertEqual(self.claim(), {})
        self.asked()
        self.assertEqual(self.claim("investigate"), {})

        job = self.claim()

        run = self.current_run()
        self.assertEqual(
            (run.state, run.fix_status, run.fix_attempts),
            ("Preparing Fix", "Working", 1),
        )
        context = job["context"]
        self.assertEqual(context["kind"], "fix")
        self.assertTrue(context["fix"]["branch"].startswith(f"copilot/{run.task}-r"))
        self.assertEqual(context["fix"]["closes"], f"Closes {run.task}")
        self.assertEqual(context["fix"]["repositories"], [REPO])
        self.assertEqual(context["diagnosis"]["root_cause_category"], "bug")
        self.assertEqual(
            worker_api.heartbeat(job["run"], job["lease_token"])["action"], "continue"
        )

    def test_the_push_key_is_for_the_sites_own_repository_only(self):
        self.asked()
        job = self.claim()
        with patch(
            "helpdesk.copilot.github_app.push_token",
            return_value={"token": "push-key", "expires_at": "2026-10-13T03:00:00Z"},
        ) as minted:
            key = worker_api.repo_token(
                job["run"], job["lease_token"], f"https://github.com/{REPO}.git"
            )
            with self.assertRaises(frappe.PermissionError):
                worker_api.repo_token(job["run"], job["lease_token"], "someone/else")
            with self.assertRaises(frappe.PermissionError):
                worker_api.repo_token(job["run"], "not-the-lease", REPO)

        self.assertEqual(key["token"], "push-key")
        minted.assert_called_once_with(REPO)
        self.assertTrue(self.events("push_key"))

    def test_the_change_opens_the_approval_with_what_copilot_tested(self):
        make_copilot_settings(
            enabled=1,
            approvers=[
                {"user": self.developer, "senior": 0, "active": 1},
                {"user": self.approver, "senior": 0, "active": 1},
                {"user": self.senior, "senior": 1, "active": 1},
            ],
        )
        self.asked()
        job = self.claim()
        task = self.current_run().task
        self.github.add_pull(
            REPO, 31, NEW_SHA, body=f"Closes {task}", author="tbo-copilot[bot]"
        )
        evidence = [
            {
                "check": "the bug shows before the fix",
                "result": "pass",
                "detail": "1.25",
            },
            {"check": "the check passes after the fix", "result": "pass"},
            {"check": "the app's tests", "result": "not_run", "detail": "it has none"},
        ]
        caller = Caller(user="Administrator", kind=WORKER, run=job["run"])
        with patch("helpdesk.copilot.github.copilot_only", return_value=True):
            tools_worker.submit_change(
                caller,
                REPO,
                31,
                NEW_SHA,
                branch=fixes.copilot_branch(self.current_run()),
                summary="The margin is now a share of the selling price.",
                evidence=evidence,
                tested_on="a sandbox site",
                people_checks=["the margin on one real invoice"],
            )

        run = self.current_run()
        self.assertEqual(run.fix_status, "Opened")
        self.assertFalse(run.lease_token_hash)
        self.assertEqual(run.state, "Awaiting Approval")  # followed at once
        approval = self.approval()
        payload = json.loads(approval.payload)
        self.assertTrue(payload["copilot_only"])
        self.assertEqual(payload["change"]["tested_commit"], NEW_SHA)
        self.assertEqual(
            [row["result"] for row in payload["change"]["evidence"]],
            ["pass", "pass", "not_run"],
        )
        # Copilot wrote it, so the customer's developer reviews and may approve
        self.assertEqual(approval.assigned_to, self.developer)
        self.assertIsNone(approvals.may_decide(approval, self.developer))
        with self.assertRaises(frappe.PermissionError):
            runs.check_lease(run.name, job["lease_token"])

        frappe.set_user(self.developer)
        card = api.get_run(self.ticket.name)["fix"]["approval"]
        self.assertEqual(card["change"]["tested_on"], "a sandbox site")
        self.assertFalse(card["evidence_stale"])

    def test_a_fix_copilot_could_not_make_goes_back_to_the_developer(self):
        self.asked()
        job = self.claim()

        worker_api.submit_result(
            job["run"],
            job["lease_token"],
            {"kind": "failure", "reason": "the bug does not show on the copy"},
        )

        run = self.current_run()
        self.assertEqual(
            (run.state, run.fix_status, run.fix_requested),
            ("Preparing Fix", "Failed", 0),
        )
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_doctype": "Task",
                    "reference_name": run.task,
                    "content": ["like", "%does not show on the copy%"],
                },
            )
        )
        self.assertTrue(any(self.developer in call[0] for call in self.notified))

    def test_a_lost_worker_is_tried_again_then_the_developer_takes_over(self):
        self.asked()
        for attempt in (1, 2):
            job = self.claim()
            self.assertEqual(self.current_run().fix_attempts, attempt)
            frappe.db.set_value(
                "HDS Copilot Run",
                job["run"],
                "lease_expires",
                add_to_date(now_datetime(), minutes=-1),
            )
            runs.expire_stale_leases()

        self.assertEqual(self.current_run().fix_status, "Failed")
        self.assertEqual(self.claim(), {})

    def test_a_fix_job_reports_a_change_and_nothing_else(self):
        self.asked()
        job = self.claim()
        caller = Caller(user="Administrator", kind=WORKER, run=job["run"])
        with self.assertRaises(frappe.ValidationError):
            tools_worker.submit_investigation(caller, "bug", 0.9)
        with self.assertRaises(frappe.ValidationError):
            worker_api.submit_result(
                job["run"],
                job["lease_token"],
                {
                    "kind": "investigation",
                    "root_cause_category": "bug",
                    "confidence": 0.9,
                },
            )

    def test_no_fix_job_while_a_pull_request_is_open(self):
        self.opened(draft=True)  # a developer is already on it
        with self.assertRaises(frappe.ValidationError):
            self.asked()

    def test_the_card_offers_copilot_and_shows_its_progress(self):
        frappe.set_user(self.approver)
        self.assertTrue(api.get_run(self.ticket.name)["fix"]["can_request_fix"])

        fix = api.request_copilot_fix(self.ticket.name)["fix"]

        self.assertEqual(fix["copilot"]["status"], "Queued")
        self.assertFalse(fix["can_request_fix"])


class TestAskedBySettings(FixCase):
    def test_an_ordinary_bug_is_fixed_by_itself_unless_the_settings_ask_first(self):
        self.settings(shadow_mode=0, ask_before_every_fix=0)
        self.diagnosed()
        run = self.current_run()
        self.assertEqual((run.fix_requested, run.fix_status), (1, "Queued"))
        self.assertTrue(run.task)

    def test_with_ask_before_every_fix_copilot_waits_for_a_yes(self):
        self.settings(shadow_mode=0, ask_before_every_fix=1)
        self.diagnosed()
        run = self.current_run()
        self.assertEqual((run.fix_requested, run.fix_status or None), (0, None))
        self.assertIn("ask before every fix", fixes.needs_asking(run))


class TestAskedFromTheChat(FixJobCase):
    """Teams or the panel: the diagnosis card's button, or "fix it" in words, starts the same fix."""

    def chat_lines(self, user):
        return [
            " ".join(json.loads(m.card or "{}").get("lines") or [m.text or ""])
            for m in frappe.get_all(
                assistant.MESSAGE,
                filters={"user": user, "direction": "Out"},
                fields=["card", "text"],
                order_by="creation asc",
            )
        ]

    def test_the_diagnosis_card_offers_the_fix_and_its_button_starts_it(self):
        run = self.current_run()
        self.assertEqual(
            [a["verb"] for a in assistant.diagnosis_card(run)["actions"]], ["fix"]
        )

        pressed = assistant.press(self.approver, "Web", "fix", {"run": run.name})

        run = self.current_run()
        self.assertEqual(
            (run.fix_status, run.fix_requested_by), ("Queued", self.approver)
        )
        self.assertEqual(pressed["card"]["actions"], [])  # the button goes
        self.assertIn(run.ticket, pressed["replies"][0]["lines"][0])
        self.assertEqual(assistant.watchers(run), [self.approver])
        again = assistant.press(self.approver, "Web", "fix", {"run": run.name})
        self.assertIn("already working", again["replies"][0]["lines"][0])

    def test_fix_it_in_words_asks_first_and_means_the_last_diagnosis(self):
        run = self.current_run()
        assistant.send(
            self.approver,
            assistant.diagnosis_card(run),
            run=run.name,
            ticket=run.ticket,
        )
        with patch(
            "helpdesk.ai_engine.call_haiku",
            return_value={"response": {"intent": "fix"}, "cost": 0.0001},
        ):
            proposal = assistant.receive(self.approver, "Web", "go ahead and fix it")[0]
        self.assertEqual(proposal["title"], f"Let Copilot fix ticket {run.ticket}?")
        self.assertFalse(self.current_run().fix_status)  # nothing until Yes

        assistant.press(
            self.approver, "Web", "confirm", {"message": proposal["message"]}
        )

        self.assertEqual(self.current_run().fix_status, "Queued")

    def test_below_the_fix_level_there_is_no_button_and_words_get_the_reason(self):
        frappe.db.set_value(
            "HD Customer", self.customer, "custom_copilot_level", "Diagnose only"
        )
        run = self.current_run()
        self.assertEqual(assistant.diagnosis_card(run)["actions"], [])
        with patch(
            "helpdesk.ai_engine.call_haiku",
            return_value={
                "response": {"intent": "fix", "ticket": run.ticket},
                "cost": 0,
            },
        ):
            reply = assistant.receive(self.approver, "Web", f"fix ticket {run.ticket}")[
                0
            ]
        self.assertIn("Fix level", reply["lines"][0])
        self.assertFalse(self.current_run().fix_status)

    def test_who_asked_hears_when_the_fix_waits_for_approval_or_failed(self):
        make_copilot_settings(  # the customer's developer approves, not the one who asked
            enabled=1,
            approvers=[
                {"user": self.developer, "senior": 0, "active": 1},
                {"user": self.approver, "senior": 0, "active": 1},
            ],
        )
        run = self.current_run()
        assistant.press(self.approver, "Web", "fix", {"run": run.name})
        job = self.claim()
        task = self.current_run().task
        self.github.add_pull(
            REPO, 31, NEW_SHA, body=f"Closes {task}", author="tbo-copilot[bot]"
        )
        caller = Caller(user="Administrator", kind=WORKER, run=job["run"])
        with patch("helpdesk.copilot.github.copilot_only", return_value=True):
            tools_worker.submit_change(
                caller,
                REPO,
                31,
                NEW_SHA,
                branch=fixes.copilot_branch(self.current_run()),
                summary="The margin is now a share of the selling price.",
                evidence=[{"check": "the bug shows before the fix", "result": "pass"}],
                tested_on="a sandbox site",
            )
        approval = frappe.get_doc("HDS Copilot Approval", self.current_run().approval)
        self.assertNotEqual(approval.assigned_to, self.approver)
        self.assertIn(
            "waits for {0}'s approval".format(
                frappe.utils.get_fullname(approval.assigned_to)
            ),
            self.chat_lines(self.approver)[-1],
        )

        fixes.fix_failed(self.current_run(), "the bug did not show on the copy")

        self.assertIn(
            "Copilot could not fix it: the bug did not show on the copy",
            self.chat_lines(self.approver)[-1],
        )
