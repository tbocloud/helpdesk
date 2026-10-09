# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Every MCP tool call is logged, and each person has a per-minute limit."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import audit
from helpdesk.copilot.mcp import registry
from helpdesk.copilot.mcp.auth import Caller
from helpdesk.test_utils import create_agent, hold_commits, make_assigned_ticket, make_copilot_settings

AGENT = "mcp-log-agent@example.com"


class TestCallLog(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(AGENT)
        self.ticket = make_assigned_ticket("Logged ticket", AGENT)
        self.addCleanup(frappe.cache.delete, audit.rate_key(AGENT))
        frappe.cache.delete(audit.rate_key(AGENT))
        frappe.set_user(AGENT)
        self.caller = Caller(AGENT)

    def last_log(self):
        return frappe.get_all(
            "HDS Copilot Call Log",
            filters={"user": AGENT},
            fields=["tool", "status", "ticket", "kind", "ms", "arguments", "result"],
            order_by="creation desc",
            limit=1,
        )[0]

    def test_a_call_is_logged_with_who_what_and_the_ticket(self):
        make_copilot_settings(mcp_calls_per_minute=100)
        registry.call(self.caller, "get_fix_brief", {"ticket": str(int(self.ticket))})
        log = self.last_log()
        self.assertEqual((log.tool, log.status, log.ticket, log.kind), ("get_fix_brief", "OK", self.ticket, "MCP person"))
        # the log keeps the ticket as stored, whatever way the caller wrote it
        self.assertIn(str(int(self.ticket)), log.arguments)

    def test_a_refusal_is_logged_as_refused(self):
        make_copilot_settings(mcp_calls_per_minute=100)
        registry.call(self.caller, "get_ticket", {"ticket": "9999"})
        log = self.last_log()
        self.assertEqual((log.status, log.ticket), ("Refused", "9999"))

    def test_an_unknown_tool_is_refused_and_logged(self):
        make_copilot_settings(mcp_calls_per_minute=100)
        result = registry.call(self.caller, "delete_everything", {})
        self.assertTrue(result["isError"])
        self.assertEqual(self.last_log().status, "Refused")

    def test_calls_over_the_limit_are_refused_for_the_minute(self):
        frappe.set_user("Administrator")
        make_copilot_settings(mcp_calls_per_minute=2)
        frappe.set_user(AGENT)
        for _ in range(2):
            self.assertFalse(registry.call(self.caller, "my_work", {})["isError"])
        result = registry.call(self.caller, "my_work", {})
        self.assertTrue(result["isError"])
        self.assertIn("Rate limited", result["content"][0]["text"])
        self.assertEqual(self.last_log().status, "Limited")
