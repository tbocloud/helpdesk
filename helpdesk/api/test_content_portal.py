# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api import content_portal
from helpdesk.test_utils import (
    add_contact_in_customer,
    create_customer,
    hold_commits,
    make_content_post,
    make_portal_contact,
    set_content_settings,
)

CUSTOMER = "Al Noor Trading LLC"
OTHER_CUSTOMER = "Gulf Star Logistics"
CLIENT_EMAIL = "fatima.rashid@alnoor-portal.example"
SHARED_EMAIL = "marketing@shared-portal.example"


class TestContentPortal(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        make_portal_contact(CUSTOMER, CLIENT_EMAIL)
        set_content_settings(enable_client_portal=1)
        frappe.cache.delete_value(content_portal.otp_key(CLIENT_EMAIL))

    def post(self, title, status="Client Review", customer=CUSTOMER, **kwargs):
        return make_content_post(
            title,
            customer,
            status=status,
            publish_on=add_to_date(now_datetime(), days=3),
            **kwargs,
        )

    def signed_in(self, email=CLIENT_EMAIL):
        session = {
            "email": email,
            "customers": content_portal.customers_for_email(email),
        }
        return patch.object(content_portal, "get_session", return_value=session)

    # ------------------------------------------------------------ identity --

    def test_email_reaches_every_customer_it_is_a_contact_of(self):
        make_portal_contact(OTHER_CUSTOMER, SHARED_EMAIL)
        contact = frappe.db.get_value("Contact", {"email_id": SHARED_EMAIL}, "name")
        add_contact_in_customer(frappe.get_doc("HD Customer", CUSTOMER), contact)

        self.assertEqual(
            content_portal.customers_for_email(SHARED_EMAIL.upper()),
            sorted([CUSTOMER, OTHER_CUSTOMER]),
        )
        self.assertEqual(content_portal.customers_for_email("nobody@x.example"), [])

    # ----------------------------------------------------------------- otp --

    def test_unknown_email_gets_the_same_answer_but_no_code(self):
        known = content_portal.request_code(CLIENT_EMAIL)
        unknown = content_portal.request_code("stranger@x.example")

        self.assertTrue(known["success"] and unknown["success"])
        self.assertTrue(frappe.cache.get_value(content_portal.otp_key(CLIENT_EMAIL)))
        self.assertFalse(
            frappe.cache.get_value(content_portal.otp_key("stranger@x.example"))
        )

    def test_resend_waits_for_cooldown(self):
        content_portal.request_code(CLIENT_EMAIL)
        again = content_portal.request_code(CLIENT_EMAIL)
        self.assertFalse(again["success"])

    def test_code_signs_in_once_and_locks_after_wrong_tries(self):
        content_portal.request_code(CLIENT_EMAIL)
        code = frappe.cache.get_value(content_portal.otp_key(CLIENT_EMAIL))["otp"]
        wrong = "000000" if code != "000000" else "111111"

        with patch.object(content_portal, "start_session") as start:
            self.assertFalse(content_portal.verify_code(CLIENT_EMAIL, wrong)["success"])
            self.assertTrue(content_portal.verify_code(CLIENT_EMAIL, code)["success"])
            start.assert_called_once_with(CLIENT_EMAIL, [CUSTOMER])
            # used up
            self.assertFalse(content_portal.verify_code(CLIENT_EMAIL, code)["success"])

        frappe.cache.delete_value(content_portal.otp_key(CLIENT_EMAIL))
        frappe.cache.set_value(
            content_portal.otp_key(CLIENT_EMAIL),
            {
                "otp": code,
                "sent_at": str(now_datetime()),
                "attempts": content_portal.OTP_MAX_ATTEMPTS,
            },
            expires_in_sec=60,
        )
        with patch.object(content_portal, "start_session") as start:
            self.assertFalse(content_portal.verify_code(CLIENT_EMAIL, code)["success"])
            start.assert_not_called()

    def test_portal_off_refuses_sign_in(self):
        set_content_settings(enable_client_portal=0)
        with self.assertRaises(frappe.PermissionError):
            content_portal.request_code(CLIENT_EMAIL)

    # ---------------------------------------------------------------- data --

    def test_client_sees_only_client_stage_posts_and_safe_fields(self):
        review = self.post("Eid offer", writer="Administrator")
        self.post("Internal draft", status="Drafting")
        self.post("Other client's post", customer=OTHER_CUSTOMER)

        posts = content_portal.get_portal_posts(CUSTOMER)

        self.assertEqual([p.name for p in posts], [review.name])
        self.assertNotIn("writer", posts[0])
        self.assertEqual(posts[0].images, [])

    # ------------------------------------------------------------- actions --

    def test_approve_records_the_decision(self):
        post = self.post("Eid offer")
        with self.signed_in():
            content_portal.approve(post.name)

        post.reload()
        self.assertEqual(post.status, "Approved")
        self.assertTrue(post.client_decided_on)
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {"reference_name": post.name, "content": ("like", f"%{CLIENT_EMAIL}%")},
            )
        )

    def test_request_changes_needs_notes_and_keeps_them(self):
        post = self.post("Eid offer")
        with self.signed_in():
            with self.assertRaises(frappe.ValidationError):
                content_portal.request_changes(post.name, "  ")
            content_portal.request_changes(post.name, "Use the green logo")

        post.reload()
        self.assertEqual(post.status, "Changes Requested")
        self.assertEqual(post.client_feedback, "Use the green logo")

    def test_approve_many_skips_decided_posts(self):
        waiting = self.post("Carousel 1")
        approved = self.post("Carousel 2", status="Approved")
        with self.signed_in():
            result = content_portal.approve_many([waiting.name, approved.name])

        self.assertEqual(result["approved"], [waiting.name])

    def test_cannot_touch_other_customers_or_internal_posts(self):
        other = self.post("Not yours", customer=OTHER_CUSTOMER)
        draft = self.post("Not ready", status="Drafting")
        with self.signed_in():
            for post in (other, draft):
                with self.assertRaises(frappe.DoesNotExistError):
                    content_portal.approve(post.name)
                with self.assertRaises(frappe.DoesNotExistError):
                    content_portal.add_comment(post.name, "hello")

    def test_decided_post_cannot_be_approved_again(self):
        post = self.post("Already live", status="Scheduled")
        with self.signed_in():
            with self.assertRaises(frappe.ValidationError):
                content_portal.approve(post.name)

    def test_signed_out_client_is_refused(self):
        post = self.post("Eid offer")
        with patch.object(content_portal, "get_session", return_value=None):
            with self.assertRaises(frappe.AuthenticationError):
                content_portal.approve(post.name)

    # -------------------------------------------------------------- agents --

    def test_share_needs_a_valid_email(self):
        self.assertEqual(content_portal.portal_emails(CUSTOMER), [CLIENT_EMAIL])
        with self.assertRaises(frappe.ValidationError):
            content_portal.send_portal_access(CUSTOMER, "not an email")

        result = content_portal.send_portal_access(CUSTOMER, CLIENT_EMAIL)
        self.assertTrue(result["success"])

    def test_sharing_to_a_new_email_makes_it_a_contact(self):
        new_email = "owner@alnoor-portal.example"
        content_portal.send_portal_access(CUSTOMER, new_email.upper())

        self.assertIn(new_email, content_portal.portal_emails(CUSTOMER))
        self.assertEqual(content_portal.customers_for_email(new_email), [CUSTOMER])
        self.assertTrue(frappe.cache.get_value(content_portal.otp_key(new_email)))
        # a second share reuses the contact instead of adding it again
        frappe.cache.delete_value(content_portal.otp_key(new_email))
        content_portal.send_portal_access(CUSTOMER, new_email)
        self.assertEqual(content_portal.portal_emails(CUSTOMER).count(new_email), 1)


class TestContentSettingsTemplates(FrappeTestCase):
    def setUp(self):
        hold_commits(self)

    def test_unknown_placeholder_is_refused(self):
        settings = frappe.get_single("HD Content Settings")
        settings.missed_post_subject = "Missed {campaign_name}"
        with self.assertRaises(frappe.ValidationError):
            settings.save()

    def test_render_falls_back_to_default_and_escapes_values(self):
        settings = frappe.get_single("HD Content Settings")
        settings.missed_post_subject = ""
        settings.missed_post_message = "<p>{title} {unknown}</p>"
        subject, message = settings.render(
            "missed_post", {"title": "<b>Sale</b>", "customer": "Al Noor"}
        )
        self.assertIn("Al Noor", subject)
        self.assertEqual(message, "<p>&lt;b&gt;Sale&lt;/b&gt; {unknown}</p>")
