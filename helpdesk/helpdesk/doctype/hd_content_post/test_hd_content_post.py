# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import send_due_reminders
from helpdesk.test_utils import (
    create_customer,
    make_content_campaign,
    make_content_post,
    make_tasky_user,
)

CUSTOMER = "Al Noor Trading LLC"
OTHER_CUSTOMER = "Gulf Star Logistics"
WRITER = ("meera.nair@content-smoke.example", "Meera Nair")


class TestHDContentPost(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        make_tasky_user(*WRITER)

    def test_idea_needs_no_date_but_later_stages_do(self):
        post = make_content_post("Ramadan greeting", CUSTOMER)
        self.assertFalse(post.publish_on)

        post.status = "Drafting"
        with self.assertRaises(frappe.ValidationError):
            post.save()

        post.publish_on = add_to_date(now_datetime(), days=3)
        post.save()
        self.assertEqual(post.status, "Drafting")

    def test_customer_comes_from_campaign_and_must_match(self):
        campaign = make_content_campaign("Summer Sale", CUSTOMER)
        post = make_content_post("Summer sale teaser", campaign=campaign.name)
        self.assertEqual(post.customer, CUSTOMER)

        with self.assertRaises(frappe.ValidationError):
            make_content_post("Wrong client", OTHER_CUSTOMER, campaign=campaign.name)

    def test_publishing_needs_url_and_stamps_time(self):
        post = make_content_post(
            "Launch reel", CUSTOMER, status="Approved", publish_on=now_datetime()
        )
        post.status = "Published"
        with self.assertRaises(frappe.ValidationError):
            post.save()

        post.published_url = "https://instagram.com/p/launch-reel"
        post.save()
        self.assertTrue(post.published_on)

        post.status = "Scheduled"
        post.save()
        self.assertFalse(post.published_on)

    def test_reminder_only_for_unready_posts_due_soon(self):
        soon = add_to_date(now_datetime(), hours=24)
        due = make_content_post("Offer carousel", CUSTOMER, status="Drafting", publish_on=soon, writer=WRITER[0])
        ready = make_content_post("Approved story", CUSTOMER, status="Approved", publish_on=soon, writer=WRITER[0])
        later = make_content_post(
            "Next week blog",
            CUSTOMER,
            status="Drafting",
            publish_on=add_to_date(now_datetime(), days=5),
            writer=WRITER[0],
        )

        send_due_reminders()

        notified = set(
            frappe.get_all(
                "Notification Log",
                filters={"for_user": WRITER[0], "document_type": "HD Content Post"},
                pluck="document_name",
            )
        )
        self.assertIn(due.name, notified)
        self.assertNotIn(ready.name, notified)
        self.assertNotIn(later.name, notified)
