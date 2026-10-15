# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""A Copilot fix from its task to the merge: one approval per commit, the hub merges, the customer is told."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import github_sync
from helpdesk.api import copilot as api
from helpdesk.copilot import approvals, customer, fixes, router, runs
from helpdesk.test_utils import (
    FakeGitHub,
    create_agent,
    create_customer,
    fake_investigation,
    hold_commits,
    make_copilot_settings,
    make_customer_project,
    make_hd_pull_request,
    make_site_registry,
    make_ticket,
)

REPO = "tbocloud/tbo-copilot-sandbox"
SHA = "a" * 40
NEW_SHA = "b" * 40


class FixCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.developer = create_agent("fix.developer@example.com").name
        self.approver = create_agent("fix.approver@example.com").name
        self.senior = create_agent("fix.senior@example.com").name
        self.settings(shadow_mode=0)
        self.customer = create_customer("Fix Flow Co").name
        frappe.db.set_value(
            "HD Customer", self.customer, "custom_assigned_developer", self.developer
        )
        self.project = make_customer_project(
            self.customer,
            "Fix Flow Co support",
            members=[(self.developer, "Developer")],
        )
        self.ticket = make_ticket(subject="Margin wrong", customer=self.customer)
        self.github = FakeGitHub().install(self)
        frappe.db.set_single_value(
            "HD GitHub Settings",
            {"enabled": 1, "complete_on_merge": 1, "allowed_repos": "tbocloud/*"},
        )
        frappe.clear_document_cache("HD GitHub Settings", "HD GitHub Settings")
        self.addCleanup(
            frappe.clear_document_cache, "HD GitHub Settings", "HD GitHub Settings"
        )
        self.notified = []
        patcher = patch(
            "helpdesk.work_reminders.notify_users",
            side_effect=lambda *a, **k: self.notified.append(a),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # a fix task has no due date, so it would ask the real AI for an estimate
        patcher = patch("helpdesk.task_estimates.ai_estimate", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def settings(self, **values):
        make_copilot_settings(
            enabled=1,
            min_confidence=0.6,
            handover_project=None,
            approvers=[
                {"user": self.approver, "senior": 0, "active": 1},
                {"user": self.senior, "senior": 1, "active": 1},
            ],
            **values,
        )

    def current_run(self):
        return frappe.get_doc(
            "HDS Copilot Run", customer.latest_run(self.ticket.name).name
        )

    def diagnosed(self):
        run = runs.start_run(self.ticket.name)
        run = runs.transition(run, "Investigating", runs.WORKER)
        return router.route(run, fake_investigation("bug", 0.9))

    def opened(self, number=7, sha=SHA, checks=None, **kwargs):
        task = self.current_run().task
        pull = self.github.add_pull(REPO, number, sha, body=f"Closes {task}", **kwargs)
        if checks:
            self.github.set_checks(sha, checks)
        row = make_hd_pull_request(task, REPO, number, sha)
        fixes.on_pull_request(pull, "opened", [row])
        return row

    def decide(self, user, approve=True, note="", deploy_date="2026-10-20"):
        frappe.set_user(user)
        try:
            return api.decide_fix(self.ticket.name, int(approve), note, deploy_date)
        finally:
            frappe.set_user("Administrator")

    def approval(self):
        return frappe.get_doc("HDS Copilot Approval", self.current_run().approval)

    def events(self, event_type):
        return [
            json.loads(p)
            for p in frappe.get_all(
                "HDS Copilot Event",
                filters={"run": self.current_run().name, "event_type": event_type},
                pluck="payload",
                order_by="creation asc",
            )
        ]


class TestFixTask(FixCase):
    def test_a_live_bug_gets_a_fix_task_for_the_customers_developer(self):
        run = self.diagnosed()

        self.assertEqual(run.state, "Preparing Fix")
        task = frappe.get_doc("Task", self.current_run().task)
        self.assertTrue(task.subject.startswith(fixes.FIX_TASK_PREFIX))
        self.assertEqual(
            (task.project, task.hd_ticket), (self.project, self.ticket.name)
        )
        self.assertIn(self.developer, task.assignees())
        self.assertIn(f"Closes {task.name}", task.description)
        self.assertTrue(self.events("fix_task"))

    def test_a_shadow_bug_waits_for_an_agent(self):
        self.settings(shadow_mode=1)
        self.diagnosed()
        self.assertFalse(self.current_run().task)

        frappe.set_user(self.approver)
        info = api.create_fix_task(self.ticket.name)
        frappe.set_user("Administrator")

        self.assertTrue(info["fix"]["task"]["name"].startswith("TASK-"))
        self.assertFalse(info["fix"]["can_create_task"])

    def test_the_task_lists_the_proposals_files_in_words(self):
        run = frappe._dict(
            evidence="[]",
            proposal=json.dumps({"files": ["app/invoice.py", "tests/test_invoice.py"]}),
            root_cause_category="bug",
            confidence=0.9,
            summary="The margin is wrong.",
        )
        text = fixes._task_description(run)
        self.assertIn("app/invoice.py, tests/test_invoice.py", text)
        self.assertNotIn("[", text)

    def test_no_project_is_a_note_not_an_error(self):
        frappe.db.set_value("Project", self.project, "status", "Completed")
        errors = frappe.db.count("Error Log")

        run = self.diagnosed()

        self.assertEqual(run.state, "Preparing Fix")
        self.assertFalse(self.current_run().task)
        self.assertTrue(self.events("fix_task_missing"))
        self.assertEqual(frappe.db.count("Error Log"), errors)


class TestSiteBranch(FixCase):
    """A fix must go into the branch the customer's site runs, or it never reaches the site."""

    def setUp(self):
        super().setUp()
        make_site_registry(
            self.customer,
            apps=[
                {
                    "app": "demo_app",
                    "repository": f"https://github.com/{REPO}.git",
                    "branch": "acme-live",
                }
            ],
        )
        self.diagnosed()

    def test_a_pull_request_into_another_branch_is_not_merged(self):
        self.opened()  # into main
        self.assertIn("site runs acme-live", self.approval().reasons)

        result = self.decide(self.approver)

        self.assertEqual(
            result["decision"], {"outcome": "approved", "merge": "blocked"}
        )
        self.assertIsNone(self.github.merged_with)
        self.assertIn("targets main", self.approval().merge_error)

    def test_a_pull_request_into_the_sites_branch_merges(self):
        self.opened(base="acme-live")
        self.assertNotIn("site runs", self.approval().reasons or "")

        result = self.decide(self.approver)

        self.assertEqual(result["decision"]["merge"], "merged")


class TestApprovalOpens(FixCase):
    def setUp(self):
        super().setUp()
        self.diagnosed()

    def test_a_pull_request_opens_one_approval_held_from_the_bots(self):
        self.opened()

        run, approval = self.current_run(), self.approval()
        self.assertEqual(run.state, "Awaiting Approval")
        self.assertEqual((approval.status, approval.head_sha), ("Pending", SHA))
        self.assertEqual(
            approval.assigned_to, self.approver
        )  # the developer made it, so not them
        self.assertEqual(approval.risk_level, "low")
        self.assertIn("no-auto-merge", self.github.labels(REPO, 7))

    def test_a_draft_opens_nothing(self):
        self.opened(draft=True)
        self.assertEqual(self.current_run().state, "Preparing Fix")
        self.assertFalse(self.current_run().approval)

    def test_new_commits_need_a_new_approval(self):
        row = self.opened()
        first = self.approval().name

        self.github.push(REPO, 7, NEW_SHA)
        fixes.on_pull_request(self.github.pulls[(REPO, 7)], "synchronize", [row])

        self.assertEqual(
            frappe.db.get_value("HDS Copilot Approval", first, "status"), "Superseded"
        )
        self.assertEqual(
            (self.approval().status, self.approval().head_sha), ("Pending", NEW_SHA)
        )

    def test_a_sensitive_fix_goes_to_a_senior(self):
        files = [
            {
                "filename": "demo_app/hooks.py",
                "status": "modified",
                "additions": 1,
                "deletions": 0,
                "patch": "+x",
            }
        ]
        self.opened(files=files)

        approval = self.approval()
        self.assertTrue(approval.sensitive)
        self.assertEqual(approval.risk_level, "high")
        self.assertEqual(approval.assigned_to, self.senior)
        self.assertIn("app hooks", approval.reasons)

    def test_a_second_pull_request_waits_for_the_first(self):
        first = self.opened()
        task = self.current_run().task
        other = self.github.add_pull(REPO, 8, NEW_SHA, body=f"Closes {task}")
        second = make_hd_pull_request(task, REPO, 8, NEW_SHA)

        fixes.on_pull_request(other, "opened", [second])

        self.assertEqual(self.current_run().pull_request, first.name)
        self.assertEqual(
            (self.approval().number, self.approval().status), (7, "Pending")
        )
        self.assertTrue(self.events("pull_request_ignored"))

        closed = dict(self.github.pulls[(REPO, 7)], state="closed")
        fixes.on_pull_request(closed, "closed", [first])
        frappe.db.set_value("HD Pull Request", first.name, "state", "Closed")
        fixes.refresh(self.current_run())

        self.assertEqual(self.current_run().pull_request, second.name)
        self.assertEqual(
            (self.approval().number, self.approval().status), (8, "Pending")
        )

    def test_finished_checks_reach_the_card(self):
        row = self.opened(checks={"tests": None})
        self.assertEqual(
            json.loads(self.approval().payload)["checks"]["pending"], ["tests"]
        )

        self.github.set_checks(SHA, {"tests": "success"})
        fixes.on_checks(REPO, SHA, [row])

        self.assertTrue(json.loads(self.approval().payload)["checks"]["green"])
        self.assertEqual(self.current_run().state, "Awaiting Approval")


class TestDecision(FixCase):
    def setUp(self):
        super().setUp()
        self.diagnosed()
        self.row = self.opened()

    def test_approving_merges_with_the_approved_commit_pinned(self):
        result = self.decide(self.approver)

        self.assertEqual(result["decision"], {"outcome": "approved", "merge": "merged"})
        self.assertEqual(self.current_run().state, "Merged")
        self.assertEqual(self.github.merged_with["sha"], SHA)
        self.assertEqual(self.github.merged_with["merge_method"], "merge")
        approval = self.approval()
        self.assertEqual(
            (approval.status, approval.decided_by), ("Merged", self.approver)
        )
        self.assertEqual(str(approval.deploy_date), "2026-10-20")
        self.assertEqual(self.current_run().merge_commit, "m" + SHA)
        self.assertNotIn("no-auto-merge", self.github.labels(REPO, 7))
        self.assertEqual(self.events("stage")[-1]["stage"], "Fix scheduled")

    def test_the_merge_waits_for_running_checks(self):
        self.github.set_checks(SHA, {"tests": None})
        self.decide(self.approver)
        self.assertEqual(self.current_run().state, "Approved")
        self.assertIsNone(self.github.merged_with)

        self.github.set_checks(SHA, {"tests": "success"})
        fixes.on_checks(REPO, SHA, [self.row])
        self.assertEqual(self.current_run().state, "Merged")

    def test_approving_a_changed_pull_request_asks_for_a_new_review(self):
        self.github.push(REPO, 7, NEW_SHA)
        old = self.approval().name

        result = self.decide(self.approver)

        self.assertEqual(result["decision"]["outcome"], "superseded")
        self.assertEqual(
            frappe.db.get_value("HDS Copilot Approval", old, "status"), "Superseded"
        )
        self.assertEqual(
            (self.approval().status, self.approval().head_sha), ("Pending", NEW_SHA)
        )
        self.assertIsNone(self.github.merged_with)

    def test_a_token_without_check_runs_merges_on_green_actions(self):
        self.github.check_runs_refused = True

        result = self.decide(self.approver)

        self.assertEqual(result["decision"], {"outcome": "approved", "merge": "merged"})
        self.assertTrue(json.loads(self.approval().payload)["checks"]["partial"])

    def test_github_still_settling_the_merge_state_is_a_quiet_wait(self):
        self.github.pulls[(REPO, 7)]["mergeable_state"] = "unstable"

        result = self.decide(self.approver)

        self.assertEqual(
            result["decision"], {"outcome": "approved", "merge": "waiting"}
        )
        self.assertEqual(self.current_run().state, "Approved")
        self.assertFalse(self.events("merge_blocked"))

        self.github.pulls[(REPO, 7)]["mergeable_state"] = "clean"
        fixes.on_checks(REPO, SHA, [self.row])
        self.assertEqual(self.current_run().state, "Merged")

    def test_conflicts_are_told_in_plain_words(self):
        self.github.pulls[(REPO, 7)]["mergeable_state"] = "dirty"

        self.decide(self.approver)

        self.assertEqual(self.current_run().state, "Approved")
        self.assertIn("merge conflicts", self.approval().merge_error)

    def test_a_merge_github_refuses_is_kept_and_told(self):
        self.github.merge_refusal = (405, "Pull Request is not mergeable")
        self.decide(self.approver)

        self.assertEqual(self.current_run().state, "Approved")
        self.assertEqual(self.approval().merge_error, "Pull Request is not mergeable")
        self.assertTrue(self.events("merge_blocked"))

    def test_reject_needs_a_reason_that_reaches_the_developer(self):
        with self.assertRaises(frappe.ValidationError):
            self.decide(self.approver, approve=False)

        self.decide(self.approver, approve=False, note="Round the rate to two places")

        self.assertEqual(self.approval().status, "Rejected")
        self.assertEqual(self.current_run().state, "Preparing Fix")
        self.assertIn("Round the rate to two places", self.github.comments[-1][2])
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_doctype": "Task",
                    "reference_name": self.current_run().task,
                    "content": ["like", "%two places%"],
                },
            )
        )

    def test_a_rejected_commit_is_not_asked_again(self):
        self.decide(self.approver, approve=False, note="Round the rate to two places")

        self.assertEqual(fixes.refresh(self.current_run()), "refreshed")
        self.assertEqual(self.current_run().state, "Preparing Fix")
        self.assertEqual(self.approval().status, "Rejected")

        self.github.push(REPO, 7, NEW_SHA)
        fixes.refresh(self.current_run())

        self.assertEqual(self.current_run().state, "Awaiting Approval")
        self.assertEqual(
            (self.approval().status, self.approval().head_sha), ("Pending", NEW_SHA)
        )

    def test_the_first_decision_wins(self):
        self.github.set_checks(SHA, {"tests": None})
        self.decide(self.approver)
        with self.assertRaises(frappe.ValidationError) as caught:
            approvals.decide(self.approval().name, self.senior, False, "too late")
        self.assertIn("already approved", str(caught.exception))

    def test_a_second_click_says_who_decided_first(self):
        self.github.set_checks(SHA, {"tests": None})
        self.decide(self.approver)
        with self.assertRaises(frappe.ValidationError) as caught:
            self.decide(self.senior)
        self.assertIn("already approved by " + self.approver, str(caught.exception))

    def test_the_developer_cannot_approve_their_own_fix(self):
        with self.assertRaises(frappe.PermissionError):
            self.decide(self.developer)

    def test_only_a_senior_approves_a_sensitive_fix(self):
        frappe.db.set_value(
            "HDS Copilot Approval", self.approval().name, "sensitive", 1
        )
        with self.assertRaises(frappe.PermissionError):
            self.decide(self.approver)
        self.decide(self.senior)
        self.assertEqual(self.current_run().state, "Merged")


class TestOutcomes(FixCase):
    def setUp(self):
        super().setUp()
        self.diagnosed()
        self.row = self.opened()

    def test_merged_on_github_without_the_approval_is_recorded(self):
        pull = dict(
            self.github.pulls[(REPO, 7)],
            state="closed",
            merged=True,
            merge_commit_sha="c" * 40,
        )
        with patch.object(runs, "tell_people") as tell:
            fixes.on_pull_request(pull, "closed", [self.row])

        self.assertEqual(self.current_run().state, "Merged")
        self.assertEqual(self.approval().status, "Superseded")
        self.assertTrue(self.events("merged_without_approval"))
        tell.assert_called_once()

    def test_closed_without_merging_goes_back_to_preparing_fix(self):
        pull = dict(self.github.pulls[(REPO, 7)], state="closed")
        fixes.on_pull_request(pull, "closed", [self.row])

        self.assertEqual(self.current_run().state, "Preparing Fix")
        self.assertEqual(self.approval().status, "Superseded")

    def test_mark_deployed_resolves_and_the_customer_confirms(self):
        self.decide(self.approver)
        frappe.set_user(self.approver)
        info = api.mark_deployed(self.ticket.name, "Live since 21:30")
        frappe.set_user("Administrator")

        self.assertEqual(info["state"], "Resolved")
        self.assertEqual(self.events("stage")[-1]["stage"], "Resolved")
        self.assertIn("Live since 21:30", self.events("stage")[-1]["message"])

        customer.decide_resolution(self.ticket.name, True, "works")
        self.assertEqual(self.current_run().state, "Closed")

    def test_the_card_shows_the_fix_and_who_may_decide(self):
        frappe.set_user(self.approver)
        fix = api.get_run(self.ticket.name)["fix"]
        self.assertEqual(fix["pull_request"]["number"], 7)
        self.assertEqual(fix["approval"]["status"], "Pending")
        self.assertEqual(fix["approval"]["files"][0]["filename"], "demo_app/margin.py")
        self.assertTrue(fix["approval"]["checks"]["green"])
        self.assertTrue(fix["can_decide"])

        frappe.set_user(create_agent("fix.bystander@example.com").name)
        fix = api.get_run(self.ticket.name)["fix"]
        self.assertFalse(fix["can_decide"])
        self.assertIn("approvers", fix["approval"]["why_not_me"])


class TestGitHubSync(FixCase):
    """The task sync's webhook path reaches Copilot, and a refresh finds a pull request no webhook brought."""

    def setUp(self):
        super().setUp()
        self.diagnosed()
        self.task = self.current_run().task

    def deliver(self, action, pull):
        payload = {
            "action": action,
            "repository": {"full_name": REPO},
            "pull_request": pull,
            "sender": {"login": "dev-login"},
        }
        return github_sync.handle_event("pull_request", payload, None)

    def test_an_opened_pull_request_reaches_copilot_through_the_sync(self):
        pull = self.github.add_pull(REPO, 11, SHA, body=f"Closes {self.task}")
        self.deliver("opened", pull)

        self.assertEqual(self.current_run().state, "Awaiting Approval")
        row = frappe.get_doc("HD Pull Request", self.current_run().pull_request)
        self.assertEqual((row.head_sha, row.base_branch), (SHA, "main"))

    def test_the_task_completed_note_asks_to_deploy(self):
        pull = self.github.add_pull(REPO, 12, SHA, body=f"Closes {self.task}")
        self.deliver("opened", pull)
        merged = dict(pull, state="closed", merged=True, merge_commit_sha="d" * 40)
        with patch.object(runs, "tell_people"):
            self.deliver("closed", merged)

        notes = frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": self.ticket.name},
            pluck="content",
        )
        self.assertTrue([n for n in notes if "Mark deployed" in n])
        self.assertFalse([n for n in notes if "Reply to the customer" in n])
        self.assertEqual(self.current_run().state, "Merged")

    def test_the_hubs_merge_completes_the_task_without_waiting_for_github(self):
        pull = self.github.add_pull(REPO, 15, SHA, body=f"Closes {self.task}")
        self.deliver("opened", pull)

        self.decide(self.approver)

        self.assertEqual(self.current_run().state, "Merged")
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Completed")
        row = frappe.get_doc("HD Pull Request", self.current_run().pull_request)
        self.assertEqual((row.state, row.merge_commit_sha), ("Merged", "m" + SHA))

        notes = frappe.db.count(
            "HD Ticket Comment", {"reference_ticket": self.ticket.name}
        )
        self.deliver("closed", self.github.pulls[(REPO, 15)])  # GitHub's own, later
        self.assertEqual(
            frappe.db.count(
                "HD Ticket Comment", {"reference_ticket": self.ticket.name}
            ),
            notes,
        )

    def test_with_the_sync_off_copilot_leaves_github_alone(self):
        frappe.db.set_single_value("HD GitHub Settings", "enabled", 0)
        self.github.add_pull(REPO, 16, SHA, body=f"Closes {self.task}")

        self.assertIn("sync is off", fixes.refresh(self.current_run()))
        self.assertEqual(self.current_run().state, "Preparing Fix")
        self.assertFalse(self.github.calls)

    def test_refresh_finds_a_pull_request_no_webhook_brought(self):
        self.github.add_pull(REPO, 13, SHA, body=f"Closes {self.task}")
        self.github.search_items = [
            {"repository_url": f"https://api.github.com/repos/{REPO}", "number": 13}
        ]

        frappe.set_user(self.approver)
        info = api.refresh_fix(self.ticket.name)
        frappe.set_user("Administrator")

        self.assertEqual(info["refresh"], "refreshed")
        self.assertEqual(self.current_run().state, "Awaiting Approval")
        self.assertEqual(self.approval().number, 13)

    def test_refresh_moves_on_from_a_closed_pull_request(self):
        first = self.github.add_pull(REPO, 11, SHA, body=f"Closes {self.task}")
        self.deliver("opened", first)
        self.deliver("closed", dict(first, state="closed"))
        self.assertEqual(self.current_run().state, "Preparing Fix")

        self.github.add_pull(REPO, 14, NEW_SHA, body=f"Closes {self.task}")
        self.github.search_items = [
            {"repository_url": f"https://api.github.com/repos/{REPO}", "number": 14}
        ]
        fixes.refresh(self.current_run())

        self.assertEqual(self.current_run().state, "Awaiting Approval")
        self.assertEqual(self.approval().number, 14)
