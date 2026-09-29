from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk import work_summary
from helpdesk.api import work_summary as api
from helpdesk.test_utils import (
    create_customer,
    get_reminder_messages,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
    make_work_summary,
    run_as_user,
)

CUSTOMER = "Blue Lagoon Hospitality"
OTHER_CUSTOMER = "Palm Coast Retail"
IDLE_CUSTOMER = "Desert Rose Interiors"
PM = ("pm.summary@work-summary.example", "Leena Varghese")
LEAD = ("lead.summary@work-summary.example", "Nikhil Das")
DEV = ("dev.summary@work-summary.example", "Fathima Rizwana")
OUTSIDER = ("outsider.summary@work-summary.example", "Joel Mathew")
MANAGER = ("manager.summary@work-summary.example", "Divya Menon")

AI_UNAVAILABLE = frappe.ValidationError(
    "AI API key not configured. Go to HDS Hub Settings to set it."
)


class WorkSummaryCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        for customer in (CUSTOMER, OTHER_CUSTOMER, IDLE_CUSTOMER):
            create_customer(customer)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        for user in (LEAD, DEV, OUTSIDER):
            make_tasky_user(*user)

        self.project = make_project(
            f"{CUSTOMER} - Rollout",
            members=[(LEAD[0], "Developer"), (DEV[0], "Developer")],
            owner=PM[0],
        ).name
        frappe.db.set_value(
            "Project", self.project, {"customer": CUSTOMER, "project_lead": LEAD[0]}
        )
        self.start, self.end = add_days(nowdate(), -6), nowdate()


class TestStats(WorkSummaryCase):
    def test_overdue_excludes_held_tasks(self):
        make_task(self.project, "Fix stock valuation", add_days(nowdate(), -2))
        held = make_task(self.project, "Import opening stock", add_days(nowdate(), -3))
        frappe.db.set_value(
            "Task",
            held.name,
            {
                "status": "On Hold",
                "hold_reason": "Waiting on customer data",
                "hold_since": add_days(nowdate(), -1),
            },
        )
        done = make_task(self.project, "Configure chart of accounts")
        frappe.db.set_value("Task", done.name, "status", "Completed")
        make_task(self.project, "UAT sign-off", add_days(nowdate(), 3), is_key=1)
        dropped = make_task(self.project, "Legacy report port")
        frappe.db.set_value("Task", dropped.name, "status", "Cancelled")

        stats = work_summary.collect_customer_stats(CUSTOMER, self.start, self.end)
        tasks = stats["tasks"]

        self.assertEqual(tasks["overdue"], 1)
        self.assertEqual(tasks["overdue_list"][0]["subject"], "Fix stock valuation")
        self.assertEqual(tasks["on_hold"], 1)
        self.assertEqual(
            tasks["on_hold_list"][0]["hold_reason"], "Waiting on customer data"
        )
        self.assertEqual(tasks["completed"], 1)
        self.assertEqual(tasks["open"], 3)
        self.assertEqual(tasks["due_next_7_days"], 1)
        self.assertEqual(tasks["key_open"], 1)
        progress = stats["projects"][0]
        self.assertEqual((progress["completed"], progress["tasks"]), (1, 4))
        self.assertEqual(progress["progress"], 25)

    def test_sla_breaches_and_urgent_tickets(self):
        late = make_ticket(
            subject="Payroll run failed", priority="Low", customer=CUSTOMER
        )
        frappe.db.set_value(
            "HD Ticket",
            late.name,
            {"resolution_by": add_to_date(now_datetime(), hours=-2)},
        )
        urgent = make_ticket(
            subject="Invoice print is blank", priority="Urgent", customer=CUSTOMER
        )
        frappe.db.set_value(
            "HD Ticket",
            urgent.name,
            {"resolution_by": add_to_date(now_datetime(), days=1)},
        )
        failed = make_ticket(subject="VAT return mismatch", customer=CUSTOMER)
        frappe.db.set_value(
            "HD Ticket",
            failed.name,
            {
                "status": "Resolved",
                "status_category": "Resolved",
                "agreement_status": "Failed",
                "resolution_date": now_datetime(),
            },
        )
        other = make_ticket(subject="Not this customer", customer=OTHER_CUSTOMER)
        frappe.db.set_value(
            "HD Ticket",
            other.name,
            {"resolution_by": add_to_date(now_datetime(), hours=-2)},
        )

        tickets = work_summary.collect_customer_stats(CUSTOMER, self.start, self.end)[
            "tickets"
        ]

        self.assertEqual(tickets["opened"], 3)
        self.assertEqual(tickets["resolved"], 1)
        self.assertEqual(tickets["open"], 2)
        self.assertEqual(tickets["sla_breached"], 2)
        self.assertEqual(
            [t["name"] for t in tickets["sla_breached_open"]], [str(late.name)]
        )
        self.assertEqual(tickets["urgent_high_open"], 1)


class TestSummaryText(WorkSummaryCase):
    def test_plain_summary_when_ai_is_unavailable(self):
        make_task(
            self.project, "Fix <b>GST</b> report & print", add_days(nowdate(), -1)
        )
        stats = work_summary.collect_customer_stats(CUSTOMER, self.start, self.end)

        with patch.object(
            work_summary, "call_haiku", side_effect=AI_UNAVAILABLE
        ), patch.object(frappe, "log_error") as log_error:
            text, used_ai = work_summary.write_summary(CUSTOMER, stats)

        self.assertFalse(used_ai)
        self.assertTrue(log_error.called)
        self.assertIn("Overdue since", text)
        self.assertIn("Fix &lt;b&gt;GST&lt;/b&gt; report &amp; print", text)
        self.assertNotIn("<b>GST", text)
        self.assertIn("<ul>", text)

    def test_ai_summary_is_used_and_escaped(self):
        make_task(self.project, "Go-live checklist", add_days(nowdate(), 2), is_key=1)
        stats = work_summary.collect_customer_stats(CUSTOMER, self.start, self.end)
        answer = {
            "response": {
                "overview": "One key task due <script>alert(1)</script>this week.",
                "highlights": ["Margin < 5% & falling"],
                "risks": [],
                "next_week": ["Key task: Go-live checklist", 42],
            }
        }

        with patch.object(work_summary, "call_haiku", return_value=answer) as ai:
            text, used_ai = work_summary.write_summary(CUSTOMER, stats)

        self.assertTrue(used_ai)
        self.assertIn('"due_next_7_days": 1', ai.call_args.args[1])
        self.assertNotIn("<script>", text)
        self.assertIn("Margin &lt; 5% &amp; falling", text)
        self.assertIn("<li>Key task: Go-live checklist</li>", text)
        self.assertNotIn("42", text)
        self.assertIn("No risks flagged.", text)

    def test_unusable_ai_answer_falls_back(self):
        stats = work_summary.collect_customer_stats(CUSTOMER, self.start, self.end)
        answer = {"response": {"raw_response": "Sorry", "parse_error": True}}
        with patch.object(work_summary, "call_haiku", return_value=answer):
            text, used_ai = work_summary.write_summary(CUSTOMER, stats)
        self.assertFalse(used_ai)
        self.assertIn("tickets opened", text)


class TestWeeklyRun(WorkSummaryCase):
    def test_managers_lead_and_agent_managers_are_notified(self):
        retired = ("retired.summary@work-summary.example", "Suresh Pillai")
        make_tasky_user(*retired, roles=("Agent Manager",))
        frappe.db.set_value("User", retired[0], "enabled", 0)

        with patch.object(
            work_summary, "call_haiku", side_effect=AI_UNAVAILABLE
        ), patch.object(frappe, "log_error"), patch("frappe.sendmail"):
            summary = work_summary.send_customer_summary(
                CUSTOMER, str(self.start), str(self.end)
            )

        self.assertEqual(summary.customer, CUSTOMER)
        self.assertFalse(summary.generated_by_ai)
        subject = f"Weekly summary: {CUSTOMER}"
        for user in (PM, LEAD, MANAGER):
            self.assertEqual(get_reminder_messages(user[0], summary.name), [subject])
        self.assertEqual(get_reminder_messages(DEV[0], summary.name), [])
        self.assertEqual(get_reminder_messages(retired[0], summary.name), [])

    def test_only_active_customers_are_queued_and_failures_are_isolated(self):
        make_ticket(subject="Stock ledger slow", customer=OTHER_CUSTOMER)

        def enqueue(method, **kwargs):
            if kwargs["customer"] == CUSTOMER:
                raise frappe.ValidationError("queue unavailable")

        with patch.object(
            frappe, "enqueue", side_effect=enqueue
        ) as queued, patch.object(frappe, "log_error") as log_error:
            work_summary.send_weekly_summaries()

        customers = [c.kwargs["customer"] for c in queued.call_args_list]
        self.assertIn(CUSTOMER, customers)
        self.assertIn(OTHER_CUSTOMER, customers)
        self.assertNotIn(IDLE_CUSTOMER, customers)
        self.assertTrue(log_error.called)
        call = next(
            c for c in queued.call_args_list if c.kwargs["customer"] == CUSTOMER
        )
        self.assertEqual(call.kwargs["end"], str(add_days(nowdate(), -1)))
        self.assertEqual(call.kwargs["start"], str(add_days(nowdate(), -7)))


class TestSummaryAccess(WorkSummaryCase):
    def test_only_the_customers_managers_can_read(self):
        summary = make_work_summary(CUSTOMER)
        make_work_summary(OTHER_CUSTOMER)

        for user in (PM, LEAD, MANAGER):
            names = run_as_user(user[0], lambda: api.get_summaries(customer=CUSTOMER))
            self.assertIn(summary.name, [s.name for s in names])
            self.assertEqual(
                run_as_user(user[0], lambda: api.get_summary(summary.name))["customer"],
                CUSTOMER,
            )

        pm_customers = {s.customer for s in run_as_user(PM[0], api.get_summaries)}
        self.assertNotIn(OTHER_CUSTOMER, pm_customers)
        self.assertEqual(run_as_user(OUTSIDER[0], api.get_summaries), [])
        self.assertFalse(
            frappe.has_permission(
                "HD Work Summary", "read", summary.name, user=OUTSIDER[0]
            )
        )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_summary(summary.name))

    def test_generate_now_is_for_agent_managers_and_project_managers(self):
        for user in (OUTSIDER, LEAD):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(user[0], lambda: api.generate_summary(CUSTOMER))

        with patch.object(
            work_summary, "call_haiku", side_effect=AI_UNAVAILABLE
        ), patch.object(frappe, "log_error"):
            for user in (PM, MANAGER):
                result = run_as_user(user[0], lambda: api.generate_summary(CUSTOMER))
                self.assertEqual(result["customer"], CUSTOMER)
                self.assertEqual(str(result["period_end"]), nowdate())
                self.assertIn("tasks", result["stats"])
                self.assertIn("<p>", result["summary"])
