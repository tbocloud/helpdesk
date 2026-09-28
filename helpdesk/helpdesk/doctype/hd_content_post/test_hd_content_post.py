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
    make_project,
    make_tasky_user,
)

CUSTOMER = "Al Noor Trading LLC"
OTHER_CUSTOMER = "Gulf Star Logistics"
WRITER = ("meera.nair@content-smoke.example", "Meera Nair")
TEAMMATE = ("rahul.varma@content-smoke.example", "Rahul Varma")
OUTSIDER = ("anita.joseph@content-smoke.example", "Anita Joseph")


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

        # a failed save still bumps the in-memory timestamp
        post.reload()
        post.status = "Drafting"
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

        post.reload()
        post.status = "Published"
        post.published_url = "https://instagram.com/p/launch-reel"
        post.save()
        self.assertTrue(post.published_on)

        post.status = "Scheduled"
        post.save()
        self.assertFalse(post.published_on)

    def test_reminder_only_for_unready_posts_due_soon(self):
        soon = add_to_date(now_datetime(), hours=24)
        due = make_content_post(
            "Offer carousel",
            CUSTOMER,
            status="Drafting",
            publish_on=soon,
            writer=WRITER[0],
        )
        ready = make_content_post(
            "Approved story",
            CUSTOMER,
            status="Approved",
            publish_on=soon,
            writer=WRITER[0],
        )
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


class TestHDContentPostVisibility(FrappeTestCase):
    """Writers see their own posts and their clients' posts, not other clients'."""

    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        for user in (WRITER, TEAMMATE, OUTSIDER):
            make_tasky_user(*user)
        project = make_project(
            f"{CUSTOMER} - Social", members=[(TEAMMATE[0], "Developer")]
        )
        project.db_set("customer", CUSTOMER)

        self.own = make_content_post("Meera's reel", OTHER_CUSTOMER, writer=WRITER[0])
        self.client_post = make_content_post("Al Noor story", CUSTOMER)

    def visible_to(self, user):
        frappe.set_user(user[0])
        try:
            return set(frappe.get_list("HD Content Post", pluck="name"))
        finally:
            frappe.set_user("Administrator")

    def test_writer_sees_own_posts(self):
        visible = self.visible_to(WRITER)
        self.assertIn(self.own.name, visible)
        self.assertNotIn(self.client_post.name, visible)

    def test_project_member_sees_that_clients_posts(self):
        visible = self.visible_to(TEAMMATE)
        self.assertIn(self.client_post.name, visible)
        self.assertNotIn(self.own.name, visible)

    def test_outsider_sees_nothing_and_cannot_open(self):
        self.assertEqual(self.visible_to(OUTSIDER), set())
        self.assertFalse(
            frappe.has_permission(
                "HD Content Post", "read", self.client_post, user=OUTSIDER[0]
            )
        )

    def test_project_manager_sees_everything(self):
        frappe.get_doc("User", OUTSIDER[0]).add_roles("Project Manager")
        self.assertTrue(
            {self.own.name, self.client_post.name} <= self.visible_to(OUTSIDER)
        )
