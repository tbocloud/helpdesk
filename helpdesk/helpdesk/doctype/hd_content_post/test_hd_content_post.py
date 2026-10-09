# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api import content_board
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    send_due_reminders,
    send_missed_post_alerts,
)
from helpdesk.patches.v16_0_2 import content_campaign_as_text
from helpdesk.test_utils import (
    attach_file,
    create_customer,
    get_reminder_messages,
    hold_commits,
    make_content_campaign,
    make_content_post,
    make_content_user,
    make_dm_head,
    make_project,
    make_tasky_user,
    run_as_user,
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

    def test_campaign_is_free_text(self):
        post = make_content_post(
            "Summer sale teaser", CUSTOMER, campaign="Summer Sale 2026"
        )
        self.assertEqual(post.campaign, "Summer Sale 2026")
        self.assertEqual(post.customer, CUSTOMER)

    def test_old_campaign_ids_become_their_names(self):
        campaign = make_content_campaign("Summer Sale", CUSTOMER)
        post = make_content_post("Summer sale teaser", CUSTOMER)
        # a post saved while campaign was still a link holds the campaign's ID
        frappe.db.set_value("HD Content Post", post.name, "campaign", campaign.name)

        content_campaign_as_text.execute()

        self.assertEqual(
            frappe.db.get_value("HD Content Post", post.name, "campaign"),
            "Summer Sale",
        )

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


HEAD = ("dm.head@content-smoke.example", "Shabna Rahim")
COORDINATOR = ("dm.coordinator@content-smoke.example", "Riya Thomas")
EMPLOYEE = ("dm.employee@content-smoke.example", "Arun Babu")
MARKETER = ("marketer@content-smoke.example", "Ajmal Kp")


class TestHeadApproval(FrappeTestCase):
    """After the client approves, the Digital Marketing Head approves before a post goes out."""

    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        make_tasky_user(*WRITER)
        make_tasky_user(*MARKETER)
        # the head also edits entries here, so the status select is theirs to use too
        make_dm_head(*HEAD, "DM Coordinator")
        make_content_user(*COORDINATOR, "DM Coordinator")
        self.post = make_content_post(
            "Onam offer",
            CUSTOMER,
            status="Client Review",
            writer=WRITER[0],
            marketer=MARKETER[0],
        )

    def set_status(self, status, user=COORDINATOR, **values):
        def run():
            doc = frappe.get_doc("HD Content Post", self.post.name)
            doc.update({"status": status, **values})
            doc.save()
            return doc

        return run_as_user(user[0], run)

    def notified(self, user):
        return get_reminder_messages(user[0], self.post.name)

    def head_review(self):
        frappe.set_user("Guest")
        try:
            frappe.get_doc("HD Content Post", self.post.name).approve_from_portal(
                "client@alnoor.example"
            )
        finally:
            frappe.set_user("Administrator")

    def test_the_clients_yes_goes_to_the_head(self):
        self.head_review()

        self.post.reload()
        self.assertEqual(self.post.status, "Head Review")
        self.assertTrue(self.post.client_decided_on)
        self.assertTrue(
            any("needs your approval" in m for m in self.notified(HEAD)),
        )
        # the marketer's turn comes after the head
        self.assertEqual(self.notified(MARKETER), [])

    def test_staff_recording_the_clients_yes_still_goes_to_the_head(self):
        self.assertEqual(self.set_status("Approved").status, "Head Review")

    def test_a_post_with_the_client_cannot_be_scheduled_or_published(self):
        for status, extra in (
            ("Scheduled", {}),
            ("Published", {"published_url": "https://instagram.com/p/onam"}),
        ):
            with self.assertRaises(frappe.ValidationError, msg=status):
                self.set_status(status, **extra)

    def test_changes_requested_cannot_skip_the_client_and_the_head(self):
        self.head_review()
        run_as_user(
            HEAD[0],
            lambda: content_board.head_send_back(self.post.name, "Use the new logo"),
        )

        for user in (COORDINATOR, HEAD):
            with self.assertRaises(frappe.ValidationError, msg=user[0]):
                self.set_status("Approved", user=user)
        # back to the client, then the head, as the first time
        self.set_status("Client Review")
        self.assertEqual(self.set_status("Approved").status, "Head Review")

    def test_with_no_head_yet_the_system_managers_hear(self):
        frappe.db.set_value("User", HEAD[0], "enabled", 0)
        manager = make_tasky_user(
            "sysmgr@content-smoke.example", "Rahul Sys", roles=("System Manager",)
        )

        self.head_review()

        self.assertTrue(
            any(
                "needs your approval" in m
                for m in get_reminder_messages(manager, self.post.name)
            )
        )

    def test_only_the_head_moves_it_on(self):
        self.head_review()

        for status, extra in (
            ("Approved", {}),
            ("Scheduled", {}),
            ("Published", {"published_url": "https://instagram.com/p/onam"}),
            ("Internal Review", {}),
        ):
            with self.assertRaises(frappe.ValidationError, msg=status):
                self.set_status(status, **extra)
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                COORDINATOR[0], lambda: content_board.head_approve(self.post.name)
            )

        # cancelling stays open to the team
        self.assertEqual(self.set_status("Cancelled").status, "Cancelled")

    def test_head_approves_and_the_marketer_hears(self):
        self.head_review()

        run_as_user(HEAD[0], lambda: content_board.head_approve(self.post.name))

        self.post.reload()
        self.assertEqual(self.post.status, "Approved")
        self.assertEqual(self.post.head_decided_by, HEAD[0])
        self.assertTrue(self.post.head_decided_on)
        self.assertTrue(any("your turn" in m for m in self.notified(MARKETER)))

    def test_head_sends_back_with_a_reason(self):
        self.head_review()
        decided = frappe.db.get_value(
            "HD Content Post", self.post.name, "client_decided_on"
        )

        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                HEAD[0], lambda: content_board.head_send_back(self.post.name, " ")
            )
        # the status select alone can't send it back without a reason
        with self.assertRaises(frappe.ValidationError):
            self.set_status("Changes Requested", user=HEAD)
        run_as_user(
            HEAD[0],
            lambda: content_board.head_send_back(self.post.name, "Use the new logo"),
        )

        self.post.reload()
        self.assertEqual(self.post.status, "Changes Requested")
        self.assertEqual(self.post.head_feedback, "Use the new logo")
        self.assertEqual(self.post.head_decided_by, HEAD[0])
        # the client's decision time is theirs; the head's is kept apart
        self.assertEqual(self.post.client_decided_on, decided)
        self.assertTrue(any("your turn" in m for m in self.notified(WRITER)))

    def test_a_new_client_round_clears_the_heads_last_decision(self):
        self.head_review()
        run_as_user(
            HEAD[0],
            lambda: content_board.head_send_back(self.post.name, "Use the new logo"),
        )

        doc = self.set_status("Client Review")

        self.assertEqual(
            (doc.head_decided_by, doc.head_decided_on, doc.head_feedback),
            (None, None, None),
        )

    def test_head_review_only_after_the_client(self):
        self.post.db_set("status", "Drafting")
        with self.assertRaises(frappe.ValidationError):
            self.set_status("Head Review")
        with self.assertRaises(frappe.ValidationError):
            make_content_post("New post", CUSTOMER, status="Head Review")

    def test_posts_that_never_went_to_the_client_are_unchanged(self):
        self.post = make_content_post(
            "Internal promo", CUSTOMER, status="Internal Review", writer=WRITER[0]
        )

        self.assertEqual(self.set_status("Approved").status, "Approved")

    def test_a_system_manager_can_act_so_nothing_gets_stuck(self):
        self.head_review()

        content_board.head_approve(self.post.name)

        self.assertEqual(
            frappe.db.get_value("HD Content Post", self.post.name, "status"),
            "Approved",
        )

    def test_head_hears_about_posts_due_soon_still_waiting_on_them(self):
        self.head_review()
        self.post.db_set("publish_on", add_to_date(now_datetime(), hours=20))

        send_due_reminders()

        self.assertTrue(any("still in Head Review" in m for m in self.notified(HEAD)))


class TestWhoEditsEntries(FrappeTestCase):
    """DM Coordinators, managers and System Managers edit entries; the rest attach files."""

    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        make_tasky_user(*WRITER)
        make_content_user(*COORDINATOR, "DM Coordinator")
        make_content_user(*EMPLOYEE, "DM Employee")
        self.post = make_content_post(
            "Onam offer", CUSTOMER, status="Drafting", writer=WRITER[0]
        )

    def rename(self, user):
        def run():
            doc = frappe.get_doc("HD Content Post", self.post.name)
            doc.title = "Onam mega offer"
            doc.save()

        run_as_user(user[0], run)

    def test_only_editors_change_an_entry(self):
        for user in (WRITER, EMPLOYEE):
            with self.assertRaises(frappe.PermissionError, msg=user[0]):
                self.rename(user)
            with self.assertRaises(frappe.PermissionError, msg=user[0]):
                run_as_user(
                    user[0],
                    lambda: content_board.add_entries(
                        {
                            "customer": CUSTOMER,
                            "title": "Diwali",
                            "publish_on": str(add_to_date(now_datetime(), days=3)),
                        },
                        ["Instagram"],
                    ),
                )

        self.rename(COORDINATOR)
        self.assertEqual(
            frappe.db.get_value("HD Content Post", self.post.name, "title"),
            "Onam mega offer",
        )

    def test_managers_still_edit(self):
        manager = make_tasky_user(
            "pm@content-smoke.example", "Leena V", roles=("Project Manager",)
        )
        self.rename((manager,))

    def test_anyone_on_it_attaches_files_and_removes_only_their_own(self):
        mine = run_as_user(
            WRITER[0], lambda: attach_file("HD Content Post", self.post.name)
        )
        theirs = run_as_user(
            COORDINATOR[0],
            lambda: attach_file("HD Content Post", self.post.name, "logo.png"),
        )

        with self.assertRaises(frappe.PermissionError):
            run_as_user(WRITER[0], lambda: frappe.delete_doc("File", theirs.name))
        run_as_user(WRITER[0], lambda: frappe.delete_doc("File", mine.name))
        self.assertFalse(frappe.db.exists("File", mine.name))

    def test_the_app_still_moves_entries_for_them(self):
        # a client's yes and a head's approval are made on their behalf
        self.post.db_set("status", "Client Review")
        frappe.set_user("Guest")
        try:
            frappe.get_doc("HD Content Post", self.post.name).approve_from_portal(
                "client@alnoor.example"
            )
        finally:
            frappe.set_user("Administrator")
        make_dm_head(*HEAD)  # head only, not an editor

        run_as_user(HEAD[0], lambda: content_board.head_approve(self.post.name))

        self.assertEqual(
            frappe.db.get_value("HD Content Post", self.post.name, "status"),
            "Approved",
        )


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
