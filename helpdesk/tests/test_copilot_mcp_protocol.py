# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The hub's MCP server speaks plain JSON-RPC over POST, the way the TBO Copilot desktop app expects."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import copilot_mcp
from helpdesk.copilot.mcp import registry, server
from helpdesk.copilot.mcp.auth import Caller
from helpdesk.copilot.mcp.protocol import SUPPORTED_VERSIONS
from helpdesk.test_utils import (
    create_agent,
    fake_http_request,
    hold_commits,
    make_copilot_settings,
    mcp_message,
)

AGENT = "mcp-protocol-agent@example.com"


class TestDispatch(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(AGENT)
        self.caller = Caller(AGENT)

    def reply(self, method, params=None, req_id=1):
        return server.dispatch(self.caller, mcp_message(method, params, req_id))

    def test_initialize_answers_the_clients_version_when_supported(self):
        result = self.reply("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"]["name"], "tbo-support-hub")
        self.assertIn("tools", result["capabilities"])
        older = self.reply("initialize", {"protocolVersion": "1999-01-01"})["result"]
        self.assertEqual(older["protocolVersion"], SUPPORTED_VERSIONS[0])

    def test_ping_answers(self):
        # the desktop pings when Settings -> MCP opens; an error there marks the server failed
        self.assertEqual(self.reply("ping"), {"jsonrpc": "2.0", "id": 1, "result": {}})

    def test_notifications_get_no_reply(self):
        self.assertIsNone(self.reply("notifications/initialized", req_id=None))
        self.assertIsNone(self.reply("notifications/cancelled", {"requestId": 3}, req_id=None))

    def test_a_batch_answers_its_requests_only(self):
        replies = server.dispatch(
            self.caller,
            [mcp_message("notifications/initialized", req_id=None), mcp_message("ping", req_id=7)],
        )
        self.assertEqual([r["id"] for r in replies], [7])
        self.assertEqual(server.dispatch(self.caller, [])["error"]["code"], -32600)

    def test_unknown_and_malformed_messages(self):
        self.assertEqual(self.reply("resources/list")["error"]["code"], -32601)
        self.assertEqual(server.dispatch(self.caller, {"method": "ping", "id": 1})["error"]["code"], -32600)
        self.assertEqual(self.reply("tools/call", {})["error"]["code"], -32602)

    def test_people_see_the_read_tools_and_no_worker_tools(self):
        tools = {t["name"]: t for t in self.reply("tools/list")["result"]["tools"]}
        self.assertIn("get_ticket", tools)
        self.assertIn("my_work", tools)
        self.assertTrue(tools["get_ticket"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["get_ticket"]["inputSchema"]["additionalProperties"])
        worker_tools = {n for n, t in registry.TOOLS.items() if t["kind"] == registry.WORKER_TOOL}
        self.assertFalse(worker_tools & set(tools))
        for tool in tools.values():
            # the desktop shows 120 characters of a description in its tool catalog
            self.assertLessEqual(len(tool["description"]), 120, tool["name"])


class TestEndpoint(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(AGENT)
        make_copilot_settings(mcp_enabled=1)

    def post(self, body, user=AGENT, headers=None):
        headers = {"Authorization": "token key:secret"} if headers is None else headers
        fake_http_request(self, "POST", json.dumps(body) if not isinstance(body, bytes) else body, headers)
        frappe.set_user(user)  # what Frappe's own key check leaves behind
        return copilot_mcp.handle()

    def test_replies_are_raw_json_rpc(self):
        response = self.post(mcp_message("ping", req_id=5))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(json.loads(response.get_data()), {"jsonrpc": "2.0", "id": 5, "result": {}})

    def test_a_notification_gets_202(self):
        self.assertEqual(self.post(mcp_message("notifications/initialized", req_id=None)).status_code, 202)

    def test_get_and_delete_are_not_offered(self):
        for method in ("GET", "DELETE"):
            fake_http_request(self, method)
            response = copilot_mcp.handle()
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response.headers["Allow"], "POST")

    def test_bad_json_is_400(self):
        self.assertEqual(self.post(b"{not json").status_code, 400)

    def test_no_key_is_401_and_administrator_is_403(self):
        response = self.post(mcp_message("ping"), user="Guest", headers={})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(json.loads(response.get_data())["error"]["code"], -32001)
        self.assertEqual(self.post(mcp_message("ping"), user="Administrator").status_code, 403)

    def test_switched_off(self):
        make_copilot_settings(mcp_enabled=0)
        self.assertEqual(self.post(mcp_message("ping")).status_code, 503)
