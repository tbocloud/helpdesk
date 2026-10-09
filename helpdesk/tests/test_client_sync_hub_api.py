# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The sync uses hub_api on sites whose client advertises it: statuses, replies, the customer's answers."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import client_api, ticket_puller
from helpdesk.copilot import runs
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_copilot_run,
    make_copilot_settings,
    make_status,
    make_support_connection,
    make_ticket,
    make_ticket_communication,
)


def ok(payload=None):
    return {"content": [{"type": "text", "text": json.dumps(payload or {})}], "isError": False}


class HubApiSyncCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        make_copilot_settings(enabled=1)
        self.customer = create_customer("Hub API Sync Co").name
        self.conn = make_support_connection(self.customer, client_capabilities='["hub_api_v1"]').name
        self.ticket = make_ticket(subject="Hub API sync", customer=self.customer)
        self.ticket.db_set({"custom_client_ticket": "SUP-2026-00050", "custom_qcs_connection": self.conn})
        self.calls = []
        self.changes = {"server_time": "2026-10-09 10:00:00", "tickets": []}
        self.comments = []
        self.pending = []
        for target, attribute, value in (
            (client_api, "hub_api", self.fake_hub_api),
            (ticket_puller, "MCPClient", None),
        ):
            patcher = (
                patch.object(target, attribute, side_effect=value)
                if value
                else patch.object(target, attribute, return_value=self.make_mcp())
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_mcp(self):
        mcp = MagicMock()
        mcp.call_tool.side_effect = self.fake_mcp
        self.mcp = mcp
        return mcp

    def fake_hub_api(self, conn, method, payload=None):
        self.calls.append((method, payload or {}))
        if method == "get_ticket_changes":
            return self.changes
        return {"ok": True, "applied": list((payload or {}).get("values", {}).keys()), "ignored": []}

    def fake_mcp(self, tool, args):
        if tool == "get_list" and args.get("doctype") == "Comment":
            return ok(self.comments)
        if tool == "get_list" and args.get("doctype") == "Support Ticket" and (args.get("filters") or {}).get("status") == "Pending":
            return ok(self.pending)
        return ok([])

    def calls_to(self, method, name=None):
        return [p for m, p in self.calls if m == method and (name is None or p.get("name") == name)]

    def answered_run(self, root_cause="question", stage="Resolved"):
        run = make_copilot_run(self.ticket.name, state="Answered", root_cause_category=root_cause)
        self.ticket.db_set({"custom_copilot_run": run.name, "custom_copilot_stage": stage})
        return run


class TestStatusPush(HubApiSyncCase):
    def test_the_push_uses_update_ticket_with_the_hubs_own_label(self):
        make_status("Waiting on Task", category="Paused")
        self.ticket.db_set("status", "Waiting on Task")
        ticket_puller.push_ticket_statuses()
        pushed = self.calls_to("update_ticket", "SUP-2026-00050")
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0]["values"]["status"], "Waiting on Task")
        self.assertEqual(pushed[0]["values"]["ticket_id"], self.ticket.name)
        self.assertTrue(frappe.db.get_value("HD Ticket", self.ticket.name, "custom_client_push_hash"))

        ticket_puller.push_ticket_statuses()
        self.assertEqual(len(self.calls_to("update_ticket", "SUP-2026-00050")), 1)

    def test_an_old_client_still_gets_set_values(self):
        old_customer = create_customer("Old Sync Co").name
        old_conn = make_support_connection(old_customer).name
        old = make_ticket(subject="Old client", customer=old_customer)
        old.db_set({"custom_client_ticket": "SUP-2026-00001", "custom_qcs_connection": old_conn})
        ticket_puller.push_ticket_statuses()
        set_values = [
            c.args[1]
            for c in self.mcp.call_tool.call_args_list
            if c.args[0] == "set_values" and c.args[1]["name"] == "SUP-2026-00001"
        ]
        self.assertEqual(len(set_values), 1)
        self.assertEqual(self.calls_to("update_ticket", "SUP-2026-00001"), [])


class TestReplies(HubApiSyncCase):
    def test_a_reply_goes_through_post_reply_once(self):
        reply = make_ticket_communication(self.ticket.name, "<p>We fixed it</p>", sent_or_received="Sent")
        ticket_puller.sync_conversations()
        posted = self.calls_to("post_reply", "SUP-2026-00050")
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0]["hub_ref"], reply.name)
        self.assertIn("fixed", posted[0]["content"])
        self.assertFalse([c for c in self.mcp.call_tool.call_args_list if c.args[0] == "create_doc"])

        ticket_puller.sync_conversations()
        self.assertEqual(len(self.calls_to("post_reply", "SUP-2026-00050")), 1)


class TestCustomerAnswers(HubApiSyncCase):
    def change(self, confirmation, note="", confirmed_at="2026-10-09 09:59:00"):
        return {
            "name": "SUP-2026-00050",
            "ticket_id": self.ticket.name,
            "status": "Resolved",
            "customer_confirmation": confirmation,
            "confirmation_note": note,
            "confirmed_at": confirmed_at,
            "reopen_requested": int(confirmation == "Reopened"),
            "close_requested": int(confirmation == "Confirmed"),
            "modified": confirmed_at,
        }

    def test_a_confirmation_closes_the_ticket_and_the_run_once(self):
        run = self.answered_run()
        self.changes["tickets"] = [self.change("Confirmed", "works now")]
        ticket_puller.sync_conversations()
        self.assertEqual(frappe.db.get_value("HD Ticket", self.ticket.name, "status"), "Closed")
        self.assertEqual(frappe.db.get_value("HD Ticket", self.ticket.name, "custom_customer_confirmation"), "Confirmed")
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Closed")
        self.assertEqual(
            str(frappe.db.get_value("HDS Support Connection", self.conn, "client_changes_cursor")),
            "2026-10-09 10:00:00",
        )
        self.assertEqual(self.calls_to("get_ticket_changes")[0]["since"][:4], "2026")

        comments = frappe.db.count("HD Ticket Comment", {"reference_ticket": self.ticket.name})
        ticket_puller.sync_conversations()
        self.assertEqual(frappe.db.count("HD Ticket Comment", {"reference_ticket": self.ticket.name}), comments)
        self.assertEqual(self.calls_to("get_ticket_changes")[-1]["since"], "2026-10-09 10:00:00")

    def test_a_reopen_escalates_and_hands_over(self):
        run = self.answered_run()
        self.changes["tickets"] = [self.change("Reopened", "still wrong")]
        with patch.object(runs, "tell_people") as tell:
            ticket_puller.sync_conversations()
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Escalated")
        self.assertNotEqual(frappe.db.get_value("HD Ticket", self.ticket.name, "status"), "Closed")
        self.assertEqual(frappe.db.get_value("HD Ticket", self.ticket.name, "custom_copilot_stage"), "With our team")
        self.assertEqual(self.calls_to("add_update")[-1]["stage"], "With our team")
        tell.assert_called_once()

    def test_a_customer_comment_after_a_question_starts_a_follow_up(self):
        run = self.answered_run(root_cause="unclear", stage="Waiting for you")
        self.comments = [{"name": "CMT-0001", "content": "the stock report, every morning", "owner": "user@customer.example"}]
        ticket_puller.sync_conversations()
        follow_up = frappe.db.get_value("HD Ticket", self.ticket.name, "custom_copilot_run")
        self.assertNotEqual(follow_up, run.name)
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", follow_up, ["kind", "state"]), ("followup", "Queued"))


class TestPull(HubApiSyncCase):
    def test_the_pull_writes_back_through_hub_api(self):
        self.pending = [
            {
                "name": "SUP-2026-00051",
                "subject": "New from the site",
                "description": "<p>help</p>",
                "raised_by": "user@customer.example",
                "screen_recording": None,
                "creation": "2026-10-09 09:00:00",
            }
        ]
        created = ticket_puller._pull_connection(self.conn, self.customer)
        self.assertEqual(created, 1)
        written = self.calls_to("update_ticket", "SUP-2026-00051")
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["values"]["status"], "Open")
        self.assertTrue(written[0]["values"]["ticket_id"])
        self.assertFalse([c for c in self.mcp.call_tool.call_args_list if c.args[0] == "set_values"])
