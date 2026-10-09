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
    hold_commits,
    make_content_option,
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
        self.mcp.call_tool.return_value = mcp_result(
            {"status": "created", "name": "CA-2026-00001"}
        )

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
        self.mcp.call_tool.return_value = mcp_result(
            {"status": "created", "name": "CA-2026-00001"}
        )
        content_sync.push_posts_for_approval()

        post = self.reload()
        post.db_set(
            "sent_for_approval_on",
            add_to_date(now_datetime(), minutes=-10),
            update_modified=False,
        )
        post.caption = "Updated caption"
        post.save()

        self.assertEqual(content_sync.push_posts_for_approval(), 1)
        tool, args = self.mcp.call_tool.call_args.args
        self.assertEqual(tool, "set_values")
        self.assertEqual(args["name"], "CA-2026-00001")
        self.assertEqual(args["values"]["status"], "Pending")

    def test_client_decisions_update_the_post(self):
        self.post.db_set(
            {
                "client_approval_ref": "CA-2026-00001",
                "client_connection": self.connection,
            }
        )

        self.mcp.call_tool.return_value = mcp_result(
            [
                {
                    "name": "CA-2026-00001",
                    "status": "Changes Requested",
                    "client_comment": "Use the new logo",
                    "decided_by": "fatima@alnoor.example",
                }
            ]
        )
        self.assertEqual(content_sync.pull_approval_decisions(), 1)
        post = self.reload()
        self.assertEqual(post.status, "Changes Requested")
        self.assertEqual(post.client_feedback, "Use the new logo")

        post.status = "Client Review"
        post.save()
        self.mcp.call_tool.return_value = mcp_result(
            [
                {
                    "name": "CA-2026-00001",
                    "status": "Approved",
                    "client_comment": "",
                    "decided_by": "fatima@alnoor.example",
                }
            ]
        )
        content_sync.pull_approval_decisions()
        # the client's yes goes to the Digital Marketing Head first
        self.assertEqual(self.reload().status, "Head Review")

    def test_images_go_with_the_approval_once(self):
        frappe.get_doc(
            {
                "doctype": "File",
                "file_name": "carousel-1.png",
                "attached_to_doctype": "HD Content Post",
                "attached_to_name": self.post.name,
                "content": b"fake-png-bytes",
                "is_private": 1,
            }
        ).insert(ignore_permissions=True)

        client_files = []

        def call_tool(tool, args):
            if tool == "get_list":
                return mcp_result(client_files)
            if args["doctype"] == "File":
                client_files.append({"file_name": args["values"]["file_name"]})
                return mcp_result({"status": "created", "name": "file-1"})
            return mcp_result({"status": "created", "name": "CA-2026-00001"})

        self.mcp.call_tool.side_effect = call_tool
        content_sync.push_posts_for_approval()

        uploads = [
            c.args[1]
            for c in self.mcp.call_tool.call_args_list
            if c.args[1].get("doctype") == "File" and c.args[0] == "create_doc"
        ]
        self.assertEqual(len(uploads), 1)
        values = uploads[0]["values"]
        self.assertEqual(values["attached_to_name"], "CA-2026-00001")
        self.assertEqual(values["attached_to_doctype"], "Content Approval")
        self.assertEqual(values["decode"], 1)

        # already on the client: a re-send doesn't upload it again
        content_sync.send_images(self.mcp, self.post.name, "CA-2026-00001")
        uploads = [
            c
            for c in self.mcp.call_tool.call_args_list
            if c.args[0] == "create_doc" and c.args[1].get("doctype") == "File"
        ]
        self.assertEqual(len(uploads), 1)

    def test_customer_without_connection_is_skipped(self):
        other = "Gulf Star Logistics"
        create_customer(other)
        make_content_post(
            "No ERP post",
            other,
            status="Client Review",
            publish_on=add_to_date(now_datetime(), days=2),
        )
        self.mcp.call_tool.return_value = mcp_result(
            {"status": "created", "name": "CA-2026-00002"}
        )

        # only the connected customer's post goes out
        self.assertEqual(content_sync.push_posts_for_approval(), 1)


class TestDraftCaption(FrappeTestCase):
    @patch("helpdesk.api.content.call_haiku")
    def test_returns_caption_and_clean_hashtags(self, call_haiku):
        call_haiku.return_value = {
            "response": {
                "caption": "Lights, offers, joy.",
                "hashtags": ["Diwali", "#offers", "#diwali"],
            }
        }
        result = draft_caption(
            title="Diwali offer", channel="Instagram", brief="20% off"
        )
        self.assertEqual(result["caption"], "Lights, offers, joy.")
        self.assertEqual(result["hashtags"], "#Diwali #offers")
        self.assertIn("20% off", call_haiku.call_args.args[1])

    @patch("helpdesk.api.content.call_haiku")
    def test_empty_ai_reply_is_an_error(self, call_haiku):
        call_haiku.return_value = {
            "response": {"raw_response": "oops", "parse_error": True}
        }
        with self.assertRaises(frappe.ValidationError):
            draft_caption(title="Diwali offer", channel="Instagram")

    @patch("helpdesk.api.content.call_haiku")
    def test_brief_alone_is_enough(self, call_haiku):
        call_haiku.return_value = {
            "response": {"caption": "Big savings this week.", "hashtags": []}
        }
        result = draft_caption(
            title="", channel="Facebook", brief="20% off all laptops until Friday"
        )
        self.assertEqual(result["caption"], "Big savings this week.")
        self.assertIn("20% off all laptops", call_haiku.call_args.args[1])

    @patch("helpdesk.api.content.call_haiku")
    def test_channel_and_format_guidance_reach_the_model(self, call_haiku):
        call_haiku.return_value = {
            "response": {"caption": "Swipe for 5 GST mistakes.", "hashtags": []}
        }
        draft_caption(
            title="GST mistakes", channel="LinkedIn", format="Carousel", brief="5 tips"
        )
        system_prompt, prompt = call_haiku.call_args.args[:2]
        self.assertIn("No links in the body", prompt)
        self.assertIn("swipe", prompt)
        self.assertIn("Avoid stock phrases", system_prompt)

        # a format without its own guidance adds nothing
        draft_caption(title="GST mistakes", channel="Instagram", format="Post")
        self.assertNotIn("Format:", call_haiku.call_args.args[1])

    def test_nothing_to_write_about_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            draft_caption(title=" ", channel="Instagram")

    @patch("helpdesk.api.content.call_haiku")
    def test_team_added_platform_and_campaign_reach_the_model(self, call_haiku):
        hold_commits(self)
        make_content_option("HD Content Platform", "Threads")
        call_haiku.return_value = {
            "response": {"caption": "New drop, link in bio.", "hashtags": []}
        }
        draft_caption(title="Eid sale", channel="Threads", campaign="Eid 2026")
        prompt = call_haiku.call_args.args[1]
        self.assertIn("Channel: Threads", prompt)
        self.assertNotIn("Guidelines:", prompt)
        self.assertIn("Campaign: Eid 2026", prompt)

    def test_unknown_channel_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            draft_caption(title="x", channel="MySpace")

    def test_normalize_hashtags(self):
        self.assertEqual(normalize_hashtags("sale #Sale  new"), "#sale #new")
