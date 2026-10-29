# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The error watch and known-issue memory (Phase 9): a new error on a customer's site becomes a
ticket before the customer reports it, and Copilot remembers each error, its fix and which sites
have it."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from helpdesk.copilot import assistant, customer, known_issues, runs, watch
from helpdesk.test_utils import (
    FakeErrorSite,
    create_agent,
    create_customer,
    hold_commits,
    make_copilot_run,
    make_copilot_settings,
    make_site_registry,
    make_support_connection,
)

ISSUE = "HDS Known Issue"
SITE_ERROR = "HDS Site Error"
MARGIN = "alpha_trading.accounts.margin.validate_margin_on_submit"
TIERS = "alpha_trading.selling.discounts.apply_tier_discounts"
MISSING = "AttributeError: 'AlphaDiscountSettings' object has no attribute 'get_minimum_margin'"
REPO = "tbocloud/demo-alpha-app"
SITE_COMMIT = "a" * 40
MERGE = "b" * 40


class WatchCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.developer = create_agent("watch.dev@example.com").name
        self.senior = create_agent("watch.senior@example.com").name
        make_copilot_settings(
            enabled=1,
            watch_enabled=1,
            watch_minutes=15,
            watch_new_after_days=14,
            watch_min_count=3,
            watch_min_users=2,
            watch_site_daily_cap=3,
            watch_daily_cap=10,
            watch_ignored="",
            approvers=[{"user": self.senior, "senior": 1, "active": 1}],
        )
        self.customer = self.watched("Alpha Watch Co")
        self.card = self.site(self.customer, "https://alpha.example.com")
        self.site_errors = FakeErrorSite().install(self)
        # a ticket of the watch is raised, not emailed; nothing reaches a real site
        patcher = patch(
            "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.HDTicket.send_acknowledgement_email"
        )
        self.acknowledged = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("helpdesk.task_estimates.ai_estimate", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.db.set_single_value("HD Settings", "send_acknowledgement_email", 1)
        frappe.db.set_value(
            "HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled"
        )
        # GitHub's answers are cached a day; each test asks again
        frappe.cache.delete_keys(
            "copilot:has-fix:"
        )  # other queued runs on the site would be counted

    def watched(self, name: str) -> str:
        customer_name = create_customer(name).name
        frappe.db.set_value(
            "HD Customer",
            customer_name,
            {
                "custom_copilot_watch": 1,
                "custom_copilot_enabled": 1,
                "custom_assigned_developer": self.developer,
            },
        )
        frappe.get_doc(
            {
                "doctype": "Contact",
                "first_name": "Ali",
                "email_ids": [
                    {
                        "email_id": f"ali@{name.lower().replace(' ', '-')}.example.com",
                        "is_primary": 1,
                    }
                ],
                "links": [{"link_doctype": "HD Customer", "link_name": customer_name}],
            }
        ).insert(ignore_permissions=True)
        return customer_name

    def site(self, customer_name: str, url: str):
        connection = make_support_connection(customer_name, url).name
        return make_site_registry(
            customer_name,
            connection,
            site_url=url,
            apps=[
                {
                    "app": "alpha_trading",
                    "repository": f"https://github.com/{REPO}",
                    "branch": "main",
                    "deployed_commit": SITE_COMMIT,
                }
            ],
        )

    def check(self, card=None):
        card = frappe.get_doc("HDS Site Registry", (card or self.card).name)
        watch.check_site(card)
        return card

    def started(self):
        """The site's first check (the baseline), as it would have run 15 minutes ago."""
        self.check()
        frappe.db.set_value(
            "HDS Site Registry",
            self.card.name,
            "watch_checked_at",
            add_days(now_datetime(), -1),
        )

    def rows(self, card=None):
        return frappe.get_all(
            SITE_ERROR,
            filters={"registry": (card or self.card).name},
            fields=["status", "count", "ticket", "known_issue", "signature"],
        )

    def watch_tickets(self):
        return frappe.get_all(
            "HD Ticket",
            filters={"custom_copilot_source": watch.SOURCE},
            fields=["name", "subject", "customer", "priority", "custom_known_issue"],
            order_by="creation asc",
        )

    def fixed_issue(self, status="Fixed"):
        """A known issue of the margin error, fixed by MERGE."""
        issue = known_issues.record(f"alpha_trading | {MARGIN} | {MISSING}")
        issue.update(
            {
                "status": status,
                "repository": REPO,
                "merge_commit": MERGE,
                "fixed_at": add_days(now_datetime(), -2),
                "fix_pull_request": f"https://github.com/{REPO}/pull/5",
            }
        )
        issue.save(ignore_permissions=True)
        return issue


class TestTheWatch(WatchCase):
    def test_the_first_check_is_a_baseline_and_opens_nothing(self):
        self.site_errors.error(MARGIN, MISSING, times=5)

        self.check()

        self.assertEqual([(r.status, r.count) for r in self.rows()], [("Baseline", 5)])
        self.assertFalse(self.watch_tickets())
        self.assertTrue(
            frappe.db.get_value("HDS Site Registry", self.card.name, "watch_checked_at")
        )

    def test_a_new_error_three_times_becomes_a_ticket_and_copilot_investigates(self):
        self.started()
        # not accounting code, where once would be enough
        self.site_errors.error(
            TIERS, MISSING, times=2, document="Sales Invoice/ACC-SINV-1"
        )
        self.check()
        self.assertEqual([(r.status, r.count) for r in self.rows()], [("Watching", 2)])
        self.assertFalse(self.watch_tickets())

        self.site_errors.error(TIERS, MISSING, document="Sales Invoice/ACC-SINV-2")
        self.check()

        [ticket] = self.watch_tickets()
        self.assertTrue(ticket.subject.startswith("Copilot noticed: AttributeError"))
        self.assertEqual(ticket.customer, self.customer)
        description = frappe.db.get_value("HD Ticket", ticket.name, "description")
        self.assertIn("Sales Invoice/ACC-SINV-2", description)  # the samples
        self.acknowledged.assert_not_called()  # the customer hears from a person first
        run = frappe.get_last_doc("HDS Copilot Run", filters={"ticket": ticket.name})
        self.assertEqual(run.state, "Queued")
        [row] = self.rows()
        self.assertEqual(
            (row.status, row.ticket, row.count), ("Ticket", ticket.name, 3)
        )
        issue = frappe.get_doc(ISSUE, ticket.custom_known_issue)
        self.assertEqual(issue.title, f"AttributeError in {TIERS}")
        self.assertEqual(
            [(r.registry, r.count, r.ticket) for r in issue.sites],
            [(self.card.name, 3, ticket.name)],
        )
        # the customer's developer hears it in the chat, and the diagnosis later
        self.assertIn(self.developer, assistant.watchers(run))

    def test_two_users_or_accounting_code_are_enough(self):
        self.started()
        self.site_errors.error(
            "alpha_trading.selling.discounts.apply", "ValueError: tier", owner="a@x.com"
        )
        self.site_errors.error(
            "alpha_trading.selling.discounts.apply", "ValueError: tier", owner="b@x.com"
        )
        self.site_errors.error(
            "erpnext.accounts.general_ledger.make_gl_entries",
            "ValidationError: unbalanced",
        )

        self.check()

        self.assertEqual(
            sorted(t.subject for t in self.watch_tickets()),
            [
                "Copilot noticed: ValidationError: unbalanced",
                "Copilot noticed: ValueError: tier",
            ],
        )

    def test_the_connectors_own_and_ignored_errors_never_make_a_ticket(self):
        self.started()
        self.site_errors.error(
            "helpdesk_client.mcp.handler",
            "PermissionError: refused",
            app="helpdesk_client",
            times=5,
        )
        self.site_errors.error(
            "frappe.sessions", "Session Stopped", app="frappe", times=5
        )
        # the connector's failed tool calls carry no app of their own (seen on the demo bench)
        self.site_errors.error(
            "MCP tool error: get_list",
            "('DocType', 'Alpha Discount Settings')",
            app="?",
            times=5,
        )

        self.check()

        self.assertEqual({r.status for r in self.rows()}, {"Ignored"})
        self.assertFalse(self.watch_tickets())

    def test_an_error_gone_for_the_whole_period_is_new_again(self):
        self.site_errors.error(MARGIN, MISSING, times=5)
        self.check()  # the baseline
        frappe.db.set_value(
            SITE_ERROR,
            {"registry": self.card.name},
            "last_seen",
            add_days(now_datetime(), -20),
        )
        frappe.db.set_value(
            "HDS Site Registry",
            self.card.name,
            "watch_checked_at",
            add_days(now_datetime(), -1),
        )
        self.site_errors.errors.clear()
        self.site_errors.error(MARGIN, MISSING, times=3)

        self.check()

        self.assertEqual(len(self.watch_tickets()), 1)

    def test_the_daily_caps_hold_and_the_managers_hear_it_once(self):
        frappe.db.set_single_value("HDS Copilot Settings", "watch_site_daily_cap", 1)
        self.started()
        self.site_errors.error("alpha_trading.a.one", "ValueError: one", times=3)
        self.site_errors.error("alpha_trading.b.two", "ValueError: two", times=3)
        frappe.cache.delete_keys("copilot:watch-capped:")

        with patch.object(assistant, "send") as sent, patch(
            "helpdesk.copilot.approvals._managers", return_value=[self.senior]
        ):
            self.check()

        self.assertEqual(len(self.watch_tickets()), 1)
        capped = [
            c for c in sent.call_args_list if "daily limit" in json.dumps(c.args[1])
        ]
        self.assertTrue(capped)
        self.assertEqual(
            sorted(r.status for r in self.rows()), ["Ticket", "Watching"]
        )  # the other one is still counted

    def test_a_site_that_does_not_answer_is_tried_again_from_the_same_time(self):
        self.started()
        checked = frappe.db.get_value(
            "HDS Site Registry", self.card.name, "watch_checked_at"
        )
        self.site_errors.down = True

        for _attempt in range(watch.FAILURES_NOTED):
            frappe.db.set_value(
                "HDS Site Registry", self.card.name, "watch_checked_at", checked
            )
            watch.run_due()

        card = frappe.get_doc("HDS Site Registry", self.card.name)
        self.assertEqual(str(card.watch_checked_at), str(checked))
        self.assertEqual(card.watch_failures, watch.FAILURES_NOTED)
        self.assertIn("did not answer", card.watch_note)

    def test_only_watched_customers_with_copilot_and_a_connection_are_checked(self):
        other = create_customer("Unwatched Co").name
        self.site(other, "https://other.example.com")
        frappe.db.set_single_value("HDS Copilot Settings", "watch_enabled", 0)
        self.assertEqual(watch.run_due(), [])

        frappe.db.set_single_value("HDS Copilot Settings", "watch_enabled", 1)
        self.assertEqual(watch.run_due(), [self.card.name])
        self.assertEqual(watch.run_due(), [])  # checked a moment ago


class TestTheCustomerHearsNothingFirst(WatchCase):
    def test_stages_wait_for_a_persons_reply(self):
        self.started()
        self.site_errors.error(MARGIN, MISSING, times=3)
        self.check()
        [ticket] = self.watch_tickets()
        run = frappe.get_last_doc("HDS Copilot Run", filters={"ticket": ticket.name})

        self.assertFalse(customer.send_stage(run, "Working on it"))
        held = frappe.get_last_doc(
            "HDS Copilot Event", filters={"run": run.name, "event_type": "stage"}
        )
        self.assertEqual(json.loads(held.payload).get("held"), "error watch")

        frappe.get_doc(
            {
                "doctype": "Communication",
                "communication_type": "Communication",
                "sent_or_received": "Sent",
                "reference_doctype": "HD Ticket",
                "reference_name": ticket.name,
                "content": "We are looking at it.",
                "subject": ticket.subject,
            }
        ).insert(ignore_permissions=True)
        self.assertFalse(watch.held(ticket.name))


class TestKnownIssues(WatchCase):
    def test_a_fixed_issue_on_a_site_without_the_fix_names_the_missing_fix(self):
        self.fixed_issue()
        self.started()
        self.site_errors.error(MARGIN, MISSING, times=3)

        with patch(
            "helpdesk.copilot.github.compare",
            return_value={"status": "behind", "commits": [], "files": []},
        ):
            self.check()

        [ticket] = self.watch_tickets()
        self.assertTrue(
            ticket.subject.startswith("Fixed elsewhere, not on this site yet")
        )
        self.assertFalse(frappe.db.exists("HDS Copilot Run", {"ticket": ticket.name}))

    def test_an_error_after_its_fix_on_a_site_with_it_came_back(self):
        issue = self.fixed_issue()
        self.started()
        self.site_errors.error(MARGIN, MISSING)  # once is enough

        with patch(
            "helpdesk.copilot.github.compare",
            return_value={"status": "ahead", "commits": [], "files": []},
        ):
            self.check()

        [ticket] = self.watch_tickets()
        self.assertTrue(ticket.subject.startswith("Came back after the fix"))
        self.assertEqual(ticket.priority, "High")
        issue.reload()
        self.assertEqual((issue.status, issue.came_back), ("Open", 1))
        assigned = json.loads(
            frappe.db.get_value("HD Ticket", ticket.name, "_assign") or "[]"
        )
        self.assertIn(self.senior, assigned)

    def test_a_merged_fix_marks_the_issue_fixed_and_tells_which_sites_have_it(self):
        self.started()
        self.site_errors.error(MARGIN, MISSING, times=3)
        self.check()
        [ticket] = self.watch_tickets()
        run = frappe.get_last_doc("HDS Copilot Run", filters={"ticket": ticket.name})
        run.db_set(
            {"merge_commit": SITE_COMMIT, "known_issue": ticket.custom_known_issue}
        )
        approval = frappe.get_doc(
            {
                "doctype": "HDS Copilot Approval",
                "run": run.name,
                "ticket": ticket.name,
                "status": "Merged",
                "kind": "Code Change",
                "pr_url": f"https://github.com/{REPO}/pull/9",
                "payload": json.dumps(
                    {
                        "url": f"https://github.com/{REPO}/pull/9",
                        "title": "Restore get_minimum_margin",
                        "files": [{"filename": "alpha_trading/settings.py"}],
                    }
                ),
            }
        ).insert(ignore_permissions=True)
        run.db_set("approval", approval.name)

        known_issues.on_merged(run)

        issue = frappe.get_doc(ISSUE, ticket.custom_known_issue)
        self.assertEqual(issue.status, "Fixed")
        self.assertEqual(issue.fix_title, "Restore get_minimum_margin")
        self.assertEqual(issue.fix_files, "alpha_trading/settings.py")
        self.assertEqual(
            [r.has_fix for r in issue.sites], ["Yes"]
        )  # the site runs that commit

    def test_a_diagnosis_links_only_errors_the_site_gave(self):
        ticket = frappe.get_doc(
            {
                "doctype": "HD Ticket",
                "subject": "Invoice will not submit",
                "raised_by": "ali@alpha-watch-co.example.com",
                "customer": self.customer,
            }
        ).insert(ignore_permissions=True)
        run = make_copilot_run(ticket.name, "Investigating", registry=self.card.name)
        given = f"alpha_trading | {MARGIN} | ValidationError: Row 12: margin below 10%"
        known_issues.remember_signatures(
            run.name,
            [
                {
                    "app": "alpha_trading",
                    "method": MARGIN,
                    "error": "Traceback\nValidationError: Row 12: margin below 10%",
                }
            ],
        )

        known_issues.link_run(
            run,
            [
                given.replace("Row 12", "Row 13"),  # the same error on another row
                "alpha_trading | made.up | KeyError: nothing",  # never given by the site
            ],
        )

        run.reload()
        issue = frappe.get_doc(ISSUE, run.known_issue)
        self.assertEqual(issue.signature, known_issues.normalise(given))
        self.assertEqual(frappe.db.count(ISSUE, {"method": "made.up"}), 0)
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "custom_known_issue"),
            issue.name,
        )

    def test_another_customers_worker_gets_code_facts_only(self):
        self.started()
        self.site_errors.error(
            "alpha_trading.selling.find",
            "DoesNotExistError: Customer Al Noor Stores",
            times=3,
        )
        self.check()
        [ticket] = self.watch_tickets()
        issue = frappe.get_doc(ISSUE, ticket.custom_known_issue)

        other = self.watched("Beta Watch Co")
        card = self.site(other, "https://beta.example.com")
        theirs = frappe.get_doc(
            {
                "doctype": "HD Ticket",
                "subject": "Something",
                "raised_by": "ali@beta-watch-co.example.com",
                "customer": other,
                "custom_known_issue": issue.name,
            }
        ).insert(ignore_permissions=True)
        run = make_copilot_run(theirs.name, "Investigating", registry=card.name)

        [shared] = known_issues.for_run(run)
        self.assertNotIn("signature", shared)
        self.assertNotIn("Al Noor", json.dumps(shared))
        self.assertEqual(shared["method"], "alpha_trading.selling.find")

        mine = make_copilot_run(ticket.name, "Investigating", registry=self.card.name)
        self.assertIn("Al Noor", known_issues.for_run(mine)[0]["signature"])

    def test_the_run_context_has_the_known_issues_and_the_last_deploys(self):
        self.started()
        self.site_errors.error(MARGIN, MISSING, times=3)
        self.check()
        [ticket] = self.watch_tickets()
        run = frappe.get_last_doc("HDS Copilot Run", filters={"ticket": ticket.name})

        context = runs.run_context(run)

        self.assertEqual(context["raised_by_copilot"], watch.SOURCE)
        self.assertEqual(
            [k["name"] for k in context["known_issues"]], [ticket.custom_known_issue]
        )
        self.assertEqual(context["site"]["deploys"], [])

    def test_a_kb_draft_only_for_a_resolved_customer_side_cause(self):
        self.started()
        self.site_errors.error(MARGIN, MISSING, times=3)
        self.check()
        [ticket] = self.watch_tickets()
        run = frappe.get_last_doc("HDS Copilot Run", filters={"ticket": ticket.name})
        run.db_set(
            {"root_cause_category": "bug", "known_issue": ticket.custom_known_issue}
        )
        self.assertFalse(known_issues.card(run)["can_draft_kb"])

        run.db_set("root_cause_category", "wrong_setting")
        frappe.db.set_value("HD Ticket", ticket.name, "status", "Resolved")
        with patch(
            "helpdesk.kb_drafts.draft_article",
            return_value=frappe._dict(name="kb-test-article"),
        ) as drafted:
            made = known_issues.draft_kb(run)

        drafted.assert_called_once_with(ticket.name)

        self.assertEqual(made["article"], "kb-test-article")
        self.assertEqual(
            frappe.db.get_value(ISSUE, ticket.custom_known_issue, "kb_article"),
            "kb-test-article",
        )
