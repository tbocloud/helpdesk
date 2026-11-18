# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Copilot takes a developer's pull request live (Phase 26): only when the developer asks; it fixes
what CodeRabbit and CI find (at most three rounds), asks one approver who wrote none of it, merges the
approved commit, and the release that follows deploys without another card."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api.copilot_worker import WORKER_ROLE, claim_job, ensure_role
from helpdesk.copilot import go_live, pulls
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    create_user,
    hold_commits,
    make_copilot_settings,
    make_customer_project,
)

REPO = "tbocloud/demo-alpha-app"
HEAD = "a" * 40
WORKER_USER = "pulls-worker@example.com"


class FakeGitHub:
    """The GitHub calls of helpdesk.copilot.pulls, in memory."""

    def __init__(self):
        self.pulls, self.checks_of, self.failed_of = {}, {}, {}
        self.reviews, self.threads = [], []
        self.replies, self.resolved, self.comments, self.merged = [], [], [], []
        self.files = [
            {"filename": "demo_alpha/margin.py", "additions": 3, "deletions": 1}
        ]

    def add(self, number=7, task="TASK-2026-00001", fork=False, draft=False, repo=REPO):
        self.pulls[number] = {
            "number": number,
            "title": f"Cap the discount ({task})",
            "body": f"Closes {task}",
            "html_url": f"https://github.com/{repo}/pull/{number}",
            "state": "open",
            "draft": draft,
            "merged": False,
            "mergeable_state": "clean",
            "user": {"login": "dev-login"},
            "base": {"ref": "main", "repo": {"full_name": repo}},
            "head": {
                "ref": "feature/cap",
                "sha": HEAD,
                "repo": {"full_name": "someone/fork" if fork else repo},
            },
        }
        self.green(HEAD)
        return self.pulls[number]

    def green(self, sha):
        self.checks_of[sha] = {
            "green": True,
            "total": 1,
            "pending": [],
            "failing": [],
            "partial": False,
        }

    def red(self, sha):
        self.checks_of[sha] = {
            "green": False,
            "total": 1,
            "pending": [],
            "failing": ["tests"],
            "partial": False,
        }
        self.failed_of[sha] = [
            {"name": "tests", "title": "2 failed", "summary": "test_cap: 25 != 20"}
        ]

    def reviewed(self, sha):
        self.reviews.append(
            {
                "user": {"login": pulls.CODERABBIT},
                "commit_id": sha,
                "state": "COMMENTED",
            }
        )

    def thread(self, body="Use a constant for the cap.", tid="T1", cid=11):
        self.threads.append(
            {
                "id": tid,
                "resolved": False,
                "outdated": False,
                "path": "demo_alpha/margin.py",
                "line": 4,
                "comment_id": cid,
                "author": pulls.CODERABBIT,
                "body": body,
            }
        )

    def install(self, case):
        from helpdesk.copilot import github

        fakes = {
            "get_pull": lambda repo, n: json.loads(json.dumps(self.pulls[int(n)])),
            "open_pulls": lambda repo: [
                p for p in self.pulls.values() if p["base"]["repo"]["full_name"] == repo
            ],
            "checks": lambda repo, sha: self.checks_of.get(
                sha,
                {
                    "green": False,
                    "total": 0,
                    "pending": [],
                    "failing": [],
                    "partial": False,
                },
            ),
            "failed_checks": lambda repo, sha: self.failed_of.get(sha, []),
            "pull_reviews": lambda repo, n: list(self.reviews),
            "review_threads": lambda repo, n: [
                t for t in self.threads if not t["resolved"]
            ],
            "reply_to_comment": lambda repo, n, cid, body: self.replies.append(
                (cid, body)
            ),
            "resolve_thread": lambda repo, tid: self.resolve(tid),
            "comment": lambda repo, n, text: self.comments.append(text),
            "pull_files": lambda repo, n: list(self.files),
            "pull_commits": lambda repo, n: [
                {"commit": {"author": {"email": "dev@example.com"}}}
            ],
            "merge": lambda repo, n, sha, title="": self.merge(n, sha),
        }
        for name, fn in fakes.items():
            patcher = patch.object(github, name, side_effect=fn)
            patcher.start()
            case.addCleanup(patcher.stop)
        return self

    def resolve(self, tid):
        for t in self.threads:
            if t["id"] == tid:
                t["resolved"] = True
        self.resolved.append(tid)

    def merge(self, number, sha):
        self.merged.append((number, sha))
        self.pulls[int(number)]["merged"] = True
        return "m" * 40


class PullCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.developer = create_agent("pulls.dev@example.com").name
        frappe.db.set_value("User", self.developer, "email", "dev@example.com")
        self.approver = create_agent("pulls.approver@example.com").name
        self.senior = create_agent("pulls.senior@example.com").name
        self.customer = create_customer("Pulls Co").name
        project = make_customer_project(
            self.customer, "Pulls Co support", members=[(self.developer, "Developer")]
        )
        self.task = (
            frappe.get_doc(
                {"doctype": "Task", "subject": "Cap the discount", "project": project}
            )
            .insert(ignore_permissions=True)
            .name
        )
        from helpdesk.utils import add_assignment

        add_assignment(
            {"assign_to": [self.developer], "doctype": "Task", "name": self.task},
            ignore_permissions=True,
        )
        make_copilot_settings(
            enabled=1,
            releases_enabled=1,
            release_repositories=REPO,
            copilot_takes_prs=1,
            copilot_people=[
                {
                    "role": "Fix Approver",
                    "person": self.approver,
                    "level": "Main",
                    "active": 1,
                },
                {"role": "Senior", "person": self.senior, "level": "Main", "active": 1},
            ],
        )
        self.gh = FakeGitHub().install(self)
        self.sent = []
        for target, kw in (
            (
                "helpdesk.copilot.assistant.send",
                {
                    "side_effect": lambda person, reply, **k: self.sent.append(
                        (person, reply)
                    )
                },
            ),
            (
                "helpdesk.copilot.releases.targets",
                {"return_value": {(REPO, "main", "bench-0015"): []}},
            ),
            ("helpdesk.copilot.github_app.configured", {"return_value": False}),
        ):
            patcher = patch(target, **kw)
            patcher.start()
            self.addCleanup(patcher.stop)

    def take(self, when="tonight"):
        frappe.set_user(self.developer)
        try:
            return go_live.ask_go_live(self.task, when)
        finally:
            frappe.set_user("Administrator")

    def rec(self):
        return frappe.get_doc(
            pulls.PR, frappe.db.get_value(pulls.PR, {"task": self.task})
        )

    def told(self, person) -> list[str]:
        return [
            " ".join([r.get("title") or "", *r.get("lines", [])])
            for p, r in self.sent
            if p == person
        ]


class TestTakingIt(PullCase):
    def test_ask_to_go_live_hands_the_open_pull_request_to_copilot(self):
        self.gh.add(task=self.task)
        answer = self.take()
        self.assertTrue(answer["asked"])
        rec = self.rec()
        self.assertEqual(
            (rec.repo, rec.number, rec.state, rec.developer),
            (REPO, 7, "Reviewing", self.developer),
        )
        # CI is green but CodeRabbit has not looked at this commit: Copilot asks it, at most hourly
        self.assertEqual(self.gh.comments, ["@coderabbitai review"])
        pulls.evaluate(rec.name)
        self.assertEqual(self.gh.comments, ["@coderabbitai review"])
        self.assertTrue(
            any("takes pull request #7 live" in t for t in self.told(self.developer))
        )

    def test_a_fork_a_draft_or_a_repository_outside_the_pipeline_is_not_taken(self):
        for kwargs, words in (
            ({"fork": True}, "fork"),
            ({"draft": True}, "draft"),
        ):
            self.gh.pulls.clear()
            self.gh.add(task=self.task, **kwargs)
            answer = self.take()
            self.assertFalse(answer["asked"], kwargs)
            self.assertIn(words, answer["next"])
        self.assertFalse(frappe.db.exists(pulls.PR, {"task": self.task}))

    def test_without_an_open_pull_request_the_release_flow_answers(self):
        answer = self.take()
        self.assertNotIn("followed_by_copilot", answer)
        self.assertFalse(frappe.db.exists(pulls.PR, {"task": self.task}))

    def test_github_that_cannot_be_asked_falls_back_to_the_release_flow(self):
        with patch.object(
            pulls, "find_open_pull", side_effect=frappe.ValidationError("no GitHub key")
        ):
            answer = self.take()
        self.assertNotIn("followed_by_copilot", answer)

    def test_switched_off_copilot_takes_nothing(self):
        make_copilot_settings(copilot_takes_prs=0)
        self.gh.add(task=self.task)
        self.take()
        self.assertFalse(frappe.db.exists(pulls.PR, {"task": self.task}))


class TestFixRounds(PullCase):
    def fixing(self):
        self.gh.add(task=self.task)
        self.gh.red(HEAD)
        self.gh.reviewed(HEAD)
        self.gh.thread()
        self.take()
        return self.rec()

    def test_ci_and_coderabbit_findings_become_a_round_for_a_worker(self):
        rec = self.fixing()
        self.assertEqual(rec.state, "Fixing")
        findings = json.loads(rec.findings)
        self.assertEqual({f["source"] for f in findings}, {"ci", "coderabbit"})
        job = pulls.claim("w1")
        self.assertEqual((job["kind"], job["pull_request"]), ("pr_fix", rec.name))
        context = job["context"]
        self.assertEqual(
            (context["head_branch"], context["head_sha"], context["round"]),
            ("feature/cap", HEAD, 1),
        )
        self.assertNotIn("thread_id", json.dumps(context["findings"]))
        self.assertEqual(pulls.claim("w2"), {})  # leased

    def test_the_worker_api_hands_out_rounds_only_to_a_worker_that_says_pr_fix(self):
        self.fixing()
        ensure_role()
        create_user(WORKER_USER).add_roles(WORKER_ROLE)
        frappe.set_user(WORKER_USER)
        self.assertEqual(claim_job("w1", capabilities="investigate"), {})
        self.assertEqual(
            claim_job("w1", capabilities="investigate,pr_fix")["kind"], "pr_fix"
        )

    def test_a_round_replies_resolves_and_looks_again(self):
        rec = self.fixing()
        job = pulls.claim("w1")
        with patch(
            "helpdesk.copilot.github_app.push_token",
            return_value={"token": "t", "expires_at": "x"},
        ):
            key = pulls.push_key(rec.name, job["lease_token"])
        self.assertEqual(key["branch"], "feature/cap")
        new = "b" * 40
        self.gh.pulls[7]["head"]["sha"] = new
        self.gh.green(new)
        out = pulls.result(
            rec.name,
            job["lease_token"],
            {
                "kind": "done",
                "head_sha": new,
                "fixed": [
                    {"id": "ci-1", "commit": new, "note": "cap is 20"},
                    {"id": "cr-1", "commit": new, "note": "MAX_CAP constant"},
                ],
                "not_fixed": [],
            },
        )
        self.assertEqual(out["state"], "Reviewing")
        rec.reload()
        self.assertEqual((rec.rounds, rec.head_sha), (1, new))
        self.assertEqual(self.gh.resolved, ["T1"])
        self.assertTrue(self.gh.replies[0][1].startswith("Fixed by TBO Copilot"))
        self.assertIn("@coderabbitai review", self.gh.comments)
        self.assertTrue(any("Round 1 pushed" in t for t in self.told(self.developer)))

    def test_a_round_that_changed_nothing_goes_back_to_the_developer(self):
        rec = self.fixing()
        job = pulls.claim("w1")
        pulls.result(
            rec.name,
            job["lease_token"],
            {
                "kind": "done",
                "head_sha": HEAD,
                "fixed": [],
                "not_fixed": [{"id": "cr-1", "why": "the cap is per tier"}],
            },
        )
        rec.reload()
        self.assertEqual(rec.state, "With the developer")
        self.assertTrue(self.gh.replies[0][1].startswith("Not changed by TBO Copilot"))
        self.assertFalse(self.gh.resolved)

    def test_after_three_rounds_the_developer_takes_over(self):
        rec = self.fixing()
        rec.db_set({"state": "Reviewing", "rounds": pulls.MAX_ROUNDS})
        pulls.evaluate(rec.name)
        rec.reload()
        self.assertEqual(rec.state, "With the developer")
        self.assertIn("After 3 rounds", rec.handed_back)

    def test_the_developer_pushing_cancels_the_round(self):
        rec = self.fixing()
        job = pulls.claim("w1")
        self.assertEqual(
            pulls.heartbeat(rec.name, job["lease_token"])["action"], "continue"
        )
        self.gh.pulls[7]["head"]["sha"] = "c" * 40
        self.assertEqual(
            pulls.heartbeat(rec.name, job["lease_token"])["action"], "cancel"
        )
        self.assertEqual(frappe.db.get_value(pulls.PR, rec.name, "state"), "Reviewing")

    def test_a_wrong_lease_is_refused(self):
        rec = self.fixing()
        pulls.claim("w1")
        with self.assertRaises(frappe.PermissionError):
            pulls.push_key(rec.name, "wrong")


class TestApproval(PullCase):
    def clean(self):
        self.gh.add(task=self.task)
        self.gh.reviewed(HEAD)
        self.take(when="now")
        return self.rec()

    def test_clean_asks_one_approver_who_wrote_none_of_it(self):
        rec = self.clean()
        self.assertEqual(
            (rec.state, rec.assigned_to), ("Ready for approval", self.approver)
        )
        self.assertTrue(
            any("Take pull request #7 live" in t for t in self.told(self.approver))
        )

    def test_a_sensitive_change_needs_a_senior(self):
        self.gh.files = [
            {
                "filename": "demo_alpha/accounts/ledger.py",
                "additions": 5,
                "deletions": 0,
            }
        ]
        rec = self.clean()
        self.assertEqual((rec.needs_senior, rec.assigned_to), (1, self.senior))
        with self.assertRaises(frappe.PermissionError):
            pulls.decide(rec.name, self.approver, True)

    def test_the_developer_cannot_approve_and_approve_merges_the_head(self):
        rec = self.clean()
        with self.assertRaises(frappe.PermissionError):
            pulls.decide(rec.name, self.developer, True)
        out = pulls.decide(
            rec.name, self.approver, True, expected_hash=rec.payload_hash
        )
        self.assertEqual(out["state"], "Merged")
        self.assertEqual(self.gh.merged, [(7, HEAD)])

    def test_new_commits_after_the_approval_ask_again(self):
        rec = self.clean()
        self.gh.pulls[7]["head"]["sha"] = "d" * 40
        pulls.decide(rec.name, self.approver, True)
        self.assertEqual(frappe.db.get_value(pulls.PR, rec.name, "state"), "Reviewing")
        self.assertFalse(self.gh.merged)

    def test_reject_needs_a_reason_and_tells_the_developer(self):
        rec = self.clean()
        with self.assertRaises(frappe.ValidationError):
            pulls.decide(rec.name, self.approver, False)
        pulls.decide(rec.name, self.approver, False, note="needs a test for zero")
        self.assertEqual(frappe.db.get_value(pulls.PR, rec.name, "state"), "Rejected")
        self.assertTrue(any("rejected" in t for t in self.told(self.developer)))

    def test_merge_without_coderabbit_on_the_developers_request(self):
        self.gh.add(task=self.task)
        self.take()
        rec = self.rec()
        self.assertEqual(rec.state, "Reviewing")  # waiting for CodeRabbit
        out = pulls.press_button(
            self.developer, "Teams", "pr_skip_review", {"pull_request": rec.name}, {}
        )
        self.assertIn("not wait for CodeRabbit", out["replies"][0]["lines"][0])
        rec.reload()
        self.assertEqual(
            (rec.state, rec.skip_requested_by), ("Ready for approval", self.developer)
        )
        self.assertTrue(any("skipped at" in t for t in self.told(self.approver)))


class FakeRelease:
    def __init__(self, changes, needs_senior=0):
        self.name, self.repository, self.needs_senior = (
            "TBO-DEP-TEST",
            REPO,
            needs_senior,
        )
        self.changes = json.dumps(changes)
        self.values = {}

    def db_set(self, values, *a, **k):
        self.values.update(values)


class TestTheRelease(PullCase):
    def merged(self, when="now"):
        self.gh.add(task=self.task)
        self.gh.reviewed(HEAD)
        self.take(when=when)
        rec = self.rec()
        pulls.decide(rec.name, self.approver, True)
        return self.rec()

    def test_a_release_of_the_merged_pull_request_deploys_without_another_card(self):
        rec = self.merged(when="now")
        release = FakeRelease([{"sha": "m" * 40, "pull": {"number": 7}}])
        with patch("helpdesk.copilot.releases.refresh_cards"):
            self.assertTrue(
                pulls.approved_release(
                    release, {"level": "low", "sensitive": False, "reasons": []}
                )
            )
        self.assertEqual(
            (
                release.values["status"],
                release.values["when"],
                release.values["decided_by"],
            ),
            ("Scheduled", "Now", self.approver),
        )
        self.assertEqual(
            frappe.db.get_value(pulls.PR, rec.name, "release"), "TBO-DEP-TEST"
        )

    def test_high_risk_waits_for_tonight_and_a_shared_bench_needs_a_senior_approval(
        self,
    ):
        self.merged(when="now")
        release = FakeRelease([{"pull": {"number": 7}}])
        with patch("helpdesk.copilot.releases.refresh_cards"):
            self.assertTrue(
                pulls.approved_release(
                    release, {"level": "high", "sensitive": False, "reasons": []}
                )
            )
        self.assertEqual(release.values["when"], "Tonight")
        shared = FakeRelease([{"pull": {"number": 7}}], needs_senior=1)
        self.assertFalse(
            pulls.approved_release(shared, {"level": "low", "sensitive": False})
        )

    def test_a_release_with_another_change_gets_its_own_card(self):
        self.merged()
        release = FakeRelease([{"pull": {"number": 7}}, {"pull": {"number": 8}}])
        self.assertFalse(
            pulls.approved_release(release, {"level": "low", "sensitive": False})
        )


class TestTheLook(PullCase):
    def test_no_ci_at_all_hands_back_after_half_an_hour(self):
        self.gh.add(task=self.task)
        self.gh.checks_of[HEAD] = {
            "green": False,
            "total": 0,
            "pending": [],
            "failing": [],
            "partial": False,
        }
        self.take()
        rec = self.rec()
        self.assertEqual(rec.state, "Reviewing")
        rec.db_set(
            "asked_at", add_to_date(now_datetime(), minutes=-(pulls.NO_CI_MINUTES + 1))
        )
        pulls.evaluate(rec.name)
        self.assertEqual(
            frappe.db.get_value(pulls.PR, rec.name, "state"), "With the developer"
        )

    def test_merged_outside_copilot_stops_following(self):
        self.gh.add(task=self.task)
        self.take()
        self.gh.pulls[7]["merged"] = True
        pulls.evaluate(self.rec().name)
        self.assertEqual(self.rec().state, "Closed")
