# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Tests for the zero-client-key ticket flow.

Run on the staging hub (Frappe v16 + Helpdesk + helpdesk):
    bench --site <staging-hub> run-tests --module helpdesk.tests.test_ticket_puller
"""

import gzip
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import (
    create_customer,
    make_diagnostics,
    make_download_response,
    make_puller_mcp,
    make_replay,
    make_support_connection,
    make_ticket,
)


def mcp_result(payload):
    """Shape an MCP tools/call result the way MCPClient returns it."""
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": False,
    }


class TestPendingTickets(FrappeTestCase):
    def test_parses_mcp_payload(self):
        from helpdesk.ticket_puller import _pending_tickets

        mcp = MagicMock()
        mcp.call_tool.return_value = mcp_result(
            [
                {
                    "name": "SUP-2026-00001",
                    "subject": "Printer offline",
                    "description": "<p>offline</p>",
                    "raised_by": "user@avientek.com",
                    "screen_recording": "/private/files/rec.mp4",
                },
            ]
        )

        tickets = _pending_tickets(mcp)

        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["name"], "SUP-2026-00001")

        tool, args = mcp.call_tool.call_args[0]
        self.assertEqual(tool, "get_list")
        self.assertEqual(args["doctype"], "Support Ticket")
        self.assertEqual(args["filters"], {"status": "Pending"})
        self.assertIn("description", args["fields"])

    def test_error_result_raises(self):
        from helpdesk.ticket_puller import _pending_tickets

        mcp = MagicMock()
        mcp.call_tool.return_value = {"content": [], "isError": True}

        with self.assertRaises(ValueError):
            _pending_tickets(mcp)


class TestCreateHDTicket(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        # the connection is a real link on the ticket from the insert on
        self.connection = make_support_connection(create_customer("Puller Co").name).name

    def test_creates_hd_ticket_from_pulled_payload(self):
        from helpdesk.ticket_puller import _create_hd_ticket

        hd_name = _create_hd_ticket(
            connection_name=self.connection,
            customer=None,
            ticket={
                "name": "SUP-2026-00001",
                "subject": "Printer offline",
                "description": "<p>offline</p>",
                "raised_by": "user@avientek.com",
            },
        )

        hd = frappe.get_doc("HD Ticket", hd_name)
        self.assertEqual(hd.subject, "Printer offline")
        self.assertEqual(hd.custom_client_ticket, "SUP-2026-00001")
        self.assertEqual(hd.custom_qcs_connection, self.connection)

    def test_already_imported_guard(self):
        from helpdesk.ticket_puller import _already_imported, _create_hd_ticket

        _create_hd_ticket(
            connection_name=self.connection,
            customer=None,
            ticket={
                "name": "SUP-2026-00099",
                "subject": "Dupe check",
                "description": "",
            },
        )

        self.assertTrue(_already_imported(self.connection, "SUP-2026-00099"))
        self.assertFalse(_already_imported(self.connection, "SUP-2026-00100"))


class TestAttachRecording(FrappeTestCase):
    def test_skips_when_absent(self):
        from helpdesk.ticket_puller import _attach_recording

        self.assertIsNone(_attach_recording(MagicMock(), "HD-TICKET-0001", None))


class TestAttachSessionFiles(FrappeTestCase):
    """The recorder's replay + diagnostics come through quietly, as private files."""

    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.ticket = make_ticket(subject="Cannot save Sales Invoice")

    @patch("helpdesk.ticket_puller.requests.get")
    def test_session_files_are_private_and_not_linked(self, get):
        from helpdesk.session_replay import load_diagnostics, load_replay
        from helpdesk.ticket_puller import _attach_recording

        get.side_effect = [
            make_download_response(gzip.compress(json.dumps(make_replay()).encode())),
            make_download_response(json.dumps(make_diagnostics()).encode()),
        ]
        mcp = make_puller_mcp()

        # the customer's stored path carries a Frappe suffix; the File name does not
        names = [
            _attach_recording(
                mcp,
                self.ticket.name,
                "/private/files/session-replay.json3f2a1c.gz",
                "session-replay.json.gz",
            ),
            _attach_recording(
                mcp,
                self.ticket.name,
                "/private/files/session-diagnostics.json",
                "session-diagnostics.json",
            ),
        ]

        self.assertEqual(
            get.call_args_list[0].args[0],
            "https://erp.example.com/private/files/session-replay.json3f2a1c.gz",
        )
        self.assertEqual(
            frappe.db.get_value("File", names[0], "file_name"), "session-replay.json.gz"
        )
        for name in names:
            file_doc = frappe.get_doc("File", name)
            self.assertTrue(file_doc.is_private)
            self.assertEqual(file_doc.attached_to_doctype, "HD Ticket")
            self.assertEqual(file_doc.attached_to_name, self.ticket.name)
        self.assertEqual(
            len(load_replay(self.ticket.name)["events"]), len(make_replay()["events"])
        )
        self.assertEqual(load_diagnostics(self.ticket.name)["browser"], "Chrome 128")

        comments = frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": self.ticket.name},
            pluck="content",
        )
        notes = [c for c in comments if "Session replay attached" in c]
        self.assertEqual(len(notes), 1)
        self.assertNotIn("href", notes[0])
        self.assertFalse(
            [
                c
                for c in comments
                if "session-diagnostics" in c or "session-replay.json" in c
            ]
        )

    @patch("helpdesk.ticket_puller.MAX_RECORDING_BYTES", 10)
    @patch("helpdesk.ticket_puller.requests.get")
    def test_oversized_session_file_is_skipped(self, get):
        from helpdesk.ticket_puller import _attach_recording

        get.return_value = make_download_response(b"x" * 11)

        self.assertIsNone(
            _attach_recording(
                make_puller_mcp(),
                self.ticket.name,
                "/private/files/session-replay.json.gz",
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "File",
                {
                    "attached_to_doctype": "HD Ticket",
                    "attached_to_name": self.ticket.name,
                },
            )
        )

    def test_screenshots_are_still_linked(self):
        from helpdesk.ticket_puller import _media_note

        note = _media_note(
            MagicMock(file_name="shot.png", file_url="/private/files/shot.png")
        )

        self.assertIn('href="/private/files/shot.png"', note)
        self.assertIn("Screenshot", note)


class TestPushBack(FrappeTestCase):
    def test_writes_status_and_ticket_id(self):
        from helpdesk.ticket_puller import _push_back

        mcp = MagicMock()
        mcp.call_tool.return_value = mcp_result({"name": "SUP-2026-00001"})

        _push_back(mcp, "SUP-2026-00001", {"ticket_id": "42", "status": "Open"})

        tool, args = mcp.call_tool.call_args[0]
        self.assertEqual(tool, "set_values")
        self.assertEqual(args["doctype"], "Support Ticket")
        self.assertEqual(args["name"], "SUP-2026-00001")
        self.assertEqual(args["values"]["status"], "Open")
        self.assertEqual(args["values"]["ticket_id"], "42")


class TestSchedulerWiring(FrappeTestCase):
    def test_pull_runs_every_minute_and_push_every_five(self):
        cron = frappe.get_hooks("scheduler_events", app_name="helpdesk").get("cron", {})
        self.assertIn("helpdesk.tasks.pull_client_tickets", cron.get("* * * * *", []))
        self.assertIn(
            "helpdesk.tasks.push_ticket_statuses", cron.get("*/5 * * * *", [])
        )


class TestConnectionHealth(FrappeTestCase):
    def setUp(self):
        from helpdesk.test_utils import create_customer, make_support_connection

        self.addCleanup(frappe.db.rollback)
        create_customer("Harbour Foods LLC")
        self.conn = make_support_connection(
            "Harbour Foods LLC", connection_status="Error", last_error="503 at midnight"
        ).name

    def test_error_connection_is_retried_and_recovers(self):
        from helpdesk import ticket_puller

        with patch.object(ticket_puller, "MCPClient"), patch.object(
            ticket_puller, "_pending_tickets", return_value=[]
        ) as pending:
            ticket_puller.pull_client_tickets()

        self.assertTrue(pending.called)
        row = frappe.db.get_value(
            "HDS Support Connection",
            self.conn,
            ["connection_status", "last_error"],
            as_dict=True,
        )
        self.assertEqual((row.connection_status, row.last_error), ("Connected", ""))

    def test_failure_marks_the_connection_with_the_reason(self):
        from helpdesk import ticket_puller

        frappe.db.set_value(
            "HDS Support Connection", self.conn, "connection_status", "Connected"
        )
        with patch.object(ticket_puller, "MCPClient"), patch.object(
            ticket_puller,
            "_pending_tickets",
            side_effect=RuntimeError("503 Service Unavailable"),
        ), patch.object(frappe, "log_error"):
            ticket_puller.pull_connection(self.conn)

        row = frappe.db.get_value(
            "HDS Support Connection",
            self.conn,
            ["connection_status", "last_error"],
            as_dict=True,
        )
        self.assertEqual(row.connection_status, "Error")
        self.assertIn("503", row.last_error)

    def test_ping_queues_a_pull_for_known_sites_only(self):
        from helpdesk.api import support_hub

        with patch.object(frappe, "enqueue") as enqueue:
            self.assertEqual(support_hub.ticket_raised(self.conn), {"ok": True})
            self.assertEqual(support_hub.ticket_raised("NO-SUCH-CONN"), {"ok": True})

        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(enqueue.call_args.kwargs["connection"], self.conn)

    def test_status_push_sends_the_hub_ticket_number(self):
        # a ticket restored after deletion comes back under a new number
        from helpdesk import ticket_puller

        ticket = make_ticket(subject="Filter not working")
        ticket.db_set(
            {"custom_client_ticket": "SUP-0001", "custom_qcs_connection": self.conn}
        )
        mcp = MagicMock()
        with patch.object(ticket_puller, "MCPClient", return_value=mcp):
            ticket_puller.push_ticket_statuses()

        pushed = [
            c.args[1]
            for c in mcp.call_tool.call_args_list
            if c.args[0] == "set_values" and c.args[1]["name"] == "SUP-0001"
        ]
        self.assertEqual(pushed[0]["values"]["ticket_id"], ticket.name)


class TestInstallFixes(FrappeTestCase):
    def test_illegal_check_default_is_normalised(self):
        """Helpdesk ships raised_outside_working_hours with default 'False',
        which blocks installing this app onto a fresh Helpdesk site."""
        from helpdesk.install import normalise_illegal_check_defaults

        frappe.db.set_value(
            "DocField",
            {"parent": "HD Ticket", "fieldname": "raised_outside_working_hours"},
            "default",
            "False",
            update_modified=False,
        )

        normalise_illegal_check_defaults()

        self.assertEqual(
            frappe.db.get_value(
                "DocField",
                {"parent": "HD Ticket", "fieldname": "raised_outside_working_hours"},
                "default",
            ),
            "0",
        )

    def test_normalise_is_idempotent(self):
        from helpdesk.install import normalise_illegal_check_defaults

        normalise_illegal_check_defaults()
        normalise_illegal_check_defaults()

        self.assertIn(
            frappe.db.get_value(
                "DocField",
                {"parent": "HD Ticket", "fieldname": "raised_outside_working_hours"},
                "default",
            ),
            ("0", "1"),
        )
