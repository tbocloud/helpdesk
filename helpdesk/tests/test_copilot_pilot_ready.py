# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""TBO Copilot Phase 21 on the hub: logs without customer text, writes confirmed and logged,
feedback as tasks, the Teams package, and the pilot's numbers."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime

from helpdesk.api import copilot_feedback
from helpdesk.automation import create_automation_user
from helpdesk.copilot import assistant, audit, feedback, pilot, teams
from helpdesk.copilot.mcp import registry
from helpdesk.copilot.mcp.auth import Caller
from helpdesk.patches.v16_0_2 import trim_copilot_logs
from helpdesk.test_utils import (
    create_agent,
    hold_commits,
    make_assigned_ticket,
    make_copilot_settings,
    make_project,
)

AGENT = "pilot-ready-agent@example.com"


class PilotReadyCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(AGENT)
        frappe.cache.delete(audit.rate_key(AGENT))
        frappe.cache.delete(frappe.cache.make_key(f"copilot-feedback:{AGENT}"))
        self.ai = create_automation_user("pilot-ready.ai@example.com", "Pilot AI")
        frappe.db.set_single_value("HDS Hub Settings", "automation_user", self.ai)
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")

    def logs(self, **filters):
        return frappe.get_all(
            "HDS Copilot Call Log",
            filters={"user": AGENT, **filters},
            fields=["tool", "status", "ticket", "kind", "arguments", "result"],
            order_by="creation desc",
        )


class TestLogsWithoutCustomerText(PilotReadyCase):
    def test_identifiers_stay_and_text_becomes_a_fingerprint(self):
        stored = json.loads(
            audit.safe_arguments(
                {
                    "ticket": "0042",
                    "site": "demo.tbo365.cloud",
                    "limit": 5,
                    "approve": True,
                    "query": "invoice for Acme Trading",
                    "customer": "Acme",
                    "contact_email": "buyer@acme.example",
                    "nested": {"note": "call the owner on 0501234567"},
                    "free": "two words",
                }
            )
        )
        self.assertEqual(
            (stored["ticket"], stored["site"], stored["limit"], stored["approve"]),
            ("0042", "demo.tbo365.cloud", 5, True),
        )
        for key in ("query", "customer", "contact_email", "free"):
            self.assertEqual(set(stored[key]), {"chars", "mark"}, key)
        self.assertEqual(set(stored["nested"]["note"]), {"chars", "mark"})
        text = json.dumps(stored)
        for leaked in ("Acme", "buyer@", "0501234567", "two words"):
            self.assertNotIn(leaked, text)
        # the same text gives the same mark, so a repeat can be recognised without storing it
        self.assertEqual(audit.fingerprint("invoice for Acme Trading"), stored["query"])

    def test_an_error_keeps_its_first_line_with_addresses_and_numbers_masked(self):
        self.assertEqual(
            audit.error_line(
                "Customer buyer@acme.example (account 12345678) not found\nTraceback ..."
            ),
            "Customer [email] (account …) not found",
        )

    def test_a_tool_call_keeps_the_record_and_the_size_of_its_answer_only(self):
        make_copilot_settings(mcp_calls_per_minute=100)
        ticket = make_assigned_ticket("Margin wrong for Acme Trading", AGENT)
        frappe.set_user(AGENT)
        registry.call(Caller(AGENT), "get_ticket", {"ticket": ticket})
        log = self.logs(tool="get_ticket")[0]
        self.assertEqual((log.status, log.ticket), ("OK", ticket))
        self.assertRegex(log.result, r"^\d+ characters$")
        self.assertNotIn("Acme", log.result + log.arguments)

    def test_the_patch_trims_rows_written_before(self):
        row = frappe.get_doc(
            {
                "doctype": "HDS Copilot Call Log",
                "user": AGENT,
                "kind": "Teams",
                "tool": "new_work",
                "status": "OK",
                "arguments": json.dumps(
                    {"ticket": "0042", "text": "Acme's invoice is wrong"}
                ),
                "result": "Ticket 0042 for Acme Trading, raised by buyer@acme.example",
            }
        ).insert(ignore_permissions=True)
        trim_copilot_logs.execute()
        row.reload()
        self.assertIn('"ticket": "0042"', row.arguments)
        self.assertNotIn("Acme", row.arguments + row.result)
        self.assertRegex(row.result, r"^\d+ characters$")

    def test_a_teams_message_reaches_its_job_by_key_never_as_text(self):
        make_copilot_settings(teams_tenant_id="tenant-pilot-ready")
        activity = {
            "type": "message",
            "text": "Acme's invoice is wrong",
            "channelData": {"tenant": {"id": "tenant-pilot-ready"}},
        }
        queued = []
        with patch.object(
            frappe, "enqueue", side_effect=lambda *a, **kw: queued.append(kw)
        ):
            teams.handle_activity(activity)
        self.assertEqual(len(queued), 1)
        self.assertNotIn("activity", queued[0])
        self.assertIn("activity_key", queued[0])
        self.assertNotIn("Acme", json.dumps(queued[0], default=str))
        self.assertEqual(
            frappe.cache.get_value(queued[0]["activity_key"])["text"], activity["text"]
        )


class TestWritesConfirmed(PilotReadyCase):
    def test_a_write_tool_writes_nothing_without_the_persons_yes(self):
        make_copilot_settings(mcp_calls_per_minute=100)
        ticket = make_assigned_ticket("Needs a note", AGENT)
        frappe.set_user(AGENT)
        before = frappe.db.count("HD Ticket Comment", {"reference_ticket": ticket})
        result = registry.call(
            Caller(AGENT),
            "add_ticket_comment",
            {"ticket": ticket, "text": "Checked the margin"},
        )
        self.assertTrue(result["isError"])
        self.assertIn("confirmed: true", result["content"][0]["text"])
        self.assertEqual(
            frappe.db.count("HD Ticket Comment", {"reference_ticket": ticket}), before
        )
        self.assertEqual(self.logs(tool="add_ticket_comment")[0].status, "Refused")
        result = registry.call(
            Caller(AGENT),
            "add_ticket_comment",
            {"ticket": ticket, "text": "Checked the margin", "confirmed": True},
        )
        self.assertFalse(result["isError"])
        self.assertEqual(
            frappe.db.count("HD Ticket Comment", {"reference_ticket": ticket}),
            before + 1,
        )

    def test_every_write_tool_asks_for_the_yes_in_its_schema(self):
        registry.load_tools()
        for tool in registry.TOOLS.values():
            if tool["kind"] == registry.WRITE:
                self.assertIn(
                    "confirmed", tool["input_schema"]["required"], tool["name"]
                )


class TestFeedback(PilotReadyCase):
    def setUp(self):
        super().setUp()
        self.project = make_project("Copilot pilot feedback").name
        make_copilot_settings(enabled=1, feedback_project=self.project)

    def test_report_a_problem_in_a_chat_becomes_a_task_without_the_model(self):
        frappe.set_user(AGENT)
        with patch.object(
            assistant, "read_intent", side_effect=AssertionError("no model call")
        ):
            replies = assistant.receive(
                AGENT, "Teams", "Report a problem: the fix card showed the wrong ticket"
            )
        task = frappe.get_all(
            "Task",
            filters={"project": self.project},
            fields=["name", "subject", "description", "owner", "custom_category"],
        )
        self.assertEqual(len(task), 1)
        self.assertEqual(
            task[0].subject, "Copilot feedback: the fix card showed the wrong ticket"
        )
        self.assertIn(AGENT, task[0].description)
        self.assertEqual(
            (task[0].owner, task[0].custom_category), (self.ai, "Development")
        )
        self.assertIn(task[0].name, replies[0]["title"])
        self.assertIn(f"task={task[0].name}", replies[0]["links"][0][1])
        logged = self.logs(tool="report_problem")[0]
        self.assertNotIn("wrong ticket", logged.arguments)

    def test_feedback_worded_otherwise_only_shows_how(self):
        frappe.set_user(AGENT)
        with patch.object(
            assistant, "read_intent", return_value=({"intent": "report_problem"}, 0.0)
        ):
            replies = assistant.receive(AGENT, "Teams", "your last answer was wrong")
        self.assertIn('"report a problem:"', replies[0]["lines"][0])
        self.assertFalse(frappe.db.exists("Task", {"project": self.project}))

    def test_the_desktop_app_reports_through_the_api(self):
        frappe.set_user(AGENT)
        filed = copilot_feedback.report_problem(
            "The AWS tool would not start", "Desktop"
        )
        self.assertEqual(
            frappe.db.get_value("Task", filed["task"], "project"), self.project
        )
        self.assertEqual(self.logs(tool="report_problem")[0].kind, "Desktop")

    def test_an_empty_report_is_refused_and_reports_are_limited(self):
        frappe.set_user(AGENT)
        with self.assertRaises(frappe.ValidationError):
            feedback.report(AGENT, "Desktop", "   ")
        for i in range(feedback.REPORTS_PER_HOUR):
            feedback.report(AGENT, "Desktop", f"problem {i}")
        with self.assertRaises(frappe.ValidationError):
            feedback.report(AGENT, "Desktop", "one too many")

    def test_help_says_how_to_report(self):
        self.assertTrue(
            any("Report a problem" in line for line in assistant.help_card()["lines"])
        )


class TestTeamsPackage(PilotReadyCase):
    def test_the_version_and_the_pages_come_from_the_settings(self):
        make_copilot_settings(
            teams_bot_app_id="00000000-0000-0000-0000-000000000001",
            teams_app_version="1.0.3",
            teams_privacy_url="https://www.teambackoffice.com/privacy",
            teams_terms_url="https://www.teambackoffice.com/terms",
        )
        manifest = teams.manifest()
        self.assertEqual(manifest["version"], "1.0.3")
        self.assertEqual(
            manifest["developer"]["privacyUrl"],
            "https://www.teambackoffice.com/privacy",
        )
        self.assertEqual(
            manifest["developer"]["termsOfUseUrl"],
            "https://www.teambackoffice.com/terms",
        )
        commands = [
            c["title"] for c in manifest["bots"][0]["commandLists"][0]["commands"]
        ]
        self.assertIn("report a problem", commands)

    def test_without_a_version_the_apps_own_is_used(self):
        import helpdesk

        self.assertEqual(
            teams.package_version(""), ".".join(helpdesk.__version__.split(".")[:3])
        )
        self.assertEqual(teams.package_version("2.4.1-beta"), "2.4.1")
        self.assertEqual(teams.package_version("nonsense"), teams.package_version(""))


class TestPilotNumbers(PilotReadyCase):
    def test_copilot_use_is_counted_per_person_and_channel(self):
        for kind, tool, status in (
            ("Teams", "press_status", "OK"),
            ("Teams", "report_problem", "OK"),
            ("Desktop", "decide_action", "OK"),
            ("MCP person", "get_ticket", "Refused"),
            ("Web", "question", "Error"),
        ):
            assistant.log_action(AGENT, kind, tool, status, {})
        today = getdate(now_datetime())
        rows = {r["user"]: r for r in pilot.usage_rows(add_days(today, -1), today)}
        mine = rows[AGENT]
        self.assertEqual(
            (mine["Teams"], mine["Desktop"], mine["MCP"], mine["Panel"]), (2, 1, 1, 1)
        )
        self.assertEqual((mine["refused"], mine["failed"], mine["reports"]), (1, 1, 1))
        html = pilot.usage_html(list(rows.values()))
        self.assertIn(AGENT, html)
        self.assertIn("Problems reported", html)
