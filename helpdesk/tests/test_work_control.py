from unittest.mock import patch

import frappe
from frappe.desk.doctype.notification_settings.notification_settings import (
    create_notification_settings,
)
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk import work_reminders
from helpdesk.api import work
from helpdesk.helpdesk.doctype.hd_notification.utils import clear as clear_notifications
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
            "HD Notification",
            filters={
                "user_to": user[0],
                "notification_type": "Reminder",
                "reference_name": str(name),
            },
            pluck="message",
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


class TestReminderDelivery(WorkControlCase):
    def test_reminder_opens_the_project_and_is_emailed(self):
        task = self.make_task("Share UAT build", add_days(nowdate(), 1))
        with patch("frappe.sendmail") as sendmail:
            work_reminders.send_task_reminders()

        note = frappe.get_last_doc(
            "HD Notification", filters={"user_to": DEV[0], "reference_name": task}
        )
        self.assertEqual(note.link, f"/projects/{self.project}")
        self.assertEqual(sendmail.call_args.kwargs["recipients"], DEV[0])
        self.assertTrue(
            sendmail.call_args.kwargs["args"]["doc_link"].endswith(note.link)
        )

    def test_no_email_when_the_person_turned_email_off(self):
        self.make_task("Share UAT build", add_days(nowdate(), 1))
        if not frappe.db.exists("Notification Settings", DEV[0]):
            create_notification_settings(DEV[0])
        frappe.db.set_value(
            "Notification Settings", DEV[0], "enable_email_notifications", 0
        )
        frappe.clear_document_cache("Notification Settings", DEV[0])
        with patch("frappe.sendmail") as sendmail:
            work_reminders.send_task_reminders()
        self.assertFalse(sendmail.called)

    def test_clearing_one_reminder_leaves_the_rest_unread(self):
        first = self.make_task("Share UAT build", add_days(nowdate(), 1))
        second = self.make_task("Collect sign-off", add_days(nowdate(), 1))
        with patch("frappe.sendmail"):
            work_reminders.send_task_reminders()
        one = frappe.get_last_doc(
            "HD Notification", filters={"reference_name": first, "user_to": DEV[0]}
        )

        self.as_user(DEV, lambda: clear_notifications(notification=one.name))

        self.assertTrue(frappe.db.get_value("HD Notification", one.name, "read"))
        other = frappe.get_last_doc(
            "HD Notification", filters={"reference_name": second, "user_to": DEV[0]}
        )
        self.assertFalse(other.read)


class TestDependenciesAndMilestones(WorkControlCase):
    def test_task_waits_for_its_dependency_then_is_unblocked(self):
        first = self.make_task("Install server", add_days(nowdate(), 2), assignee=LEAD)
        second = self.make_task("Deploy app", add_days(nowdate(), 4))
        self.as_user(
            LEAD, lambda: tasky.update_task_plan(task=second, depends_on_task=first)
        )

        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                DEV, lambda: tasky.move_task(task=second, new_status="Working")
            )

        self.as_user(LEAD, lambda: tasky.move_task(task=first, new_status="Completed"))
        self.assertTrue(any("Unblocked" in s for s in self.notified(DEV, second)))
        self.as_user(DEV, lambda: tasky.move_task(task=second, new_status="Working"))
        self.assertEqual(frappe.db.get_value("Task", second, "status"), "Working")

    def test_dependency_loops_and_other_projects_are_refused(self):
        first = self.make_task("Design", add_days(nowdate(), 2))
        second = self.make_task("Build", add_days(nowdate(), 4))
        self.as_user(
            LEAD, lambda: tasky.update_task_plan(task=second, depends_on_task=first)
        )
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                LEAD, lambda: tasky.update_task_plan(task=first, depends_on_task=second)
            )

        other = make_project(f"{OTHER_CUSTOMER} - Support", owner=PM[0]).name
        stranger = frappe.get_doc(
            {"doctype": "Task", "subject": "Elsewhere", "project": other}
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                LEAD,
                lambda: tasky.update_task_plan(
                    task=first, depends_on_task=stranger.name
                ),
            )

    def test_milestones_show_on_the_project_dashboard(self):
        go_live = self.make_task("Go-live", add_days(nowdate(), 20))
        self.as_user(
            LEAD, lambda: tasky.update_task_plan(task=go_live, is_milestone=True)
        )
        dashboard = self.as_user(
            PM, lambda: tasky.get_project_dashboard(project=self.project)
        )
        self.assertEqual([m["name"] for m in dashboard["milestones"]], [go_live])


class TestReviewBeforeDone(WorkControlCase):
    def setUp(self):
        super().setUp()
        frappe.db.set_value("Project", self.project, "review_before_done", 1)

    def test_done_goes_to_the_lead_who_approves(self):
        task = self.make_task("Sales invoice print format", add_days(nowdate(), 3))
        result = self.as_user(
            DEV, lambda: tasky.move_task(task=task, new_status="Completed")
        )

        self.assertEqual(result["status"], "Pending Review")
        self.assertTrue(any("Ready for review" in s for s in self.notified(LEAD, task)))
        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV, lambda: tasky.approve_task(task=task))

        self.as_user(LEAD, lambda: tasky.approve_task(task=task))
        self.assertEqual(frappe.db.get_value("Task", task, "status"), "Completed")

    def test_lead_sends_it_back_with_a_note(self):
        task = self.make_task("Purchase workflow", add_days(nowdate(), 3))
        self.as_user(
            DEV, lambda: tasky.update_task_status(task=task, status="Completed")
        )

        self.as_user(
            LEAD, lambda: tasky.send_back_task(task=task, note="Approval limit missing")
        )

        self.assertEqual(frappe.db.get_value("Task", task, "status"), "Open")
        self.assertTrue(any("Sent back" in s for s in self.notified(DEV, task)))

    def test_ticket_waits_until_the_lead_approves(self):
        ticket = make_ticket(subject="Add approval step", customer=CUSTOMER)
        make_assignment("HD Ticket", ticket.name, SUPPORT[0])
        task = self.as_user(
            SUPPORT,
            lambda: work.create_task_from_ticket(
                ticket=ticket.name, project=self.project, assigned_to=DEV[0]
            ),
        )["task"]["name"]

        self.as_user(DEV, lambda: tasky.move_task(task=task, new_status="Completed"))
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "status"), "Waiting on Task"
        )

        self.as_user(LEAD, lambda: tasky.approve_task(task=task))
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "status"), "Open"
        )


class TestRescheduling(WorkControlCase):
    def test_moving_later_needs_a_reason_and_is_counted(self):
        due = add_days(nowdate(), 3)
        task = self.make_task("Stock reconciliation", due, is_key=1)
        later = add_days(due, 5)
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                LEAD, lambda: tasky.update_task_plan(task=task, due_date=later)
            )

        self.as_user(
            LEAD,
            lambda: tasky.update_task_plan(
                task=task, due_date=later, reason="Customer data late"
            ),
        )

        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.slip_count, 1)
        self.assertTrue(any("Due date moved" in s for s in self.notified(DEV, task)))
        self.assertTrue(
            any("Key task rescheduled" in s for s in self.notified(PM, task))
        )
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Task", "reference_name": task},
            pluck="content",
        )
        self.assertTrue(any("Customer data late" in c for c in comments))

    def test_only_leads_and_managers_reschedule(self):
        task = self.make_task("Opening stock", add_days(nowdate(), 3))
        with self.assertRaises(frappe.PermissionError):
            self.as_user(
                DEV,
                lambda: tasky.update_task_plan(
                    task=task, due_date=add_days(nowdate(), 9), reason="Busy"
                ),
            )

    def test_hold_extension_is_not_a_slip(self):
        task = self.make_task("Payroll setup", add_days(nowdate(), 3))
        self.as_user(DEV, lambda: tasky.hold_task(task=task, reason="Leave"))
        frappe.db.set_value("Task", task, "hold_since", add_days(nowdate(), -2))
        self.as_user(DEV, lambda: tasky.resume_task(task=task))
        self.assertEqual(frappe.db.get_value("Task", task, "slip_count"), 0)


class TestAtRisk(WorkControlCase):
    def test_unstarted_and_often_moved_work_is_at_risk(self):
        unstarted = self.make_task("Train accounts team", add_days(nowdate(), 1))
        moved = self.make_task("Migrate balances", add_days(nowdate(), 10))
        frappe.db.set_value("Task", moved, {"slip_count": 2, "status": "Working"})
        fine = self.make_task("Write user guide", add_days(nowdate(), 10))

        result = self.as_user(PM, lambda: work.get_overview(project=self.project))
        risky = {i["name"]: i["risks"] for i in result["buckets"]["at_risk"]}
        self.assertIn("Not started", risky[unstarted][0])
        self.assertIn("Rescheduled 2 times", risky[moved])
        self.assertNotIn(fine, risky)

    def test_urgent_unassigned_ticket_is_at_risk(self):
        ticket = make_ticket(
            subject="Server down", priority="Urgent", customer=CUSTOMER
        )
        frappe.db.set_value("HD Ticket", ticket.name, "_assign", "[]")
        result = self.as_user(PM, lambda: work.get_overview(customer=CUSTOMER))
        risky = {i["name"]: i["risks"] for i in result["buckets"]["at_risk"]}
        self.assertTrue(any("unassigned" in r for r in risky.get(str(ticket.name), [])))


class TestTeamWorkload(WorkControlCase):
    def test_lead_sees_who_is_doing_what(self):
        working = self.make_task("Payroll setup", add_days(nowdate(), 2))
        frappe.db.set_value("Task", working, "status", "Working")
        self.make_task("Leave policy", add_days(nowdate(), -1))
        done = self.make_task("Chart of accounts", add_days(nowdate(), -3))
        frappe.db.set_value(
            "Task", done, {"status": "Completed", "completed_on": nowdate()}
        )

        result = self.as_user(
            LEAD, lambda: work.get_team_workload(project=self.project)
        )
        people = {p["user"]: p for p in result["people"]}

        dev = people[DEV[0]]
        self.assertEqual([w["title"] for w in dev["working_on"]], ["Payroll setup"])
        self.assertEqual(
            (dev["open"], dev["working"], dev["overdue"], dev["done_this_week"]),
            (2, 1, 1, 1),
        )
        self.assertEqual(dev["next_due"]["title"], "Leave policy")
        self.assertEqual(people[LEAD[0]]["open"], 0)
        self.assertEqual(result["totals"]["working_now"], 1)
        self.assertGreaterEqual(result["totals"]["free"], 1)
        self.assertNotIn(SUPPORT[0], people)

    def test_developers_cannot_see_the_team(self):
        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV, work.get_team_workload)
