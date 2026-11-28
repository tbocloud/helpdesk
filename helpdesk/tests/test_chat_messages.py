import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import get_datetime

from helpdesk import chat_messages, chatwoot_bridge
from helpdesk.test_utils import (
    CHATWOOT_TEST_URL,
    create_user,
    enable_chatwoot_bridge,
    make_chat_conversation,
    make_chatwoot_payload,
    make_ticket,
    send_chatwoot_webhook,
)
from helpdesk.tests.test_chatwoot_bridge import ChatwootCase

MESSAGE = "HD Chat Message"
DOWNLOAD = "helpdesk.chat_messages.requests.get"


def kept(message_id):
    return frappe.get_doc(MESSAGE, {"chatwoot_message_id": message_id})


def epoch(moment: datetime) -> int:
    return int(moment.replace(tzinfo=timezone.utc).timestamp())


class FakeDownload:
    """Stands in for requests.get(stream=True) as a context manager."""

    def __init__(self, data: bytes = b"\x89PNG fake", length: int | None = None):
        self.data = data
        self.length = length
        self.urls = []

    def __call__(self, url, stream=True, timeout=None):
        self.urls.append(url)
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.headers = {
            "Content-Length": str(
                len(self.data) if self.length is None else self.length
            )
        }
        response.iter_content.return_value = [self.data]
        response.raise_for_status.return_value = None
        return response


class MessagesCase(ChatwootCase):
    def setUp(self):
        super().setUp()
        enable_chatwoot_bridge(messages_section=1, max_file_mb=1)

    def send(self, source="account", **overrides):
        overrides.setdefault("conversation_id", self.cid)
        overrides.setdefault("message_id", self.mid)
        payload = make_chatwoot_payload("message_created", **overrides)
        for key in ("created_at", "content_attributes", "status"):
            if f"msg_{key}" in overrides:
                payload[key] = overrides[f"msg_{key}"]
        return send_chatwoot_webhook(source, payload)

    def receipt(self, status, message_id=None, error=None):
        payload = make_chatwoot_payload(
            "message_updated",
            conversation_id=self.cid,
            message_id=message_id or self.mid,
            message_type="outgoing",
            sender_type="user",
        )
        payload["status"] = status
        if error:
            payload["content_attributes"] = {"external_error": error}
        return send_chatwoot_webhook("account", payload)


class TestOffByDefault(ChatwootCase):
    def test_without_the_switch_nothing_is_kept_and_agents_messages_are_ignored(self):
        answer = self.message(message_type="outgoing", sender_type="user")
        self.assertIn("ignored", answer)
        self.assertFalse(frappe.db.exists(MESSAGE, {"chatwoot_message_id": self.mid}))


class TestKeepingMessages(MessagesCase):
    def test_a_customers_whatsapp_message_is_kept_and_opens_the_window(self):
        with patch(chatwoot_bridge.__name__ + ".is_ai_configured", return_value=False):
            self.send(content="Hi, do you do ERPNext?", channel="Channel::Whatsapp")
        message = kept(self.mid)
        self.assertEqual(
            (message.direction, message.sender_type, message.kind, message.content),
            ("In", "Customer", "Text", "Hi, do you do ERPNext?"),
        )
        row = self.row()
        self.assertEqual(message.conversation, row.name)
        self.assertEqual((row.waiting_on, row.unread), ("Us", 1))
        self.assertEqual(row.last_message, "Hi, do you do ERPNext?")
        self.assertEqual(
            get_datetime(row.window_closes_at),
            get_datetime(message.sent_at) + timedelta(hours=24),
        )

    def test_the_website_chat_has_no_reply_window(self):
        with patch(chatwoot_bridge.__name__ + ".is_ai_configured", return_value=False):
            self.send(channel="Channel::WebWidget")
        self.assertIsNone(self.row().window_closes_at)

    def test_a_reply_typed_in_chatwoot_is_kept_as_the_staff_member_who_typed_it(self):
        user = create_user(f"agent-{self.cid}@example.com")
        payload = make_chatwoot_payload(
            "message_created",
            conversation_id=self.cid,
            message_id=self.mid,
            message_type="outgoing",
            sender_type="user",
            content="Yes, we do.",
        )
        payload["sender"]["email"] = user.name
        send_chatwoot_webhook("account", payload)
        message = kept(self.mid)
        self.assertEqual(
            (message.direction, message.sender_type, message.author),
            ("Out", "Staff", user.name),
        )
        self.assertEqual(self.row().waiting_on, "Customer")
        # an agent's message never renames the contact
        self.assertEqual(self.row().contact_name, "Anita Rao")

    def test_the_ais_reply_and_private_notes(self):
        self.send(message_type="outgoing", sender_type="agent_bot", content="Hello!")
        self.send(
            message_id=self.mid + 1,
            message_type="outgoing",
            sender_type="user",
            private=True,
            content="VIP customer",
        )
        self.assertEqual(kept(self.mid).sender_type, "AI")
        note = kept(self.mid + 1)
        self.assertEqual(note.kind, "Note")
        # a note is for staff: it is not the conversation's last message
        self.assertEqual(self.row().last_message, "Hello!")

    def test_both_webhooks_delivering_the_same_message_keep_one_row(self):
        self.send(source="bot", message_type="outgoing", sender_type="agent_bot")
        self.send(source="account", message_type="outgoing", sender_type="agent_bot")
        self.assertEqual(frappe.db.count(MESSAGE, {"chatwoot_message_id": self.mid}), 1)

    def test_an_older_message_arriving_late_does_not_change_the_last_message(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.send(
            message_type="outgoing",
            sender_type="agent_bot",
            content="newer",
            msg_created_at=epoch(now),
        )
        self.send(
            message_id=self.mid + 1,
            message_type="outgoing",
            sender_type="agent_bot",
            content="older",
            msg_created_at=epoch(now - timedelta(minutes=5)),
        )
        self.assertEqual(self.row().last_message, "newer")
        self.assertEqual(
            get_datetime(kept(self.mid + 1).sent_at) + timedelta(minutes=5),
            get_datetime(kept(self.mid).sent_at),
        )


class TestDelivery(MessagesCase):
    def setUp(self):
        super().setUp()
        self.send(message_type="outgoing", sender_type="user", content="Our offer")

    def test_delivery_moves_forward_only(self):
        self.receipt("delivered")
        self.receipt("read")
        self.receipt("delivered")
        self.assertEqual(kept(self.mid).status, "Read")

    def test_a_failed_message_says_why(self):
        self.receipt("failed", error="Re-engagement message: more than 24 hours passed")
        message = kept(self.mid)
        self.assertEqual(message.status, "Failed")
        self.assertIn("24 hours", message.error)


class TestRepliesFromTBOSupport(MessagesCase):
    def test_a_ticket_reply_keeps_the_person_who_sent_it(self):
        user = create_user(f"agent-{self.cid}@example.com")
        ticket = make_ticket(subject="Chat ticket")
        make_chat_conversation(self.cid, hd_ticket=ticket.name, status="Open")
        conversation = chatwoot_bridge.ChatConversation.for_ticket(ticket.name)
        self.assertTrue(
            conversation.post_agent_reply("<p>We will call you.</p>", author=user.name)
        )
        # the fake Chatwoot answers each POST with id 900000 + the number of calls so far
        posted_id = 900000 + len(self.api.calls)
        message = kept(posted_id)
        self.assertEqual((message.sender_type, message.author), ("Staff", user.name))
        self.assertEqual(message.hd_ticket, ticket.name)
        # Chatwoot's echo of the same message (as the bridge's user) keeps the person and fills the text
        payload = make_chatwoot_payload(
            "message_created",
            conversation_id=self.cid,
            message_id=posted_id,
            message_type="outgoing",
            sender_type="user",
            content="We will call you.",
        )
        send_chatwoot_webhook("account", payload)
        message.reload()
        self.assertEqual(
            (message.author, message.content), (user.name, "We will call you.")
        )

    def test_copilots_stage_lines_are_the_systems(self):
        ticket = make_ticket(subject="Chat ticket")
        make_chat_conversation(self.cid, hd_ticket=ticket.name, status="Open")
        conversation = chatwoot_bridge.ChatConversation.for_ticket(ticket.name)
        conversation.post_agent_reply("Working on it", sender_type="System")
        self.assertEqual(kept(900000 + len(self.api.calls)).sender_type, "System")


class TestFiles(MessagesCase):
    def picture(self, url=None, file_type="image"):
        return {
            "id": 1,
            "file_type": file_type,
            "data_url": url
            or f"{CHATWOOT_TEST_URL}/rails/active_storage/blobs/redirect/x/receipt.png",
        }

    def test_a_picture_is_copied_privately(self):
        download = FakeDownload()
        with patch(DOWNLOAD, download), patch(
            chatwoot_bridge.__name__ + ".is_ai_configured", return_value=False
        ):
            self.send(content="", attachments=[self.picture()])
        row = kept(self.mid).files[0]
        self.assertEqual(row.file_type, "Image")
        self.assertTrue(row.file)
        self.assertEqual(row.file_name, "receipt.png")
        saved = frappe.get_doc("File", {"file_url": row.file})
        path = saved.get_full_path()
        # the copy on disk outlives the rolled-back test: remove it
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.assertEqual(saved.is_private, 1)
        self.assertEqual(self.row().last_message, "[Image]")

    def test_a_file_over_the_limit_keeps_only_a_note(self):
        with patch(DOWNLOAD, FakeDownload(length=5 * 1024 * 1024)), patch(
            chatwoot_bridge.__name__ + ".is_ai_configured", return_value=False
        ):
            self.send(attachments=[self.picture()])
        row = kept(self.mid).files[0]
        self.assertFalse(row.file)
        self.assertIn("bigger than 1 MB", row.note)

    def test_a_file_from_elsewhere_is_never_fetched(self):
        download = FakeDownload()
        with patch(DOWNLOAD, download), patch(
            chatwoot_bridge.__name__ + ".is_ai_configured", return_value=False
        ):
            self.send(
                attachments=[
                    self.picture(url="http://169.254.169.254/latest/meta-data")
                ]
            )
        self.assertEqual(download.urls, [])
        self.assertIn("isn't served by TBO Chat", kept(self.mid).files[0].note)

    def test_a_story_mention_keeps_no_media(self):
        download = FakeDownload()
        with patch(DOWNLOAD, download), patch(
            chatwoot_bridge.__name__ + ".is_ai_configured", return_value=False
        ):
            self.send(
                channel="Channel::Instagram",
                attachments=[self.picture(file_type="story_mention")],
            )
        row = kept(self.mid).files[0]
        self.assertEqual((row.file_type, row.source_url or ""), ("Story", ""))
        self.assertFalse(row.file)
        self.assertEqual(download.urls, [])


class TestReading(MessagesCase):
    def test_created_at_in_both_forms(self):
        moment = datetime(2026, 11, 28, 6, 30, tzinfo=timezone.utc)
        from_epoch = chat_messages.sent_at({"created_at": int(moment.timestamp())})
        from_iso = chat_messages.sent_at({"created_at": "2026-11-28T06:30:00.000Z"})
        self.assertEqual(from_epoch, from_iso)
        self.assertIsNone(from_epoch.tzinfo)
