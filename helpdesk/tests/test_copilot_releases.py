# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Releases (Phase 7): every merge into a branch a customer site runs goes out the same way."""

import json
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import copilot as api
from helpdesk.api import copilot_worker
from helpdesk.copilot import assistant, deploy, releases
from helpdesk.test_utils import (
    FakeGitHub,
    FakePress,
    create_agent,
    create_customer,
    hold_commits,
    make_copilot_run,
    make_copilot_settings,
    make_customer_project,
    make_site_registry,
    make_support_connection,
    make_task,
    make_ticket,
    site_tool_replies,
)

REPO = "tbocloud/demo-app"
RUNNING = "o" * 40  # what the bench runs before any release
A, B, C = "a" * 40, "b" * 40, "c" * 40


def head(sha: str) -> str:
    """The last commit of the pull request that `sha` merged."""
    return "h" + sha[1:]


class ReleaseCase(FrappeTestCase):
    sites = ("site1.example.com",)

    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.cache().delete_value(releases.SEEN_KEY)
        self.addCleanup(frappe.cache().delete_value, releases.SEEN_KEY)
        self.approver = create_agent("release.approver@example.com").name
        self.senior = create_agent("release.senior@example.com").name
        self.customer = create_customer("Release Co").name
        self.settings()
        self.card = make_site_registry(
            self.customer,
            press_site="site1.example.com",
            press_release_group="bench-1",
            apps=[self.app_row()],
        )
        self.github = FakeGitHub().install(self)
        self.github.commit(REPO, RUNNING, message="What the bench runs")
        self.press = FakePress(sites=self.sites, current=RUNNING).install(self)

    def settings(self, **values):
        make_copilot_settings(
            **{
                "enabled": 1,
                "releases_enabled": 1,
                "release_staging": 0,
                "release_repositories": f"https://github.com/{REPO}\n",
                "press_url": "https://press.example.com",
                "press_api_key": "k",
                "press_api_secret": "s",
                "approvers": [
                    {"user": self.approver, "senior": 0, "active": 1},
                    {"user": self.senior, "senior": 1, "active": 1},
                ],
                **values,
            }
        )

    @staticmethod
    def app_row(repo: str = REPO, branch: str = "main") -> dict:
        return {
            "app": "demo_app",
            "repository": f"https://github.com/{repo}",
            "branch": branch,
            "deployed_commit": RUNNING,
        }

    def merged(
        self,
        number: int,
        sha: str,
        author: str = "dev-one",
        body: str = "",
        files=None,
    ):
        """A pull request merged into main, landing as commit `sha`; its CI ran (green) on its head, head(sha)."""
        self.github.add_pull(
            REPO,
            number,
            head(sha),
            files=files,
            body=body,
            author=author,
            merged=True,
            state="closed",
        )
        self.github.commit(
            REPO, sha, message=f"Merge #{number}", author=author, pull=number
        )

    def releases_of(self, repo: str = REPO) -> list:
        return [
            frappe.get_doc(deploy.DEPLOY, name)
            for name in frappe.get_all(
                deploy.DEPLOY,
                filters={"repository": repo, "staging_for": ["is", "not set"]},
                order_by="creation asc",
                pluck="name",
            )
        ]

    def only_release(self):
        found = self.releases_of()
        self.assertEqual(len(found), 1)
        return found[0]


class TestReleaseWatch(ReleaseCase):
    def test_a_merged_pull_request_becomes_a_release_waiting_for_ci(self):
        project = make_customer_project(self.customer, "Release Co support")
        task = make_task(project, "Margin report").name
        ticket = make_ticket(subject="Margin wrong", customer=self.customer).name
        frappe.db.set_value("Task", task, "hd_ticket", ticket)
        self.merged(5, A, body=f"Closes {task}")

        releases.watch()

        release = self.only_release()
        self.assertEqual(release.status, "Waiting for CI")
        self.assertEqual(release.ci_status, "Pending")
        self.assertEqual(release.source, "Pull request")
        self.assertFalse(release.run)
        self.assertEqual((release.branch, release.release_group), ("main", "bench-1"))
        self.assertEqual(
            [(s.site, s.customer, s.registry) for s in release.sites],
            [("site1.example.com", self.customer, self.card.name)],
        )
        self.assertEqual(
            (
                release.apps[0].app,
                release.apps[0].from_commit,
                release.apps[0].to_commit,
            ),
            ("demo_app", RUNNING, A),
        )
        self.assertEqual((release.task, release.ticket), (task, ticket))
        self.assertEqual(release.authors, "dev-one")
        self.assertFalse(release.needs_senior)
        change = json.loads(release.changes)[0]
        self.assertEqual((change["sha"], change["pull"]["number"]), (A, 5))

    def test_a_push_without_a_pull_request_needs_a_senior(self):
        self.github.commit(REPO, A, message="hotfix", author="pusher")

        releases.watch()

        release = self.only_release()
        self.assertEqual(release.source, "Push")
        self.assertTrue(release.needs_senior)
        self.assertEqual(release.authors, "pusher")

    def test_other_customers_on_the_bench_need_a_senior(self):
        self.press.sites.append(
            {"name": "other.example.com", "server": "f1", "bench": "bench-1-old"}
        )
        self.merged(5, A)

        releases.watch()

        release = self.only_release()
        self.assertTrue(release.needs_senior)
        self.assertEqual(release.other_sites, "other.example.com")

    def test_later_commits_join_a_release_not_yet_approved(self):
        self.merged(5, A)
        releases.watch()
        frappe.db.set_value(
            deploy.DEPLOY,
            self.only_release().name,
            {
                "status": "Waiting for approval",
                "ci_status": "Passed",
                "approval_hash": "h",
            },
        )
        self.merged(6, B, author="dev-two")

        releases.watch()

        release = self.only_release()
        self.assertEqual(release.status, "Waiting for CI")
        self.assertEqual(release.ci_status, "Pending")
        self.assertFalse(release.approval_hash)
        self.assertEqual(
            (release.apps[0].from_commit, release.apps[0].to_commit), (RUNNING, B)
        )
        self.assertEqual([c["sha"] for c in json.loads(release.changes)], [A, B])
        self.assertEqual(release.authors.splitlines(), ["dev-one", "dev-two"])

    def test_an_approved_release_is_followed_by_a_new_one(self):
        self.merged(5, A)
        releases.watch()
        frappe.db.set_value(
            deploy.DEPLOY, self.only_release().name, "status", "Scheduled"
        )
        self.merged(6, B)

        releases.watch()

        first, second = self.releases_of()
        self.assertEqual(first.apps[0].to_commit, A)
        self.assertEqual((second.apps[0].from_commit, second.apps[0].to_commit), (A, B))
        self.assertEqual([c["sha"] for c in json.loads(second.changes)], [B])

    def test_copilot_fixes_alone_go_their_own_way(self):
        ticket = make_ticket(subject="Copilot fixed this", customer=self.customer).name
        run = make_copilot_run(ticket, state="Merged")
        frappe.get_doc(
            {
                "doctype": "HDS Copilot Approval",
                "run": run.name,
                "ticket": ticket,
                "kind": "Code Change",
                "status": "Merged",
                "repo": REPO,
                "number": 7,
            }
        ).insert(ignore_permissions=True)
        self.merged(7, A, author="tbo-copilot[bot]")

        releases.watch()
        self.assertEqual(self.releases_of(), [])

        self.merged(8, B)
        releases.watch()

        release = self.only_release()
        self.assertEqual(release.apps[0].from_commit, RUNNING)
        first, second = json.loads(release.changes)
        self.assertEqual((first["run"], second.get("run")), (run.name, None))

    def test_only_listed_repositories_on_production_cards_other_than_the_hub(self):
        make_site_registry(
            self.customer,
            environment="UAT",
            press_site="uat.example.com",
            press_release_group="bench-uat",
            apps=[self.app_row()],
        )
        make_site_registry(
            create_customer("Hub Card Co").name,
            press_site=deploy.hub_site(),
            press_release_group="bench-hub",
            apps=[self.app_row()],
        )
        make_site_registry(
            create_customer("Unlisted Repo Co").name,
            press_site="site3.example.com",
            press_release_group="bench-3",
            apps=[self.app_row(repo="tbocloud/not-listed")],
        )

        found = releases.targets()

        self.assertEqual(list(found), [(REPO, "main", "bench-1")])
        self.assertEqual(
            [s["site"] for s in found[(REPO, "main", "bench-1")]], ["site1.example.com"]
        )

    def test_one_release_per_bench(self):
        other = create_customer("Second Release Co").name
        make_site_registry(
            other,
            press_site="site2.example.com",
            press_release_group="bench-2",
            apps=[self.app_row()],
        )
        self.merged(5, A)

        releases.watch()

        self.assertEqual(
            sorted((r.release_group, r.sites[0].site) for r in self.releases_of()),
            [("bench-1", "site1.example.com"), ("bench-2", "site2.example.com")],
        )

    def test_an_unchanged_tip_is_not_compared_again(self):
        self.merged(5, A)
        releases.watch()
        releases.watch()

        compares = [call for call in self.github.calls if "/compare/" in call[1]]
        self.assertEqual(len(compares), 1)
        self.assertEqual(len(self.releases_of()), 1)

    def test_nothing_new_makes_nothing(self):
        releases.watch()

        self.assertEqual(self.releases_of(), [])

    def test_off_by_default(self):
        self.settings(releases_enabled=0)
        self.merged(5, A)

        releases.watch()

        self.assertEqual(self.releases_of(), [])
        self.assertFalse([c for c in self.github.calls if "/branches/" in c[1]])

    def test_a_branch_github_cannot_read_is_logged_once(self):
        marker = frappe.cache().make_key(f"copilot_release_trouble:{REPO}|main|bench-1")
        frappe.cache().delete(marker)
        self.addCleanup(frappe.cache().delete, marker)
        del self.github.branches[(REPO, "main")]
        logged = {"method": ["like", "Copilot could not read%"]}
        before = frappe.db.count("Error Log", logged)

        releases.watch()
        releases.watch()

        self.assertEqual(frappe.db.count("Error Log", logged) - before, 1)
        self.assertEqual(self.releases_of(), [])


class GateCase(ReleaseCase):
    def setUp(self):
        super().setUp()
        self.notified = []
        patcher = patch(
            "helpdesk.work_reminders.notify_users",
            side_effect=lambda *a, **k: self.notified.append((a, k)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        project = make_customer_project(self.customer, "Release Co support")
        self.task = make_task(project, "Margin report").name
        # the approver wrote it: they are on its task
        frappe.db.set_value("Task", self.task, "_assign", json.dumps([self.approver]))

    def told(self, user: str) -> list[str]:
        return [a[3] for a, _k in self.notified if user in a[0]]

    def waiting(self, sha: str = A, number: int = 5, files=None, checks=None):
        """A merged pull request, the release it makes, and its CI gate; `checks`: its CI instead of green."""
        self.merged(number, sha, body=f"Closes {self.task}", files=files)
        if checks:
            self.github.set_checks(head(sha), checks)
        releases.watch()
        releases.run_due()
        return self.only_release()


class TestCiGate(GateCase):
    def test_green_ci_asks_one_approver_who_wrote_none_of_it(self):
        release = self.waiting()

        self.assertEqual(release.status, "Waiting for approval")
        self.assertEqual(release.ci_status, "Passed")
        self.assertIn("1 checks green on 1 commits", release.ci_detail)
        self.assertEqual(release.assigned_to, self.senior)
        self.assertEqual(release.approval_hash, releases.approval_hash(release))
        self.assertTrue(self.told(self.senior))
        card = frappe.get_all(
            assistant.MESSAGE,
            filters={"release": release.name, "user": self.senior},
            pluck="card",
        )
        self.assertIn("release_approve", card[0])

    def test_red_ci_waits_and_tells_the_people_who_wrote_it_once(self):
        release = self.waiting(checks={"tests": "failure"})

        self.assertEqual(
            (release.status, release.ci_status), ("Waiting for CI", "Failed")
        )
        self.assertIn("tests", release.ci_detail)
        self.assertEqual(len(self.told(self.approver)), 1)
        releases.run_due()
        self.assertEqual(len(self.told(self.approver)), 1)

    def test_ci_still_running_waits(self):
        release = self.waiting(checks={"tests": None})

        self.assertEqual(
            (release.status, release.ci_status), ("Waiting for CI", "Pending")
        )
        self.assertIn("still running", release.ci_detail)

    def test_a_push_without_ci_fails_and_only_a_senior_lets_it_through(self):
        self.github.commit(REPO, A, message="hotfix", author="pusher")
        releases.watch()
        releases.run_due()
        release = self.only_release()
        self.assertEqual(release.ci_status, "Failed")
        self.assertIn("no CI ran on", release.ci_detail)

        with self.assertRaises(frappe.PermissionError):
            releases.override_ci(release, self.approver, "urgent")
        with self.assertRaises(frappe.ValidationError):
            releases.override_ci(release, self.senior, " ")
        releases.override_ci(release, self.senior, "the customer is down")

        release.reload()
        self.assertEqual(release.status, "Waiting for approval")
        self.assertEqual(release.ci_status, "Overridden")
        self.assertEqual(release.ci_override_reason, "the customer is down")
        self.assertTrue(release.needs_senior)
        self.assertEqual(release.assigned_to, self.senior)

    def test_a_sensitive_change_needs_a_senior(self):
        release = self.waiting(
            files=[
                {
                    "filename": "demo_app/hooks.py",
                    "additions": 2,
                    "deletions": 0,
                    "patch": "+doc_events = {}",
                }
            ]
        )

        self.assertEqual(release.risk_level, "high")
        self.assertTrue(release.needs_senior)
        self.assertIn("hooks.py", release.risk_reasons)


class TestDecision(GateCase):
    def test_the_approver_schedules_it_for_the_next_window(self):
        release = self.waiting()

        result = releases.decide(
            release.name, self.senior, True, expected_hash=release.approval_hash
        )

        release.reload()
        self.assertEqual((release.status, release.when), ("Scheduled", "Tonight"))
        self.assertEqual(result["status"], "Scheduled")
        self.assertEqual(
            (release.decided_by, release.requested_by), (self.senior, self.senior)
        )
        self.assertTrue(
            abs((release.scheduled_for - deploy.next_opening()).total_seconds()) < 120
        )
        card = json.loads(
            frappe.get_all(
                assistant.MESSAGE, filters={"release": release.name}, pluck="card"
            )[0]
        )
        self.assertFalse(card["actions"])  # the card shows the decision

    def test_the_people_who_wrote_it_and_non_seniors_where_needed_may_not_decide(self):
        release = self.waiting()
        with self.assertRaisesRegex(frappe.PermissionError, "You wrote part"):
            releases.decide(release.name, self.approver, True)

        frappe.db.set_value(deploy.DEPLOY, release.name, "needs_senior", 1)
        frappe.db.set_value("Task", self.task, "_assign", "[]")
        with self.assertRaisesRegex(frappe.PermissionError, "senior"):
            releases.decide(release.name, self.approver, True)

    def test_a_rejection_needs_a_reason_and_reaches_the_people_who_wrote_it(self):
        release = self.waiting()
        with self.assertRaises(frappe.ValidationError):
            releases.decide(release.name, self.senior, False, "")

        releases.decide(release.name, self.senior, False, "breaks the POS invoices")

        release.reload()
        self.assertEqual(release.status, "Rejected")
        self.assertIn("breaks the POS invoices", self.told(self.approver)[-1])

    def test_deploy_now_is_for_seniors_and_managers(self):
        frappe.db.set_value("Task", self.task, "_assign", json.dumps([self.senior]))
        release = self.waiting()
        self.assertEqual(release.assigned_to, self.approver)
        with self.assertRaises(frappe.PermissionError):
            releases.decide(release.name, self.approver, True, when="now")

        releases.decide(release.name, self.approver, True)
        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "when"), "Tonight"
        )

    def test_a_card_seen_before_the_release_changed_is_refused(self):
        release = self.waiting()
        with self.assertRaisesRegex(frappe.ValidationError, "changed"):
            releases.decide(release.name, self.senior, True, expected_hash="old")

    def test_the_first_decision_wins(self):
        release = self.waiting()
        releases.decide(release.name, self.senior, True)
        with self.assertRaisesRegex(frappe.ValidationError, "already decided"):
            releases.decide(release.name, self.senior, False, "no")

    def test_new_commits_after_the_card_ask_for_ci_and_approval_again(self):
        release = self.waiting()
        self.merged(6, B)
        releases.watch()

        release.reload()
        self.assertEqual(release.status, "Waiting for CI")
        with self.assertRaisesRegex(frappe.ValidationError, "not waiting"):
            releases.decide(release.name, self.senior, True)

    def test_the_buttons_in_teams_or_the_panel_decide_it_as_the_person(self):
        release = self.waiting()

        result = assistant.press(
            self.senior,
            "Web",
            "release_approve",
            {"release": release.name, "hash": release.approval_hash},
            {},
        )

        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"), "Scheduled"
        )
        self.assertIn("scheduled", result["card"]["title"].lower())
        logged = frappe.get_all(
            "HDS Copilot Call Log",
            filters={"tool": "decide_release", "user": self.senior},
            fields=["status", "kind"],
        )
        self.assertEqual([(r.status, r.kind) for r in logged], [("OK", "Web")])

    def test_reject_from_a_card_needs_the_reason_box(self):
        release = self.waiting()

        result = assistant.press(
            self.senior, "Web", "release_reject", {"release": release.name}, {}
        )

        self.assertIn("reason", result["replies"][0]["lines"][0])
        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"),
            "Waiting for approval",
        )

    def test_the_desk_endpoints_follow_the_same_rules(self):
        release = self.waiting()
        frappe.set_user(self.senior)

        seen = api.get_release(release.name)
        self.assertTrue(seen["may_decide"])
        api.decide_release(release.name, 1, expected_hash=seen["hash"])

        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"), "Scheduled"
        )
        api.cancel_release(release.name, "the customer asked to wait")
        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"), "Cancelled"
        )


class TestReleaseDeploy(GateCase):
    def setUp(self):
        super().setUp()
        frappe.cache().delete(deploy._lock_key())
        self.addCleanup(lambda: frappe.cache().delete(deploy._lock_key()))
        self.press.apps[0]["next_hash"] = A

    def approved(self):
        release = self.waiting()
        releases.decide(release.name, self.senior, True)
        frappe.db.set_value(
            deploy.DEPLOY,
            release.name,
            "scheduled_for",
            frappe.utils.now_datetime() - timedelta(minutes=1),
        )
        return frappe.get_doc(deploy.DEPLOY, release.name)

    def checked_site(self, commit=A, errors=None):
        connection = make_support_connection(self.customer).name
        self.card.db_set("connection", connection)
        replies = {
            "get_code_identity": [{"app": "demo_app", "commit": commit}],
            "get_deploy_status": {
                "scheduler_enabled": True,
                "maintenance_mode": False,
                "errors": {"top": [{"signature": s, "count": 1} for s in errors or []]},
            },
            "get_error_log": [],
        }
        client = patch("helpdesk.mcp_client.MCPClient")
        mocked = client.start()
        self.addCleanup(client.stop)
        mocked.return_value.call_tool.side_effect = site_tool_replies(replies)

    def test_an_approved_release_deploys_and_is_checked(self):
        release = self.approved()
        self.checked_site()

        deploy.run_due()
        release.reload()
        self.assertEqual(release.status, "Deploying")
        sent = self.press.deploys[0]
        self.assertEqual([s["name"] for s in sent["sites"]], ["site1.example.com"])
        self.assertEqual(sent["apps"][0]["hash"], A)

        self.press.finish("Success")
        deploy.run_due()
        deploy.run_due()

        release.reload()
        self.assertEqual(release.status, "Succeeded")
        self.assertIn("live and checked", self.told(self.approver)[-1])
        self.assertTrue(deploy._take_lock("TBO-DEP-NEXT"))  # released

    def test_a_new_error_after_the_deploy_fails_the_release_and_tells_people(self):
        release = self.approved()
        self.checked_site(
            errors=["demo_app | demo_app.margin.validate | ZeroDivisionError"]
        )

        deploy.run_due()
        self.press.finish("Success")
        deploy.run_due()
        deploy.run_due()

        release.reload()
        self.assertEqual(release.status, "Failed")
        self.assertIn("ZeroDivisionError", release.error)
        escalated = [k for _a, k in self.notified if k.get("escalate")]
        self.assertTrue(escalated)

    def test_two_releases_on_one_bench_go_in_one_press_deploy(self):
        first = self.approved()
        self.press.apps.append(
            {
                "app": "other_app",
                "source": "SRC-2",
                "release": "REL-3",
                "hash": "p" * 40,
                "next_release": "REL-4",
                "next_hash": C,
            }
        )
        second = frappe.get_doc(
            {
                "doctype": deploy.DEPLOY,
                "status": "Scheduled",
                "source": "Pull request",
                "repository": "tbocloud/other-app",
                "branch": "main",
                "release_group": "bench-1",
                "scheduled_for": frappe.utils.now_datetime() - timedelta(minutes=1),
                "sites": [{"site": "site1.example.com", "customer": self.customer}],
                "apps": [{"app": "other_app", "from_commit": "p" * 40, "to_commit": C}],
            }
        ).insert(ignore_permissions=True)

        deploy.run_due()

        self.assertEqual(len(self.press.deploys), 1)
        self.assertEqual(
            sorted(a["app"] for a in self.press.deploys[0]["apps"]),
            ["demo_app", "other_app"],
        )
        first.reload()
        second.reload()
        self.assertEqual((first.status, second.status), ("Deploying", "Deploying"))
        self.assertEqual(first.train, second.train)

    def test_copilot_fixes_inside_the_release_are_resolved_with_it(self):
        ticket = make_ticket(subject="Copilot fixed this", customer=self.customer).name
        run = make_copilot_run(ticket, state="Merged")
        frappe.get_doc(
            {
                "doctype": "HDS Copilot Approval",
                "run": run.name,
                "ticket": ticket,
                "kind": "Code Change",
                "status": "Merged",
                "repo": REPO,
                "number": 7,
            }
        ).insert(ignore_permissions=True)
        self.github.add_pull(REPO, 7, head(B), merged=True, state="closed")
        self.github.commit(REPO, B, pull=7)
        self.merged(8, A)
        self.press.apps[0]["next_hash"] = A
        releases.watch()
        releases.run_due()
        release = self.only_release()
        releases.decide(release.name, self.senior, True, when="now")
        self.checked_site()

        deploy.run_due()
        self.press.finish("Success")
        deploy.run_due()
        deploy.run_due()

        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"), "Succeeded"
        )
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Resolved"
        )


class StagingCase(TestReleaseDeploy):
    """Releases with staging on: the sandbox check by a worker, or the customer's UAT site."""

    def setUp(self):
        super().setUp()
        self.settings(release_staging=1, release_check_hours=6)
        # queued runs of other tests would be handed out before a check
        frappe.db.set_value(
            "HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled"
        )

    # the deploy tests are inherited for their helpers only
    test_an_approved_release_deploys_and_is_checked = None
    test_a_new_error_after_the_deploy_fails_the_release_and_tells_people = None
    test_two_releases_on_one_bench_go_in_one_press_deploy = None
    test_copilot_fixes_inside_the_release_are_resolved_with_it = None


class TestSandboxCheck(StagingCase):
    def test_without_a_uat_site_a_worker_checks_it_on_the_sandbox(self):
        release = self.waiting()
        self.assertEqual(
            (release.status, release.staging, release.staging_status),
            ("Staging", "Sandbox", "Queued"),
        )
        self.assertEqual(
            copilot_worker.claim_job("w1"), {}
        )  # a worker that can't check

        job = copilot_worker.claim_job("w1", capabilities="investigate, release_check")

        self.assertEqual((job["kind"], job["release"]), ("release_check", release.name))
        context = job["context"]
        self.assertEqual((context["app"], context["commit"]), ("demo_app", A))
        self.assertEqual(context["apps"][0]["commit"], A)
        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "staging_status"),
            "Running",
        )
        self.assertEqual(
            copilot_worker.claim_job("w2", capabilities="release_check"), {}
        )

        result = copilot_worker.release_check_result(
            release.name,
            job["lease_token"],
            json.dumps(
                [
                    {"check": "migrate", "result": "pass"},
                    {"check": "demo_app tests", "result": "pass", "detail": "9 passed"},
                    {"check": "no new errors", "result": "pass"},
                ]
            ),
            "a fresh ERPNext site with the customer's apps",
        )

        release.reload()
        self.assertEqual(result["staging_status"], "Passed")
        self.assertEqual(
            (release.status, release.staging_status), ("Waiting for approval", "Passed")
        )
        self.assertIn("9 passed", release.staging_detail)
        self.assertEqual(release.assigned_to, self.senior)

    def test_a_failed_check_waits_for_a_fix_or_a_senior(self):
        release = self.waiting()
        job = releases.claim_check("w1")
        releases.check_result(
            release.name,
            job["lease_token"],
            [{"check": "migrate", "result": "fail", "detail": "patch failed"}],
        )

        release.reload()
        self.assertEqual(
            (release.status, release.staging_status), ("Staging", "Failed")
        )
        self.assertIn("patch failed", self.told(self.approver)[-1])

        with self.assertRaises(frappe.PermissionError):
            releases.override_ci(release, self.approver, "fine")
        releases.override_ci(release, self.senior, "the patch only runs once")
        release.reload()
        self.assertEqual(release.status, "Waiting for approval")
        self.assertTrue(release.needs_senior)

    def test_a_check_that_could_not_run_goes_to_the_seniors_not_the_authors(self):
        release = self.waiting()
        job = releases.claim_check("w1")
        before = len(self.told(self.approver))

        result = releases.check_result(
            release.name,
            job["lease_token"],
            [{"check": "the sandbox check", "result": "not_run", "detail": "runner unreachable"}],
        )

        release.reload()
        self.assertEqual(result["staging_status"], "Not run")
        self.assertEqual((release.status, release.staging_status), ("Staging", "Not run"))
        self.assertIn("runner unreachable", self.told(self.senior)[-1])
        self.assertEqual(len(self.told(self.approver)), before)
        releases.override_ci(release, self.senior, "the runner is down; CI was green")
        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"), "Waiting for approval"
        )

    def test_a_lease_that_is_not_the_workers_is_refused(self):
        release = self.waiting()
        releases.claim_check("w1")
        with self.assertRaises(frappe.PermissionError):
            releases.check_result(release.name, "not-the-token", [])

    def test_a_quiet_worker_loses_the_check_and_one_nobody_takes_is_not_run(self):
        release = self.waiting()
        releases.claim_check("w1")
        frappe.db.set_value(
            deploy.DEPLOY,
            release.name,
            "check_lease_expires",
            frappe.utils.now_datetime() - timedelta(minutes=1),
        )
        releases.run_due()
        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "staging_status"), "Queued"
        )

        frappe.db.set_value(
            deploy.DEPLOY,
            release.name,
            "modified",
            frappe.utils.now_datetime() - timedelta(hours=7),
            update_modified=False,
        )
        releases.run_due()

        release.reload()
        self.assertEqual(release.staging_status, "Not run")
        self.assertIn("No worker checked", self.told(self.senior)[-1])

    def test_new_commits_during_the_check_start_it_over(self):
        release = self.waiting()
        job = releases.claim_check("w1")
        self.merged(6, B)
        releases.watch()

        release.reload()
        self.assertEqual(
            (release.status, release.staging_status), ("Waiting for CI", None)
        )
        with self.assertRaises(frappe.PermissionError):
            releases.check_result(release.name, job["lease_token"], [])

    def test_staging_off_goes_straight_to_the_approval(self):
        self.settings(release_staging=0)
        release = self.waiting()

        self.assertEqual(
            (release.status, release.staging_status),
            ("Waiting for approval", "Not run"),
        )


class TestUatStaging(StagingCase):
    def setUp(self):
        super().setUp()
        self.uat_card = make_site_registry(
            self.customer,
            environment="UAT",
            press_site="uat.example.com",
            press_release_group="bench-uat",
            apps=[self.app_row()],
        )
        self.press.sites.append(
            {"name": "uat.example.com", "server": "f1", "bench": "bench-uat-old"}
        )

    def uat_request(self, release):
        return frappe.get_doc(deploy.DEPLOY, release.staging_request)

    def test_the_customers_uat_site_takes_it_first(self):
        release = self.waiting()
        self.assertEqual(
            (release.status, release.staging, release.staging_status),
            ("Staging", "UAT site", "Queued"),
        )
        uat = self.uat_request(release)
        self.assertEqual(
            (uat.status, uat.staging_for, uat.release_group),
            ("Scheduled", release.name, "bench-uat"),
        )
        self.assertEqual([s.site for s in uat.sites], ["uat.example.com"])

        self.checked_site()
        self.uat_card.db_set("connection", self.card.connection)
        uat.db_set("scheduled_for", frappe.utils.now_datetime() - timedelta(minutes=1))
        deploy.run_due()
        self.press.finish("Success")
        deploy.run_due()
        deploy.run_due()

        release.reload()
        self.assertEqual(self.uat_request(release).status, "Succeeded")
        self.assertEqual(
            (release.status, release.staging_status), ("Waiting for approval", "Passed")
        )

    def test_a_failed_uat_deploy_fails_staging(self):
        release = self.waiting()
        uat = self.uat_request(release)
        uat.db_set("scheduled_for", frappe.utils.now_datetime() - timedelta(minutes=1))
        deploy.run_due()
        self.press.finish("Failure")
        deploy.run_due()

        release.reload()
        self.assertEqual(self.uat_request(release).status, "Failed")
        self.assertEqual(
            (release.status, release.staging_status), ("Staging", "Failed")
        )

    def test_new_commits_cancel_a_uat_deploy_not_yet_started(self):
        release = self.waiting()
        uat = self.uat_request(release)
        self.merged(6, B)
        releases.watch()

        uat.reload()
        release.reload()
        self.assertEqual(uat.status, "Cancelled")
        self.assertEqual(release.status, "Waiting for CI")


class TestUndoAndRecord(TestReleaseDeploy):
    test_an_approved_release_deploys_and_is_checked = None
    test_a_new_error_after_the_deploy_fails_the_release_and_tells_people = None
    test_two_releases_on_one_bench_go_in_one_press_deploy = None
    test_copilot_fixes_inside_the_release_are_resolved_with_it = None

    def test_a_failed_check_after_reverts_each_pull_request_newest_first(self):
        self.merged(4, C)
        self.merged(5, A)
        releases.watch()
        releases.run_due()
        release = self.only_release()
        releases.decide(release.name, self.senior, True, when="now")
        self.checked_site(errors=["demo_app | demo_app.margin.validate | KeyError"])

        deploy.run_due()
        self.press.finish("Success")
        deploy.run_due()
        deploy.run_due()

        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"), "Failed"
        )
        self.assertEqual(self.github.reverted, [(REPO, 5), (REPO, 4)])
        escalated = [a[3] for a, k in self.notified if k.get("escalate")]
        self.assertIn("Reverted in", escalated[-1])

    def test_a_press_failure_is_not_reverted(self):
        release = self.approved()
        deploy.run_due()
        self.press.finish("Failure")
        deploy.run_due()

        self.assertEqual(
            frappe.db.get_value(deploy.DEPLOY, release.name, "status"), "Failed"
        )
        self.assertEqual(self.github.reverted, [])

    def test_the_weekly_email_has_a_releases_section(self):
        from frappe.utils import add_days, getdate

        release = self.approved()
        frappe.db.set_value(
            deploy.DEPLOY,
            release.name,
            {"status": "Succeeded", "finished_at": frappe.utils.now_datetime()},
        )
        today = getdate()

        numbers = releases.week_numbers(add_days(today, -1), today)

        self.assertEqual((numbers["made"], numbers["succeeded"]), (1, 1))
        self.assertIsNotNone(numbers["median_wait_hours"])
        self.assertEqual(numbers["bypasses"], 0)
        self.assertIn("Releases", releases.week_html(add_days(today, -1), today))
