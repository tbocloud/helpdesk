from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk import work_reminders
from helpdesk.api import work
from helpdesk.patches.v16_0_2.add_waiting_on_task_status import (
    execute as add_waiting_status,
)
from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    create_customer,
    make_assignment,
    make_project,
    make_tasky_user,
    make_ticket,
)

CUSTOMER = "Al Noor Trading LLC"
OTHER_CUSTOMER = "Gulf Star Logistics"
PM = ("pm.control@work-control.example", "Leena Varghese")
LEAD = ("lead.control@work-control.example", "Nikhil Das")
DEV = ("dev.control@work-control.example", "Fathima Rizwana")
SUPPORT = ("support.control@work-control.example", "Joel Mathew")


class WorkControlCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (LEAD, DEV, SUPPORT):
            make_tasky_user(*user)
        add_waiting_status()

        self.project = make_project(
            f"{CUSTOMER} - Rollout",
            members=[(LEAD[0], "Developer"), (DEV[0], "Developer")],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "customer", CUSTOMER)
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])

    def as_user(self, user, fn):
        frappe.set_user(user[0])
        try:
            return fn()
        finally:
            frappe.set_user("Administrator")

    def make_task(self, subject, due, assignee=DEV, is_key=0):
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": subject,
                "project": self.project,
                "status": "Open",
                "exp_end_date": due,
                "is_key": is_key,
            }
        ).insert(ignore_permissions=True)
        if assignee:
            make_assignment("Task", task.name, assignee[0])
        return task.name

    def notified(self, user, name):
        return frappe.get_all(
            "Notification Log",
            # assigning also notifies, so only count reminder alerts
            filters={"for_user": user[0], "document_name": str(name), "type": "Alert"},
            pluck="subject",
        )


class TestMyWorkAndOverview(WorkControlCase):
    def test_my_work_combines_tasks_and_tickets_overdue_first(self):
        late = self.make_task("Fix stock valuation", add_days(nowdate(), -2))
        later = self.make_task("Train users", add_days(nowdate(), 10))
        ticket = make_ticket(
            subject="Invoice print is blank", priority="Urgent", customer=CUSTOMER
        )
        make_assignment("HD Ticket", ticket.name, DEV[0])

        result = self.as_user(DEV, work.get_my_work)
        names = [i["name"] for i in result["items"]]
        self.assertEqual(names[0], late)
        self.assertIn(later, names)
        self.assertIn(str(ticket.name), names)
        ticket_item = next(i for i in result["items"] if i["kind"] == "ticket")
        self.assertTrue(ticket_item["is_key"])
        self.assertGreaterEqual(result["counts"]["overdue"], 1)

    def test_overview_buckets_for_the_project_manager(self):
        overdue = self.make_task("Close GL", add_days(nowdate(), -1))
        soon = self.make_task("UAT sign-off", add_days(nowdate(), 1), is_key=1)
        self.make_task("Phase 2 scoping", add_days(nowdate(), 30))

        result = self.as_user(PM, lambda: work.get_overview(project=self.project))
        names = lambda bucket: {i["name"] for i in result["buckets"][bucket]}
        self.assertIn(overdue, names("overdue"))
        self.assertIn(soon, names("due_soon"))
        self.assertIn(soon, names("key"))
        self.assertNotIn(overdue, names("due_soon"))


class TestTicketToTask(WorkControlCase):
    def make_ticket(self, customer=CUSTOMER):
        ticket = make_ticket(
            subject="Add GST column to sales register", customer=customer
        )
        make_assignment("HD Ticket", ticket.name, SUPPORT[0])
        return ticket

    def test_support_agent_raises_task_and_ticket_waits(self):
        ticket = self.make_ticket()
        result = self.as_user(
            SUPPORT,
            lambda: work.create_task_from_ticket(
                ticket=ticket.name,
                project=self.project,
                assigned_to=DEV[0],
                is_key=True,
            ),
        )
        task = frappe.get_doc("Task", result["task"]["name"])
        self.assertEqual(task.hd_ticket, str(ticket.name))
        self.assertTrue(task.is_key)
        self.assertEqual(result["task"]["assignees"], [DEV[0]])
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "status"), "Waiting on Task"
        )

    def test_other_customers_projects_are_off_limits(self):
        other = make_project(f"{OTHER_CUSTOMER} - Support", owner=PM[0]).name
        frappe.db.set_value("Project", other, "customer", OTHER_CUSTOMER)
        ticket = self.make_ticket()
        with self.assertRaises(frappe.PermissionError):
            self.as_user(
                SUPPORT,
                lambda: work.create_task_from_ticket(ticket=ticket.name, project=other),
            )

    def test_assignee_must_be_a_project_member(self):
        ticket = self.make_ticket()
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                SUPPORT,
                lambda: work.create_task_from_ticket(
                    ticket=ticket.name, project=self.project, assigned_to=SUPPORT[0]
                ),
            )

    def test_completing_the_task_reopens_the_ticket(self):
        ticket = self.make_ticket()
        task = self.as_user(
            SUPPORT,
            lambda: work.create_task_from_ticket(
                ticket=ticket.name, project=self.project, assigned_to=DEV[0]
            ),
        )["task"]["name"]

        self.as_user(DEV, lambda: tasky.move_task(task=task, new_status="Completed"))

        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "status"), "Open"
        )
        comments = frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": ticket.name},
            pluck="content",
        )
        self.assertTrue(any("was completed" in c for c in comments))

    def test_context_lists_customer_projects_and_linked_tasks(self):
        ticket = self.make_ticket()
        self.as_user(
            SUPPORT,
            lambda: work.create_task_from_ticket(
                ticket=ticket.name, project=self.project
            ),
        )
        context = self.as_user(
            SUPPORT, lambda: work.get_ticket_task_context(ticket.name)
        )
        project = next(p for p in context["projects"] if p["name"] == self.project)
        self.assertEqual({m["user"] for m in project["members"]}, {LEAD[0], DEV[0]})
        self.assertEqual(len(context["linked_tasks"]), 1)


class TestReminders(WorkControlCase):
    def test_task_stages_reach_the_right_people_once(self):
        soon = self.make_task("Data migration", add_days(nowdate(), 1))
        late = self.make_task("Opening balances", add_days(nowdate(), -1))
        very_late = self.make_task(
            "Go-live checklist", add_days(nowdate(), -5), is_key=1
        )

        work_reminders.send_task_reminders()
        work_reminders.send_task_reminders()  # a second run must not repeat anything

        self.assertEqual(len(self.notified(DEV, soon)), 1)
        self.assertEqual(len(self.notified(LEAD, late)), 1)
        self.assertEqual(self.notified(LEAD, soon), [])
        escalations = [s for s in self.notified(PM, very_late) if "Escalated" in s]
        self.assertEqual(len(escalations), 1)
        self.assertIn("Key task", escalations[0])

    def test_breached_ticket_goes_to_agent_managers(self):
        manager = ("manager.control@work-control.example", "Divya Menon")
        make_tasky_user(*manager, roles=("Agent Manager",))
        ticket = make_ticket(subject="Payroll run failed", customer=CUSTOMER)
        make_assignment("HD Ticket", ticket.name, SUPPORT[0])
        frappe.db.set_value(
            "HD Ticket",
            ticket.name,
            "resolution_by",
            add_to_date(now_datetime(), hours=-2),
        )

        work_reminders.send_ticket_reminders()

        self.assertTrue(
            any("SLA breached" in s for s in self.notified(SUPPORT, ticket.name))
        )
        self.assertTrue(
            any("SLA breached" in s for s in self.notified(manager, ticket.name))
        )


class TestTaskHold(WorkControlCase):
    def hold(self, task, reason="Laptop / system issue", days_ago=0):
        self.as_user(
            DEV,
            lambda: tasky.hold_task(
                task=task, reason=reason, note="Laptop sent for repair"
            ),
        )
        if days_ago:
            frappe.db.set_value(
                "Task", task, "hold_since", add_days(nowdate(), -days_ago)
            )

    def test_hold_needs_a_reason(self):
        task = self.make_task("Build sales dashboard", add_days(nowdate(), 5))
        with self.assertRaises(frappe.ValidationError):
            self.as_user(DEV, lambda: tasky.hold_task(task=task, reason=""))

    def test_assignee_holds_and_lead_hears_about_it(self):
        task = self.make_task("Configure payroll", add_days(nowdate(), -1))
        frappe.db.set_value("Task", task, "status", "Working")
        self.hold(task)

        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.status, "On Hold")
        self.assertEqual(str(doc.hold_since), nowdate())
        self.assertEqual(doc.hold_previous_status, "Working")
        self.assertTrue(any("On hold since" in s for s in self.notified(LEAD, task)))

        item = next(
            i for i in self.as_user(DEV, work.get_my_work)["items"] if i["name"] == task
        )
        self.assertFalse(item["is_overdue"])
        self.assertEqual(item["hold_reason"], "Laptop / system issue")

    def test_resume_moves_the_due_date_by_the_days_on_hold(self):
        due = add_days(nowdate(), 1)
        task = self.make_task("Import item master", due)
        self.hold(task, days_ago=2)

        self.as_user(DEV, lambda: tasky.resume_task(task=task))

        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.status, "Open")
        self.assertEqual(str(doc.exp_end_date), str(add_days(due, 2)))
        self.assertEqual(doc.hold_days_total, 2)
        self.assertIsNone(doc.hold_since)
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Task", "reference_name": task},
            pluck="content",
        )
        self.assertTrue(any("Due date moved" in c for c in comments))

    def test_resume_can_keep_the_due_date(self):
        due = add_days(nowdate(), 1)
        task = self.make_task("Set up email alerts", due)
        self.hold(task, days_ago=2)

        self.as_user(DEV, lambda: tasky.resume_task(task=task, extend_due_date=False))

        self.assertEqual(
            str(frappe.db.get_value("Task", task, "exp_end_date")), str(due)
        )

    def test_board_moves_cannot_skip_the_reason_but_can_resume(self):
        task = self.make_task("Print formats", add_days(nowdate(), 3))
        with self.assertRaises(frappe.ValidationError):
            self.as_user(DEV, lambda: tasky.move_task(task=task, new_status="On Hold"))

        self.hold(task, days_ago=1)
        self.as_user(DEV, lambda: tasky.move_task(task=task, new_status="Completed"))
        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.status, "Completed")
        self.assertEqual(doc.hold_days_total, 1)

    def test_held_tasks_skip_due_reminders_and_escalate_when_stuck(self):
        task = self.make_task("Bank reconciliation", add_days(nowdate(), -4))
        self.hold(task, days_ago=4)

        work_reminders.send_task_reminders()
        work_reminders.send_hold_reminders()
        work_reminders.send_hold_reminders()

        self.assertFalse(any("Overdue" in s for s in self.notified(DEV, task)))
        stuck = [s for s in self.notified(PM, task) if "On hold for over" in s]
        self.assertEqual(len(stuck), 1)

    def test_overview_lists_held_work(self):
        task = self.make_task("Tally migration", add_days(nowdate(), -1))
        self.hold(task)
        result = self.as_user(PM, lambda: work.get_overview(project=self.project))
        self.assertIn(task, {i["name"] for i in result["buckets"]["on_hold"]})
        self.assertNotIn(task, {i["name"] for i in result["buckets"]["overdue"]})
