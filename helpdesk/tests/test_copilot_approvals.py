# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Who approves a Copilot fix, and what happens when nobody does."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.copilot import approvals
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    hold_commits,
    make_copilot_run,
    make_copilot_settings,
    make_ticket,
)


class ApprovalCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.one = create_agent("approver.one@example.com").name
        self.two = create_agent("approver.two@example.com").name
        self.senior = create_agent("approver.senior@example.com").name
        make_copilot_settings(
            enabled=1,
            approvers=[
                {"user": self.one, "senior": 0, "active": 1},
                {"user": self.two, "senior": 0, "active": 1},
                {"user": self.senior, "senior": 1, "active": 1},
            ],
            approval_reminder_hours=4,
            approval_escalate_hours=24,
        )
        self.customer = create_customer("Approval Rules Co").name
        self.ticket = make_ticket(subject="Approval rules", customer=self.customer)
        self.run = make_copilot_run(self.ticket.name, state="Awaiting Approval")
        self.notified, self.channel = [], []

        def notify(users, doctype, name, *args, **kwargs):
            if name != self.ticket.name:
                return  # another approval on the site (a real one) is reminded too
            self.notified.append(list(users))
            self.channel.append(bool(kwargs.get("escalate")))

        patcher = patch("helpdesk.work_reminders.notify_users", side_effect=notify)
        patcher.start()
        self.addCleanup(patcher.stop)

    def approval(self, assigned_to, hours_ago=0, sensitive=0, status="Pending"):
        return frappe.get_doc(
            {
                "doctype": "HDS Copilot Approval",
                "run": self.run.name,
                "ticket": self.ticket.name,
                "status": status,
                "repo": "tbocloud/tbo-copilot-sandbox",
                "number": 1,
                "head_sha": "a" * 40,
                "sensitive": sensitive,
                "assigned_to": assigned_to,
                "assigned_at": add_to_date(now_datetime(), hours=-hours_ago),
            }
        ).insert(ignore_permissions=True)


class TestAssignment(ApprovalCase):
    def test_the_least_loaded_approver_gets_it(self):
        self.approval(self.one)
        self.assertEqual(approvals.pick_approver(self.run, sensitive=False), self.two)

    def test_a_sensitive_fix_only_goes_to_a_senior(self):
        self.assertEqual(approvals.pick_approver(self.run, sensitive=True), self.senior)

    def test_the_customers_developer_comes_first_when_allowed(self):
        frappe.db.set_value(
            "HD Customer", self.customer, "custom_assigned_developer", self.two
        )
        self.approval(self.two)
        self.assertEqual(approvals.pick_approver(self.run, sensitive=False), self.two)

    def test_without_seniors_the_agent_managers_are_seniors(self):
        manager = create_agent("approval.manager@example.com")
        # create_agent's User is stale once the HD Agent exists
        manager = frappe.get_doc("User", manager.name)
        manager.add_roles("Agent Manager")
        make_copilot_settings(
            enabled=1, approvers=[{"user": self.one, "senior": 0, "active": 1}]
        )
        self.assertIn(manager.name, approvals.seniors())
        self.assertNotIn(self.one, approvals.seniors())


class TestReminders(ApprovalCase):
    def test_a_waiting_approval_is_reminded_once_per_interval(self):
        doc = self.approval(self.one, hours_ago=5)

        approvals.remind_and_escalate()
        approvals.remind_and_escalate()

        self.assertTrue(
            frappe.db.get_value("HDS Copilot Approval", doc.name, "reminded_at")
        )
        self.assertEqual(self.notified, [[self.one]])
        self.assertEqual(self.channel, [False])  # a reminder stays between two people

    def test_a_long_wait_goes_to_a_senior_and_the_managers_hear_it(self):
        doc = self.approval(self.one, hours_ago=25)

        approvals.remind_and_escalate()

        doc.reload()
        self.assertEqual(doc.assigned_to, self.senior)
        self.assertTrue(doc.escalated_at)
        self.assertIn(self.senior, self.notified[-1])
        self.assertTrue(self.channel[-1])  # a long wait is told in the team's channel

    def test_decided_approvals_are_left_alone(self):
        self.approval(self.one, hours_ago=30, status="Approved")
        approvals.remind_and_escalate()
        self.assertEqual(self.notified, [])
