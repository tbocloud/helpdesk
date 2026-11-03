import json
import random
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import whatsapp_outreach as wa
from helpdesk.api import leads as leads_api
from helpdesk.api import outreach as outreach_api
from helpdesk.api import whatsapp as api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    WHATSAPP_INBOX,
    FakeChatwootAPI,
    FakeCRM,
    create_agent,
    enable_chatwoot_bridge,
    enable_leads,
    enable_whatsapp_outreach,
    get_chat_conversation,
    hold_commits,
    make_whatsapp_payload,
    outbox,
    outreach_message,
    send_chatwoot_webhook,
    whatsapp_queue_row,
    whatsapp_template_row,
)

BDE = "wa.bde@leads.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
REQUEST = "helpdesk.chatwoot_bridge.requests.request"
CALL_AI = "helpdesk.chatwoot_bridge.call_haiku"
SEARCH = "GET /contacts/search?q=%2B919847012345"
STATE = {
    "to": "+919847012345",
    "conversation_id": None,
    "contact_id": None,
    "window_open": False,
    "blocked": None,
    "can_write": True,
}


class WhatsAppCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "BDE")
        enable_leads(teams=())
        enable_whatsapp_outreach()
        self.crm = FakeCRM()
        self.chat = FakeChatwootAPI()
        for target, replacement in (
            (FROM_SETTINGS, {"return_value": self.crm}),
            (REQUEST, {"new": self.chat}),
        ):
            patcher = patch(target, **replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def erp_calls(self, method):
        return [
            (post, params)
            for name, post, params in self.crm.lead_calls
            if name == method
        ]

    def queue(self, *rows):
        self.crm.lead_answers["get_whatsapp_queue"] = list(rows)
        self.crm.lead_answers["report_whatsapp"] = {"status": "Sent"}

    def report(self):
        return self.erp_calls("report_whatsapp")[0][1]


class TestWhatsAppPlan(WhatsAppCase):
    def facts(self, **fields):
        return {
            "first_name": "Palm",
            "company_name": "Palm Resort",
            "why_call": "You take bookings by phone only",
            "body": "Hello",
            "window_open": False,
            **fields,
        }

    def test_a_first_message_outside_24_hours_must_be_a_template_with_its_blanks_filled(
        self,
    ):
        plan = wa.plan(self.facts())
        self.assertEqual(plan["mode"], "template")
        self.assertEqual(plan["template"], "tbo_intro")
        self.assertEqual(
            plan["preview"],
            "Hi Palm, this is TBO. You take bookings by phone only. Can we talk?",
        )
        self.assertIn("approved message templates", plan["note"])

    def test_a_template_can_name_the_leads_product_and_its_intro(self):
        enable_whatsapp_outreach(
            templates=[
                whatsapp_template_row(
                    body="Hi {{1}}, this is {{2}}. {{3}}",
                    variables="name,product,product_intro",
                )
            ]
        )
        plan = wa.plan(
            self.facts(
                product="PhoebiX", product_intro="PhoebiX - solar ERP for installers"
            )
        )
        self.assertEqual(
            plan["preview"],
            "Hi Palm, this is PhoebiX. PhoebiX - solar ERP for installers",
        )
        # a lead with no product is from TBO as before
        plain = wa.plan(self.facts())
        self.assertTrue(plain["preview"].startswith("Hi Palm, this is TBO."))

    def test_the_lead_page_facts_carry_the_product(self):
        facts = wa.lead_facts(
            {
                "lead_name": "Palm Resort",
                "product": "PhoebiX",
                "product_intro": "Solar ERP",
            }
        )
        self.assertEqual(
            (facts["product"], facts["product_intro"]), ("PhoebiX", "Solar ERP")
        )

    def test_free_text_is_allowed_only_inside_24_hours(self):
        plan = wa.plan(self.facts(window_open=True))
        self.assertEqual((plan["mode"], plan["preview"]), ("text", "Hello"))

    def test_a_blank_with_nothing_to_fill_it_gets_a_neutral_word(self):
        plan = wa.plan(self.facts(first_name="", why_call=None))
        self.assertEqual(
            plan["preview"], "Hi there, this is TBO. your business. Can we talk?"
        )

    def test_without_a_template_it_falls_back_to_manual_and_says_why(self):
        enable_whatsapp_outreach(templates=[])
        plan = wa.plan(self.facts())
        self.assertEqual(plan["mode"], "manual")
        self.assertIn("Settings → TBO Chat", plan["note"])

    def test_without_an_inbox_it_is_manual_as_before(self):
        enable_chatwoot_bridge(whatsapp_inbox_id=0)
        self.assertEqual(wa.plan(self.facts())["mode"], "manual")
        self.assertFalse(wa.auto_send())

    def test_the_template_ticked_for_first_messages_wins(self):
        enable_whatsapp_outreach(
            templates=[
                whatsapp_template_row(
                    template_name="other",
                    is_default=0,
                    body="Hi {{1}}",
                    variables="name",
                ),
                whatsapp_template_row(template_name="chosen", body="Hello {{1}}"),
            ]
        )
        self.assertEqual(wa.plan(self.facts())["template"], "chosen")


class TestSendingTheQueue(WhatsAppCase):
    def test_a_first_message_goes_as_the_template_through_a_new_contact_and_conversation(
        self,
    ):
        self.queue(whatsapp_queue_row())
        self.assertEqual(wa.send_pending(), 1)
        self.assertEqual(
            self.erp_calls("get_whatsapp_queue")[0][1], {"country_code": "91"}
        )
        self.assertEqual(len(self.chat.calls_to("/contacts")), 1)
        contact = self.chat.calls_to("/contacts")[0]["body"]
        self.assertEqual(
            (contact["inbox_id"], contact["phone_number"]),
            (WHATSAPP_INBOX, "+919847012345"),
        )
        self.assertEqual(
            self.chat.calls_to("/conversations")[0]["body"]["inbox_id"], WHATSAPP_INBOX
        )
        message = self.chat.calls_to("/messages")[0]["body"]
        params = message["template_params"]
        self.assertEqual(params["name"], "tbo_intro")
        self.assertEqual(
            params["processed_params"],
            {"1": "Palm", "2": "You take bookings by phone only"},
        )
        self.assertIn("Hi Palm", message["content"])
        report = self.report()
        self.assertEqual((report["state"], report["template"]), ("sent", "tbo_intro"))
        self.assertTrue(report["message_id"] and report["conversation_id"])
        self.assertEqual(report["text"], message["content"])

    def test_inside_24_hours_the_text_goes_as_written_on_the_known_conversation(self):
        self.queue(
            whatsapp_queue_row(window_open=True, contact_id="5", conversation_id="88")
        )
        wa.send_pending()
        self.assertEqual(self.chat.calls_to("/contacts"), [])
        self.assertEqual(self.chat.calls_to("/conversations"), [])
        message = self.chat.calls_to("/conversations/88/messages")[0]["body"]
        self.assertEqual(
            message["content"], "Hi, we help resorts take bookings online."
        )
        self.assertNotIn("template_params", message)
        self.assertIsNone(self.report()["template"])

    def test_an_existing_contact_is_found_by_phone(self):
        self.chat.answers[SEARCH] = {
            "payload": [{"id": 31, "phone_number": "+919847012345"}]
        }
        self.queue(whatsapp_queue_row())
        wa.send_pending()
        self.assertEqual(self.chat.calls_to("/contacts"), [])
        self.assertEqual(
            self.chat.calls_to("/conversations")[0]["body"]["contact_id"], 31
        )

    def test_no_template_means_manual_not_failed(self):
        enable_whatsapp_outreach(templates=[])
        self.queue(whatsapp_queue_row())
        wa.send_pending()
        self.assertEqual(self.chat.calls_to("/messages"), [])
        self.assertEqual(self.report()["state"], "manual")

    def test_a_chatwoot_failure_is_reported_in_words(self):
        self.chat.answers["POST /contacts"] = None
        self.queue(whatsapp_queue_row())
        wa.send_pending()
        report = self.report()
        self.assertEqual(report["state"], "failed")
        self.assertIn("contact", report["error"])

    def test_one_failing_message_does_not_stop_the_rest(self):
        self.queue(
            whatsapp_queue_row("OUT-1", to="+919000000001"),
            whatsapp_queue_row("OUT-2", window_open=True, conversation_id="7"),
        )
        with patch.object(wa, "contact_for", side_effect=[RuntimeError("boom"), 5]):
            wa.send_pending()
        states = [params["state"] for _p, params in self.erp_calls("report_whatsapp")]
        self.assertEqual(states, ["failed", "sent"])

    def test_nothing_is_asked_without_an_inbox_or_with_automatic_sending_off(self):
        for values in ({"whatsapp_auto_send": 0}, {"whatsapp_inbox_id": 0}):
            enable_whatsapp_outreach(**values)
            self.assertEqual(wa.send_pending(), 0)
        self.assertEqual(self.erp_calls("get_whatsapp_queue"), [])

    def test_the_default_country_code_is_passed_to_the_erp(self):
        enable_whatsapp_outreach(whatsapp_country_code="+971")
        self.queue()
        wa.send_pending()
        self.assertEqual(
            self.erp_calls("get_whatsapp_queue")[0][1]["country_code"], "971"
        )

    def test_an_unreachable_erp_site_is_survived(self):
        self.crm.lead_answers["get_whatsapp_queue"] = CRMError("down")
        self.assertEqual(wa.send_pending(), 0)


class TestApproving(WhatsAppCase):
    def setUp(self):
        super().setUp()
        frappe.set_user(BDE)
        self.crm.lead_answers["approve_outreach"] = [{"name": "OUT-00001"}]
        self.crm.lead_answers["get_whatsapp_queue"] = []

    def test_with_an_inbox_approving_queues_it_for_chat_and_sends_soon(self):
        with patch.object(wa, "send_pending") as send:
            outreach_api.approve_outreach(["OUT-00001"])
        self.assertEqual(self.erp_calls("approve_outreach")[0][1]["send_whatsapp"], 1)
        send.assert_called_once()

    def test_without_an_inbox_it_stays_manual(self):
        enable_chatwoot_bridge(whatsapp_inbox_id=0)
        with patch.object(wa, "send_pending") as send:
            outreach_api.approve_outreach(["OUT-00001"])
        self.assertEqual(self.erp_calls("approve_outreach")[0][1]["send_whatsapp"], 0)
        send.assert_not_called()

    def test_the_outbox_says_how_each_whatsapp_row_will_go(self):
        row = outreach_message(
            channel="WhatsApp",
            subject=None,
            whatsapp={
                "first_name": "Palm",
                "company_name": "Palm Resort",
                "why_call": "You take bookings by phone only",
                "window_open": False,
                "via_chat": False,
                "chat_status": None,
                "template": None,
            },
        )
        self.crm.lead_answers["get_outbox"] = outbox([row, outreach_message("OUT-2")])
        result = outreach_api.get_outbox()
        plan = result["rows"][0]["whatsapp"]["plan"]
        self.assertEqual(plan["mode"], "template")
        self.assertIn("Hi Palm", plan["preview"])
        self.assertTrue(result["whatsapp"]["sends_by_itself"])
        self.assertNotIn("plan", result["rows"][1].get("whatsapp") or {})

    def test_without_an_inbox_the_outbox_keeps_open_whatsapp(self):
        enable_chatwoot_bridge(whatsapp_inbox_id=0)
        row = outreach_message(
            channel="WhatsApp",
            url="https://wa.me/919847012345?text=Hi",
            whatsapp={"window_open": False},
        )
        self.crm.lead_answers["get_outbox"] = outbox([row])
        result = outreach_api.get_outbox()
        self.assertEqual(result["rows"][0]["whatsapp"]["plan"]["mode"], "manual")
        self.assertFalse(result["whatsapp"]["connected"])
        self.assertTrue(result["rows"][0]["url"])


class TestIncoming(WhatsAppCase):
    def setUp(self):
        super().setUp()
        self.cid = random.randint(10**6, 10**8)
        self.mid = self.cid * 10

    def deliver(self, source="account", **overrides):
        overrides.setdefault("conversation_id", self.cid)
        overrides.setdefault("message_id", self.mid)
        return send_chatwoot_webhook(
            source, make_whatsapp_payload("message_created", **overrides)
        )

    def test_a_leads_reply_goes_to_the_erp_and_not_to_the_support_ai(self):
        self.crm.lead_answers["receive_whatsapp"] = {
            "matched": True,
            "lead": "CRM-LEAD-1",
        }
        with patch(CALL_AI) as ai:
            result = self.deliver(content="Yes, tell me more", name="Palm Owner")
        self.assertTrue(result.get("queued"))
        post, params = self.erp_calls("receive_whatsapp")[0]
        self.assertTrue(post)
        self.assertEqual(
            (params["phone"], params["text"], params["conversation_id"]),
            ("+919847012345", "Yes, tell me more", str(self.cid)),
        )
        ai.assert_not_called()
        self.assertIsNone(get_chat_conversation(self.cid), "no support chat is opened")

    def test_a_chat_from_someone_else_carries_on_as_support(self):
        self.crm.lead_answers["receive_whatsapp"] = {"matched": False}
        self.deliver(phone="+919000000000")
        self.assertTrue(get_chat_conversation(self.cid))

    def test_the_other_inboxes_are_not_asked_about(self):
        self.deliver(inbox_id=3, channel="Channel::WebWidget")
        self.assertEqual(self.erp_calls("receive_whatsapp"), [])

    def test_an_erp_failure_shows_as_a_failed_event_and_the_ai_stays_out(self):
        self.crm.lead_answers["receive_whatsapp"] = CRMError("down")
        with patch(CALL_AI) as ai:
            self.deliver()
        ai.assert_not_called()
        event = frappe.get_all(
            "HD Chatwoot Event",
            filters={"event_key": f"message:{self.mid}"},
            pluck="status",
        )
        self.assertEqual(event, ["Failed"])

    def test_an_unsigned_or_wrongly_signed_delivery_is_refused_before_anything_is_read(
        self,
    ):
        payload = make_whatsapp_payload(
            "message_created", conversation_id=self.cid, message_id=self.mid
        )
        for signature in (None, "sha256=bad"):
            with self.assertRaises(frappe.AuthenticationError):
                send_chatwoot_webhook("account", payload, signature=signature)
        self.assertEqual(self.erp_calls("receive_whatsapp"), [])
        self.assertFalse(
            frappe.db.exists("HD Chatwoot Event", {"event_key": f"message:{self.mid}"})
        )

    def test_a_replayed_delivery_is_handled_once(self):
        self.crm.lead_answers["receive_whatsapp"] = {"matched": True}
        self.deliver()
        self.assertTrue(self.deliver().get("duplicate"))
        self.assertEqual(len(self.erp_calls("receive_whatsapp")), 1)


class TestReceipts(WhatsAppCase):
    def receipt(self, status, **overrides):
        overrides.setdefault("message_id", 4242)
        return send_chatwoot_webhook(
            "account",
            make_whatsapp_payload("message_updated", status=status, **overrides),
        )

    def test_read_and_delivered_receipts_are_forwarded(self):
        self.crm.lead_answers["whatsapp_status"] = {"matched": True}
        for status in ("delivered", "read"):
            self.assertTrue(self.receipt(status).get("queued"))
        statuses = [p["status"] for _x, p in self.erp_calls("whatsapp_status")]
        self.assertEqual(statuses, ["delivered", "read"])
        self.assertEqual(self.erp_calls("whatsapp_status")[0][1]["message_id"], "4242")

    def test_a_failure_carries_the_reason(self):
        self.crm.lead_answers["whatsapp_status"] = {"matched": True}
        payload = make_whatsapp_payload(
            "message_updated", status="failed", message_id=77
        )
        payload["content_attributes"] = {"external_error": "Number is not on WhatsApp"}
        send_chatwoot_webhook("account", payload)
        self.assertEqual(
            self.erp_calls("whatsapp_status")[0][1]["error"],
            "Number is not on WhatsApp",
        )

    def test_updates_outside_the_whatsapp_inbox_are_ignored(self):
        result = self.receipt("read", inbox_id=3)
        self.assertIn("ignored", result)
        self.assertEqual(self.erp_calls("whatsapp_status"), [])

    def test_an_unsigned_receipt_is_refused(self):
        with self.assertRaises(frappe.AuthenticationError):
            send_chatwoot_webhook(
                "account",
                make_whatsapp_payload("message_updated", status="read"),
                signature=None,
            )
        self.assertEqual(self.erp_calls("whatsapp_status"), [])


class TestTemplatesAndSettings(WhatsAppCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")

    def test_approved_templates_are_read_from_the_inbox(self):
        self.chat.answers["GET /inboxes/9"] = {
            "message_templates": [
                {
                    "name": "tbo_intro",
                    "language": "en",
                    "status": "APPROVED",
                    "components": [
                        {"type": "BODY", "text": "Hi {{1}}, new text {{2}}"}
                    ],
                },
                {
                    "name": "tbo_offer",
                    "language": "en",
                    "status": "APPROVED",
                    "components": [{"type": "BODY", "text": "Offer for {{1}}"}],
                },
                {"name": "tbo_draft", "language": "en", "status": "PENDING"},
            ]
        }
        result = api.sync_templates()
        self.assertTrue(result["ok"])
        names = {t["template_name"]: t for t in result["templates"]}
        self.assertEqual(set(names), {"tbo_intro", "tbo_offer"})
        self.assertTrue(names["tbo_intro"]["is_default"], "what the owner set is kept")
        self.assertEqual(names["tbo_intro"]["body"], "Hi {{1}}, new text {{2}}")
        self.assertIn("1 new", result["message"])

    def test_a_template_no_longer_approved_is_put_out_of_use(self):
        self.chat.answers["GET /inboxes/9"] = {"message_templates": []}
        result = api.sync_templates()
        self.assertFalse(result["templates"][0]["enabled"])

    def test_the_sync_says_in_words_when_chat_does_not_answer(self):
        self.chat.answers["GET /inboxes/9"] = None
        result = api.sync_templates()
        self.assertFalse(result["ok"])
        self.assertIn("did not answer", result["message"])

    def test_settings_are_saved_and_the_country_code_is_cleaned(self):
        saved = api.save_settings(
            {
                "whatsapp_inbox_id": 12,
                "whatsapp_country_code": "+971",
                "whatsapp_auto_send": 0,
            },
            templates=json.dumps([whatsapp_template_row(template_name="mine")]),
        )
        self.assertEqual(saved["settings"]["whatsapp_country_code"], "971")
        self.assertEqual(saved["settings"]["whatsapp_inbox_id"], 12)
        self.assertEqual([t["template_name"] for t in saved["templates"]], ["mine"])
        self.assertTrue(saved["connected"])

    def test_the_country_code_must_be_digits(self):
        with self.assertRaises(frappe.ValidationError):
            api.save_settings({"whatsapp_country_code": "IN"})

    def test_only_a_system_manager_may_change_them(self):
        frappe.set_user(BDE)
        with self.assertRaises(frappe.PermissionError):
            api.save_settings({"whatsapp_inbox_id": 1})
        with self.assertRaises(frappe.PermissionError):
            api.sync_templates()


class TestLeadReplyBox(WhatsAppCase):
    LEAD = {
        "lead_name": "Palm Resort",
        "company_name": "Palm Resort",
        "prospect": {"why_call": "You take bookings by phone only"},
    }

    def setUp(self):
        super().setUp()
        frappe.set_user(BDE)
        self.crm.lead_answers["get_lead_whatsapp"] = dict(STATE)
        self.crm.lead_answers["get_lead"] = {"lead": dict(self.LEAD)}
        self.crm.lead_answers["log_lead_whatsapp"] = {"communication": "COMM-1"}

    def set_state(self, **fields):
        self.crm.lead_answers["get_lead_whatsapp"] = {**STATE, **fields}

    def test_inside_24_hours_the_persons_own_words_go_and_are_logged(self):
        self.set_state(window_open=True, conversation_id="55", contact_id="6")
        result = api.reply("CRM-LEAD-1", text="Thanks, call you at 4?")
        message = self.chat.calls_to("/conversations/55/messages")[0]["body"]
        self.assertEqual(message["content"], "Thanks, call you at 4?")
        self.assertNotIn("template_params", message)
        post, params = self.erp_calls("log_lead_whatsapp")[0]
        self.assertTrue(post)
        self.assertEqual(
            (params["lead"], params["text"], params["conversation_id"]),
            ("CRM-LEAD-1", "Thanks, call you at 4?", "55"),
        )
        self.assertIn("/conversations/55", result["chat_url"])

    def test_outside_24_hours_a_template_is_sent_instead_of_free_text(self):
        result = api.reply("CRM-LEAD-1", text="ignored free text")
        message = self.chat.calls_to("/messages")[0]["body"]
        self.assertEqual(message["template_params"]["name"], "tbo_intro")
        self.assertIn("Hi Palm", self.erp_calls("log_lead_whatsapp")[0][1]["text"])
        self.assertEqual(result["template"], "tbo_intro")

    def test_an_unsubscribed_lead_cannot_be_written_to(self):
        self.set_state(blocked="The lead unsubscribed.")
        with self.assertRaises(frappe.ValidationError):
            api.reply("CRM-LEAD-1", text="Hi")
        self.assertEqual(self.chat.calls_to("/messages"), [])

    def test_someone_who_cannot_write_to_the_lead_cannot_send(self):
        self.set_state(can_write=False)
        with self.assertRaises(frappe.PermissionError):
            api.reply("CRM-LEAD-1", text="Hi")

    def test_without_an_inbox_it_says_to_use_open_whatsapp(self):
        enable_chatwoot_bridge(whatsapp_inbox_id=0)
        with self.assertRaises(frappe.ValidationError) as caught:
            api.reply("CRM-LEAD-1", text="Hi")
        self.assertIn("Open WhatsApp", str(caught.exception))

    def test_nothing_is_logged_when_chat_refuses(self):
        self.set_state(window_open=True, conversation_id="55")
        self.chat.answers["POST /conversations/55/messages"] = None
        with self.assertRaises(frappe.ValidationError):
            api.reply("CRM-LEAD-1", text="Hi")
        self.assertEqual(self.erp_calls("log_lead_whatsapp"), [])

    def test_the_lead_page_carries_the_card_with_a_link_and_filled_templates(self):
        lead = {
            **self.LEAD,
            "whatsapp": {**STATE, "conversation_id": "55"},
        }
        self.crm.lead_answers["get_lead"] = {"lead": lead}
        box = leads_api.get_lead("CRM-LEAD-1")["lead"]["whatsapp_box"]
        self.assertTrue(box["chat_ready"])
        self.assertTrue(box["chat_url"].endswith("/app/accounts/1/conversations/55"))
        self.assertIn("Hi Palm", box["templates"][0]["preview"])
