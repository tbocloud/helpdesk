from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from helpdesk.api import content_plans
from helpdesk.api.content_board import get_occasions
from helpdesk.content_follow_up import send_client_follow_ups
from helpdesk.helpdesk.doctype.hd_content_package.hd_content_package import (
    plan_upcoming_months,
)
from helpdesk.helpdesk.report.content_delivery.content_delivery import execute
from helpdesk.test_utils import (
    content_plan_values,
    create_customer,
    hold_commits,
    make_content_occasion,
    make_content_package,
    make_content_post,
    make_portal_contact,
    make_tasky_user,
    set_content_settings,
)

CUSTOMER = "Planning Bakery LLC"
OTHER_CUSTOMER = "Planning Gym LLC"
WRITER = ("writer.plan@content-planning.example", "Aysha Writer")
DESIGNER = ("designer.plan@content-planning.example", "Rahul Designer")
MARKETER = ("marketer.plan@content-planning.example", "Fida Marketer")
CLIENT_EMAIL = "owner@planning-bakery.example"
TODAY = "2026-10-21"  # planning day passed; next month is November 2026
NOWDATE = "helpdesk.helpdesk.doctype.hd_content_package.hd_content_package.nowdate"


class ContentPlanningCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        for person in (WRITER, DESIGNER, MARKETER):
            make_tasky_user(*person)
        # only this test's occasions
        frappe.db.delete("HD Content Occasion")
        set_content_settings(
            plan_day=20,
            default_task_mode="One task per person",
            writer_days_before=3,
            designer_days_before=1,
        )
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")

    def package(self, **values):
        return make_content_package(
            CUSTOMER,
            [("Instagram", "Post", 8), ("Instagram", "Reel", 4)],
            writer=WRITER[0],
            designer=DESIGNER[0],
            marketer=MARKETER[0],
            **values,
        )

    def planned(self, package):
        return frappe.get_all(
            "HD Content Post",
            filters={"content_package": package.name},
            fields=[
                "name",
                "title",
                "status",
                "format",
                "publish_on",
                "brief",
                "writer",
            ],
            order_by="publish_on asc",
        )


class TestMonthlyPlan(ContentPlanningCase):
    def test_next_month_is_spread_over_posting_days_with_the_team(self):
        package = self.package()
        with patch(NOWDATE, return_value=TODAY):
            self.assertEqual(package.plan("next"), 12)

        posts = self.planned(package)
        self.assertEqual(len(posts), 12)
        days = [getdate(p.publish_on) for p in posts]
        self.assertTrue(all(d.month == 11 and d.year == 2026 for d in days))
        self.assertTrue(all(d.weekday() != 6 for d in days))  # no Sundays
        self.assertEqual(len(set(days)), 12)
        self.assertEqual(get_datetime(posts[0].publish_on).hour, 10)
        self.assertEqual(sorted(p.format for p in posts), ["Post"] * 8 + ["Reel"] * 4)
        self.assertTrue(
            all(p.status == "Idea" and p.writer == WRITER[0] for p in posts)
        )
        package.reload()
        self.assertEqual(getdate(package.last_planned_month), date(2026, 11, 1))

    def test_team_gets_one_summary_not_a_notice_per_task(self):
        package = self.package()
        with patch(NOWDATE, return_value=TODAY):
            package.plan("next")

        self.assertEqual(
            frappe.db.count(
                "ToDo",
                {"allocated_to": WRITER[0], "reference_type": "Task", "status": "Open"},
            ),
            12,
        )
        self.assertEqual(
            frappe.db.count(
                "HD Notification",
                {"user_to": WRITER[0], "reference_doctype": "HD Content Package"},
            ),
            1,
        )
        self.assertFalse(
            frappe.db.exists(
                "HD Notification",
                {"user_to": WRITER[0], "message": ("like", "New content task:%")},
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "Notification Log", {"for_user": WRITER[0], "type": "Assignment"}
            )
        )

    def test_occasions_take_the_nearest_post_for_the_packages_regions(self):
        make_content_occasion(
            "Diwali", "2026-11-08", region="India", idea="Lights and sweets offer"
        )
        make_content_occasion("UAE Flag Day", "2026-11-03", region="UAE")
        package = self.package()
        with patch(NOWDATE, return_value=TODAY):
            package.plan("next")

        posts = self.planned(package)
        diwali = [p for p in posts if p.title.startswith("Diwali")]
        self.assertEqual(len(diwali), 1)
        # a Sunday, but the occasion decides the day
        self.assertEqual(getdate(diwali[0].publish_on), date(2026, 11, 8))
        self.assertEqual(diwali[0].brief, "Lights and sweets offer")
        self.assertFalse([p for p in posts if p.title.startswith("UAE Flag Day")])
        self.assertEqual(len(posts), 12)

    def test_a_month_is_planned_once(self):
        package = self.package()
        with patch(NOWDATE, return_value=TODAY):
            package.plan("next")
            with self.assertRaises(frappe.ValidationError):
                package.plan("next")
            plan_upcoming_months()
        self.assertEqual(len(self.planned(package)), 12)

    def test_scheduler_waits_for_the_planning_day(self):
        package = self.package()
        with patch(NOWDATE, return_value="2026-10-10"):
            plan_upcoming_months()
        self.assertEqual(self.planned(package), [])

        with patch(NOWDATE, return_value=TODAY):
            plan_upcoming_months()
        self.assertEqual(len(self.planned(package)), 12)

    def test_rest_of_this_month_starts_tomorrow(self):
        package = self.package()
        with patch(NOWDATE, return_value=TODAY):
            package.plan("this")
        days = [getdate(p.publish_on) for p in self.planned(package)]
        self.assertEqual(len(days), 12)
        self.assertTrue(
            all(date(2026, 10, 22) <= d <= date(2026, 10, 31) for d in days)
        )


class TestPromisedAndOccasions(ContentPlanningCase):
    def test_report_shows_what_the_package_promises(self):
        self.package()
        _columns, rows, *_ = execute(
            {"from_date": "2026-11-01", "to_date": "2026-11-15"}
        )
        row = next(r for r in rows if r["customer"] == CUSTOMER)
        self.assertEqual(row["promised"], 6)  # half of 12 a month
        self.assertEqual(row["planned"], 0)

    def test_occasions_repeat_yearly_and_follow_the_customers_regions(self):
        make_content_occasion("New Year's Day", "2026-01-01", repeats_yearly=1)
        make_content_occasion(
            "UAE National Day", "2026-12-02", region="UAE", repeats_yearly=1
        )
        self.package(occasions_india=1, occasions_uae=0)

        everything = get_occasions("2026-11-25", "2027-01-05")
        self.assertEqual(
            [(o["date"], o["occasion"]) for o in everything],
            [("2026-12-02", "UAE National Day"), ("2027-01-01", "New Year's Day")],
        )
        for_customer = get_occasions("2026-11-25", "2027-01-05", CUSTOMER)
        self.assertEqual([o["occasion"] for o in for_customer], ["New Year's Day"])


class TestClientFollowUp(ContentPlanningCase):
    def setUp(self):
        super().setUp()
        make_portal_contact(CUSTOMER, CLIENT_EMAIL)
        set_content_settings(
            enable_client_portal=1, client_reminder_days=2, client_escalate_days=4
        )
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        self.post = make_content_post(
            "Weekend brunch",
            CUSTOMER,
            status="Client Review",
            publish_on=add_days(now_datetime(), 6),
            marketer=MARKETER[0],
            task_mode="No tasks",
        )

    def waited(self, days):
        frappe.db.set_value(
            "HD Content Post",
            self.post.name,
            "client_review_since",
            add_days(now_datetime(), -days),
            update_modified=False,
        )

    def test_entering_client_review_starts_the_clock(self):
        self.assertTrue(self.post.client_review_since)

    def test_client_is_reminded_once_after_two_days(self):
        self.waited(1)
        with patch.object(frappe, "sendmail") as sendmail:
            send_client_follow_ups()
        sendmail.assert_not_called()

        self.waited(3)
        with patch.object(frappe, "sendmail") as sendmail:
            send_client_follow_ups()
            send_client_follow_ups()
        sendmail.assert_called_once()
        self.assertIn(CLIENT_EMAIL, sendmail.call_args.kwargs["recipients"])
        self.assertIn("Weekend brunch", sendmail.call_args.kwargs["message"])
        self.assertIn("/content-portal", sendmail.call_args.kwargs["message"])
        self.assertTrue(
            frappe.db.get_value("HD Content Post", self.post.name, "client_reminded_on")
        )
        # not yet long enough to alert the team
        self.assertFalse(frappe.db.exists("HD Notification", {"user_to": MARKETER[0]}))

    def test_team_is_alerted_after_four_days(self):
        self.waited(5)
        with patch.object(frappe, "sendmail"):
            send_client_follow_ups()
            send_client_follow_ups()
        self.assertEqual(
            frappe.db.count(
                "HD Notification",
                {"user_to": MARKETER[0], "message": ("like", "%waited 5 days%")},
            ),
            1,
        )

    def test_no_email_when_the_client_has_nowhere_to_approve(self):
        set_content_settings(enable_client_portal=0)
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        self.waited(3)
        with patch.object(frappe, "sendmail") as sendmail:
            send_client_follow_ups()
        sendmail.assert_not_called()

    def test_sending_for_review_again_restarts_the_follow_up(self):
        self.waited(5)
        with patch.object(frappe, "sendmail"):
            send_client_follow_ups()

        post = frappe.get_doc("HD Content Post", self.post.name)
        post.status = "Changes Requested"
        post.save(ignore_permissions=True)
        post.status = "Client Review"
        post.save(ignore_permissions=True)

        self.assertIsNone(post.client_reminded_on)
        self.assertIsNone(post.client_escalated_on)
        self.assertGreater(
            get_datetime(post.client_review_since), add_days(now_datetime(), -1)
        )


class TestMonthlyPlansPage(ContentPlanningCase):
    """The API behind the Content Calendar's Monthly plans page."""

    PLANS_NOWDATE = "helpdesk.api.content_plans.nowdate"

    def test_create_edit_plan_and_list_it(self):
        name = content_plans.save_plan(content_plan_values(CUSTOMER, writer=WRITER[0]))
        content_plans.save_plan(
            content_plan_values(
                CUSTOMER,
                writer=WRITER[0],
                items=[
                    {"channel": "Instagram", "format": "Reel", "posts_per_month": 3}
                ],
            ),
            name=name,
        )
        with patch(self.PLANS_NOWDATE, return_value=TODAY):
            data = content_plans.get_plans()

        plan = next(p for p in data["plans"] if p["customer"] == CUSTOMER)
        self.assertEqual(plan["posts_per_month"], 3)
        self.assertEqual(
            plan["items"],
            [{"channel": "Instagram", "format": "Reel", "posts_per_month": 3}],
        )
        self.assertEqual(plan["team"], {"writer": WRITER[1]})
        self.assertEqual(plan["publish_time"], "18:30")
        self.assertFalse(plan["next_month_planned"])
        self.assertEqual(data["next_month"], "2026-11-01")
        self.assertTrue(data["can_edit"])

    def test_plan_now_from_the_page(self):
        name = content_plans.save_plan(content_plan_values(CUSTOMER, writer=WRITER[0]))
        with patch(NOWDATE, return_value=TODAY):
            self.assertEqual(content_plans.plan_now(name, "next"), 8)
        with patch(self.PLANS_NOWDATE, return_value=TODAY):
            plan = content_plans.get_plans()["plans"][0]
        self.assertTrue(plan["next_month_planned"])
        posts = frappe.get_all(
            "HD Content Post", filters={"content_package": name}, pluck="publish_on"
        )
        self.assertTrue(
            all(get_datetime(p).strftime("%H:%M") == "18:30" for p in posts)
        )
        self.assertTrue(all(getdate(p).weekday() < 5 for p in posts))

    def test_deleting_a_plan_keeps_its_posts(self):
        name = content_plans.save_plan(content_plan_values(CUSTOMER, writer=WRITER[0]))
        with patch(NOWDATE, return_value=TODAY):
            content_plans.plan_now(name, "next")
        content_plans.delete_plan(name)
        self.assertFalse(frappe.db.exists("HD Content Package", name))
        self.assertEqual(frappe.db.count("HD Content Post", {"customer": CUSTOMER}), 8)

    def test_occasions_for_a_year(self):
        diwali = content_plans.save_occasion(
            {
                "occasion_name": "Diwali",
                "occasion_date": "2027-10-29",
                "region": "India",
            }
        )
        content_plans.save_occasion(
            {
                "occasion_name": "New Year's Day",
                "occasion_date": "2026-01-01",
                "repeats_yearly": 1,
            }
        )
        listed = content_plans.get_occasions_for_year(2027)["occasions"]
        self.assertEqual(
            [(o["date"], o["occasion_name"]) for o in listed],
            [("2027-01-01", "New Year's Day"), ("2027-10-29", "Diwali")],
        )
        self.assertEqual(
            content_plans.get_occasions_for_year(2026)["occasions"][0]["occasion_name"],
            "New Year's Day",
        )

        content_plans.save_occasion({"idea": "Lights offer"}, name=diwali)
        self.assertEqual(
            frappe.db.get_value("HD Content Occasion", diwali, "idea"), "Lights offer"
        )
        content_plans.delete_occasion(diwali)
        self.assertFalse(frappe.db.exists("HD Content Occasion", diwali))


class TestTopicIdeas(ContentPlanningCase):
    """After planning, the AI gives each placeholder post a topic and brief."""

    AI_ON = "helpdesk.ai_suggestion.is_ai_configured"
    CALL = "helpdesk.content_topics.call_haiku"

    def ideas(self, count):
        return {
            "response": {
                "ideas": [
                    {
                        "slot": i,
                        "title": f"Topic {i}",
                        "brief": f"Brief for topic {i}.",
                    }
                    for i in range(1, count + 1)
                ]
            }
        }

    def plan(self, **values):
        package = make_content_package(
            CUSTOMER,
            [("Instagram", "Post", 3)],
            writer=WRITER[0],
            about_brand="Artisan bakery in Kochi; sourdough and custom cakes.",
            **values,
        )
        with patch(NOWDATE, return_value=TODAY):
            package.plan("next")
        return package

    def test_placeholders_get_topics_and_occasions_keep_theirs(self):
        make_content_occasion("Diwali", "2026-11-08", region="India", idea="Sweets")
        with patch(self.AI_ON, return_value=True), patch(
            self.CALL, return_value=self.ideas(2)
        ) as call:
            package = self.plan()

        prompt = call.call_args.args[1]
        self.assertIn("Artisan bakery in Kochi", prompt)
        self.assertIn("Diwali", prompt)
        titles = sorted(p.title for p in self.planned(package))
        self.assertEqual(titles[:2], ["Diwali · Instagram Post", "Topic 1"])
        self.assertEqual(titles[2], "Topic 2")
        post = frappe.get_doc(
            "HD Content Post", {"content_package": package.name, "title": "Topic 1"}
        )
        self.assertIn("Brief for topic 1.", post.brief)
        # the writer's task follows the new title
        self.assertTrue(
            frappe.db.exists(
                "Task",
                {"content_post": post.name, "subject": ("like", "Writer: Topic 1%")},
            )
        )

    def test_a_renamed_post_is_left_alone(self):
        from helpdesk.content_topics import fill_topics

        with patch(self.AI_ON, return_value=False):
            package = self.plan()
        posts = self.planned(package)
        placeholders = {p.name: p.title for p in posts}
        frappe.db.set_value("HD Content Post", posts[0].name, "title", "Our own idea")

        with patch(self.CALL, return_value=self.ideas(3)):
            fill_topics(package.name, placeholders)
        titles = {p.name: p.title for p in self.planned(package)}
        self.assertEqual(titles[posts[0].name], "Our own idea")
        self.assertEqual(titles[posts[1].name], "Topic 2")

    def test_ai_failure_keeps_the_placeholders(self):
        with patch(self.AI_ON, return_value=True), patch(
            self.CALL, side_effect=TimeoutError("model timed out")
        ):
            package = self.plan()
        self.assertTrue(all("/3 · Nov 2026" in p.title for p in self.planned(package)))

    def test_the_brand_note_is_saved_from_the_plans_page(self):
        name = content_plans.save_plan(
            content_plan_values(
                CUSTOMER, ai_topics=1, about_brand="Bakery; sourdough and cakes."
            )
        )
        plan = next(p for p in content_plans.get_plans()["plans"] if p["name"] == name)
        self.assertEqual(plan["about_brand"], "Bakery; sourdough and cakes.")
        self.assertTrue(plan["ai_topics"])

    def test_switched_off_means_no_ai_call(self):
        with patch(self.AI_ON, return_value=True), patch(self.CALL) as call:
            self.plan(ai_topics=0)
        call.assert_not_called()
