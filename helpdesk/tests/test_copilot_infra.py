# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot on infrastructure alerts (Phase 25): the bot tells the alert's people, Copilot
investigates with secrets taken out, proposes at most one listed action on a place it may change,
nothing runs before a DevOps person approves, and the watcher's next check says whether it worked."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk import intake, monitor
from helpdesk.api.copilot_worker import WORKER_ROLE, claim_job, ensure_role
from helpdesk.automation import automation_user, create_automation_user
from helpdesk.copilot import actions, assistant, infra, press_tools, runs
from helpdesk.copilot.mcp import registry
from helpdesk.copilot.mcp.auth import identify_from
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    create_user,
    hold_commits,
    make_copilot_settings,
    make_project,
    mcp_tool_result,
)

KEY = "site-down:demo-alpha.tbocloud.in"
SITE = "demo-alpha.tbocloud.in"
WORKER_USER = "infra-worker@example.com"
FACTS = {
    "available": True,
    "site": {"name": SITE, "bench": "bench-0015-000001", "group": "bench-0015"},
    "jobs": [],
    "failed_jobs": [],
}


class InfraCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        intake.ensure_intake_defaults()
        self.ai = create_automation_user("infra.ai@example.com", "TBO AI")
        self.customer = create_customer("Team Back Office International LLP").name
        self.project = make_project("Team Back Office Internal").name
        frappe.db.set_single_value(
            "HDS Hub Settings",
            {
                "automation_user": self.ai,
                "internal_customer": self.customer,
                "internal_project": self.project,
                "monitor_quiet_minutes": 3,
            },
        )
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        self.devops = create_agent("infra.devops@example.com").name
        self.leader = create_agent("infra.leader@example.com").name
        self.settings()
        frappe.db.set_value(
            "HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled"
        )
        self.delivered, self.cards = [], []
        for target, side_effect in (
            (
                "helpdesk.copilot.assistant.send",
                lambda person, reply, **k: self.delivered.append((person, reply)),
            ),
            (
                "helpdesk.copilot.actions.send_card",
                lambda person, approval: self.cards.append(person),
            ),
            ("helpdesk.work_reminders.notify_users", lambda *a, **k: None),
            ("helpdesk.intake.announce", lambda *a, **k: None),
        ):
            patcher = patch(target, side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(infra, "press_facts", return_value=FACTS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def settings(self, **values):
        values.setdefault("infra_investigate", 1)
        values.setdefault("infra_propose", 1)
        values.setdefault("infra_may_change", "bench-0015\n" + SITE)
        make_copilot_settings(
            enabled=1,
            mcp_enabled=1,
            mcp_calls_per_minute=1000,
            copilot_people=[
                {
                    "role": "Infrastructure",
                    "person": self.devops,
                    "level": "Main",
                    "active": 1,
                },
                {"role": "Leader", "person": self.leader, "level": "Main", "active": 1},
            ],
            **values,
        )

    def open_alert(self, text="demo-alpha does not answer: 502 from nginx", key=KEY):
        return monitor.alert(key, "open", f"Site down: {SITE}", text, "critical")[
            "ticket"
        ]

    def run_of(self, ticket):
        name = frappe.db.get_value(
            "HDS Copilot Run", {"ticket": ticket, "kind": "infra"}, "name"
        )
        return frappe.get_doc("HDS Copilot Run", name) if name else None

    def claimed(self, ticket):
        """The run as a worker that can investigate infrastructure claims it."""
        run, _token = runs.claim("w1", "investigate,infra")
        self.assertEqual(run.ticket, ticket)
        return run

    def report(self, run, **proposal):
        return infra.on_report(
            run.name,
            {
                "summary": "The site's web workers on bench-0015 stopped after the 03:10 restart.",
                "confidence": 0.8,
                "cause": "web workers down",
                "evidence": [
                    "nginx 502 for 12 minutes",
                    "no Bench Restart job since 03:10",
                ],
                "proposal": proposal,
            },
        )

    def said_to(self, person) -> list[str]:
        return [
            " ".join([reply.get("title") or "", *reply.get("lines", [])])
            for who, reply in self.delivered
            if who == person
        ]


class TestTheAlertOpens(InfraCase):
    def test_the_bot_tells_the_owner_and_infrastructure_and_copilot_starts(self):
        ticket = self.open_alert()
        run = self.run_of(ticket)
        self.assertEqual((run.state, run.shadow), ("Queued", 0))
        told = self.said_to(self.devops)
        self.assertTrue(
            any("Alert: Site down" in t and "looking into it" in t for t in told), told
        )

    def test_with_investigation_off_nobody_starts_and_the_card_says_so(self):
        self.settings(infra_investigate=0)
        ticket = self.open_alert()
        self.assertIsNone(self.run_of(ticket))
        self.assertTrue(any("not looking" in t for t in self.said_to(self.devops)))

    def test_only_a_worker_that_says_infra_gets_the_alert(self):
        ticket = self.open_alert()
        self.assertEqual(runs.claim("old-worker", "investigate,fix"), (None, None))
        self.assertEqual(self.claimed(ticket).state, "Investigating")


class TestTheContext(InfraCase):
    def test_the_worker_sees_the_alert_the_list_and_where_it_may_act_and_no_secrets(
        self,
    ):
        ticket = self.open_alert(
            "backup failed: redis://:S3cretPass@10.0.0.5:6379/0 password=hunter22 "
            "Authorization: Bearer abcdefghijklmnop1234"
        )
        context = runs.run_context(self.claimed(ticket))
        text = json.dumps(context)
        self.assertEqual(context["kind"], "infra")
        self.assertEqual(context["target"], SITE)
        self.assertEqual(
            [a["name"] for a in context["actions"]],
            ["backup", "restart_bench", "migrate_site", "update_site"],
        )
        self.assertIn("bench-0015", context["may_target"])
        self.assertIn(SITE, context["may_change"])
        for secret in ("S3cretPass", "hunter22", "abcdefghijklmnop1234"):
            self.assertNotIn(secret, text)
        self.assertNotIn("api_key", text)

    def test_redact_takes_out_every_kind_of_secret(self):
        out = infra.redact(
            {
                "log": "postgres://app:pw123@db/x sk-abcdefghijklmnopqrstu AKIAABCDEFGHIJKLMNOP "
                "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----",
                "nested": [{"api_key": "k-1"}, "token: t0k3n-value"],
            }
        )
        text = json.dumps(out)
        for secret in (
            "pw123",
            "sk-abcdefghijklmnopqrstu",
            "AKIAABCDEFGHIJKLMNOP",
            "abc\\n",
            "k-1",
            "t0k3n-value",
        ):
            self.assertNotIn(secret, text)
        self.assertIn("postgres://app:[hidden]@db/x", text)


class TestTheProposal(InfraCase):
    def test_an_action_in_scope_asks_devops_and_runs_nothing(self):
        ticket = self.open_alert()
        run = self.report(
            self.claimed(ticket),
            action="restart_bench",
            target="bench-0015",
            why="workers down",
        )
        self.assertEqual(run.state, "Awaiting Approval")
        approval_name = (frappe.parse_json(run.proposal) or {})["approval"]
        approval = frappe.get_doc(actions.ACTION, approval_name)
        self.assertEqual(
            (
                approval.status,
                approval.assigned_to,
                approval.requested_by,
                approval.risk,
            ),
            ("Pending", self.devops, automation_user(), "normal"),
        )
        payload = frappe.parse_json(approval.payload)
        self.assertEqual(
            (payload["action"], payload["target"], payload["copilot_run"]),
            ("restart_bench", "bench-0015", run.name),
        )
        self.assertEqual(self.cards, [self.devops])
        told = self.said_to(self.devops)
        self.assertTrue(
            any("What Copilot found" in t and "Copilot proposes" in t for t in told),
            told,
        )

    def test_a_backup_also_waits_for_approval(self):
        ticket = self.open_alert()
        with patch("helpdesk.copilot.press.call") as press_call:
            run = self.report(self.claimed(ticket), action="backup", target=SITE)
            press_call.assert_not_called()
        self.assertEqual(run.state, "Awaiting Approval")

    def test_a_place_copilot_may_not_change_goes_to_a_person(self):
        self.settings(infra_may_change="bench-0015")
        ticket = self.open_alert()
        run = self.report(self.claimed(ticket), action="migrate_site", target=SITE)
        self.assertEqual(run.state, "Handed Over")
        self.assertFalse(frappe.db.exists(actions.ACTION, {"ticket": ticket}))
        self.assertTrue(any("A person runs it" in t for t in self.said_to(self.devops)))

    def test_an_action_off_the_list_or_a_target_off_the_alert_goes_to_a_person(self):
        for proposal in (
            {"action": "archive_site", "target": SITE},
            {"action": "restart_bench", "target": "bench-0020"},
        ):
            ticket = self.open_alert(key=f"site-down:{SITE}-{proposal['action']}")
            frappe.db.set_value("HD Ticket", ticket, "alert_key", KEY)
            run = self.report(self.claimed(ticket), **proposal)
            self.assertEqual(run.state, "Handed Over", proposal)
        self.assertFalse(
            frappe.db.exists(actions.ACTION, {"requested_by": automation_user()})
        )

    def test_proposals_off_or_auto_repair_paused_means_a_person_acts(self):
        self.settings(infra_propose=0)
        ticket = self.open_alert()
        self.assertEqual(
            self.report(
                self.claimed(ticket), action="restart_bench", target="bench-0015"
            ).state,
            "Handed Over",
        )
        self.settings(infra_propose=1)
        frappe.db.set_single_value("HDS Hub Settings", "auto_repair_paused", 1)
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        ticket = self.open_alert(key=f"{KEY}-2")
        frappe.db.set_value("HD Ticket", ticket, "alert_key", KEY)
        self.assertEqual(
            self.report(
                self.claimed(ticket), action="restart_bench", target="bench-0015"
            ).state,
            "Handed Over",
        )

    def test_no_proposal_hands_over_with_what_a_person_should_do(self):
        ticket = self.open_alert()
        run = infra.on_report(
            self.claimed(ticket).name,
            {
                "summary": "Disk on the workload is filling with old logs.",
                "confidence": 0.6,
                "person_steps": "Clear /var/log/old on the workload.",
            },
        )
        self.assertEqual(run.state, "Handed Over")
        self.assertTrue(
            any("What a person should do" in t for t in self.said_to(self.devops))
        )


class TestAfterTheDecision(InfraCase):
    def asked(self):
        ticket = self.open_alert()
        run = self.report(
            self.claimed(ticket), action="restart_bench", target="bench-0015"
        )
        return ticket, run, (frappe.parse_json(run.proposal) or {})["approval"]

    def test_approve_run_and_the_watcher_sees_it_healthy_is_fixed_by_copilot(self):
        ticket, run, approval = self.asked()
        actions.decide(approval, self.devops, True, via="Teams")
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Approved"
        )
        actions.mark_executed(approval, True, "Restart bench-0015: job J1 success")
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Verifying"
        )
        monitor.alert(KEY, "resolved", "", "answers again")
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Resolved"
        )
        notes = frappe.get_all(
            "HD Ticket Comment", filters={"reference_ticket": ticket}, pluck="content"
        )
        self.assertTrue(any("Fixed by Copilot" in (n or "") for n in notes), notes)

    def test_a_failed_action_goes_to_a_leader(self):
        _ticket, run, approval = self.asked()
        actions.decide(approval, self.devops, True)
        actions.mark_executed(approval, False, "Press refused: bench busy")
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Escalated"
        )
        self.assertTrue(
            any("A Leader is needed" in t for t in self.said_to(self.leader))
        )

    def test_rejected_goes_to_a_person(self):
        _ticket, run, approval = self.asked()
        actions.decide(approval, self.devops, False, note="not during the demo")
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Handed Over"
        )

    def test_still_failing_half_an_hour_after_goes_to_a_leader(self):
        _ticket, run, approval = self.asked()
        actions.decide(approval, self.devops, True)
        actions.mark_executed(approval, True, "done")
        infra.check_verifying(
            add_to_date(now_datetime(), minutes=infra.VERIFY_MINUTES + 1)
        )
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Escalated"
        )

    def test_the_alert_resolving_before_anyone_decides_withdraws_the_request(self):
        _ticket, run, approval = self.asked()
        monitor.alert(KEY, "resolved", "", "answers again")
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Closed"
        )
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, approval, "status"), "Expired"
        )

    def test_the_approved_payload_is_what_press_receives(self):
        _ticket, _run, approval = self.asked()
        actions.decide(approval, self.devops, True)
        calls = []

        def fake(method, **args):
            calls.append((method, args))
            if method == "press.api.client.get_list":
                return [
                    {
                        "name": "J1",
                        "status": "Success",
                        "creation": "2026-11-18 03:00:00",
                    }
                ]
            return None

        with patch("helpdesk.copilot.press.call", side_effect=fake), patch.object(
            press_tools.time, "sleep"
        ):
            press_tools.execute_approved(approval)
        self.assertEqual(calls[0], ("press.api.bench.restart", {"name": "bench-0015"}))
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, approval, "status"), "Executed"
        )


class TestTheWorkerTools(InfraCase):
    def setUp(self):
        super().setUp()
        ensure_role()
        create_user(WORKER_USER).add_roles(WORKER_ROLE)
        self.ticket = self.open_alert()
        frappe.set_user(WORKER_USER)
        job = claim_job("w1", capabilities="investigate,infra")
        self.assertEqual(job["context"]["kind"], "infra")
        self.caller = identify_from(None, f"{job['run']}:{job['lease_token']}", "Guest")

    def call(self, tool, **arguments):
        result = registry.call(self.caller, tool, arguments)
        return result["isError"], mcp_tool_result(result)

    def test_the_worker_reports_with_its_own_tool_and_not_the_old_one(self):
        is_error, text = self.call(
            "submit_investigation", root_cause_category="bug", confidence=0.9
        )
        self.assertTrue(is_error)
        self.assertIn("submit_infra_investigation", text)
        is_error, result = self.call(
            "submit_infra_investigation",
            summary="Workers down after the restart.",
            confidence=0.7,
            proposal={"action": "restart_bench", "target": "bench-0015"},
        )
        self.assertFalse(is_error, result)
        self.assertEqual(
            (result["state"], result["decision"]), ("Awaiting Approval", "ask")
        )

    def test_press_reads_are_read_only_and_redacted(self):
        with patch.object(
            press_tools,
            "job",
            return_value={"steps": [{"output": "mysql://root:Pa55@db failed"}]},
        ):
            is_error, result = self.call("press_read", what="job", job="J1")
        self.assertFalse(is_error, result)
        self.assertNotIn("Pa55", json.dumps(result))
        is_error, text = self.call("press_read", what="restart")
        self.assertTrue(is_error)
