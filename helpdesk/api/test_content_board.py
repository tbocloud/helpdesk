# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime

from helpdesk.api import content_board
from helpdesk.test_utils import (
    create_customer,
    make_content_post,
    make_tasky_user,
    set_content_settings,
)

CUSTOMER = "Al Noor Trading LLC"
WRITER = ("meera.nair@content-smoke.example", "Meera Nair")


class TestContentBoard(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
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

    def test_export_matches_the_sheet_filters(self):
        import io

        import openpyxl

        content_board.add_entries(self.entry(), ["Instagram", "Facebook"], separate=1)
        day = str(getdate(add_to_date(now_datetime(), days=3)))
        frappe.response.clear()
        content_board.export_posts(
            start=day, end=day, customer=CUSTOMER, channel="Facebook"
        )
        sheet = openpyxl.load_workbook(io.BytesIO(frappe.response.filecontent)).active
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(
            rows[0][:4], ("Post", "Publish date", "Time", "Campaign or topic")
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][6], "Facebook")

    def test_needs_a_platform_and_valid_post(self):
        with self.assertRaises(frappe.ValidationError):
            content_board.add_entries(self.entry(), [])
        # later stages need a date; none of the posts may be created
        with self.assertRaises(frappe.ValidationError):
            content_board.add_entries(self.entry(publish_on=None), ["Instagram"])

    def test_team_defaults_come_from_the_latest_post(self):
        self.assertEqual(
            content_board.get_team_defaults(CUSTOMER),
            {"writer": None, "designer": None, "marketer": None},
        )
        make_content_post("Older", CUSTOMER, designer="Administrator")
        make_content_post("Newer", CUSTOMER, writer=WRITER[0])

        team = content_board.get_team_defaults(CUSTOMER)
        self.assertEqual(team.writer, WRITER[0])
        self.assertFalse(team.designer)

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


class TestContentRoleTasks(FrappeTestCase):
    """Assigning someone to a post gives them an ERPNext Task for their part."""

    DESIGNER = ("arjun.menon@content-smoke.example", "Arjun Menon")

    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        if not frappe.get_meta("Task").has_field("content_post"):
            self.skipTest("needs ERPNext's Task with helpdesk's content fields")
        create_customer(CUSTOMER)
        make_tasky_user(*WRITER)
        make_tasky_user(*self.DESIGNER)
        set_content_settings(
            create_tasks_on_assign=1, writer_hours=2, designer_hours=3, marketer_hours=1
        )
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        self.due = add_to_date(now_datetime(), days=4)

    def role_task(self, post, role):
        return frappe.get_all(
            "Task",
            filters={"content_post": post.name, "content_role": role},
            fields=[
                "name",
                "subject",
                "priority",
                "status",
                "exp_end_date",
                "expected_time",
                "_assign",
            ],
        )

    def test_assigning_creates_a_task_for_that_person(self):
        post = make_content_post(
            "Diwali reel",
            CUSTOMER,
            status="Drafting",
            publish_on=self.due,
            format="Reel",
        )
        content_board.assign(post.name, "writer", WRITER[0])
        content_board.assign(post.name, "designer", self.DESIGNER[0], hours=5)

        [writer_task] = self.role_task(post, "writer")
        self.assertTrue(writer_task.subject.startswith("Content Finalization"))
        self.assertEqual(writer_task.priority, "High")
        self.assertEqual(writer_task.expected_time, 2)
        self.assertEqual(getdate(writer_task.exp_end_date), getdate(self.due))
        self.assertIn(WRITER[0], writer_task._assign)

        [designer_task] = self.role_task(post, "designer")
        self.assertTrue(designer_task.subject.startswith("Video Production"))
        self.assertEqual(designer_task.expected_time, 5)

    def test_reassign_moves_the_task_and_unassign_cancels_it(self):
        post = make_content_post(
            "Offer post",
            CUSTOMER,
            status="Drafting",
            publish_on=self.due,
            writer=WRITER[0],
        )
        [task] = self.role_task(post, "writer")

        content_board.assign(post.name, "writer", self.DESIGNER[0])
        [moved] = self.role_task(post, "writer")
        self.assertEqual(moved.name, task.name)
        self.assertIn(self.DESIGNER[0], moved._assign)
        self.assertNotIn(WRITER[0], moved._assign)

        content_board.assign(post.name, "writer", None)
        self.assertEqual(self.role_task(post, "writer")[0].status, "Cancelled")

    def test_postpone_moves_the_deadline_and_cancel_closes_tasks(self):
        post = make_content_post(
            "Launch", CUSTOMER, status="Drafting", publish_on=self.due, writer=WRITER[0]
        )
        later = add_to_date(self.due, days=3)
        content_board.postpone(post.name, str(later), "Client asked")
        self.assertEqual(
            getdate(self.role_task(post, "writer")[0].exp_end_date), getdate(later)
        )

        content_board.cancel(post.name, "Dropped")
        self.assertEqual(self.role_task(post, "writer")[0].status, "Cancelled")

    def test_turned_off_creates_nothing(self):
        set_content_settings(create_tasks_on_assign=0)
        post = make_content_post(
            "No tasks",
            CUSTOMER,
            status="Drafting",
            publish_on=self.due,
            writer=WRITER[0],
        )
        self.assertFalse(self.role_task(post, "writer"))
