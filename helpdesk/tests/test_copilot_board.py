# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Copilot board (Phase 10): all of Copilot's work on one page, read with the person's own
permissions; the worker and the AI budget for Agent Managers only."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from helpdesk.api import copilot_board as api
from helpdesk.copilot import board, runs
from helpdesk.test_utils import (create_agent, create_customer, create_user,
                                 hold_commits, make_copilot_run,
                                 make_copilot_settings, make_site_registry,
                                 make_team, make_ticket, run_as_user)

APPROVAL = "HDS Copilot Approval"
DEPLOY = "HDS Deploy Request"


class BoardCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_copilot_settings(enabled=1, monthly_ai_budget_usd=50)
        frappe.db.set_single_value("HD Settings", "restrict_tickets_by_agent_group", 0)
        self.agent = create_agent("board.agent@example.com").name
        self.approver = create_agent("board.approver@example.com").name
        self.customer = create_customer("Board Co").name

    def run_in(self, state: str, subject: str = "Margin wrong", **values):
        ticket = make_ticket(subject=subject, customer=self.customer).name
        run = make_copilot_run(ticket, state, **values)
        frappe.db.set_value("HD Ticket", ticket, "custom_copilot_run", run.name)
        return run

    def column(self, result: dict, key: str) -> list[dict]:
        return next(c for c in result["columns"] if c["key"] == key)["cards"]

    def as_agent(self, fn, user=None):
        return run_as_user(user or self.agent, fn)


class TestWork(BoardCase):
    def test_each_ticket_is_in_its_column_with_who_it_waits_on(self):
        self.run_in("Queued", "Queued one")
        self.run_in("Explaining", "Explain it")
        self.run_in("Preparing Fix", "Fix failed", fix_status="Failed")
        waiting = self.run_in("Awaiting Approval", "Approve me")
        approval = frappe.get_doc(
            {
                "doctype": APPROVAL,
                "run": waiting.name,
                "ticket": waiting.ticket,
                "status": "Pending",
                "kind": "Code Change",
                "assigned_to": self.approver,
                "assigned_at": now_datetime(),
            }
        ).insert(ignore_permissions=True)
        waiting.db_set("approval", approval.name)
        self.run_in("Merged", "Ship it")
        self.run_in("Escalated", "Needs Ali")

        result = board.work(customer=self.customer)

        self.assertEqual(
            [c["key"] for c in result["columns"]],
            ["investigating", "customer", "fixing", "approval", "shipping", "person"],
        )
        cards = {
            c["key"]: [x["subject"] for x in c["cards"]] for c in result["columns"]
        }
        self.assertEqual(cards["investigating"], ["Queued one"])
        self.assertEqual(cards["customer"], ["Explain it"])
        self.assertEqual(cards["fixing"], ["Fix failed"])
        self.assertEqual(cards["approval"], ["Approve me"])
        self.assertEqual(cards["shipping"], ["Ship it"])
        self.assertEqual(cards["person"], ["Needs Ali"])
        self.assertEqual(
            self.column(result, "approval")[0]["waits_on"],
            frappe.utils.get_fullname(self.approver),
        )
        self.assertIn("developer", self.column(result, "fixing")[0]["waits_on"])
        self.assertEqual(
            self.column(result, "customer")[0]["waits_on"],
            "an agent to send the explanation",
        )

    def test_only_the_tickets_latest_run_and_recent_problems(self):
        old = self.run_in("Escalated", "Long ago")
        frappe.db.set_value(
            "HDS Copilot Run",
            old.name,
            "modified",
            add_days(now_datetime(), -40),
            update_modified=False,
        )
        first = self.run_in("Failed", "Tried twice")
        second = make_copilot_run(first.ticket, "Queued")
        frappe.db.set_value(
            "HD Ticket", first.ticket, "custom_copilot_run", second.name
        )

        result = board.work(customer=self.customer)

        self.assertEqual(self.column(result, "person"), [])
        self.assertEqual(
            [c["run"] for c in self.column(result, "investigating")], [second.name]
        )

    def test_mine_and_the_error_watch_filters(self):
        theirs = self.run_in("Preparing Fix", "Someone else's")
        mine = self.run_in("Preparing Fix", "Mine")
        frappe.db.set_value("HD Ticket", mine.ticket, "_assign", f'["{self.agent}"]')
        frappe.db.set_value(
            "HD Ticket", theirs.ticket, "custom_copilot_source", "Error watch"
        )

        mine_only = self.as_agent(lambda: board.work(customer=self.customer, mine=True))
        watch_only = board.work(customer=self.customer, source="Error watch")

        self.assertEqual(
            [c["subject"] for c in self.column(mine_only, "fixing")], ["Mine"]
        )
        self.assertEqual(
            [c["subject"] for c in self.column(watch_only, "fixing")],
            ["Someone else's"],
        )

    def test_resolved_this_week_is_counted(self):
        done = self.run_in("Resolved", "Fixed it")
        done.db_set("finished_at", now_datetime())
        self.assertEqual(board.work(customer=self.customer)["resolved_this_week"], 1)


class TestPermissions(BoardCase):
    def test_an_agent_outside_the_tickets_team_does_not_see_its_run(self):
        hidden = self.run_in("Preparing Fix", "Other team's")
        self.run_in("Preparing Fix", "Open to all")
        team = make_team("Board Restricted Team", members=[self.approver])
        frappe.db.set_value("HD Ticket", hidden.ticket, "agent_group", team.name)
        frappe.db.set_single_value(
            "HD Settings",
            {
                "restrict_tickets_by_agent_group": 1,
                "do_not_restrict_tickets_without_an_agent_group": 1,
            },
        )

        seen = self.as_agent(lambda: board.work(customer=self.customer))

        self.assertEqual(
            [c["subject"] for c in self.column(seen, "fixing")], ["Open to all"]
        )

    def test_the_worker_and_the_budget_are_for_managers(self):
        board.worker_seen("demo-worker")
        frappe.cache.hdel(board.WORKERS_SEEN, "old-worker")

        plain = self.as_agent(board.summary)
        managed = board.summary()  # Administrator

        self.assertNotIn("workers", plain)
        self.assertNotIn("month_spend_usd", plain)
        self.assertEqual(managed["month_budget_usd"], 50)
        worker = next(w for w in managed["workers"] if w["worker"] == "demo-worker")
        self.assertTrue(worker["online"])
        frappe.cache.hdel(board.WORKERS_SEEN, "demo-worker")

    def test_only_agents_may_open_it(self):
        outsider = create_user("board.outsider@example.com").name
        for call in (
            api.summary,
            api.work,
            api.approvals,
            api.releases,
            api.sites,
            api.known_issues,
        ):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(outsider, call)

    def test_a_run_change_tells_open_boards_without_naming_it(self):
        run = self.run_in("Queued")
        with patch("frappe.publish_realtime") as published:
            runs.publish_run(run)
        boards = [c for c in published.call_args_list if c.args[0] == board.BOARD_EVENT]
        self.assertEqual(len(boards), 1)
        self.assertEqual(boards[0].args[1], {})


class TestTheOtherTabs(BoardCase):
    def test_approvals_lists_fixes_and_releases_the_longest_wait_first(self):
        run = self.run_in("Awaiting Approval", "A fix")
        frappe.get_doc(
            {
                "doctype": APPROVAL,
                "run": run.name,
                "ticket": run.ticket,
                "status": "Pending",
                "kind": "Code Change",
                "assigned_to": self.approver,
                "assigned_at": add_days(now_datetime(), -1),
                "risk_level": "high",
                "sensitive": 1,
            }
        ).insert(ignore_permissions=True)
        release = frappe.get_doc(
            {
                "doctype": DEPLOY,
                "status": "Waiting for approval",
                "source": "Push",
                "repository": "tbocloud/demo-alpha-app",
                "branch": "main",
                "assigned_to": self.agent,
                "assigned_at": now_datetime(),
            }
        )
        release.flags.ignore_mandatory = True
        release.insert(ignore_permissions=True)

        rows = [
            r
            for r in board.approvals()
            if r["name"] in (release.name,) or r["ticket"] == run.ticket
        ]

        self.assertEqual([r["type"] for r in rows], ["Code Change", "Release"])
        self.assertTrue(rows[0]["sensitive"])
        self.assertGreater(rows[0]["waited_hours"], 23)
        self.assertIn("/app/hds-deploy-request/", rows[1]["link"])

    def test_sites_show_drift_the_watch_and_missing_fixes(self):
        card = make_site_registry(
            self.customer,
            site_url="https://board.example.com",
            apps=[
                {
                    "app": "alpha_trading",
                    "branch": "main",
                    "deployed_commit": "a" * 40,
                    "drift_status": "Drift",
                }
            ],
        )
        frappe.db.set_value("HD Customer", self.customer, "custom_copilot_watch", 1)
        issue = frappe.get_doc(
            {
                "doctype": "HDS Known Issue",
                "title": "AttributeError in alpha_trading.x",
                "status": "Fixed",
                "signature_key": frappe.generate_hash(length=20),
                "sites": [
                    {"registry": card.name, "customer": self.customer, "has_fix": "No"}
                ],
            }
        ).insert(ignore_permissions=True)

        [site] = board.sites(self.customer)
        [known] = [i for i in board.known_issues("Fixed") if i["name"] == issue.name]

        self.assertEqual(site["apps"][0]["drift"], "Drift")
        self.assertTrue(site["watch"]["on"])
        self.assertEqual((site["open_issues"], site["missing_fixes"]), (0, 1))
        self.assertEqual(known["missing_fix"], 1)
        self.assertEqual(known["sites"][0]["site"], "https://board.example.com")

    def test_releases_split_the_pipeline_from_the_last_days(self):
        def release(status, days_ago=0):
            doc = frappe.get_doc(
                {
                    "doctype": DEPLOY,
                    "status": status,
                    "source": "Push",
                    "repository": "tbocloud/demo-beta-app",
                    "branch": "main",
                }
            )
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            if days_ago:
                frappe.db.set_value(
                    DEPLOY,
                    doc.name,
                    "modified",
                    add_days(now_datetime(), -days_ago),
                    update_modified=False,
                )
            return doc.name

        waiting = release("Waiting for CI")
        done = release("Succeeded")
        old = release("Failed", days_ago=10)

        result = board.releases(7)

        self.assertIn(waiting, [r["name"] for r in result["pipeline"]])
        finished = [r["name"] for r in result["finished"]]
        self.assertIn(done, finished)
        self.assertNotIn(old, finished)
