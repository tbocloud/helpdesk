# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, now_datetime

from helpdesk.api import content_board
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_content_post,
    make_tasky_user,
)

CUSTOMER = "Al Noor Trading LLC"
WRITER = ("meera.nair@content-smoke.example", "Meera Nair")


class TestContentBoard(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)
        make_tasky_user(*WRITER)

    def entry(self, **values):
        return {
            "customer": CUSTOMER,
            "title": "Diwali offer",
            "format": "Carousel",
            "status": "Drafting",
            "publish_on": str(add_to_date(now_datetime(), days=3)),
            "brief": "Gold and green",
            **values,
        }

    def test_one_post_per_platform(self):
        names = content_board.add_entries(
            self.entry(), ["Instagram", "Facebook", "Instagram"]
        )

        posts = frappe.get_all(
            "HD Content Post",
            filters={"name": ("in", names)},
            fields=["channel", "title", "format", "brief"],
        )
        self.assertEqual(sorted(p.channel for p in posts), ["Facebook", "Instagram"])
        self.assertTrue(all(p.brief == "Gold and green" for p in posts))

    def test_one_post_can_cover_several_platforms(self):
        [name] = content_board.add_entries(
            self.entry(), ["Instagram", "Facebook", "LinkedIn"], separate=0
        )
        post = frappe.get_doc("HD Content Post", name)
        self.assertEqual(post.channel, "Instagram")
        self.assertEqual(post.platforms, "Instagram, Facebook, LinkedIn")

        # an edit that only changes channel (Desk form, older screens) makes it the main platform
        post.channel = "LinkedIn"
        post.save()
        self.assertEqual(post.platforms, "LinkedIn, Instagram, Facebook")

        # unknown platforms are dropped, never saved
        post.platforms = "Facebook, MySpace"
        post.save()
        self.assertEqual((post.channel, post.platforms), ("Facebook", "Facebook"))

    def test_special_day_is_kept_on_every_post(self):
        names = content_board.add_entries(
            self.entry(special_day="Diwali"), ["Instagram", "Facebook"]
        )

        self.assertEqual(
            set(
                frappe.get_all(
                    "HD Content Post", {"name": ("in", names)}, pluck="special_day"
                )
            ),
            {"Diwali"},
        )

    def test_needs_a_platform_and_valid_post(self):
        with self.assertRaises(frappe.ValidationError):
            content_board.add_entries(self.entry(), [])
        # every new entry needs its posting date and time, even an idea
        for status in ("Drafting", "Idea"):
            with self.assertRaises(frappe.ValidationError):
                content_board.add_entries(
                    self.entry(publish_on=None, status=status), ["Instagram"]
                )
        self.assertFalse(frappe.db.exists("HD Content Post", {"title": "Diwali offer"}))

    def test_team_defaults_come_from_the_latest_post(self):
        self.assertEqual(
            content_board.get_team_defaults(CUSTOMER),
            {"writer": [], "designer": [], "marketer": [], "video_editor": []},
        )
        make_content_post("Older", CUSTOMER, designer="Administrator")
        make_content_post("Newer", CUSTOMER, writer=WRITER[0])

        team = content_board.get_team_defaults(CUSTOMER)
        self.assertEqual(team["writer"], [WRITER[0]])
        self.assertEqual(team["designer"], [])

    def test_postpone_needs_a_reason_and_is_recorded(self):
        due = add_to_date(now_datetime(), hours=-2)
        post = make_content_post(
            "Late reel", CUSTOMER, status="Drafting", publish_on=due
        )
        post.db_set("missed_alert_sent", 1)
        later = add_to_date(now_datetime(), days=2)

        with self.assertRaises(frappe.ValidationError):
            content_board.postpone(post.name, str(later), " ")
        with self.assertRaises(frappe.ValidationError):
            content_board.postpone(post.name, str(due), "same time")

        content_board.postpone(post.name, str(later), "Client approval delayed")

        post.reload()
        self.assertEqual(get_datetime(post.publish_on), get_datetime(later))
        self.assertEqual(post.times_postponed, 1)
        self.assertFalse(post.missed_alert_sent)
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_name": post.name,
                    "content": ("like", "%Client approval delayed%"),
                },
            )
        )

    def test_cancel_but_not_once_published(self):
        post = make_content_post("Dropped", CUSTOMER)
        content_board.cancel(post.name, "Client paused the campaign")
        self.assertEqual(
            frappe.db.get_value("HD Content Post", post.name, "status"), "Cancelled"
        )

        live = make_content_post(
            "Live",
            CUSTOMER,
            status="Published",
            publish_on=now_datetime(),
            published_url="https://instagram.com/p/live",
        )
        with self.assertRaises(frappe.ValidationError):
            content_board.cancel(live.name)
