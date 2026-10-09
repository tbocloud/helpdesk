# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The worker's run token: only its run, only worker tools, only while the lease lives."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import copilot_mcp
from helpdesk.api.copilot_worker import WORKER_ROLE, claim_job, ensure_role
from helpdesk.copilot import runs
from helpdesk.copilot.mcp import registry
from helpdesk.copilot.mcp.auth import WORKER, Caller, identify_from
from helpdesk.copilot.mcp.tools_worker import MAX_SITE_RESULT_CHARS
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    create_user,
    fake_http_request,
    fake_investigation,
    hold_commits,
    make_copilot_settings,
    make_support_connection,
    make_ticket,
    mcp_message,
    mcp_tool_result,
)

WORKER_USER = "mcp-worker@example.com"
WORKER_TOOLS = {"get_run_context", "post_event", "submit_investigation", "customer_erp_read"}


def site_result(payload, is_error=False):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class WorkerCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_copilot_settings(enabled=1, mcp_enabled=1, mcp_calls_per_minute=1000)
        ensure_role()
        create_user(WORKER_USER).add_roles(WORKER_ROLE)
        customer = create_customer("MCP Worker Co").name
        self.conn = make_support_connection(customer).name
        ticket = make_ticket(subject="Worker ticket", customer=customer)
        ticket.db_set("custom_qcs_connection", self.conn)
        frappe.db.set_value("HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled")
        self.run = runs.start_run(ticket.name).name
        frappe.set_user(WORKER_USER)
        job = claim_job("w1")
        self.token = f"{job['run']}:{job['lease_token']}"
        self.assertEqual(job["run"], self.run)
        self.caller = identify_from(None, self.token, "Guest")

    def call(self, tool_name, caller=None, **arguments):
        result = registry.call(caller or self.caller, tool_name, arguments)
        return result["isError"], mcp_tool_result(result)


class TestRunToken(WorkerCase):
    def test_the_token_acts_as_the_worker_for_its_run(self):
        self.assertEqual((self.caller.kind, self.caller.run, self.caller.user), (WORKER, self.run, WORKER_USER))
        self.assertEqual(frappe.session.user, WORKER_USER)

    def test_bad_tokens_are_refused(self):
        for token in (f"{self.run}:wrong", "TBO-RUN-2026-99999:x", "no-colon"):
            with self.assertRaises(frappe.AuthenticationError, msg=token):
                identify_from(None, token, "Guest")

    def test_the_token_dies_with_the_lease(self):
        frappe.set_user("Administrator")
        runs.transition(self.run, "Cancelled", runs.AGENT)
        with self.assertRaises(frappe.AuthenticationError):
            identify_from(None, self.token, "Guest")

    def test_the_endpoint_takes_the_token_header(self):
        fake_http_request(
            self, "POST", json.dumps(mcp_message("tools/list")), {"X-Copilot-Run-Token": self.token}
        )
        frappe.set_user("Guest")  # no Authorization header: Frappe leaves the request as Guest
        reply = json.loads(copilot_mcp.handle().get_data())
        self.assertEqual({t["name"] for t in reply["result"]["tools"]}, WORKER_TOOLS)


class TestToolsKeptApart(WorkerCase):
    def test_worker_and_people_tools_are_kept_apart(self):
        self.assertEqual({t["name"] for t in registry.definitions_for(self.caller)}, WORKER_TOOLS)
        is_error, text = self.call("get_ticket", ticket="0001")
        self.assertTrue(is_error)
        self.assertIn("Unknown tool", text)
        agent = create_agent("mcp-worker-agent@example.com").name
        is_error, text = self.call("get_run_context", caller=Caller(agent))
        self.assertTrue(is_error)
        self.assertIn("Unknown tool", text)


class TestWorkerTools(WorkerCase):
    def test_context_and_events(self):
        is_error, context = self.call("get_run_context")
        self.assertFalse(is_error, context)
        self.assertEqual(context["ticket"]["subject"], "Worker ticket")
        self.assertNotIn("api_key", json.dumps(context))
        self.assertEqual(self.call("post_event", seq=1, type="tool_call", payload={"tool": "get_doc"})[1]["stored"], True)
        self.assertEqual(self.call("post_event", seq=1, type="tool_call")[1]["stored"], False)

    @patch("helpdesk.mcp_client.MCPClient")
    def test_customer_erp_read_goes_through_the_hub_and_only_reads(self, client):
        site = MagicMock()
        client.return_value = site
        site.call_tool.return_value = site_result([{"name": "ACC-SINV-2026-00042"}])
        is_error, data = self.call("customer_erp_read", tool="get_list", arguments={"doctype": "Sales Invoice"})
        self.assertFalse(is_error, data)
        self.assertEqual(data["result"], [{"name": "ACC-SINV-2026-00042"}])
        client.assert_called_with(self.conn)
        self.assertEqual(site.call_tool.call_args.kwargs["session_id"], self.run)

        site.call_tool.reset_mock()
        is_error, text = self.call("customer_erp_read", tool="set_value", arguments={})
        self.assertTrue(is_error)
        site.call_tool.assert_not_called()

        site.call_tool.return_value = site_result("Doctype Sales Invoice is blocked", is_error=True)
        is_error, text = self.call("customer_erp_read", tool="get_doc", arguments={"doctype": "Sales Invoice", "name": "x"})
        self.assertTrue(is_error)
        self.assertIn("refused", text)

        site.call_tool.return_value = site_result("x" * (MAX_SITE_RESULT_CHARS + 10))
        is_error, data = self.call("customer_erp_read", tool="get_error_log", arguments={})
        self.assertEqual(data["cut_at_characters"], MAX_SITE_RESULT_CHARS)

    def test_no_site_no_read(self):
        frappe.db.set_value("HDS Copilot Run", self.run, "connection", None)
        is_error, text = self.call("customer_erp_read", tool="get_site_info")
        self.assertTrue(is_error)
        self.assertIn("No customer site", text)

    def test_submit_investigation_routes_the_run_and_ends_the_lease(self):
        result = fake_investigation("bug")
        result.pop("kind")
        is_error, data = self.call("submit_investigation", **result)
        self.assertFalse(is_error, data)
        self.assertEqual((data["state"], data["root_cause"]), ("Preparing Fix", "bug"))
        with self.assertRaises(frappe.AuthenticationError):
            identify_from(None, self.token, "Guest")
