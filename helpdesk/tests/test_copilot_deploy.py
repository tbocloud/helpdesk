# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Deploying a merged Copilot fix through Press (Phase 2): when, where, one at a time, and the check after."""

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_system_timezone

from helpdesk.api import copilot as api
from helpdesk.copilot import deploy, fixes
from helpdesk.test_utils import (
    FakePress,
    make_hd_pull_request,
    make_site_registry,
    make_support_connection,
    site_tool_replies,
)
from helpdesk.tests.test_copilot_fix_flow import REPO, SHA, FixCase

MERGED = "m" + SHA
OLD = "o" * 40
REVERT_HEAD = "r" * 40
REVERTED = "m" + REVERT_HEAD  # the fake GitHub merges a head as "m" + its sha


def riyadh(hour: int, minute: int = 0, days: int = 0) -> datetime:
    """Today (plus `days`) at hour:minute in Riyadh, as the site's own naive time."""
    local = datetime.now(ZoneInfo("Asia/Riyadh")).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ) + timedelta(days=days)
    return local.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


class DeployCase(FixCase):
    sites = ("site1.example.com",)
    auto = ""  # Auto-deploy categories

    def setUp(self):
        super().setUp()
        frappe.cache().delete(deploy._lock_key())
        self.addCleanup(lambda: frappe.cache().delete(deploy._lock_key()))
        self.settings(
            shadow_mode=0,
            press_url="https://press.example.com",
            press_api_key="k",
            press_api_secret="s",
            auto_deploy_categories=self.auto,
        )
        make_site_registry(
            self.customer,
            press_site="site1.example.com",
            press_release_group="bench-1",
            apps=[
                {
                    "app": "demo_app",
                    "repository": f"https://github.com/{REPO}",
                    "branch": "main",
                    "deployed_commit": OLD,
                }
            ],
        )
        self.press = FakePress(sites=self.sites, next_hash=MERGED).install(self)
        self.diagnosed()
        self.opened()
        self.decide(self.approver)
        self.assertEqual(self.current_run().state, "Merged")

    def at(self, moment):
        return patch("helpdesk.copilot.deploy.now_datetime", return_value=moment)

    def request(self, user, when="tonight", moment=None):
        """Tonight is asked for in the afternoon; Now at 22:00, inside the window."""
        moment = moment or (riyadh(14) if when == "tonight" else riyadh(22))
        self.clock = max(getattr(self, "clock", moment), moment)
        with self.at(moment):
            return deploy.request_deploy(self.current_run(), when, user)

    def cron(self, moment=None):
        """The five-minute cron; without a time, five minutes after the last step."""
        self.clock = moment or getattr(self, "clock", riyadh(22)) + timedelta(minutes=5)
        with self.at(self.clock):
            deploy.run_due()

    def checked_site(
        self,
        commit=MERGED,
        errors=None,
        known=None,
        scheduler=True,
        answers=None,
        refuse=(),
    ):
        """The customer's site as the check after the deploy reads it; `refuse` lists tools it does not answer."""
        connection = make_support_connection(self.customer).name
        self.current_run().db_set("connection", connection, update_modified=False)
        replies = {
            "get_code_identity": [{"app": "demo_app", "commit": commit}],
            "get_deploy_status": {
                "scheduler_enabled": scheduler,
                "maintenance_mode": False,
                "errors": {"top": [{"signature": s, "count": 1} for s in errors or []]},
            },
            "get_error_log": known or [],
            **(answers or {}),
        }
        for tool in refuse:
            replies.pop(tool)
        client = patch("helpdesk.mcp_client.MCPClient")
        mocked = client.start()
        self.addCleanup(client.stop)
        mocked.return_value.call_tool.side_effect = site_tool_replies(replies)


class TestWhenAndWhere(DeployCase):
    def test_tonight_waits_for_the_window_then_updates_only_the_customers_site(self):
        request = self.request(self.approver)
        self.assertEqual(request.status, "Scheduled")
        self.assertIn("21:00", deploy.local_time(request.scheduled_for))
        self.assertIn("21:00", self.events("stage")[-1]["message"])

        self.cron(riyadh(14, 5))
        self.assertEqual(self.press.deploys, [])

        self.cron(riyadh(21, 5))
        sent = self.press.deploys[0]
        self.assertEqual(
            [site["name"] for site in sent["sites"]], ["site1.example.com"]
        )
        self.assertFalse(sent["sites"][0]["skip_backups"])
        self.assertEqual(sent["apps"][0]["hash"], MERGED)
        self.assertEqual(self.current_run().state, "Deploying")

    def test_now_is_for_seniors_and_managers(self):
        with self.assertRaises(frappe.PermissionError):
            self.request(self.approver, "now")
        self.request(self.senior, "now")
        self.cron()
        self.assertEqual(len(self.press.deploys), 1)

    def test_the_merged_commit_must_reach_press_first(self):
        self.press.apps[0]["next_hash"] = OLD
        self.press.on_fetch = lambda: self.press.apps[0].update(next_hash=MERGED)
        self.request(self.senior, "now")

        self.cron()
        self.assertEqual(self.press.fetched, ["demo_app"])
        self.assertEqual(
            frappe.get_doc(deploy.DEPLOY, self.current_run().deploy_request).status,
            "Waiting for Press",
        )

        self.cron()
        self.assertEqual(len(self.press.deploys), 1)

    def test_one_deploy_at_a_time(self):
        self.assertTrue(deploy._take_lock("TBO-DEP-OTHER"))
        self.request(self.senior, "now")
        self.cron()
        request = frappe.get_doc(deploy.DEPLOY, self.current_run().deploy_request)
        self.assertEqual(request.status, "Waiting for Press")
        self.assertIn("another Copilot deploy", request.error)
        self.assertEqual(self.press.deploys, [])

    def test_a_deploy_that_cannot_start_moves_to_the_next_window(self):
        self.press.deploy_in_progress = True
        self.request(self.senior, "now", riyadh(22))
        self.cron(riyadh(22))
        request = frappe.get_doc(deploy.DEPLOY, self.current_run().deploy_request)
        self.assertEqual(request.status, "Waiting for Press")

        self.cron(riyadh(23, 30))
        request.reload()
        self.assertEqual(request.status, "Scheduled")
        self.assertGreater(request.scheduled_for, riyadh(23, 30))
        self.assertIn("already deploying", request.error)

    def test_cancel_before_it_starts_and_mark_deployed_waits_for_it(self):
        self.request(self.approver)
        with self.assertRaises(frappe.ValidationError):
            fixes.mark_deployed(self.current_run(), self.approver)
        deploy.cancel_deploy(self.current_run(), self.approver)
        self.assertEqual(
            fixes.mark_deployed(self.current_run(), self.approver).state, "Resolved"
        )

    def test_the_card_offers_deploy_and_shows_it(self):
        frappe.set_user(self.senior)
        fix = api.get_run(self.ticket.name)["fix"]
        self.assertTrue(fix["can_deploy"] and fix["can_deploy_now"])
        with self.at(riyadh(14)):
            fix = api.request_deploy(self.ticket.name, "tonight")["fix"]
        self.assertEqual(
            (fix["deploy"]["status"], fix["deploy"]["can_cancel"]), ("Scheduled", True)
        )
        self.assertFalse(fix["can_deploy"] or fix["can_mark_deployed"])

    def test_skip_presss_backup_on_a_test_bench(self):
        self.settings(press_skip_backups=1)
        frappe.set_user(self.senior)
        self.assertFalse(api.get_run(self.ticket.name)["fix"]["press_backups"])
        self.request(self.senior, "now")
        self.cron()
        self.assertTrue(self.press.deploys[0]["sites"][0]["skip_backups"])
        self.assertFalse(self.events("deploy_started")[-1]["backups"])


class TestSharedBench(DeployCase):
    sites = ("site1.example.com", "other-customer.example.com")

    def test_another_site_on_the_bench_needs_a_senior_and_is_left_alone(self):
        with self.assertRaises(frappe.PermissionError) as caught:
            self.request(self.approver)
        self.assertIn("other-customer.example.com", str(caught.exception))
        self.request(self.senior, "now")
        self.cron()
        self.assertEqual(
            [site["name"] for site in self.press.deploys[0]["sites"]],
            ["site1.example.com"],
        )


class TestAutomaticDeploys(DeployCase):
    auto = "low"

    def test_a_listed_low_risk_fix_is_scheduled_for_the_window_by_itself(self):
        request = frappe.get_doc(deploy.DEPLOY, self.current_run().deploy_request)
        self.assertEqual(
            (request.when, request.status, request.requested_by),
            ("Tonight", "Scheduled", self.approver),
        )
        self.assertTrue(self.events("deploy_requested")[-1]["auto"])

    def test_never_a_sensitive_or_high_risk_fix_nor_an_undo(self):
        deploy.cancel_deploy(self.current_run(), self.approver)
        run = self.current_run()
        for approval in (
            frappe._dict(risk_level="high", sensitive=0, decided_by=self.approver),
            frappe._dict(risk_level="low", sensitive=1, decided_by=self.approver),
        ):
            self.assertIsNone(deploy.auto_request(run, approval))
        run.kind = "revert"
        self.assertIsNone(deploy.auto_request(run, self.approval()))
        self.assertFalse(deploy.open_request(run))


class TestNoAutomaticDeployOnASharedBench(DeployCase):
    sites = ("site1.example.com", "other-customer.example.com")
    auto = "low"

    def test_a_shared_bench_waits_for_a_person(self):
        self.assertFalse(self.current_run().deploy_request)
        self.assertIn(
            "share this bench", self.events("auto_deploy_skipped")[-1]["reason"]
        )


class TestTheHubOnTheBench(DeployCase):
    """TBO Support's own site shares the customer's bench, as on TBO's demo bench."""

    auto = "low"

    @property
    def sites(self):
        return ("site1.example.com", frappe.local.site)

    def test_it_is_no_other_customer_and_never_moves(self):
        request = frappe.get_doc(deploy.DEPLOY, self.current_run().deploy_request)
        self.assertEqual(
            (request.requested_by, request.other_sites),
            (self.approver, frappe.local.site),
        )
        self.cron(riyadh(21, 5))
        self.assertEqual(
            [site["name"] for site in self.press.deploys[0]["sites"]],
            ["site1.example.com"],
        )

    def test_a_card_naming_it_is_refused(self):
        run = self.current_run()
        deploy.cancel_deploy(run, self.approver)
        frappe.db.set_value(
            "HDS Site Registry", run.registry, "press_site", frappe.local.site
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            self.request(self.senior, "now")
        self.assertIn("TBO Support itself", str(caught.exception))


class TestTheCheckAfter(DeployCase):
    def deployed(self):
        self.request(self.senior, "now")
        self.cron()
        self.press.finish("Success")
        self.cron()
        self.assertEqual(self.current_run().state, "Verifying")

    def test_a_clean_check_resolves_the_run_and_tells_the_customer(self):
        self.checked_site(
            errors=["helpdesk_client | helpdesk_client.mcp.handle | noise"]
        )
        self.deployed()
        self.cron()

        run = self.current_run()
        request = frappe.get_doc(deploy.DEPLOY, run.deploy_request)
        self.assertEqual((request.status, run.state), ("Succeeded", "Resolved"))
        self.assertEqual(self.events("stage")[-1]["stage"], "Resolved")
        self.assertIn("The fix is live", self.events("stage")[-1]["message"])
        self.assertTrue(deploy._take_lock("TBO-DEP-NEXT"))  # released

    def test_a_new_error_after_the_deploy_escalates_it(self):
        self.checked_site(
            errors=[
                "demo_app | demo_app.invoice.validate | ZeroDivisionError",
                "demo_app | old.job | KeyError",
            ],
            known=[
                {"app": "demo_app", "method": "old.job", "error": "Traceback\nKeyError"}
            ],
        )
        self.deployed()
        self.cron()

        run = self.current_run()
        request = frappe.get_doc(deploy.DEPLOY, run.deploy_request)
        self.assertEqual((request.status, run.state), ("Failed", "Escalated"))
        self.assertIn("ZeroDivisionError", request.error)
        self.assertNotIn("KeyError", request.error)

    def test_the_site_not_running_the_merged_commit_escalates_it(self):
        self.checked_site(commit=OLD)
        self.deployed()
        self.cron()
        self.assertEqual(self.current_run().state, "Escalated")

    def test_a_failed_build_escalates_at_once_with_presss_build(self):
        self.request(self.senior, "now")
        self.cron()
        self.press.fail_build()
        self.cron()

        run = self.current_run()
        request = frappe.get_doc(deploy.DEPLOY, run.deploy_request)
        self.assertEqual((request.status, run.state), ("Failed", "Escalated"))
        self.assertIn(
            "https://press.example.com/app/deploy-candidate-build/DCB-1", request.error
        )

    def test_a_failed_site_update_escalates_with_presss_reason(self):
        self.request(self.senior, "now")
        self.cron()
        self.press.finish("Recovered")
        self.cron()

        run = self.current_run()
        request = frappe.get_doc(deploy.DEPLOY, run.deploy_request)
        self.assertEqual((request.status, run.state), ("Failed", "Escalated"))
        self.assertIn("Recovered", request.error)
        self.assertTrue(any("failed" in str(call[3]) for call in self.notified))
        # the people told find Press's update and the backup Press took first
        self.assertEqual(request.sites[0].backup, "BKP-1")
        note = frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": self.ticket.name},
            pluck="content",
            order_by="creation desc",
            limit=1,
        )[0]
        self.assertIn("https://press.example.com/app/site-update/SU-1", note)
        self.assertIn("BKP-1", note)


class TestUndo(DeployCase):
    def failed_deploy(self):
        self.request(self.senior, "now")
        self.cron()
        self.press.finish("Recovered")
        self.cron()
        self.assertEqual(self.current_run().state, "Escalated")
        return self.current_run()

    def test_undo_reverts_through_the_one_approval_and_a_deploy_without_telling_the_customer(
        self,
    ):
        fixed = self.failed_deploy()
        with self.assertRaises(frappe.ValidationError):
            fixes.undo(fixed, self.senior, "  ")

        revert = fixes.undo(fixed, self.senior, "the invoice page broke")

        # GitHub's own revert of the merged pull request, closing the undo's own task
        self.assertEqual(self.github.reverted, [(REPO, 7)])
        number = max(n for (_repo, n) in self.github.pulls)
        pull = self.github.pulls[(REPO, number)]
        task = frappe.get_doc("Task", revert.task)
        self.assertTrue(task.subject.startswith(fixes.REVERT_TASK_PREFIX))
        self.assertIn(f"Closes {task.name}", pull["body"])
        self.assertIn(f"Copilot-Run: {revert.name}", pull["body"])
        self.assertEqual(
            (revert.kind, revert.reverts, revert.state),
            ("revert", fixed.name, "Preparing Fix"),
        )
        self.assertEqual(self.current_run().name, revert.name)  # the card follows it
        self.assertFalse(fixes.can_undo(frappe.get_doc("HDS Copilot Run", fixed.name)))

        # Phase 1d follows the revert: the one approval, then the merge
        row = make_hd_pull_request(task.name, REPO, number, REVERT_HEAD)
        fixes.on_pull_request(pull, "opened", [row])
        self.assertEqual(self.current_run().state, "Awaiting Approval")
        self.decide(self.approver)
        self.assertEqual(
            (self.current_run().state, self.current_run().merge_commit),
            ("Merged", REVERTED),
        )

        # and Deploy, now; the customer hears nothing from the undo
        self.press.apps[0]["next_hash"] = REVERTED
        self.checked_site(commit=REVERTED)
        self.request(self.senior, "now")
        self.cron()
        self.assertEqual(self.press.deploys[-1]["apps"][0]["hash"], REVERTED)
        self.press.finish("Success")
        self.cron()
        self.cron()

        self.assertEqual(self.current_run().state, "Resolved")
        stages = self.events("stage")
        self.assertTrue(stages)
        self.assertFalse(any(stage["pushed"] for stage in stages))
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", fixed.name, "state"), "Escalated"
        )

    def test_the_card_offers_undo_to_approvers_after_a_failed_deploy(self):
        fixed = self.failed_deploy()
        frappe.set_user(self.approver)
        self.assertTrue(api.get_run(self.ticket.name)["fix"]["can_undo"])

        fix = api.undo_fix(self.ticket.name, "the invoice page broke")["fix"]

        self.assertEqual(fix["reverts"], fixed.name)
        self.assertFalse(fix["can_undo"])
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.ValidationError):
            fixes.undo(fixed, self.senior, "again")
