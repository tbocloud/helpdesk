# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    send_due_reminders,
    send_missed_post_alerts,
)
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_content_campaign,
    make_content_post,
    make_project,
    make_tasky_user,
    set_content_settings,
)

CUSTOMER = "Al Noor Trading LLC"
OTHER_CUSTOMER = "Gulf Star Logistics"
WRITER = ("meera.nair@content-smoke.example", "Meera Nair")
TEAMMATE = ("rahul.varma@content-smoke.example", "Rahul Varma")
OUTSIDER = ("anita.joseph@content-smoke.example", "Anita Joseph")


class TestHDContentPost(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        make_tasky_user(*WRITER)

    def test_every_post_needs_a_date(self):
        # an undated post has no slot on the calendar, so nobody would see it
        for status in ("Idea", "Drafting"):
            with self.assertRaises(frappe.ValidationError):
                make_content_post(
                    "Ramadan greeting", CUSTOMER, status=status, publish_on=None
                )

        post = make_content_post("Ramadan greeting", CUSTOMER)
        post.publish_on = None
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

        # reminders go through HD Notification: the bell plus Teams or email
        notified = set(
            frappe.get_all(
                "HD Notification",
                filters={"user_to": WRITER[0], "reference_doctype": "HD Content Post"},
                pluck="reference_name",
            )
        )
        self.assertIn(due.name, notified)
        self.assertNotIn(ready.name, notified)
        self.assertNotIn(later.name, notified)


class TestMissedPostAlerts(FrappeTestCase):
    """Hourly email about posts whose publish time passed without being published or cancelled."""

    OPS = "content-ops@content-smoke.example"

    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)
        make_tasky_user(*WRITER)
        set_content_settings(
            enable_missed_post_alerts=1,
            grace_period_minutes=30,
            notify_post_team=1,
            alert_emails=self.OPS,
            missed_post_subject="",
            missed_post_message="",
        )
        # only the recipients each test sets up, not whatever the site has configured
        frappe.db.delete(
            "HD Content Alert Recipient", {"parent": "HD Content Settings"}
        )

    def alerts_for(self, post) -> list[str]:
        return frappe.get_all(
            "Email Queue",
            filters={
                "reference_doctype": "HD Content Post",
                "reference_name": post.name,
            },
            pluck="name",
        )

    def overdue_post(self, title, status="Drafting", **kwargs):
        return make_content_post(
            title,
            CUSTOMER,
            status=status,
            publish_on=add_to_date(now_datetime(), hours=-2),
            writer=WRITER[0],
            **kwargs,
        )

    def test_alerts_once_per_publish_time(self):
        post = self.overdue_post("Diwali carousel")

        send_missed_post_alerts()
        self.assertEqual(
            frappe.db.get_single_value("HD Content Settings", "last_alerts_sent"), 1
        )
        send_missed_post_alerts()

        self.assertEqual(len(self.alerts_for(post)), 1)
        recipients = frappe.get_all(
            "Email Queue Recipient",
            filters={"parent": self.alerts_for(post)[0]},
            pluck="recipient",
        )
        self.assertEqual(set(recipients), {self.OPS, WRITER[0]})

        # a new publish time is a new deadline
        post.reload()
        post.publish_on = add_to_date(now_datetime(), hours=-1)
        post.save()
        self.assertFalse(post.missed_alert_sent)
        send_missed_post_alerts()
        self.assertEqual(len(self.alerts_for(post)), 2)

    def test_skips_done_future_and_grace_period_posts(self):
        published = self.overdue_post(
            "Live reel", status="Published", published_url="https://instagram.com/p/x"
        )
        cancelled = self.overdue_post("Dropped story", status="Cancelled")
        future = make_content_post(
            "Next week",
            CUSTOMER,
            status="Drafting",
            publish_on=add_to_date(now_datetime(), days=2),
        )
        within_grace = make_content_post(
            "Just now",
            CUSTOMER,
            status="Drafting",
            publish_on=add_to_date(now_datetime(), minutes=-10),
        )

        send_missed_post_alerts()

        for post in (published, cancelled, future, within_grace):
            self.assertFalse(self.alerts_for(post), post.title)

    def test_no_recipients_leaves_post_for_later(self):
        set_content_settings(alert_emails="", notify_post_team=0)
        post = self.overdue_post("Nobody to tell")

        send_missed_post_alerts()

        self.assertFalse(self.alerts_for(post))
        self.assertFalse(
            frappe.db.get_value("HD Content Post", post.name, "missed_alert_sent")
        )

    def test_disabled_sends_nothing(self):
        set_content_settings(enable_missed_post_alerts=0)
        post = self.overdue_post("Alerts off")

        send_missed_post_alerts()

        self.assertFalse(self.alerts_for(post))

    def test_cancelled_post_needs_no_date(self):
        post = make_content_post(
            "Scrapped idea", CUSTOMER, status="Cancelled", publish_on=None
        )
        self.assertEqual(post.status, "Cancelled")
        self.assertFalse(post.publish_on)


class TestHDContentPostVisibility(FrappeTestCase):
    """Writers see their own posts and their clients' posts, not other clients'."""

    def setUp(self):
        hold_commits(self)
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
