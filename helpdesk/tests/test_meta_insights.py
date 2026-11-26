from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from helpdesk.api import meta as meta_api
from helpdesk.api import meta_insights
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    content_project_for,
)
from helpdesk.integrations.meta import connect, insights, signing
from helpdesk.integrations.meta.graph import MetaError
from helpdesk.test_utils import (
    FakeGraph,
    create_customer,
    enable_meta,
    enable_meta_insights,
    hold_commits,
    insights_graph_routes,
    make_approved_post,
    make_content_project,
    make_content_user,
    make_daily_insight,
    make_dm_head,
    make_insights_connection,
    make_meta_connection,
    make_post_insight,
    publish_post_on_meta,
    run_as_user,
)

CUSTOMER = "Meta Reach Client"
OTHER = "Meta Reach Other Client"
MANAGER = "reach.manager@meta.example"
MEMBER = "reach.member@meta.example"
OUTSIDER = "reach.outsider@meta.example"
HEAD = "reach.head@meta.example"
ENQUEUE = "helpdesk.integrations.meta.insights.frappe.enqueue"
PAGES = {
    "GET me/accounts": {
        "data": [
            {
                "id": "page-1",
                "name": "Client Page",
                "access_token": "page-token",
                "tasks": ["CREATE_CONTENT"],
            }
        ]
    }
}


def yesterday():
    return getdate(add_days(today(), -1))


class MetaInsightsCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        enable_meta()
        enable_meta_insights()
        create_customer(CUSTOMER)
        create_customer(OTHER)
        make_content_user(MANAGER, "Reach Manager", "DM Employee")
        make_content_user(MEMBER, "Reach Member", "DM Employee")
        make_content_user(OUTSIDER, "Reach Outsider", "DM Employee")
        make_dm_head(HEAD, "Reach Head")
        self.post = make_approved_post("Monday offer", CUSTOMER)
        self.project = content_project_for(CUSTOMER)
        project = frappe.get_doc("Project", self.project)
        project.append("users", {"user": MANAGER, "custom_role": "Project Manager"})
        # a Select without a default takes its first option, Project Manager
        project.append(
            "users", {"user": MEMBER, "custom_role": "Content Writer / Copywriter"}
        )
        project.save(ignore_permissions=True)
        patcher = patch(ENQUEUE)
        self.enqueue = patcher.start()
        self.addCleanup(patcher.stop)

    def sync(self, routes=None, days=insights.NIGHTLY_DAYS):
        graph = FakeGraph(routes or insights_graph_routes(yesterday()))
        with graph.patch():
            insights.sync_connection(self.project, days)
        return graph


class TestConnecting(MetaInsightsCase):
    def sign_in(self, *scopes):
        routes = {
            "GET oauth/access_token": [
                {"access_token": "short"},
                {"access_token": "long-lived"},
            ],
            "GET me/permissions": {
                "data": [{"permission": s, "status": "granted"} for s in scopes]
            },
        }
        state = signing.make_state("Administrator", self.project)
        with FakeGraph(routes).patch():
            connect.finish_login("code", state, "Administrator")
        return frappe.get_doc(connect.CONNECTION, self.project)

    def test_asks_for_insights_only_when_switched_on(self):
        self.assertEqual(connect.scopes(), connect.SCOPES + connect.INSIGHTS_SCOPES)
        frappe.db.set_single_value("HD Meta Settings", "insights_enabled", 0)
        self.assertEqual(connect.scopes(), connect.SCOPES)

    def test_allowing_insights_is_recorded(self):
        connection = self.sign_in(*connect.SCOPES, *connect.INSIGHTS_SCOPES)
        self.assertTrue(connection.insights_allowed)

    def test_declining_insights_still_connects(self):
        connection = self.sign_in(*connect.SCOPES, "read_insights")
        self.assertFalse(connection.insights_allowed)
        self.assertEqual(connection.status, "Pending")

    def test_picking_the_page_fills_in_90_days(self):
        make_insights_connection(
            self.project, status="Pending", user_access_token="user-token"
        )
        with FakeGraph(PAGES).patch():
            meta_api.select_page(self.project, "page-1")
        self.enqueue.assert_called_once()
        self.assertEqual(self.enqueue.call_args.kwargs["days"], insights.BACKFILL_DAYS)


class TestSync(MetaInsightsCase):
    def setUp(self):
        super().setUp()
        make_insights_connection(self.project)

    def test_days_posts_and_followers_are_saved(self):
        publish_post_on_meta(self.post.name, "Facebook", "Instagram")
        self.sync()
        day = yesterday()
        facebook = frappe.get_doc(
            insights.DAILY, f"{self.project}-Facebook-{day}"
        ).as_dict()
        self.assertEqual(
            {k: facebook[k] for k in ("reach", "views", "engagements", "followers")},
            {"reach": 1200, "views": 3000, "engagements": 150, "followers": 5400},
        )
        self.assertEqual((facebook.follows, facebook.unfollows), (12, 2))
        instagram = frappe.get_doc(insights.DAILY, f"{self.project}-Instagram-{day}")
        self.assertEqual(
            (instagram.reach, instagram.engaged_accounts, instagram.engagements),
            (2500, 300, 420),
        )
        self.assertEqual((instagram.follows, instagram.unfollows), (25, 5))
        self.assertEqual(instagram.followers, 8100)

        photo = frappe.get_doc(insights.POSTS, "Facebook-page-1_555")
        self.assertEqual(photo.kind, "Image")
        # reactions come by type and are added up; interactions add comments and shares
        self.assertEqual((photo.reach, photo.reactions), (800, 50))
        self.assertEqual(photo.interactions, 50 + 6 + 4)
        self.assertEqual(photo.content_post, self.post.name)
        reel = frappe.get_doc(insights.POSTS, "Instagram-ig-media-9")
        self.assertEqual((reel.kind, reel.reach, reel.saves), ("Reel", 1900, 21))
        self.assertEqual(reel.content_post, self.post.name)

        connection = frappe.get_doc(connect.CONNECTION, self.project)
        self.assertTrue(connection.insights_synced_on)
        self.assertFalse(connection.insights_error)

    def test_a_second_sync_updates_the_same_rows(self):
        self.sync()
        routes = insights_graph_routes(yesterday())
        routes["GET page-1"] = {"followers_count": 5500}
        self.sync(routes)
        rows = frappe.get_all(
            insights.DAILY,
            filters={"project": self.project, "platform": "Facebook"},
            pluck="followers",
        )
        self.assertEqual(rows, [5500])
        self.assertEqual(frappe.db.count(insights.POSTS, {"project": self.project}), 2)

    def test_a_retired_metric_is_skipped_and_named(self):
        retired = {
            "_status": 400,
            "error": {
                "code": 100,
                "message": "(#100) The value must be a valid insights metric",
            },
        }
        routes = insights_graph_routes(yesterday())
        good = routes["GET page-1/insights"]
        # the whole request is refused, then each metric is asked alone
        routes["GET page-1/insights"] = [
            retired,
            {"data": [good["data"][0]]},
            retired,
            {"data": [good["data"][2]]},
            {"data": [good["data"][3]]},
            {"data": [good["data"][4]]},
        ]
        self.sync(routes)
        facebook = frappe.get_doc(
            insights.DAILY, f"{self.project}-Facebook-{yesterday()}"
        )
        self.assertEqual((facebook.reach, facebook.views), (1200, 0))
        error = frappe.db.get_value(connect.CONNECTION, self.project, "insights_error")
        self.assertIn("page_media_view", error)

    def test_an_expired_token_marks_the_connection(self):
        routes = insights_graph_routes(yesterday())
        routes["GET page-1/insights"] = {
            "_status": 400,
            "error": {"code": 190, "message": "Session expired"},
        }
        self.sync(routes)
        connection = frappe.get_doc(connect.CONNECTION, self.project)
        self.assertEqual(connection.status, "Expired")
        self.assertIn("expired", connection.insights_error)

    def test_a_story_with_few_viewers_keeps_a_note(self):
        routes = insights_graph_routes(yesterday())
        routes["GET ig-1/stories"] = {
            "data": [
                {
                    "id": "story-1",
                    "media_type": "IMAGE",
                    "media_product_type": "STORY",
                    "timestamp": f"{yesterday()}T10:00:00+0000",
                }
            ]
        }
        routes["GET story-1/insights"] = {
            "_status": 400,
            "error": {"code": 10, "message": "(#10) Not enough viewers"},
        }
        with FakeGraph(routes).patch():
            insights.sync_stories()
        story = frappe.get_doc(insights.POSTS, "Instagram-story-1")
        self.assertEqual(story.kind, "Story")
        self.assertIn("Fewer than 5", story.insights_note)

    def test_without_permission_nothing_is_read(self):
        frappe.db.set_value(connect.CONNECTION, self.project, "insights_allowed", 0)
        graph = self.sync()
        self.assertEqual(graph.calls, [])

    def test_nightly_sync_waits_for_the_switch(self):
        frappe.db.set_single_value("HD Meta Settings", "insights_enabled", 0)
        graph = FakeGraph(insights_graph_routes(yesterday()))
        with graph.patch():
            insights.sync_all()
        self.assertEqual(graph.calls, [])


class TestReport(MetaInsightsCase):
    def setUp(self):
        super().setUp()
        make_insights_connection(self.project, customer=CUSTOMER)
        other = make_content_project(OTHER)
        make_meta_connection(other, facebook_page_name="Other Page")
        self.first = getdate(add_days(today(), -14))
        self.last = getdate(add_days(today(), -8))
        for i in range(7):
            make_daily_insight(
                self.project,
                "Facebook",
                add_days(self.first, i),
                reach=100,
                views=200,
                engagements=10,
                follows=3,
                unfollows=1,
            )
            # the week before, for the comparison
            make_daily_insight(
                self.project, "Facebook", add_days(self.first, i - 7), reach=50
            )
        frappe.db.set_value(
            insights.DAILY, f"{self.project}-Facebook-{self.last}", "followers", 900
        )
        make_post_insight(
            self.project,
            "Instagram",
            "m-1",
            f"{self.first} 10:00:00",
            kind="Reel",
            reach=400,
            interactions=40,
        )
        make_post_insight(
            self.project,
            "Facebook",
            "p-1",
            f"{self.first} 12:00:00",
            kind="Image",
            reach=100,
            interactions=20,
        )

    def report(self, user="Administrator", project=None):
        return run_as_user(
            user,
            lambda: meta_insights.get_reach_report(
                str(self.first), str(self.last), project or self.project
            ),
        )

    def test_totals_compare_with_the_period_before(self):
        result = self.report(HEAD)
        facebook = result["report"]["platforms"][0]
        self.assertEqual(facebook["platform"], "Facebook")
        self.assertEqual(facebook["current"]["reach"], 700)
        self.assertEqual(facebook["previous"]["reach"], 350)
        self.assertEqual(facebook["current"]["net_follows"], 14)
        self.assertEqual(facebook["followers"], 900)
        self.assertEqual(result["report"]["days"][0], str(self.first))
        self.assertEqual(result["report"]["series"]["Facebook"]["reach"], [100] * 7)

    def test_posts_by_reach_and_kind(self):
        report = self.report(HEAD)["report"]
        self.assertEqual(
            [p["name"] for p in report["posts"]], ["Instagram-m-1", "Facebook-p-1"]
        )
        self.assertEqual(report["kinds"][0]["kind"], "Reel")
        # (40 + 20) interactions over (400 + 100) reached
        self.assertEqual(report["engagement_rate"], 12.0)

    def test_the_content_team_sees_only_their_clients(self):
        projects = [c.project for c in self.report(MEMBER)["connections"]]
        self.assertEqual(projects, [self.project])
        self.assertEqual(len(self.report(HEAD)["connections"]), 2)
        self.assertRaises(frappe.PermissionError, self.report, OUTSIDER)
        self.assertEqual(
            run_as_user(
                OUTSIDER,
                lambda: meta_insights.get_reach_report(str(self.first), str(self.last)),
            )["connections"],
            [],
        )

    def test_only_managers_can_sync_now(self):
        self.assertRaises(
            frappe.PermissionError,
            run_as_user,
            MEMBER,
            lambda: meta_insights.sync_now(self.project),
        )
        run_as_user(MANAGER, lambda: meta_insights.sync_now(self.project))
        self.enqueue.assert_called_once()

    def test_pdf_download(self):
        with patch("shutil.which", return_value=None):
            meta_insights.export_pdf(self.project, str(self.first), str(self.last))
        html = frappe.response.filecontent
        self.assertIn("Reach report", html)
        self.assertIn("Daily reach on Facebook", html)
        self.assertTrue(frappe.response.filename.endswith(".html"))

    def test_a_long_period_is_refused(self):
        self.assertRaises(
            frappe.ValidationError,
            meta_insights.get_reach_report,
            "2025-01-01",
            "2026-06-01",
        )


class TestMetricErrors(FrappeTestCase):
    def test_only_metric_messages_count_as_retired(self):
        self.assertTrue(
            insights.refused_metric(
                MetaError("Meta said: (#100) must be a valid insights metric", code=100)
            )
        )
        self.assertFalse(
            insights.refused_metric(
                MetaError("Meta said: Unsupported get request", code=100)
            )
        )
