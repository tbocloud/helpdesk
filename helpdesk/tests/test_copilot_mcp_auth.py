# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Only agents, with their own key, may use the hub's MCP server; never Administrator."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot.mcp.auth import PERSON, identify_from
from helpdesk.test_utils import create_agent, create_user, hold_commits

KEY = "token key:secret"


class TestIdentify(FrappeTestCase):
    def setUp(self):
        hold_commits(self)

    def test_an_agent_with_a_key_is_a_person(self):
        agent = create_agent("mcp-auth-agent@example.com").name
        caller = identify_from(KEY, None, agent)
        self.assertEqual((caller.user, caller.kind, caller.run), (agent, PERSON, None))

    def test_without_a_key_nobody_gets_in(self):
        agent = create_agent("mcp-auth-agent@example.com").name
        with self.assertRaises(frappe.AuthenticationError):
            identify_from(None, None, agent)  # a browser session alone is not enough
        with self.assertRaises(frappe.AuthenticationError):
            identify_from(KEY, None, "Guest")

    def test_administrator_and_non_agents_are_refused(self):
        with self.assertRaises(frappe.PermissionError):
            identify_from(KEY, None, "Administrator")
        outsider = create_user("mcp-auth-outsider@example.com").name
        with self.assertRaises(frappe.PermissionError):
            identify_from(KEY, None, outsider)

    def test_a_disabled_user_is_refused(self):
        agent = create_agent("mcp-auth-disabled@example.com").name
        frappe.db.set_value("User", agent, "enabled", 0)
        with self.assertRaises(frappe.AuthenticationError):
            identify_from(KEY, None, agent)

    def test_a_key_and_a_run_token_together_are_refused(self):
        with self.assertRaises(frappe.AuthenticationError):
            identify_from(KEY, "TBO-RUN-2026-00001:token", "Guest")
