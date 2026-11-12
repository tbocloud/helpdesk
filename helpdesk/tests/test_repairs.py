# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Auto-repair (Phase 19): the switch, one record per repair, the hand-over to DevOps, repairs
that wait for an approver, and the weekly count."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from helpdesk import intake, monitor, repairs
from helpdesk.api import monitor as api
from helpdesk.automation import create_automation_user
from helpdesk.copilot import actions, assistant
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    hold_commits,
    make_copilot_settings,
    make_project,
)

KEY = "workers:bench-0020-000123-f1"


class RepairCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        intake.ensure_intake_defaults()
        self.ai = create_automation_user("repair.ai@example.com", "Repair AI")
        self.manager = create_agent("repair.manager@example.com").name
        frappe.get_doc("User", self.manager).add_roles("Agent Manager")
        self.devops = create_agent("repair.devops@example.com").name
        self.devops_two = create_agent("repair.devops2@example.com").name
        self.agent = create_agent("repair.agent@example.com").name
        self.approver = create_agent("repair.approver@example.com").name
        make_copilot_settings(
            enabled=1, approvers=[{"user": self.approver, "senior": 1, "active": 1}]
        )
        self.customer = create_customer("Team Back Office International LLP").name
        self.project = make_project(
            "Team Back Office Internal",
            members=[
                (self.devops, "DevOps Engineer"),
                (self.devops_two, "DevOps Engineer"),
            ],
        ).name
        frappe.db.set_single_value(
            "HDS Hub Settings",
            {
                "automation_user": self.ai,
                "internal_customer": self.customer,
                "internal_project": self.project,
                "auto_repair_paused": 0,
                "auto_repair_off": "",
                "auto_repair_max_per_hour": 6,
            },
        )
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        self.watcher = monitor.ensure_user()
        self.channel, self.sent = [], []
        for target, kw in (
            (
                "helpdesk.repairs.tell_channel",
                {"side_effect": lambda text, ticket=None: self.channel.append(text)},
            ),
            ("helpdesk.intake.announce", {"return_value": None}),
            (
                "helpdesk.copilot.actions.send_card",
                {"side_effect": lambda person, approval: self.sent.append(person)},
            ),
            ("helpdesk.work_reminders.notify_users", {"return_value": None}),
        ):
            patcher = patch(target, **kw)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(frappe.set_user, "Administrator")

    def alert(self):
        return monitor.alert(KEY, "open", title="Workers stopped on bench-0020")[
            "ticket"
        ]

    def comments(self, ticket):
        return frappe.get_all(
            "HD Ticket Comment", filters={"reference_ticket": ticket}, pluck="content"
        )


class TestSwitch(RepairCase):
    def test_the_policy_reads_the_settings(self):
        frappe.db.set_single_value(
            "HDS Hub Settings",
            {
                "auto_repair_off": "disk-cleanup\n\nnginx ",
                "auto_repair_max_per_hour": 4,
            },
        )
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        policy = repairs.policy()
        self.assertEqual(policy["paused"], False)
        self.assertEqual(policy["off"], ["disk-cleanup", "nginx"])
        self.assertEqual(policy["max_per_hour"], 4)

    def test_a_manager_or_a_devops_engineer_may_pause_and_nobody_else(self):
        state = repairs.set_paused(self.devops, True, "migration tonight")
        self.assertEqual(
            (state["paused"], state["paused_by"], state["reason"]),
            (True, self.devops, "migration tonight"),
        )
        self.assertIn("paused", self.channel[-1])
        self.assertEqual(repairs.set_paused(self.manager, False)["paused"], False)
        self.assertIsNone(repairs.policy()["paused_by"])
        with self.assertRaises(frappe.PermissionError):
            repairs.set_paused(self.agent, True)
        self.assertEqual(repairs.policy()["paused"], False)

    def test_teams_pause_and_resume(self):
        intents = {
            "pause auto-repair: migration tonight": {
                "intent": "repair_pause",
                "reason": "migration tonight",
            },
            "resume auto-repair": {"intent": "repair_resume"},
        }

        def fake_ai(system_prompt, user_message, ticket_name=None, job=None):
            text = user_message.rsplit("<<<\n", 1)[-1].rsplit("\n>>>", 1)[0]
            return {"response": intents.get(text, {"intent": "unclear"}), "cost": 0}

        with patch("helpdesk.ai_engine.call_haiku", side_effect=fake_ai):
            frappe.cache.delete_keys("copilot-chat:")
            refused = assistant.receive(
                self.agent, "Web", "pause auto-repair: migration tonight"
            )
            self.assertIn("Only the Agent Managers", refused[0]["lines"][0])
            self.assertEqual(repairs.policy()["paused"], False)
            paused = assistant.receive(
                self.manager, "Web", "pause auto-repair: migration tonight"
            )
            self.assertEqual(paused[0]["title"], "Auto-repair is paused")
            self.assertEqual(repairs.policy()["reason"], "migration tonight")
            resumed = assistant.receive(self.manager, "Web", "resume auto-repair")
            self.assertEqual(resumed[0]["title"], "Auto-repair is running again")
            self.assertEqual(repairs.policy()["paused"], False)


class TestRecord(RepairCase):
    def test_a_fixed_automatic_repair_is_noted_on_the_ticket_and_told_to_teams(self):
        ticket = self.alert()
        started = repairs.started(
            KEY,
            "stuck-workers",
            target="bench-0020-000123-f1",
            evidence={"fatal": 3, "waiting": 212},
            action={
                "document": "TBO-Repair-RestartWorkers",
                "bench": "bench-0020-000123-f1",
            },
        )
        self.assertEqual(started["ticket"], ticket)
        record = frappe.get_doc(repairs.REPAIR, started["repair"])
        self.assertEqual(
            (record.status, record.level, record.attempt, record.owner),
            ("Running", "Automatic", 1, self.ai),
        )
        self.assertIn("212", record.evidence)
        done = repairs.finished(
            started["repair"],
            "Fixed",
            "Restarted the workers; all running, queue at 4.",
            verify={"waiting": 4},
        )
        self.assertEqual(
            (done["outcome"], done["ticket"], done["assigned_to"]),
            ("Fixed", ticket, None),
        )
        self.assertTrue(
            any("stuck-workers, attempt 1): fixed" in c for c in self.comments(ticket))
        )
        self.assertIn("Fixed by Copilot", self.channel[-1])
        # a second report changes nothing
        again = repairs.finished(started["repair"], "Not fixed", "late")
        self.assertEqual(again["outcome"], "Fixed")

    def test_a_failed_repair_goes_to_the_least_busy_devops_engineer(self):
        ticket = self.alert()
        first = repairs.started(
            KEY, "stuck-workers", target="bench-0020-000123-f1", attempt=2
        )
        done = repairs.finished(
            first["repair"],
            "Not fixed",
            "Workers fail again within a minute.",
            escalate=True,
        )
        self.assertIn(done["assigned_to"], (self.devops, self.devops_two))
        assignees = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "HD Ticket",
                "reference_name": ticket,
                "status": "Open",
            },
            pluck="allocated_to",
        )
        self.assertEqual(assignees, [done["assigned_to"]])
        self.assertIn("could not repair", self.channel[-1])
        self.assertEqual(
            frappe.db.get_value(repairs.REPAIR, first["repair"], "escalated"), 1
        )
        # a second hand-over keeps the same person
        second = repairs.started(
            KEY, "stuck-workers", target="bench-0020-000123-f1", attempt=2
        )
        self.assertEqual(
            repairs.finished(second["repair"], "Not fixed", "still", escalate=True)[
                "assigned_to"
            ],
            done["assigned_to"],
        )

    def test_without_devops_engineers_the_managers_get_it(self):
        frappe.db.delete("Project User", {"parent": self.project})
        ticket = self.alert()
        started = repairs.started(KEY, "nginx", target="workload")
        done = repairs.finished(
            started["repair"], "Not fixed", "nginx -t fails", escalate=True
        )
        self.assertEqual(done["assigned_to"], self.manager)
        self.assertTrue(ticket)

    def test_unknown_level_or_outcome_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            repairs.started(KEY, "x", level="Sometimes")
        started = repairs.started(KEY, "x")
        with self.assertRaises(frappe.ValidationError):
            repairs.finished(started["repair"], "Maybe")


class TestApproval(RepairCase):
    PAYLOAD = {"document": "TBO-Repair-RestartMariaDB", "instance": "workload"}

    def ask(self):
        return repairs.request(
            "mariadb-down:workload",
            "restart-mariadb",
            "workload",
            "Restart MariaDB on the workload",
            "the database stopped answering 4 minutes ago; 2 lighter repairs did not help",
            "Pre-checks: no Agent Job running, no build. Outside the maintenance window.",
            self.PAYLOAD,
            risk="senior",
        )

    def test_a_repair_waits_for_an_approver_then_is_handed_to_the_watcher_once(self):
        asked = self.ask()
        self.assertEqual(
            (asked["status"], asked["assigned_to"]), ("Pending", self.approver)
        )
        self.assertEqual(self.sent, [self.approver])
        record = frappe.get_doc(actions.ACTION, asked["approval"])
        self.assertEqual(
            (record.kind, record.requested_by, record.risk),
            ("Repair", self.watcher, "senior"),
        )
        self.assertIn("lighter repairs did not help", record.details)
        self.assertEqual(
            self.ask()["approval"], asked["approval"]
        )  # the same ask, the same card
        self.assertEqual(repairs.approved(), [])
        actions.decide(asked["approval"], self.approver, True, via="Teams")
        [ready] = repairs.approved()
        self.assertEqual(
            (
                ready["approval"],
                ready["runbook"],
                ready["target"],
                ready["key"],
                ready["payload"],
            ),
            (
                asked["approval"],
                "restart-mariadb",
                "workload",
                "mariadb-down:workload",
                self.PAYLOAD,
            ),
        )
        self.assertEqual(ready["payload_hash"], actions.payload_hash(self.PAYLOAD))
        self.assertEqual(ready["decided_by"], self.approver)
        repairs.executed(asked["approval"], True, "MariaDB restarted in 27 s")
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, asked["approval"], "status"), "Executed"
        )
        self.assertEqual(repairs.approved(), [])

    def test_the_watcher_cannot_approve_its_own_repair_or_run_someone_elses_action(
        self,
    ):
        asked = self.ask()
        with self.assertRaises(frappe.PermissionError):
            actions.decide(asked["approval"], self.watcher, True)
        other = actions.request(
            "Press", "Restart bench-0020", "x", {"m": "restart"}, user=self.agent
        )
        actions.decide(other.name, self.approver, True)
        with self.assertRaises(frappe.PermissionError):
            repairs.executed(other.name, True)


class TestWeek(RepairCase):
    def test_the_week_is_counted_and_a_repeat_becomes_a_devops_task(self):
        for i in range(3):
            r = repairs.started(KEY, "stuck-workers", target="bench-0020-000123-f1")
            repairs.finished(r["repair"], "Fixed", f"run {i}")
        r = repairs.started("disk:workload", "disk-cleanup", target="workload")
        repairs.finished(r["repair"], "Not fixed", "still 88 %", escalate=True)
        repairs.weekly(now_datetime() + timedelta(minutes=1))
        summary = [t for t in self.channel if t.startswith("Repairs last week")][-1]
        self.assertIn("4 (stuck-workers 3, disk-cleanup 1)", summary)
        self.assertIn("3 worked, 1 went to DevOps", summary)
        task = frappe.get_doc(
            "Task",
            {"custom_monitor_key": "root-cause:stuck-workers:bench-0020-000123-f1"},
        )
        self.assertEqual(
            (task.project, task.custom_category, task.priority),
            (self.project, "DevOps", "High"),
        )
        self.assertIn("ran 3 times", task.subject)
        assigned = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Task",
                "reference_name": task.name,
                "status": "Open",
            },
            pluck="allocated_to",
        )
        self.assertEqual(len(assigned), 1)
        self.assertIn(assigned[0], (self.devops, self.devops_two))
        # the disk ran once: no task
        self.assertFalse(
            frappe.db.exists(
                "Task", {"custom_monitor_key": "root-cause:disk-cleanup:workload"}
            )
        )

    def test_an_empty_week_says_nothing(self):
        repairs.weekly()
        self.assertEqual(self.channel, [])


class TestApi(RepairCase):
    def test_only_the_watcher_may_call_the_repair_endpoints(self):
        frappe.set_user(self.manager)
        for call in (api.repair_policy, api.approved_repairs):
            with self.assertRaises(frappe.PermissionError):
                call()
        with self.assertRaises(frappe.PermissionError):
            api.repair_started(KEY, "stuck-workers")
        frappe.set_user(self.watcher)
        self.assertEqual(api.repair_policy()["max_per_hour"], 6)
        started = api.repair_started(
            KEY, "stuck-workers", target="bench-0020-000123-f1", evidence='{"fatal": 3}'
        )
        done = api.repair_finished(
            started["repair"], "Fixed", "ok", verify='{"waiting": 0}', escalate="0"
        )
        self.assertEqual(done["outcome"], "Fixed")
        asked = api.request_repair(
            "disk:workload",
            "purge-binlogs",
            "workload",
            "Purge binlogs older than 3 days",
            payload='{"days": 3}',
        )
        self.assertEqual(asked["status"], "Pending")
        self.assertEqual(api.approved_repairs(), [])
