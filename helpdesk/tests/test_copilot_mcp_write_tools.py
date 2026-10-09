# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Write tools act as the person, with the same guards as the screens, and never reach the customer."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot.mcp import registry
from helpdesk.copilot.mcp.auth import Caller
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    hold_commits,
    make_article_category,
    make_assigned_ticket,
    make_copilot_settings,
    make_project,
    make_task,
    make_team,
    make_ticket,
    mcp_tool_result,
    restrict_tickets_to_teams,
)

AGENT = "mcp-write-agent@example.com"


class WriteCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_copilot_settings(mcp_enabled=1, mcp_calls_per_minute=1000)
        create_agent(AGENT)
        self.customer = create_customer("MCP Write Co").name
        self.ticket = make_assigned_ticket("Needs a reply", AGENT, customer=self.customer)
        frappe.set_user(AGENT)
        self.caller = Caller(AGENT)

    def call(self, tool, **arguments):
        result = registry.call(self.caller, tool, arguments)
        return result["isError"], mcp_tool_result(result)

    def communications(self):
        return frappe.db.count("Communication", {"reference_doctype": "HD Ticket", "reference_name": self.ticket})


class TestTicketWrites(WriteCase):
    def test_a_note_is_internal_and_shown_as_text(self):
        before = self.communications()
        is_error, data = self.call("add_ticket_comment", ticket=self.ticket, text="Check row 2\n\n<script>x()</script>")
        self.assertFalse(is_error, data)
        self.assertFalse(data["visible_to_customer"])
        content, by = frappe.db.get_value("HD Ticket Comment", data["comment"], ["content", "commented_by"])
        self.assertEqual(by, AGENT)
        self.assertIn("<p>Check row 2</p>", content)
        self.assertIn("&lt;script&gt;", content)
        self.assertEqual(self.communications(), before)  # nothing went to the customer

    def test_a_draft_fills_the_card_and_sends_nothing(self):
        before = self.communications()
        is_error, data = self.call("draft_ticket_reply", ticket=self.ticket, text="Hello,\n\nThe total is right.")
        self.assertFalse(is_error, data)
        self.assertFalse(data["sent_to_customer"])
        status, reply, note = frappe.db.get_value(
            "HD Ticket", self.ticket, ["custom_ai_suggestion_status", "custom_ai_suggested_reply", "custom_ai_suggestion_note"]
        )
        self.assertEqual(status, "Ready")
        self.assertIn("The total is right.", reply)
        self.assertIn("TBO Copilot", note)
        self.assertEqual(self.communications(), before)

    def test_no_draft_on_a_closed_ticket(self):
        frappe.db.set_value("HD Ticket", self.ticket, {"status": "Closed", "status_category": "Resolved"})
        is_error, text = self.call("draft_ticket_reply", ticket=self.ticket, text="Hi")
        self.assertTrue(is_error)
        self.assertIn("closed", text)

    def test_nothing_is_written_on_a_ticket_the_agent_cannot_see(self):
        from frappe.cache_manager import clear_doctype_map

        self.addCleanup(clear_doctype_map, "Assignment Rule", "HD Ticket")
        frappe.set_user("Administrator")
        team = make_team("MCP Write Team", members=[create_agent("mcp-write-member@example.com").name])
        other = make_ticket(subject="Another team's ticket", customer=self.customer).name
        frappe.db.set_value("HD Ticket", other, "agent_group", team.name)
        restrict_tickets_to_teams(self)
        frappe.set_user(AGENT)
        for tool in ("add_ticket_comment", "draft_ticket_reply"):
            is_error, text = self.call(tool, ticket=other, text="hello")
            self.assertTrue(is_error, tool)
        self.assertFalse(frappe.db.exists("HD Ticket Comment", {"reference_ticket": other}))


class TestTasksAndArticles(WriteCase):
    def make_assigned_task(self, assignee=AGENT):
        frappe.set_user("Administrator")
        project = make_project("MCP Write Project")
        task = make_task(project.name, "Fix the print format")
        task.db_set("_assign", json.dumps([assignee]))
        frappe.set_user(AGENT)
        return task.name

    def test_the_assignee_moves_their_task(self):
        task = self.make_assigned_task()
        is_error, data = self.call("update_task_status", task=task, status="Working")
        self.assertFalse(is_error, data)
        self.assertEqual(data["status"], "Working")
        is_error, text = self.call("update_task_status", task=task, status="On Hold")
        self.assertTrue(is_error)
        self.assertIn("reason", text)
        is_error, data = self.call("update_task_status", task=task, status="On Hold", reason="Waiting on customer", notes="Asked for the invoice")
        self.assertEqual(data["status"], "On Hold")
        is_error, data = self.call("update_task_status", task=task, status="Working")
        self.assertFalse(is_error, data)
        self.assertEqual(data["status"], "Working")

    def test_the_hold_reasons_match_the_task_field(self):
        from helpdesk.copilot.mcp.tools_write import HOLD_REASONS

        options = [o for o in (frappe.get_meta("Task").get_field("hold_reason").options or "").split("\n") if o]
        self.assertEqual(HOLD_REASONS, options)

    def test_someone_elses_task_is_refused(self):
        task = self.make_assigned_task(assignee="Administrator")
        is_error, _text = self.call("update_task_status", task=task, status="Working")
        self.assertTrue(is_error)
        self.assertEqual(frappe.db.get_value("Task", task, "status"), "Open")

    def test_a_kb_draft_is_never_published(self):
        frappe.set_user("Administrator")
        if not frappe.db.exists("HD Article Category", {"category_name": "General"}):
            make_article_category("General")
        frappe.set_user(AGENT)
        is_error, data = self.call(
            "create_kb_article_draft",
            title="Print a Delivery Note in two languages",
            content="# Steps\n\n1. Open the Delivery Note\n2. Choose AR/EN",
            ticket=self.ticket,
        )
        self.assertFalse(is_error, data)
        self.assertFalse(data["published"])
        status, source, content, owner = frappe.db.get_value(
            "HD Article", data["article"], ["status", "source_ticket", "content", "owner"]
        )
        self.assertEqual((status, source, owner), ("Draft", self.ticket, AGENT))
        self.assertIn("<h1", content)
