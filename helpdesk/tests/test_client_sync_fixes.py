# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Write-backs to the customer site are honest: refusals surface, unchanged tickets stay quiet."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import ticket_puller
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_status,
    make_support_connection,
    make_ticket,
    make_ticket_communication,
)


def ok(payload=None):
    return {"content": [{"type": "text", "text": json.dumps(payload or {})}], "isError": False}


def refused(message="Write operations are disabled"):
    return {"content": [{"type": "text", "text": message}], "isError": True}


class TestPushBackRefusal(FrappeTestCase):
    def test_a_refused_write_raises_instead_of_passing_silently(self):
        mcp = MagicMock()
        mcp.call_tool.return_value = refused()

        with self.assertRaises(ValueError) as caught:
            ticket_puller._push_back(mcp, "SUP-0001", {"status": "Open"})
        self.assertIn("Write operations are disabled", str(caught.exception))


class TestClientStatusLabels(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)

    def test_labels_the_customer_app_knows_pass_through(self):
        self.assertEqual(ticket_puller.client_status_for("Open"), "Open")
        self.assertEqual(ticket_puller.client_status_for("Closed"), "Closed")

    def test_other_labels_map_by_category(self):
        make_status("Waiting on Task", category="Paused")
        make_status("Under Review", category="Open")
        self.assertEqual(ticket_puller.client_status_for("Waiting on Task"), "Paused")
        self.assertEqual(ticket_puller.client_status_for("Under Review"), "Open")

    def test_an_unknown_label_is_left_out(self):
        self.assertIsNone(ticket_puller.client_status_for("No Such Status"))


class TestStatusPushOnlyOnChange(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        customer = create_customer("Sync Fix Co")
        self.conn = make_support_connection(customer.name).name
        self.ticket = make_ticket(subject="Push on change")
        self.ticket.db_set({"custom_client_ticket": "SUP-0101", "custom_qcs_connection": self.conn})

    def push(self, mcp):
        with patch.object(ticket_puller, "MCPClient", return_value=mcp):
            return ticket_puller.push_ticket_statuses()

    def pushed_values(self, mcp):
        return [
            c.args[1]["values"]
            for c in mcp.call_tool.call_args_list
            if c.args[0] == "set_values" and c.args[1]["name"] == "SUP-0101"
        ]

    def test_unchanged_tickets_are_not_pushed_again(self):
        mcp = MagicMock()
        mcp.call_tool.return_value = ok()

        self.push(mcp)
        self.assertEqual(len(self.pushed_values(mcp)), 1)
        self.assertTrue(frappe.db.get_value("HD Ticket", self.ticket.name, "custom_client_push_hash"))

        self.push(mcp)
        self.assertEqual(len(self.pushed_values(mcp)), 1)

    def test_a_status_change_is_pushed_with_a_label_the_client_accepts(self):
        make_status("Waiting on Task", category="Paused")
        mcp = MagicMock()
        mcp.call_tool.return_value = ok()
        self.push(mcp)

        self.ticket.db_set("status", "Waiting on Task")
        self.push(mcp)

        values = self.pushed_values(mcp)
        self.assertEqual(len(values), 2)
        self.assertEqual(values[-1]["status"], "Paused")
        self.assertEqual(values[-1]["ticket_id"], self.ticket.name)

    def test_a_refused_push_is_retried_next_time(self):
        mcp = MagicMock()
        mcp.call_tool.return_value = refused()
        self.push(mcp)
        self.assertFalse(frappe.db.get_value("HD Ticket", self.ticket.name, "custom_client_push_hash"))

        mcp.call_tool.return_value = ok()
        self.push(mcp)
        self.assertEqual(len(self.pushed_values(mcp)), 2)


class TestOnePullAtATime(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        customer = create_customer("Pull Lock Co")
        self.conn = make_support_connection(customer.name).name
        self.lock = frappe.cache.make_key(f"hds_pull_lock:{self.conn}")
        self.addCleanup(frappe.cache.delete, self.lock)

    def test_a_second_pull_of_the_same_site_is_skipped(self):
        frappe.cache.set(self.lock, 1, ex=60)
        mcp = MagicMock()
        with patch.object(ticket_puller, "MCPClient", return_value=mcp):
            self.assertEqual(ticket_puller.pull_connection(self.conn), 0)
        mcp.call_tool.assert_not_called()

    def test_the_lock_is_released_after_a_pull(self):
        mcp = MagicMock()
        mcp.call_tool.return_value = ok([])
        with patch.object(ticket_puller, "MCPClient", return_value=mcp):
            ticket_puller.pull_connection(self.conn)
        self.assertIsNone(frappe.cache.get(self.lock))

    def test_a_ping_triggered_pull_runs_as_the_automation_user(self):
        from helpdesk.automation import automation_user

        frappe.set_user("Guest")
        mcp = MagicMock()
        mcp.call_tool.return_value = ok([])
        with patch.object(ticket_puller, "MCPClient", return_value=mcp):
            ticket_puller.pull_connection(self.conn)
        self.assertEqual(frappe.session.user, automation_user())


class TestConversationSync(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        customer = create_customer("Reply Sync Co")
        self.conn = make_support_connection(customer.name).name
        self.ticket = make_ticket(subject="Reply sync")
        self.ticket.db_set({"custom_client_ticket": "SUP-0202", "custom_qcs_connection": self.conn})

    def mcp_with(self, create_doc_result, close_requested=False):
        def call_tool(tool, args):
            if tool == "create_doc":
                return create_doc_result
            if tool == "get_list" and args.get("doctype") == "Support Ticket":
                return ok([{"name": "SUP-0202"}] if close_requested else [])
            return ok([])

        mcp = MagicMock()
        mcp.call_tool.side_effect = call_tool
        return mcp

    def sync(self, mcp):
        with patch.object(ticket_puller, "MCPClient", return_value=mcp):
            ticket_puller.sync_conversations()

    def synced_replies(self):
        state = json.loads(frappe.db.get_value("HD Ticket", self.ticket.name, "custom_sync_state") or "{}")
        return state.get("hub", [])

    def test_a_refused_reply_is_not_marked_as_sent(self):
        reply = make_ticket_communication(self.ticket.name, "We fixed it", sent_or_received="Sent")

        # the sync rolls back on failure, which in a test would undo the fixtures above
        with patch.object(frappe.db, "rollback"):
            self.sync(self.mcp_with(refused()))
        self.assertNotIn(reply.name, self.synced_replies())

        self.sync(self.mcp_with(ok({"name": "CMT-1"})))
        self.assertIn(reply.name, self.synced_replies())

    def test_a_close_request_closes_through_the_controller(self):
        self.sync(self.mcp_with(ok(), close_requested=True))

        status, category = frappe.db.get_value(
            "HD Ticket", self.ticket.name, ["status", "status_category"]
        )
        self.assertEqual(status, "Closed")
        self.assertEqual(category, "Resolved")
