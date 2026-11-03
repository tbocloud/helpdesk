from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from frappe.utils.password import get_decrypted_password

from helpdesk.api import meta as meta_api
from helpdesk.api import meta_ads
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    content_project_for,
)
from helpdesk.integrations.meta import ads, connect, signing
from helpdesk.test_utils import (
    FakeGraph,
    ads_graph_routes,
    boost_values,
    create_customer,
    enable_meta,
    enable_meta_ads,
    hold_commits,
    make_ads_connection,
    make_approved_post,
    make_content_user,
    make_department,
    make_dm_head,
    make_meta_connection,
    make_sales_employee,
    make_tasky_user,
    publish_post_on_meta,
    run_as_user,
)

CUSTOMER = "Meta Ads Client"
MANAGER = "ads.manager@meta.example"
MEMBER = "ads.member@meta.example"
EDITOR = "ads.editor@meta.example"
SALES = "ads.sales@meta.example"
HEAD = "ads.head@meta.example"
NOTIFY = "helpdesk.integrations.meta.ads.notify_users"

SIGN_IN = {
    "GET oauth/access_token": [
        {"access_token": "short"},
        {"access_token": "long-lived"},
    ],
    "GET me/accounts": {
        "data": [
            {
                "id": "page-1",
                "name": "Client Page",
                "access_token": "page-token",
                "tasks": ["CREATE_CONTENT"],
                "instagram_business_account": {"id": "ig-1", "username": "client_ig"},
            }
        ]
    },
    "GET me/adaccounts": {
        "data": [
            {
                "id": "act_100",
                "name": "Client Ads",
                "currency": "INR",
                "account_status": 1,
                "business": {"name": "Client Co"},
            },
            {"id": "act_200", "name": "Old", "currency": "USD", "account_status": 2},
        ]
    },
}


def granted(*scopes):
    return {
        "GET me/permissions": {
            "data": [{"permission": s, "status": "granted"} for s in scopes]
        }
    }


class AdsCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        enable_meta()
        enable_meta_ads()
        create_customer(CUSTOMER)
        make_tasky_user(MANAGER, "Ads Manager", roles=("Project Manager",))
        make_tasky_user(MEMBER, "Ads Member")
        make_content_user(EDITOR, "Ads Editor", "DM Coordinator")
        make_sales_employee(SALES, "Ads Sales")
        make_dm_head(HEAD, "Ads Head")
        digital = make_department("Digital")
        self.post = make_approved_post("Monday offer", CUSTOMER)
        self.project = content_project_for(CUSTOMER)
        project = frappe.get_doc("Project", self.project)
        project.custom_department = digital.name
        project.append("users", {"user": MANAGER, "custom_role": "Project Manager"})
        project.save(ignore_permissions=True)
        make_ads_connection(self.project)
        publish_post_on_meta(self.post.name, "Facebook", "Instagram")
        patcher = patch(NOTIFY)
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def boost(self, user=MANAGER, routes=None, **values):
        """Submits the dialog as `user` against a Graph that accepts everything."""
        graph = FakeGraph(routes or ads_graph_routes())
        with graph.patch():
            result = run_as_user(
                user, lambda: meta_ads.submit(self.post.name, boost_values(**values))
            )
        return result, graph

    def timeline(self):
        return frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Project", "reference_name": self.project},
            pluck="content",
        )


class TestAdsConnect(AdsCase):
    def sign_in(self, *scopes, user=MANAGER):
        project = self.project + "-new"
        frappe.get_doc("Project", self.project)  # the connection exists already
        frappe.delete_doc("HD Meta Connection", self.project, ignore_permissions=True)
        state = signing.make_state(user, self.project)
        with FakeGraph({**SIGN_IN, **granted(*scopes)}).patch():
            connect.finish_login("code", state, user)
        return project

    def test_scopes_are_the_phase_one_ones_unless_ads_are_switched_on(self):
        frappe.db.set_single_value("HD Meta Settings", "ads_enabled", 0)
        frappe.clear_cache(doctype="HD Meta Settings")
        self.assertEqual(connect.scopes(), connect.SCOPES)
        self.assertNotIn("ads_management", connect.login_url(self.project, MANAGER))
        enable_meta_ads()
        self.assertEqual(connect.scopes(), connect.SCOPES + connect.ADS_SCOPES)
        url = connect.login_url(self.project, MANAGER)
        self.assertIn("ads_management", url)
        self.assertIn("ads_read", url)

    def test_allowing_ads_keeps_the_user_token_for_the_ad_account(self):
        self.sign_in(*connect.SCOPES, *connect.ADS_SCOPES)
        with FakeGraph(SIGN_IN).patch():
            run_as_user(MANAGER, lambda: meta_api.select_page(self.project, "page-1"))
        connection = frappe.get_doc("HD Meta Connection", self.project)
        self.assertTrue(connection.ads_allowed)
        self.assertEqual(connection.user_token(), "long-lived")

    def test_declining_ads_still_connects_without_keeping_the_token(self):
        self.sign_in(*connect.SCOPES)
        with FakeGraph(SIGN_IN).patch():
            run_as_user(MANAGER, lambda: meta_api.select_page(self.project, "page-1"))
        connection = frappe.get_doc("HD Meta Connection", self.project)
        self.assertFalse(connection.ads_allowed)
        self.assertFalse(
            get_decrypted_password(
                "HD Meta Connection",
                self.project,
                "user_access_token",
                raise_exception=False,
            )
        )
        self.assertIn("Reconnect Meta to allow ads", ads.ads_blocker(connection))

    def test_missing_posting_permissions_still_refuse_the_sign_in(self):
        with self.assertRaises(frappe.ValidationError):
            self.sign_in("pages_show_list", *connect.ADS_SCOPES)

    def test_the_ad_account_pick_stores_currency_and_status(self):
        with FakeGraph(SIGN_IN).patch():
            accounts = run_as_user(
                MANAGER, lambda: meta_ads.list_ad_accounts(self.project)
            )
            self.assertEqual(
                [(a["id"], a["currency"], a["status"], a["usable"]) for a in accounts],
                [
                    ("act_100", "INR", "Active", True),
                    ("act_200", "USD", "Disabled", False),
                ],
            )
            self.assertNotIn("token", str(accounts))
            summary = run_as_user(
                MANAGER, lambda: meta_ads.select_ad_account(self.project, "act_100")
            )
            self.assertEqual(summary["ad_account_currency"], "INR")
            with self.assertRaises(frappe.ValidationError):
                run_as_user(
                    MANAGER, lambda: meta_ads.select_ad_account(self.project, "act_999")
                )

    def test_a_connection_without_ads_permission_says_to_reconnect(self):
        frappe.db.set_value("HD Meta Connection", self.project, "ads_allowed", 0)
        state = run_as_user(MANAGER, lambda: meta_ads.get_boost_state(self.post.name))
        self.assertTrue(state["needs_reconnect"])
        self.assertEqual(state["blocked_reason"], "Reconnect Meta to allow ads.")
        graph = FakeGraph(ads_graph_routes())
        with graph.patch(), self.assertRaises(frappe.ValidationError):
            run_as_user(
                MANAGER, lambda: meta_ads.submit(self.post.name, boost_values())
            )
        self.assertEqual(graph.calls, [])

    def test_only_a_system_manager_or_the_head_changes_the_cap(self):
        for user in (MANAGER, MEMBER):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(user, lambda: meta_ads.set_monthly_cap(self.project, 500))
        run_as_user(HEAD, lambda: meta_ads.set_monthly_cap(self.project, 5000))
        self.assertEqual(
            frappe.db.get_value("HD Meta Connection", self.project, "monthly_ad_cap"),
            5000,
        )


class TestBoostLaunch(AdsCase):
    def test_a_boost_is_built_paused_and_switched_on_last(self):
        result, graph = self.boost()
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["total_budget"], 2500)
        posts = [(p, params) for m, p, params in graph.calls if m == "POST"]
        paths = [p for p, _params in posts]
        self.assertEqual(
            paths,
            [
                "act_100/campaigns",
                "act_100/adsets",
                "act_100/ads",
                "a-300",
                "s-200",
                "c-100",
            ],
        )
        campaign, adset, ad = (params for _p, params in posts[:3])
        self.assertEqual(
            [campaign["status"], adset["status"], ad["status"]], ["PAUSED"] * 3
        )
        self.assertEqual(campaign["objective"], "OUTCOME_AWARENESS")
        self.assertEqual(adset["optimization_goal"], "REACH")
        self.assertEqual(adset["daily_budget"], 50000)
        self.assertNotIn("lifetime_budget", adset)
        self.assertIn('"object_story_id": "page-1_555"', ad["creative"])
        self.assertIn('"regions": [{"key": "1234"}]', adset["targeting"])
        self.assertIn('"advantage_audience": 1', adset["targeting"])
        self.assertTrue(all(params["status"] == "ACTIVE" for _p, params in posts[3:]))
        self.assertEqual(
            frappe.db.get_value("HD Content Post", self.post.name, "meta_boosted"), 1
        )
        self.assertTrue(any("started a boost" in line for line in self.timeline()))

    def test_an_instagram_post_is_the_creative_by_its_media_id(self):
        _result, graph = self.boost(target="Instagram", goal="More messages")
        params = dict((p, q) for m, p, q in graph.calls if m == "POST")
        self.assertIn(
            '"source_instagram_media_id": "ig-media-9"',
            params["act_100/ads"]["creative"],
        )
        self.assertEqual(
            params["act_100/adsets"]["destination_type"], "INSTAGRAM_DIRECT"
        )
        self.assertEqual(params["act_100/adsets"]["optimization_goal"], "CONVERSATIONS")
        self.assertEqual(params["act_100/campaigns"]["objective"], "OUTCOME_ENGAGEMENT")

    def test_a_total_budget_is_sent_as_a_lifetime_budget(self):
        _result, graph = self.boost(budget_type="Total", budget_amount=1500)
        adset = dict((p, q) for m, p, q in graph.calls if m == "POST")["act_100/adsets"]
        self.assertEqual(adset["lifetime_budget"], 150000)
        self.assertNotIn("daily_budget", adset)

    def test_website_visits_need_a_link_on_the_post(self):
        with FakeGraph(ads_graph_routes()).patch():
            with self.assertRaises(frappe.ValidationError):
                run_as_user(
                    MANAGER,
                    lambda: meta_ads.submit(
                        self.post.name, boost_values(goal="More website visits")
                    ),
                )

    def test_a_post_cannot_be_boosted_twice_at_once(self):
        self.boost()
        with FakeGraph(ads_graph_routes()).patch(), self.assertRaises(
            frappe.ValidationError
        ):
            run_as_user(
                MANAGER, lambda: meta_ads.submit(self.post.name, boost_values())
            )

    def test_only_a_published_post_can_be_boosted_on_that_network(self):
        frappe.db.delete(
            "HD Content Publish", {"parent": self.post.name, "target": "Instagram"}
        )
        with FakeGraph(ads_graph_routes()).patch(), self.assertRaises(
            frappe.ValidationError
        ):
            run_as_user(
                MANAGER,
                lambda: meta_ads.submit(
                    self.post.name, boost_values(target="Instagram")
                ),
            )

    def test_the_preview_is_plain_and_the_estimate_is_optional(self):
        routes = ads_graph_routes(
            **{
                "GET act_100/delivery_estimate": {
                    "data": [
                        {
                            "estimate_mau_lower_bound": 12000,
                            "estimate_mau_upper_bound": 35000,
                        }
                    ]
                }
            }
        )
        with FakeGraph(routes).patch():
            shown = run_as_user(
                MANAGER, lambda: meta_ads.preview(self.post.name, boost_values())
            )
        self.assertIn("₹ 2,500.00 total", shown["summary"])
        self.assertIn("5 days", shown["summary"])
        self.assertIn("Kerala, 18–55", shown["summary"])
        self.assertIn("12,000 to 35,000", shown["summary"])
        self.assertFalse(shown["over_cap"])
        with FakeGraph(ads_graph_routes()).patch():
            shown = run_as_user(
                MANAGER, lambda: meta_ads.preview(self.post.name, boost_values())
            )
        self.assertNotIn("estimated reach", shown["summary"])


class TestBoostGuards(AdsCase):
    def test_a_boost_past_the_monthly_cap_is_refused_before_anything_is_sent(self):
        frappe.db.set_value("HD Meta Connection", self.project, "monthly_ad_cap", 2000)
        graph = FakeGraph(ads_graph_routes())
        with graph.patch(), self.assertRaises(frappe.ValidationError) as caught:
            run_as_user(
                MANAGER, lambda: meta_ads.submit(self.post.name, boost_values())
            )
        self.assertIn("limit", str(caught.exception))
        self.assertEqual(graph.calls, [])

    def test_the_cap_counts_boosts_already_planned_this_month(self):
        frappe.db.set_value("HD Meta Connection", self.project, "monthly_ad_cap", 3000)
        self.boost()
        other = make_approved_post("Second offer", CUSTOMER)
        publish_post_on_meta(other.name, "Facebook")
        with FakeGraph(ads_graph_routes()).patch(), self.assertRaises(
            frappe.ValidationError
        ) as caught:
            run_as_user(
                MANAGER,
                lambda: meta_ads.submit(other.name, boost_values(budget_amount=200)),
            )
        self.assertIn("500", str(caught.exception))

    def test_a_boost_that_just_fits_is_allowed(self):
        frappe.db.set_value("HD Meta Connection", self.project, "monthly_ad_cap", 2500)
        result, _graph = self.boost()
        self.assertEqual(result["status"], "Active")

    def test_an_editor_asks_for_approval_and_nothing_goes_to_meta(self):
        result, graph = self.boost(user=EDITOR)
        self.assertEqual(result["status"], "Pending approval")
        self.assertEqual(graph.calls, [])
        users = self.notify.call_args[0][0]
        self.assertIn(HEAD, users)
        self.assertIn("Approve or reject", self.notify.call_args[0][3])

    def test_the_head_approves_and_it_goes_live_with_a_notice(self):
        pending, _graph = self.boost(user=EDITOR)
        self.notify.reset_mock()
        graph = FakeGraph(ads_graph_routes())
        with graph.patch():
            result = run_as_user(HEAD, lambda: meta_ads.approve(pending["name"]))
        self.assertEqual(result["status"], "Active")
        self.assertEqual(
            frappe.db.get_value("HD Meta Boost", pending["name"], "approved_by"), HEAD
        )
        self.assertEqual(
            graph.paths("POST")[:3],
            ["act_100/campaigns", "act_100/adsets", "act_100/ads"],
        )
        self.assertIn(EDITOR, self.notify.call_args[0][0])
        self.assertIn("live", self.notify.call_args[0][3])

    def test_the_cap_is_checked_again_when_the_head_approves(self):
        pending, _graph = self.boost(user=EDITOR)
        frappe.db.set_value("HD Meta Connection", self.project, "monthly_ad_cap", 100)
        graph = FakeGraph(ads_graph_routes())
        with graph.patch(), self.assertRaises(frappe.ValidationError):
            run_as_user(HEAD, lambda: meta_ads.approve(pending["name"]))
        self.assertEqual(graph.calls, [])

    def test_a_rejected_request_never_reaches_meta(self):
        pending, graph = self.boost(user=EDITOR)
        result = run_as_user(
            HEAD, lambda: meta_ads.reject(pending["name"], "Too much for now")
        )
        self.assertEqual(result["status"], "Rejected")
        self.assertEqual(graph.calls, [])
        with FakeGraph(ads_graph_routes()).patch(), self.assertRaises(
            frappe.ValidationError
        ):
            run_as_user(HEAD, lambda: meta_ads.approve(pending["name"]))

    def test_an_editor_cannot_spend_or_change_a_boost(self):
        result, _graph = self.boost()
        for call in (meta_ads.approve, meta_ads.pause, meta_ads.resume, meta_ads.stop):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(EDITOR, lambda: call(result["name"]))
        self.assertEqual(
            frappe.db.get_value("HD Meta Boost", result["name"], "status"), "Active"
        )

    def test_a_member_who_cannot_edit_the_post_cannot_boost_it(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(MEMBER, lambda: meta_ads.get_boost_state(self.post.name))

    def test_a_sales_employee_sees_and_does_nothing(self):
        for call in (
            lambda: meta_ads.get_boost_state(self.post.name),
            lambda: meta_ads.submit(self.post.name, boost_values()),
            lambda: meta_ads.get_project_ads(self.project),
        ):
            with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
                run_as_user(SALES, call)

    def test_the_ads_tab_is_for_whoever_handles_the_clients_accounts(self):
        self.boost()
        for user in (MANAGER, HEAD):
            tab = run_as_user(user, lambda: meta_ads.get_project_ads(self.project))
            self.assertEqual(len(tab["boosts"]), 1)
            self.assertEqual(tab["spend"]["planned"], 2500)
            self.assertEqual(tab["spend"]["left"], 7500)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(EDITOR, lambda: meta_ads.get_project_ads(self.project))

    def test_ads_switched_off_in_settings_blocks_a_boost(self):
        frappe.db.set_single_value("HD Meta Settings", "ads_enabled", 0)
        frappe.clear_cache(doctype="HD Meta Settings")
        with FakeGraph(ads_graph_routes()).patch(), self.assertRaises(
            frappe.ValidationError
        ):
            run_as_user(
                MANAGER, lambda: meta_ads.submit(self.post.name, boost_values())
            )

    def test_disconnecting_is_refused_while_a_boost_runs(self):
        self.boost()
        with self.assertRaises(frappe.ValidationError):
            run_as_user(MANAGER, lambda: meta_api.disconnect(self.project))


class TestBoostLifecycle(AdsCase):
    def test_insights_fill_in_spend_reach_and_cost_per_result(self):
        result, _graph = self.boost(goal="More engagement")
        with FakeGraph(ads_graph_routes()).patch():
            boost = ads.sync_boost(result["name"])
        self.assertEqual(
            (boost.spend, boost.reach, boost.impressions, boost.clicks, boost.results),
            (120.5, 4000, 5200, 80, 60),
        )
        self.assertAlmostEqual(boost.cost_per_result, 120.5 / 60)
        self.assertEqual(boost.meta_status, "Running")
        self.assertTrue(boost.last_synced)

    def test_the_hourly_job_syncs_running_boosts_and_survives_a_bad_one(self):
        first, _graph = self.boost()
        other = make_approved_post("Second offer", CUSTOMER)
        publish_post_on_meta(other.name, "Facebook")
        with FakeGraph(ads_graph_routes()).patch():
            run_as_user(
                MANAGER,
                lambda: meta_ads.submit(other.name, boost_values(budget_amount=100)),
            )
        frappe.db.set_value("HD Meta Boost", first["name"], "ad_id", "broken")
        failing = FakeGraph(
            {
                **ads_graph_routes(),
                "GET broken": {
                    "_status": 400,
                    "error": {"code": 100, "message": "bad"},
                },
            }
        )
        with failing.patch(), patch("frappe.log_error") as log_error:
            ads.sync_active_boosts()
        log_error.assert_called_once()
        spent = frappe.get_all(
            "HD Meta Boost", filters={"spend": [">", 0]}, pluck="name"
        )
        self.assertEqual(len(spent), 1)

    def test_pause_resume_and_stop_change_the_campaign_on_meta(self):
        result, _graph = self.boost()
        name = result["name"]
        graph = FakeGraph(ads_graph_routes())
        with graph.patch():
            self.assertEqual(
                run_as_user(MANAGER, lambda: meta_ads.pause(name))["status"], "Paused"
            )
            self.assertEqual(
                run_as_user(MANAGER, lambda: meta_ads.resume(name))["status"], "Active"
            )
            stopped = run_as_user(MANAGER, lambda: meta_ads.stop(name))
        statuses = [
            p["status"] for m, path, p in graph.calls if m == "POST" and path == "c-100"
        ]
        self.assertEqual(statuses, ["PAUSED", "ACTIVE", "ARCHIVED"])
        self.assertEqual(stopped["status"], "Completed")
        self.assertEqual(stopped["meta_status"], "Stopped")
        # the final numbers were read once, and a stopped boost counts what it spent
        self.assertEqual(stopped["spend"], 120.5)
        self.assertEqual(ads.planned_this_month(self.project), 120.5)
        lines = " ".join(self.timeline())
        for word in ("paused", "resumed", "stopped"):
            self.assertIn(word, lines)
        with self.assertRaises(frappe.ValidationError):
            run_as_user(MANAGER, lambda: meta_ads.pause(name))

    def test_a_pause_made_in_ads_manager_is_followed(self):
        result, _graph = self.boost()
        routes = ads_graph_routes(
            **{"GET a-300": {"effective_status": "CAMPAIGN_PAUSED"}}
        )
        with FakeGraph(routes).patch():
            boost = ads.sync_boost(result["name"])
        self.assertEqual((boost.status, boost.meta_status), ("Paused", "Paused"))

    def test_a_boost_past_its_end_date_is_completed(self):
        result, _graph = self.boost()
        frappe.db.set_value(
            "HD Meta Boost", result["name"], "end_date", add_days(today(), -1)
        )
        with FakeGraph(ads_graph_routes()).patch():
            self.assertEqual(ads.sync_boost(result["name"]).status, "Completed")


class TestMetaRefusals(AdsCase):
    def refused(self, error: dict, **values):
        routes = ads_graph_routes(
            **{"POST act_100/adsets": {"_status": 400, "error": error}}
        )
        result, graph = self.boost(routes=routes, **values)
        return result, graph

    def test_a_refusal_when_creating_is_shown_and_nothing_is_switched_on(self):
        result, graph = self.refused({"code": 100, "message": "Invalid parameter"})
        self.assertEqual(result["status"], "Failed")
        self.assertIn("Invalid parameter", result["failure_reason"])
        self.assertFalse(any(p.get("status") == "ACTIVE" for _m, _p, p in graph.calls))
        self.assertEqual(
            frappe.db.get_value("HD Content Post", self.post.name, "meta_boosted"), 0
        )
        self.assertTrue(any("didn't start" in line for line in self.timeline()))
        self.assertIn("didn't start", self.notify.call_args[0][3])

    def test_a_missing_payment_method_is_explained(self):
        result, _graph = self.refused(
            {"code": 100, "message": "No payment method on the account"}
        )
        self.assertIn("payment method", result["failure_reason"])
        self.assertIn("adds one", result["failure_reason"])

    def test_no_access_to_the_ad_account_says_what_to_do(self):
        result, _graph = self.refused(
            {"code": 200, "message": "Requires ads_management"}
        )
        self.assertIn("partner", result["failure_reason"])
        self.assertIn("advertiser role", result["failure_reason"])

    def test_an_expired_token_marks_the_connection(self):
        self.refused({"code": 190, "message": "expired"})
        self.assertEqual(
            frappe.db.get_value("HD Meta Connection", self.project, "status"), "Expired"
        )

    def test_a_failed_launch_does_not_count_against_the_cap(self):
        self.refused({"code": 100, "message": "Invalid parameter"})
        self.assertEqual(ads.planned_this_month(self.project), 0)

    def test_an_ad_meta_does_not_approve_shows_the_reason_in_plain_words(self):
        result, _graph = self.boost()
        routes = ads_graph_routes(
            **{
                "GET a-300": {
                    "effective_status": "DISAPPROVED",
                    "ad_review_feedback": {"global": {"Adult_Content": "code 1"}},
                }
            }
        )
        with FakeGraph(routes).patch():
            boost = ads.sync_boost(result["name"])
        self.assertEqual(boost.status, "Failed")
        self.assertIn("adult content", boost.failure_reason)
        self.assertIn("boost again", boost.failure_reason)
        self.assertIn(
            self.notify.call_args[0][3].split(": ", 1)[1], boost.failure_reason
        )
