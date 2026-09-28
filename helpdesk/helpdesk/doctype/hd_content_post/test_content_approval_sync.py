# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk import content_sync
from helpdesk.api.content import draft_caption, normalize_hashtags
from helpdesk.test_utils import (
    create_customer,
    make_content_post,
    make_support_connection,
)

CUSTOMER = "Al Noor Trading LLC"


def mcp_result(payload):
    """Shape a value the way MCP tool results arrive."""
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


class TestContentApprovalSync(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        create_customer(CUSTOMER)
        self.connection = make_support_connection(CUSTOMER).name
        self.post = make_content_post(
            "Diwali offer carousel",
            CUSTOMER,
            status="Client Review",
            publish_on=add_to_date(now_datetime(), days=3),
        )

        self.mcp = MagicMock()
        mcp_cls = patch.object(content_sync, "MCPClient", return_value=self.mcp)
        mcp_cls.start()
        self.addCleanup(mcp_cls.stop)

    def reload(self):
        return frappe.get_doc("HD Content Post", self.post.name)

    def test_push_creates_approval_on_client_once(self):
        self.mcp.call_tool.return_value = mcp_result({"status": "created", "name": "CA-2026-00001"})

        self.assertEqual(content_sync.push_posts_for_approval(), 1)
        tool, args = self.mcp.call_tool.call_args.args
        self.assertEqual(tool, "create_doc")
        self.assertEqual(args["doctype"], "Content Approval")
        self.assertEqual(args["values"]["hub_post"], self.post.name)

        post = self.reload()
        self.assertEqual(post.client_approval_ref, "CA-2026-00001")
        self.assertEqual(post.client_connection, self.connection)

        # unchanged since it was sent: nothing to push
        self.assertEqual(content_sync.push_posts_for_approval(), 0)

    def test_edited_post_is_resent_as_pending(self):
        self.mcp.call_tool.return_value = mcp_result({"status": "created", "name": "CA-2026-00001"})
        content_sync.push_posts_for_approval()

        post = self.reload()
        post.db_set("sent_for_approval_on", add_to_date(now_datetime(), minutes=-10), update_modified=False)
        post.caption = "Updated caption"
        post.save()

        self.assertEqual(content_sync.push_posts_for_approval(), 1)
        tool, args = self.mcp.call_tool.call_args.args
        self.assertEqual(tool, "set_values")
        self.assertEqual(args["name"], "CA-2026-00001")
        self.assertEqual(args["values"]["status"], "Pending")

    def test_client_decisions_update_the_post(self):
        self.post.db_set({"client_approval_ref": "CA-2026-00001", "client_connection": self.connection})

        self.mcp.call_tool.return_value = mcp_result(
            [{"name": "CA-2026-00001", "status": "Changes Requested", "client_comment": "Use the new logo", "decided_by": "fatima@alnoor.example"}]
        )
        self.assertEqual(content_sync.pull_approval_decisions(), 1)
        post = self.reload()
        self.assertEqual(post.status, "Changes Requested")
        self.assertEqual(post.client_feedback, "Use the new logo")

        post.status = "Client Review"
        post.save()
        self.mcp.call_tool.return_value = mcp_result(
            [{"name": "CA-2026-00001", "status": "Approved", "client_comment": "", "decided_by": "fatima@alnoor.example"}]
        )
        content_sync.pull_approval_decisions()
        self.assertEqual(self.reload().status, "Approved")

    def test_customer_without_connection_is_skipped(self):
        other = "Gulf Star Logistics"
        create_customer(other)
        make_content_post("No ERP post", other, status="Client Review", publish_on=add_to_date(now_datetime(), days=2))
        self.mcp.call_tool.return_value = mcp_result({"status": "created", "name": "CA-2026-00002"})

        # only the connected customer's post goes out
        self.assertEqual(content_sync.push_posts_for_approval(), 1)


class TestDraftCaption(FrappeTestCase):
    @patch("helpdesk.api.content.call_haiku")
    def test_returns_caption_and_clean_hashtags(self, call_haiku):
        call_haiku.return_value = {
            "response": {"caption": "Lights, offers, joy.", "hashtags": ["Diwali", "#offers", "#diwali"]}
        }
        result = draft_caption(title="Diwali offer", channel="Instagram", brief="20% off")
        self.assertEqual(result["caption"], "Lights, offers, joy.")
        self.assertEqual(result["hashtags"], "#Diwali #offers")
        self.assertIn("20% off", call_haiku.call_args.args[1])

    @patch("helpdesk.api.content.call_haiku")
    def test_empty_ai_reply_is_an_error(self, call_haiku):
        call_haiku.return_value = {"response": {"raw_response": "oops", "parse_error": True}}
        with self.assertRaises(frappe.ValidationError):
            draft_caption(title="Diwali offer", channel="Instagram")

    def test_unknown_channel_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            draft_caption(title="x", channel="MySpace")

    def test_normalize_hashtags(self):
        self.assertEqual(normalize_hashtags("sale #Sale  new"), "#sale #new")
