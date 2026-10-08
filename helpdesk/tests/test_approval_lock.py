# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""An action request is decided once and executed once, whoever clicks twice."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import approval
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_ai_support_session,
    make_support_connection,
    make_ticket,
)


class TestApprovalLock(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        customer = create_customer("Approval Lock Co")
        self.conn = make_support_connection(customer.name).name
        self.ticket = make_ticket(subject="Approval lock")
        session = make_ai_support_session(self.ticket.name, self.conn)
        self.request = approval.create_action_request(
            session.name,
            self.ticket.name,
            [
                {
                    "tool_name": "set_value",
                    "description": "fix the rate",
                    "arguments": {"doctype": "Item", "name": "X", "fieldname": "rate", "value": 1},
                }
            ],
        )

    def test_a_request_is_approved_only_once(self):
        self.assertEqual(approval.approve_actions(self.request), "Approved")
        with self.assertRaises(frappe.ValidationError):
            approval.approve_actions(self.request)
        with self.assertRaises(frappe.ValidationError):
            approval.reject_actions(self.request)

    def test_a_request_is_executed_only_once(self):
        approval.approve_actions(self.request)
        seen = []

        def call_tool(tool, args):
            # by the time the first remote write runs, the request is already claimed
            seen.append(frappe.db.get_value("HDS Support Action Request", self.request, "status"))
            return {"content": [{"type": "text", "text": "ok"}], "isError": False}

        mcp = MagicMock()
        mcp.call_tool.side_effect = call_tool
        with patch.object(approval, "MCPClient", return_value=mcp):
            result = approval.execute_approved_actions(self.request)
            self.assertEqual(result["status"], "Executed")
            self.assertEqual(seen, ["Executing"])

            with self.assertRaises(frappe.ValidationError):
                approval.execute_approved_actions(self.request)
        self.assertEqual(mcp.call_tool.call_count, 1)
