# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Releases (Phase 7): every merge into a branch a customer site runs goes out the same way."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import deploy, releases
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
    make_task,
    make_ticket,
)

REPO = "tbocloud/demo-app"
RUNNING = "o" * 40  # what the bench runs before any release
A, B, C = "a" * 40, "b" * 40, "c" * 40


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

    def merged(self, number: int, sha: str, author: str = "dev-one", body: str = ""):
        """A pull request merged into main, landing as commit `sha`."""
        self.github.add_pull(
            REPO, number, sha, body=body, author=author, merged=True, state="closed"
        )
        self.github.commit(
            REPO, sha, message=f"Merge #{number}", author=author, pull=number
        )

    def releases_of(self, repo: str = REPO) -> list:
        return [
            frappe.get_doc(deploy.DEPLOY, name)
            for name in frappe.get_all(
                deploy.DEPLOY,
                filters={"repository": repo},
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
