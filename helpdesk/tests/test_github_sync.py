from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import github_sync
from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    GITHUB_TEST_REPO,
    enable_github_sync,
    get_reminder_messages,
    get_task_comments,
    github_signature,
    make_assignment,
    make_github_payload,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
    run_as_user,
    send_github_webhook,
)

PM = ("pm.github@github-sync.example", "Sneha Kurian")
LEAD = ("lead.github@github-sync.example", "Arun Menon")
DEV = ("dev.github@github-sync.example", "Divya Suresh")
OUTSIDER = ("outsider.github@github-sync.example", "Kiran Babu")


class GitHubSyncCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (LEAD, DEV, OUTSIDER):
            make_tasky_user(*user)
        self.project = make_project(
            "GitHub Sync - Billing Revamp",
            members=[(LEAD[0], "Developer"), (DEV[0], "Developer")],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])
        self.task = make_task(self.project, "Invoice print format").name
        make_assignment("Task", self.task, DEV[0])
        enable_github_sync()

    def send(self, event, action="", **overrides):
        overrides.setdefault("body", f"Closes {self.task}")
        return send_github_webhook(
            event, make_github_payload(event, action, **overrides)
        )

    def status(self, task=None):
        return frappe.db.get_value("Task", task or self.task, "status")

    def rows(self, task=None):
        return frappe.get_all(
            "HD Pull Request",
            filters={"task": task or self.task},
            fields=["name", "repo", "number", "state", "review_state", "ci_state"],
        )


class TestWebhookReceiving(GitHubSyncCase):
    def test_signed_ping_is_answered(self):
        result = send_github_webhook("ping", {"zen": "Keep it logically awesome."})
        self.assertTrue(result.get("pong"))

    def test_wrong_signature_is_refused(self):
        with self.assertRaises(frappe.AuthenticationError):
            send_github_webhook(
                "ping", {"zen": "hi"}, signature=github_signature(b"other body")
            )

    def test_missing_signature_is_refused(self):
        with self.assertRaises(frappe.AuthenticationError):
            send_github_webhook("ping", {"zen": "hi"}, signature=None)

    def test_disabled_sync_refuses_even_signed_deliveries(self):
        enable_github_sync(enabled=0)
        with self.assertRaises(frappe.AuthenticationError):
            self.send("pull_request", "opened")
        self.assertEqual(self.rows(), [])

    def test_same_delivery_is_processed_once(self):
        payload = make_github_payload(
            "pull_request", "opened", body=f"Closes {self.task}"
        )
        first = send_github_webhook("pull_request", payload, delivery="gh-dup-1")
        second = send_github_webhook("pull_request", payload, delivery="gh-dup-1")

        self.assertTrue(first.get("queued"))
        self.assertTrue(second.get("duplicate"))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(get_task_comments(self.task, "%opened by%")), 1)

    def test_repository_outside_the_allowed_list_is_ignored(self):
        result = send_github_webhook(
            "pull_request",
            make_github_payload(
                "pull_request",
                "opened",
                repo="someone-else/tool",
                body=f"Closes {self.task}",
            ),
            delivery="gh-foreign-1",
        )

        self.assertIn("ignored", result)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.status(), "Open")
        self.assertEqual(
            frappe.db.get_value("HD GitHub Delivery", "gh-foreign-1", "status"),
            "Ignored",
        )


class TestPullRequestFlow(GitHubSyncCase):
    def test_opened_pr_links_the_task_and_starts_work(self):
        self.send("pull_request", "opened")

        row = frappe.get_doc("HD Pull Request", self.rows()[0].name)
        self.assertEqual(
            (row.repo, row.number, row.state, row.link_kind),
            (GITHUB_TEST_REPO, 7, "Open", "Closes"),
        )
        self.assertEqual(row.author, "dev-octocat")
        self.assertEqual(self.status(), "Working")
        self.assertEqual(len(get_task_comments(self.task, "%opened by @dev-octocat%")), 1)

    def test_task_named_only_in_the_branch_is_a_reference(self):
        self.send(
            "pull_request",
            "opened",
            body="",
            branch=f"feature/{self.task.lower()}_print",
        )
        self.assertEqual(
            frappe.db.get_value("HD Pull Request", {"task": self.task}, "link_kind"),
            "Refs",
        )

    def test_review_request_sends_the_task_to_review(self):
        self.send("pull_request", "opened")
        self.send("pull_request", "review_requested")

        self.assertEqual(self.status(), "Pending Review")
        self.assertEqual(self.rows()[0].review_state, "Review requested")
        self.assertTrue(
            any(
                "PR #7 ready for review" in m
                for m in get_reminder_messages(LEAD[0], self.task)
            )
        )

    def test_changes_requested_sends_it_back_to_working(self):
        self.send("pull_request", "opened")
        self.send("pull_request", "ready_for_review")
        self.send(
            "pull_request_review",
            "submitted",
            review_state="changes_requested",
            review_body="**Totals** are rounded twice.",
        )

        self.assertEqual(self.status(), "Working")
        self.assertEqual(self.rows()[0].review_state, "Changes requested")
        messages = get_reminder_messages(DEV[0], self.task)
        self.assertTrue(
            any("Totals are rounded twice." in m for m in messages), messages
        )

    def test_approval_tells_the_assignee(self):
        self.send("pull_request", "opened")
        self.send("pull_request_review", "submitted", review_state="approved")

        self.assertEqual(self.rows()[0].review_state, "Approved")
        self.assertTrue(
            any("approved" in m for m in get_reminder_messages(DEV[0], self.task))
        )

    def test_failing_ci_is_flagged_until_a_new_commit_passes(self):
        self.send("pull_request", "opened")
        send_github_webhook(
            "workflow_run",
            make_github_payload("workflow_run", "completed", conclusion="failure"),
        )
        self.assertEqual(self.rows()[0].ci_state, "Failing")
        self.assertTrue(
            any("CI failing on PR #7" in m for m in get_reminder_messages(DEV[0], self.task))
        )

        # another workflow passing on the same commit doesn't clear the failure
        send_github_webhook(
            "workflow_run",
            make_github_payload("workflow_run", "completed", conclusion="success"),
        )
        self.assertEqual(self.rows()[0].ci_state, "Failing")

        send_github_webhook(
            "workflow_run",
            make_github_payload(
                "workflow_run", "completed", conclusion="success", sha="d4e5f6"
            ),
        )
        self.assertEqual(self.rows()[0].ci_state, "Passing")

    def test_merged_closing_pr_completes_the_task(self):
        self.send("pull_request", "opened")
        self.send("pull_request", "closed", merged=True)

        self.assertEqual(self.status(), "Completed")
        self.assertEqual(self.rows()[0].state, "Merged")
        self.assertTrue(frappe.db.get_value("Task", self.task, "completed_on"))

    def test_merge_on_a_review_project_waits_for_the_lead(self):
        frappe.db.set_value("Project", self.project, "review_before_done", 1)
        self.send("pull_request", "opened")
        self.send("pull_request", "closed", merged=True)

        self.assertEqual(self.status(), "Pending Review")
        run_as_user(LEAD[0], lambda: tasky.approve_task(task=self.task))
        self.assertEqual(self.status(), "Completed")

    def test_merge_tells_the_linked_ticket(self):
        ticket = make_ticket(subject="Invoice print shows wrong totals")
        frappe.db.set_value("Task", self.task, "hd_ticket", ticket.name)

        self.send("pull_request", "opened")
        self.send("pull_request", "closed", merged=True)

        comments = frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": ticket.name},
            pluck="content",
        )
        self.assertEqual(len([c for c in comments if "Fix merged in" in c]), 1)

    def test_pr_closed_without_merging_puts_the_task_on_hold(self):
        self.send("pull_request", "opened")
        self.send("pull_request", "closed", merged=False, closed=True)

        task = frappe.get_doc("Task", self.task)
        self.assertEqual(task.status, "On Hold")
        self.assertEqual(task.hold_reason, "Other")
        self.assertEqual(
            task.hold_note,
            "PR #7 closed without merging: Invoice print format",
        )
        self.assertEqual(self.rows()[0].state, "Closed")
        self.assertTrue(get_reminder_messages(LEAD[0], self.task))

    def test_reopening_our_closed_pr_lifts_the_hold(self):
        self.send("pull_request", "opened")
        self.send("pull_request", "closed", closed=True)
        self.send("pull_request", "reopened")

        self.assertEqual(self.status(), "Working")
        self.assertEqual(self.rows()[0].state, "Open")

    def test_merged_reference_only_comments(self):
        self.send("pull_request", "opened", body=f"Part of {self.task}")
        self.send("pull_request", "closed", body=f"Part of {self.task}", merged=True)

        self.assertEqual(self.status(), "Working")
        self.assertEqual(len(get_task_comments(self.task, "%merged by @lead-octocat%")), 1)

    def test_dependency_blocking_a_move_is_noted_not_failed(self):
        blocker = make_task(self.project, "Tax template").name
        frappe.db.set_value("Task", self.task, "depends_on_task", blocker)

        result = self.send("pull_request", "opened")

        self.assertEqual(self.status(), "Open")
        self.assertEqual(
            frappe.db.get_value("HD GitHub Delivery", result["queued"], "status"),
            "Processed",
        )
        self.assertEqual(len(get_task_comments(self.task, "%move the task to Working%")), 1)

    def test_unlinked_pr_gets_a_task_in_the_configured_project(self):
        inbox = make_project("GitHub Sync - Unplanned Work", owner=PM[0]).name
        enable_github_sync(unlinked_pr_project=inbox)

        self.send("pull_request", "opened", number=42, title="Fix typo", body="")

        task = frappe.get_all(
            "Task",
            filters={"project": inbox, "subject": "Unlinked PR #42: Fix typo"},
            fields=["name", "status", "is_key", "_assign"],
        )
        self.assertEqual(len(task), 1)
        self.assertEqual(task[0].status, "Working")
        self.assertFalse(task[0].is_key)
        self.assertFalse(frappe.parse_json(task[0]._assign or "[]"))

        # later events follow the created task even though the PR still names none
        self.send("pull_request", "closed", number=42, title="Fix typo", body="", merged=True)
        self.assertEqual(self.status(task[0].name), "Completed")

    def test_unlinked_pr_without_a_project_asks_on_github(self):
        enable_github_sync(github_token="ghp_test_token")
        with patch.object(github_sync.requests, "request") as request:
            self.send("pull_request", "opened", number=43, body="")

        method, url = request.call_args.args
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith(f"/repos/{GITHUB_TEST_REPO}/issues/43/comments"))
        self.assertEqual(frappe.get_all("HD Pull Request", filters={"number": 43}), [])

    def test_processing_an_event_twice_adds_nothing(self):
        for delivery in ("gh-twice-1", "gh-twice-2"):
            send_github_webhook(
                "pull_request",
                make_github_payload("pull_request", "opened", body=f"Closes {self.task}"),
                delivery=delivery,
            )
        for delivery in ("gh-twice-3", "gh-twice-4"):
            send_github_webhook(
                "pull_request",
                make_github_payload(
                    "pull_request", "closed", body=f"Closes {self.task}", merged=True
                ),
                delivery=delivery,
            )

        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(get_task_comments(self.task, "%opened by%")), 1)
        self.assertEqual(len(get_task_comments(self.task, "%merged by%")), 1)
        self.assertEqual(self.status(), "Completed")


class TestPullRequestAccess(GitHubSyncCase):
    def test_prs_follow_task_read_permission(self):
        self.send("pull_request", "opened")
        row = self.rows()[0].name

        self.assertTrue(
            frappe.has_permission("HD Pull Request", "read", row, user=DEV[0])
        )
        self.assertFalse(
            frappe.has_permission("HD Pull Request", "read", row, user=OUTSIDER[0])
        )
        self.assertFalse(
            frappe.has_permission("HD Pull Request", "write", row, user=DEV[0])
        )

    def test_task_detail_and_kanban_carry_the_pr(self):
        self.send("pull_request", "opened")

        detail = run_as_user(DEV[0], lambda: tasky.get_task_detail(task=self.task))
        self.assertEqual(
            [(p["repo"], p["number"]) for p in detail["pull_requests"]],
            [(GITHUB_TEST_REPO, 7)],
        )
        board = run_as_user(LEAD[0], lambda: tasky.get_kanban_tasks(project=self.project))
        card = next(t for t in board["columns"]["Working"] if t["name"] == self.task)
        self.assertEqual(card["pull_request"]["number"], 7)
