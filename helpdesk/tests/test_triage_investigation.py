import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import triage
from helpdesk.session_manager import post_investigation_comment
from helpdesk.test_utils import (
    create_customer,
    make_ai_support_session,
    make_support_connection,
    make_ticket,
)

CUSTOMER = "Al Noor Trading LLC"
TRACEBACK = (
    "Traceback (most recent call last):\n  File ...\n"
    "frappe.exceptions.ValidationError: Stock Ledger Entry missing for Item ABC-001"
)


def mcp_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


class TestTriageWithCustomerSite(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        create_customer(CUSTOMER)
        self.connection = make_support_connection(CUSTOMER).name
        self.ticket = make_ticket(
            subject="Stock balance report shows wrong quantity",
            description="Since yesterday the Stock Balance report is wrong for ABC-001.",
            customer=CUSTOMER,
        )
        mcp = MagicMock()
        mcp.call_tool.return_value = mcp_result(
            [
                {
                    "creation": "2026-09-28 09:12:00",
                    "method": "stock_balance.execute",
                    "error": TRACEBACK,
                }
            ]
        )
        patcher = patch("helpdesk.mcp_client.MCPClient", return_value=mcp)
        self.mcp_cls = patcher.start()
        self.addCleanup(patcher.stop)

    def test_triage_input_includes_customer_error_logs(self):
        prompt = triage._build_triage_input(self.ticket)
        self.assertIn("Recent error logs", prompt)
        self.assertIn("Stock Ledger Entry missing for Item ABC-001", prompt)
        self.mcp_cls.assert_called_with(self.connection)

    def test_no_connection_means_no_error_logs(self):
        other = "Gulf Star Logistics"
        create_customer(other)
        ticket = make_ticket(
            subject="How do I print an invoice?",
            description="Where is the print button?",
            customer=other,
        )
        self.assertNotIn("Recent error logs", triage._build_triage_input(ticket))

    def test_unreachable_site_does_not_block_triage(self):
        self.mcp_cls.side_effect = ConnectionError("site down")
        prompt = triage._build_triage_input(self.ticket)
        self.assertIn("Stock balance report shows wrong quantity", prompt)
        self.assertNotIn("Recent error logs", prompt)

    @patch(
        "helpdesk.session_manager.start_investigation", return_value="QCS-AI-2026-00001"
    )
    def test_auto_investigation_only_for_non_trivial_tracks(self, start):
        frappe.db.set_single_value("HDS Hub Settings", "auto_investigate", 1)
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")

        self.assertEqual(
            triage._maybe_start_investigation(
                self.ticket, {"recommended_track": "dev"}
            ),
            "QCS-AI-2026-00001",
        )
        start.assert_called_once_with(
            self.ticket.name,
            self.connection,
            agent_notes="Started automatically after triage.",
        )
        self.assertIsNone(
            triage._maybe_start_investigation(
                self.ticket, {"recommended_track": "manual"}
            )
        )

        frappe.db.set_single_value("HDS Hub Settings", "auto_investigate", 0)
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        self.assertIsNone(
            triage._maybe_start_investigation(self.ticket, {"recommended_track": "dev"})
        )

    def test_triage_comment_shows_findings_and_investigation(self):
        triage._post_triage_comment(
            self.ticket.name,
            {
                "priority": "High",
                "category": "Stock",
                "summary": "Stock Balance is wrong because a Stock Ledger Entry is missing.",
                "error_findings": [
                    "2026-09-28 09:12 stock_balance.execute: missing SLE for ABC-001"
                ],
                "investigation_steps": ["Compare Bin with Stock Ledger for ABC-001"],
                "recommended_track": "ai_investigate",
            },
            investigation="QCS-AI-2026-00001",
        )
        content = frappe.db.get_value(
            "HD Ticket Comment",
            {"reference_ticket": self.ticket.name},
            "content",
            order_by="creation desc",
        )
        self.assertIn("Error log findings", content)
        self.assertIn("missing SLE for ABC-001", content)
        self.assertIn("AI investigation started", content)


class TestInvestigationComment(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        create_customer(CUSTOMER)
        self.connection = make_support_connection(CUSTOMER).name
        self.ticket = make_ticket(
            subject="Stock balance wrong", description="Report wrong", customer=CUSTOMER
        )

    def test_result_and_proposed_fixes_are_posted_on_ticket(self):
        session = make_ai_support_session(
            self.ticket.name,
            self.connection,
            status="Completed",
            diagnosis="## DIAGNOSIS\n- Root cause: repost pending for ABC-001",
            total_tool_calls=7,
        )
        post_investigation_comment(session.name, self.ticket.name, proposed_fixes=2)

        content = frappe.db.get_value(
            "HD Ticket Comment",
            {"reference_ticket": self.ticket.name},
            "content",
            order_by="creation desc",
        )
        self.assertIn("AI Investigation complete", content)
        self.assertIn("Root cause: repost pending for ABC-001", content)
        self.assertIn("2 fix(es) proposed", content)
        self.assertIn("Nothing has been changed", content)
