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
    hold_commits,
    make_assignment,
    make_department,
    make_project,
    make_pull_request,
    make_task,
    make_tasky_user,
    make_ticket,
    make_timesheet,
    make_work_summary,
)

CUSTOMER = "Al Noor Trading LLC"
OTHER_CUSTOMER = "Gulf Star Logistics"
PM = ("pm.control@work-control.example", "Leena Varghese")
LEAD = ("lead.control@work-control.example", "Nikhil Das")
DEV = ("dev.control@work-control.example", "Fathima Rizwana")
SUPPORT = ("support.control@work-control.example", "Joel Mathew")
TEAMMATE = ("teammate.control@work-control.example", "Anjali Menon")


class WorkControlCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")

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

    def test_tasks_waiting_for_review_say_who_may_approve(self):
        task = self.make_task("Sign off payroll", add_days(nowdate(), 2), LEAD)
        frappe.db.set_value("Task", task, "status", "Pending Review")

        def review_item(user):
            items = self.as_user(user, work.get_my_work)["items"]
            return next(i for i in items if i["name"] == task)

        # the project lead may sign it off; a developer on it may not
        self.assertTrue(review_item(LEAD)["can_approve"])
        make_assignment("Task", task, DEV[0])
        self.assertFalse(review_item(DEV)["can_approve"])
        open_task = self.make_task("Train users", add_days(nowdate(), 5))
        items = self.as_user(DEV, work.get_my_work)["items"]
        self.assertNotIn(
            "can_approve", next(i for i in items if i["name"] == open_task)
        )

    def test_a_ticket_becomes_a_task_in_any_project_you_are_on(self):
        internal = make_project(
            "Internal tooling", members=[(SUPPORT[0], "Developer")]
        ).name
        ticket = make_ticket(subject="Need a report", customer=OTHER_CUSTOMER)

        context = self.as_user(
            SUPPORT, lambda: work.get_ticket_task_context(ticket.name)
        )
        self.assertIn(internal, [p["name"] for p in context["projects"]])
        result = self.as_user(
            SUPPORT,
            lambda: work.create_task_from_ticket(
                ticket.name, internal, task_name="Build the report"
            ),
        )
        self.assertEqual(
            frappe.db.get_value("Task", result["task"]["name"], "hd_ticket"),
            str(ticket.name),
        )

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

    def test_overview_kpi_row(self):
        mine = self.make_task("Close GL", add_days(nowdate(), 5))
        nobody = self.make_task("Archive old data", add_days(nowdate(), 5), None)
        make_project("Internal tooling", owner=PM[0])

        result = self.as_user(PM, lambda: work.get_overview(project=self.project))
        names = lambda bucket: {i["name"] for i in result["buckets"][bucket]}
        self.assertEqual(names("all"), {mine, nobody})
        self.assertEqual(names("unassigned"), {nobody})
        self.assertEqual(result["counts"]["all"], 2)
        self.assertEqual(result["people_busy"], 1)
        self.assertEqual(result["open_projects"], 1)

        # for one person: only the projects they have open tasks in
        result = self.as_user(PM, lambda: work.get_overview(assignee=DEV[0]))
        self.assertEqual(result["open_projects"], 1)
        self.assertEqual(result["people_busy"], 1)

    def test_overview_donut_counts_each_item_once(self):
        self.make_task("Close GL", add_days(nowdate(), -1), is_key=1)
        soon = self.make_task("UAT sign-off", add_days(nowdate(), 1), is_key=1)
        frappe.db.set_value("Task", soon, "status", "Working")
        self.make_task("Phase 2 scoping", add_days(nowdate(), 30), is_key=1)
        self.make_task("Write user guide", add_days(nowdate(), 30))

        result = self.as_user(PM, lambda: work.get_overview(project=self.project))
        self.assertEqual(
            result["active"],
            {
                "total": 4,
                "overdue": 1,
                "at_risk": 0,
                "due_soon": 1,
                "key": 1,
                "other": 1,
            },
        )
        # the tiles still count every key item
        self.assertEqual(result["counts"]["key"], 3)

    def test_tasks_by_project_follow_the_filters(self):
        other = make_project(f"{OTHER_CUSTOMER} - Support", owner=PM[0]).name
        frappe.db.set_value("Project", other, "customer", OTHER_CUSTOMER)
        self.make_task("Close GL", add_days(nowdate(), 2))
        self.make_task("Train users", add_days(nowdate(), 5), LEAD)
        done = self.make_task("Chart of accounts", add_days(nowdate(), -3))
        frappe.db.set_value("Task", done, "status", "Completed")
        elsewhere = make_task(other, "Route planning", add_days(nowdate(), 4)).name
        make_assignment("Task", elsewhere, DEV[0])

        def counts(**filters):
            result = self.as_user(PM, lambda: work.get_overview(**filters))
            return [
                (p["project"], p["count"])
                for p in result["projects"]
                if p["project"] in (self.project, other)
            ]

        self.assertEqual(counts(), [(self.project, 2), (other, 1)])
        self.assertEqual(counts(customer=CUSTOMER), [(self.project, 2)])
        self.assertEqual(counts(project=other), [(other, 1)])

        make_department("Work Control Creative")
        frappe.db.set_value(
            "Project", other, "custom_department", "Work Control Creative"
        )
        self.assertEqual(counts(department="Work Control Creative"), [(other, 1)])
        self.assertEqual(
            counts(department="Work Control Creative", customer=CUSTOMER), []
        )
        self.assertEqual(
            sorted(counts(assignee=DEV[0])), sorted([(self.project, 1), (other, 1)])
        )
        result = self.as_user(PM, lambda: work.get_overview(project=self.project))
        self.assertEqual(result["projects"][0]["project_name"], f"{CUSTOMER} - Rollout")

    def test_attention_lists_overdue_work_before_risky_work(self):
        risky = self.make_task("Train accounts team", add_days(nowdate(), 1))
        overdue = self.make_task("Close GL", add_days(nowdate(), -3))
        on_track = self.make_task("Phase 2 scoping", add_days(nowdate(), 30))
        # overdue and at risk at once, but listed once
        ticket = make_ticket(
            subject="Server down", priority="Urgent", customer=CUSTOMER
        )
        frappe.db.set_value(
            "HD Ticket",
            ticket.name,
            {"_assign": "[]", "resolution_by": add_to_date(now_datetime(), hours=-2)},
        )
        make_work_summary(
            CUSTOMER,
            period_start=add_days(nowdate(), -13),
            period_end=add_days(nowdate(), -7),
        )
        latest = make_work_summary(CUSTOMER).name

        result = self.as_user(PM, lambda: work.get_overview(customer=CUSTOMER))
        names = [i["name"] for i in result["attention"]]
        self.assertEqual(names.count(str(ticket.name)), 1)
        self.assertLess(names.index(overdue), names.index(risky))
        self.assertLess(names.index(str(ticket.name)), names.index(risky))
        self.assertNotIn(on_track, names)
        task = next(i for i in result["attention"] if i["name"] == overdue)
        self.assertEqual(task["customer"], CUSTOMER)
        self.assertEqual(task["summary"]["name"], latest)

    def test_attention_hides_summaries_the_user_cannot_read(self):
        overdue = self.make_task("Close GL", add_days(nowdate(), -3))
        make_work_summary(CUSTOMER)

        result = self.as_user(DEV, lambda: work.get_overview(project=self.project))
        item = next(i for i in result["attention"] if i["name"] == overdue)
        self.assertIsNone(item["summary"])


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

        self.as_user(
            DEV, lambda: tasky.complete_task(task=task, hours_worked=1, notes="Done")
        )

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
        self.as_user(DEV, lambda: tasky.move_task(task=task, new_status="Working"))
        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.status, "Working")
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

        self.as_user(
            LEAD, lambda: tasky.complete_task(task=first, hours_worked=1, notes="Done")
        )
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
            DEV,
            lambda: tasky.complete_task(task=task, hours_worked=1, notes="Done"),
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
            DEV,
            lambda: tasky.complete_task(task=task, hours_worked=1, notes="Done"),
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

        self.as_user(
            DEV,
            lambda: tasky.complete_task(task=task, hours_worked=1, notes="Done"),
        )
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

    def test_a_lead_cannot_filter_to_someone_elses_project(self):
        other = make_project(
            f"{OTHER_CUSTOMER} - Support", members=[(SUPPORT[0], "Developer")]
        ).name
        result = self.as_user(LEAD, lambda: work.get_team_workload(project=other))
        self.assertEqual(result["people"], [])

    def test_developers_cannot_see_the_team(self):
        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV, work.get_team_workload)


class TestViewTeamMemberWork(WorkControlCase):
    def test_lead_opens_a_team_members_work(self):
        task = self.make_task("Bank reconciliation", add_days(nowdate(), 2))
        result = self.as_user(LEAD, lambda: work.get_my_work(user=DEV[0]))
        self.assertIn(task, [i["name"] for i in result["items"]])

    def test_plan_is_offered_to_the_projects_lead_not_the_assignee(self):
        task = self.make_task("Opening stock import", add_days(nowdate(), 4))

        def item(viewer, user=None):
            items = self.as_user(viewer, lambda: work.get_my_work(user=user))["items"]
            return next(i for i in items if i["name"] == task)

        self.assertFalse(item(DEV)["can_plan"])
        self.assertTrue(item(LEAD, user=DEV[0])["can_plan"])
        # the overview doesn't ask, so it doesn't pay for the lookup
        overview = self.as_user(PM, lambda: work.get_overview(project=self.project))
        self.assertTrue(overview["buckets"]["all"])
        self.assertNotIn("can_plan", overview["buckets"]["all"][0])

    def test_developers_only_see_their_own(self):
        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV, lambda: work.get_my_work(user=LEAD[0]))

    def test_leads_cannot_open_people_outside_their_projects(self):
        with self.assertRaises(frappe.PermissionError):
            self.as_user(LEAD, lambda: work.get_my_work(user=SUPPORT[0]))


class TestProjectPortfolio(WorkControlCase):
    def setUp(self):
        super().setUp()
        self.working = self.make_task("Payroll setup", add_days(nowdate(), 2))
        frappe.db.set_value("Task", self.working, "status", "Working")
        self.make_task("Leave policy", add_days(nowdate(), -1))
        done = self.make_task("Chart of accounts", add_days(nowdate(), -3))
        frappe.db.set_value("Task", done, "status", "Completed")
        cancelled = self.make_task("Old import", add_days(nowdate(), -5))
        frappe.db.set_value("Task", cancelled, "status", "Cancelled")
        go_live = self.make_task("Go-live", add_days(nowdate(), 5), assignee=LEAD)
        frappe.db.set_value("Task", go_live, "is_milestone", 1)

        # the PM runs a second project; the lead has no say in it
        self.other = make_project(
            f"{OTHER_CUSTOMER} - Support", members=[(DEV[0], "Developer")], owner=PM[0]
        ).name
        task = make_task(self.other, "Fix POS sync", add_days(nowdate(), 4))
        make_assignment("Task", task.name, DEV[0])

    def portfolio(self, user, **kwargs):
        return self.as_user(user, lambda: work.get_project_portfolio(**kwargs))

    def test_lead_sees_their_project_with_its_team(self):
        result = self.portfolio(LEAD)
        cards = {c["name"]: c for c in result["projects"]}
        self.assertNotIn(self.other, cards)

        card = cards[self.project]
        self.assertEqual(card["lead"], LEAD[0])
        self.assertEqual(card["lead_name"], LEAD[1])
        self.assertEqual(card["customer"], CUSTOMER)
        # cancelled work isn't counted; completed work isn't open
        self.assertEqual(
            {
                k: card["counts"][k]
                for k in ("total", "done", "open", "working", "overdue")
            },
            {"total": 4, "done": 1, "open": 3, "working": 1, "overdue": 1},
        )
        self.assertEqual(card["progress"], 25)
        self.assertEqual(card["next_milestone"]["subject"], "Go-live")

        members = card["members"]
        # whoever is working right now comes first
        self.assertEqual(members[0]["user"], DEV[0])
        self.assertTrue(members[0]["working_now"])
        self.assertEqual(members[0]["working_on"]["subject"], "Payroll setup")
        self.assertEqual(members[0]["open"], 2)
        self.assertEqual(members[0]["role"], "Developer")
        lead = next(m for m in members if m["user"] == LEAD[0])
        self.assertTrue(lead["is_lead"])
        self.assertFalse(lead["working_now"])
        self.assertEqual(lead["open"], 1)
        self.assertIsNone(result["totals"]["people_free"])

    def test_developers_cannot_see_the_portfolio(self):
        with self.assertRaises(frappe.PermissionError):
            self.portfolio(DEV)

    def test_person_matrix_lists_the_projects_they_work_on(self):
        result = self.portfolio(PM)
        people = {p["user"]: p for p in result["people"]}
        dev = people[DEV[0]]
        self.assertEqual(
            [(p["project"], p["open"], p["working_now"]) for p in dev["projects"]],
            [(self.project, 2, True), (self.other, 1, False)],
        )
        self.assertEqual(dev["open"], 3)
        self.assertEqual(
            [p["project"] for p in people[LEAD[0]]["projects"]], [self.project]
        )
        self.assertNotIn(SUPPORT[0], people)
        self.assertEqual(result["totals"]["projects"], 2)

    def test_admin_sees_every_project_and_who_is_free(self):
        unrelated = make_project("Internal tooling").name
        result = self.portfolio(("Administrator", ""))
        names = {c["name"] for c in result["projects"]}
        self.assertTrue({self.project, self.other, unrelated} <= names)

        people = {p["user"]: p for p in result["people"]}
        self.assertTrue(people[SUPPORT[0]]["is_free"])
        self.assertFalse(people[DEV[0]]["is_free"])
        # free people come after everyone with work
        self.assertTrue(result["people"][-1]["is_free"])
        self.assertGreaterEqual(result["totals"]["people_free"], 1)

    def test_status_and_customer_filters(self):
        frappe.db.set_value("Project", self.other, "status", "Completed")
        open_only = {c["name"] for c in self.portfolio(PM)["projects"]}
        self.assertEqual(open_only, {self.project})
        everything = {c["name"] for c in self.portfolio(PM, status="All")["projects"]}
        self.assertEqual(everything, {self.project, self.other})
        by_customer = self.portfolio(PM, status="All", customer=CUSTOMER)
        self.assertEqual([c["name"] for c in by_customer["projects"]], [self.project])


class TestAssigneeOutsideTeam(WorkControlCase):
    def test_lead_can_open_work_of_someone_only_assigned_a_task(self):
        task = self.make_task("Bank feeds", add_days(nowdate(), 3), assignee=SUPPORT)
        result = self.as_user(LEAD, lambda: work.get_my_work(user=SUPPORT[0]))
        self.assertIn(task, [i["name"] for i in result["items"]])


class TestHelpAndHandOver(WorkControlCase):
    def setUp(self):
        super().setUp()
        make_tasky_user(*TEAMMATE)
        project = frappe.get_doc("Project", self.project)
        project.append("users", {"user": TEAMMATE[0], "custom_role": "Developer"})
        project.save(ignore_permissions=True)

    def ask(self, task, teammate=TEAMMATE, due=None, user=DEV):
        return self.as_user(
            user,
            lambda: tasky.request_help(
                task=task,
                teammate=teammate[0],
                task_name="Share the customer's chart of accounts",
                description="Needed to map the opening balances",
                due_date=due,
            ),
        )

    def comments(self, task):
        return frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Task", "reference_name": task},
            pluck="content",
        )

    def test_assignee_asks_a_teammate_and_waits_for_it(self):
        task = self.make_task("Import opening balances", add_days(nowdate(), 5))
        result = self.ask(task, due=add_days(nowdate(), 2))

        help_task = result["help_task"]["name"]
        self.assertEqual(result["task"]["depends_on_task"], help_task)
        self.assertTrue(result["task"]["blocked"])
        helper = frappe.get_doc("Task", help_task)
        self.assertEqual(helper.project, self.project)
        self.assertEqual(helper.assignees(), [TEAMMATE[0]])
        self.assertEqual(str(helper.exp_end_date), str(add_days(nowdate(), 2)))
        self.assertTrue(
            any("needs your help" in s for s in self.notified(TEAMMATE, help_task))
        )
        self.assertTrue(any("asked" in s for s in self.notified(LEAD, task)))
        self.assertTrue(any("Waiting on" in c for c in self.comments(task)))

        self.as_user(
            TEAMMATE,
            lambda: tasky.complete_task(task=help_task, hours_worked=1, notes="Done"),
        )
        self.assertTrue(any("Unblocked" in s for s in self.notified(DEV, task)))

    def test_help_must_fit_before_the_task_is_due(self):
        task = self.make_task("Import opening balances", add_days(nowdate(), 3))
        with self.assertRaises(frappe.ValidationError):
            self.ask(task, due=add_days(nowdate(), 4))
        with self.assertRaises(frappe.ValidationError):
            self.ask(task, due=add_days(nowdate(), -1))

    def test_an_open_dependency_is_not_replaced(self):
        first = self.make_task("Install server", add_days(nowdate(), 2), assignee=LEAD)
        task = self.make_task("Deploy app", add_days(nowdate(), 5))
        self.as_user(
            LEAD, lambda: tasky.update_task_plan(task=task, depends_on_task=first)
        )
        with self.assertRaises(frappe.ValidationError):
            self.ask(task)

    def test_developers_only_ask_people_on_the_team(self):
        task = self.make_task("Import opening balances", add_days(nowdate(), 5))
        with self.assertRaises(frappe.ValidationError):
            self.ask(task, teammate=SUPPORT)
        with self.assertRaises(frappe.ValidationError):
            self.ask(task, teammate=DEV)

    def test_only_the_assignee_or_lead_can_ask(self):
        task = self.make_task("Import opening balances", add_days(nowdate(), 5))
        with self.assertRaises(frappe.PermissionError):
            self.ask(task, teammate=LEAD, user=TEAMMATE)

    def test_assignee_hands_over_and_the_lead_hears_why(self):
        task = self.make_task("Configure payroll", add_days(nowdate(), 4))
        self.as_user(
            DEV,
            lambda: tasky.hand_over_task(
                task=task, teammate=TEAMMATE[0], reason="Moved to the Galom go-live"
            ),
        )

        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.assignees(), [TEAMMATE[0]])
        self.assertTrue(
            any("handed you a task" in s for s in self.notified(TEAMMATE, task))
        )
        self.assertTrue(any("Galom go-live" in s for s in self.notified(LEAD, task)))
        self.assertTrue(any("Handed over" in c for c in self.comments(task)))
        self.assertNotIn(
            task, [t["name"] for t in self.as_user(DEV, tasky.get_my_tasks)]
        )

    def test_hand_over_needs_a_reason_a_teammate_and_a_stopped_timer(self):
        task = self.make_task("Configure payroll", add_days(nowdate(), 4))
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                DEV,
                lambda: tasky.hand_over_task(
                    task=task, teammate=TEAMMATE[0], reason=" "
                ),
            )
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                DEV,
                lambda: tasky.hand_over_task(
                    task=task, teammate=SUPPORT[0], reason="Busy"
                ),
            )
        frappe.db.set_value("Task", task, "custom_timer_start", now_datetime())
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                DEV,
                lambda: tasky.hand_over_task(
                    task=task, teammate=TEAMMATE[0], reason="Busy"
                ),
            )

    def test_closed_tasks_cannot_be_handed_over(self):
        task = self.make_task("Configure payroll", add_days(nowdate(), 4))
        frappe.db.set_value("Task", task, "status", "Completed")
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                DEV,
                lambda: tasky.hand_over_task(
                    task=task, teammate=TEAMMATE[0], reason="Busy"
                ),
            )


class TestCompletionNeedsTime(WorkControlCase):
    def test_board_and_status_changes_cannot_complete_without_hours(self):
        task = self.make_task("Payroll setup", add_days(nowdate(), 3))
        for status in ("Completed", "Pending Review"):
            with self.assertRaises(frappe.ValidationError):
                self.as_user(
                    DEV, lambda s=status: tasky.move_task(task=task, new_status=s)
                )
            with self.assertRaises(frappe.ValidationError):
                self.as_user(
                    DEV, lambda s=status: tasky.update_task_status(task=task, status=s)
                )
        self.assertEqual(frappe.db.get_value("Task", task, "status"), "Open")

    def test_timer_uses_the_site_time_zone_and_never_goes_negative(self):
        task = self.make_task("Payroll setup", add_days(nowdate(), 3))
        frappe.db.set_value(
            "Task", task, "custom_timer_start", add_to_date(now_datetime(), hours=-1)
        )
        elapsed = self.as_user(DEV, lambda: tasky.stop_timer(task=task))["elapsed"]
        self.assertAlmostEqual(elapsed, 1, delta=0.05)

        frappe.db.set_value(
            "Task", task, "custom_timer_start", add_to_date(now_datetime(), hours=2)
        )
        self.assertEqual(
            self.as_user(DEV, lambda: tasky.stop_timer(task=task))["elapsed"], 0
        )
        self.assertGreaterEqual(
            frappe.db.get_value("Task", task, "custom_actual_hours"), 0
        )


class TestTeamTimesheets(WorkControlCase):
    def test_lead_sees_the_teams_timesheets_and_developers_only_their_own(self):
        task = self.make_task("Opening balances", add_days(nowdate(), 3))
        self.as_user(
            DEV,
            lambda: tasky.complete_task(task=task, hours_worked=2, notes="Imported"),
        )

        team = self.as_user(LEAD, lambda: tasky.get_my_timesheets(team=1))
        mine = [t for t in team if t["owner"] == DEV[0]]
        self.assertTrue(mine)
        self.assertEqual(mine[0]["owner_name"], DEV[1])
        self.assertEqual(self.as_user(LEAD, tasky.get_my_timesheets), [])
        self.assertTrue(self.as_user(DEV, tasky.get_my_timesheets))
        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV, lambda: tasky.get_my_timesheets(team=1))

    def test_lead_filters_by_agent_and_date_and_downloads_csv(self):
        task = self.make_task("Opening balances", add_days(nowdate(), 3))
        self.as_user(
            DEV,
            lambda: tasky.complete_task(task=task, hours_worked=2, notes="Imported"),
        )

        def names(**filters):
            rows = self.as_user(
                LEAD, lambda: tasky.get_my_timesheets(team=1, **filters)
            )
            return {t["owner"] for t in rows}

        self.assertEqual(names(agent=DEV[0]), {DEV[0]})
        self.assertEqual(names(agent=LEAD[0]), set())
        self.assertEqual(names(agent=DEV[0], from_date=nowdate()), {DEV[0]})
        self.assertEqual(names(from_date=add_days(nowdate(), 1)), set())

        # entered today for work done ten days ago: it belongs to that date
        late = self.as_user(
            DEV,
            lambda: make_timesheet(
                self.project, 1.5, add_to_date(now_datetime(), days=-10)
            ),
        ).name
        rows = self.as_user(
            LEAD,
            lambda: tasky.get_my_timesheets(
                team=1,
                from_date=add_days(nowdate(), -11),
                to_date=add_days(nowdate(), -9),
            ),
        )
        self.assertEqual([t["name"] for t in rows], [late])
        today = self.as_user(
            LEAD, lambda: tasky.get_my_timesheets(team=1, from_date=nowdate())
        )
        self.assertNotIn(late, [t["name"] for t in today])

        agents = self.as_user(LEAD, tasky.get_timesheet_agents)
        self.assertIn({"user": DEV[0], "full_name": DEV[1]}, agents)

        frappe.response.clear()
        self.as_user(LEAD, lambda: tasky.export_timesheets_csv(team=1, agent=DEV[0]))
        self.assertEqual(frappe.response.type, "download")
        self.assertTrue(frappe.response.filename.endswith(".csv"))
        lines = frappe.response.filecontent.strip().splitlines()
        self.assertTrue(lines[0].startswith("Date,Agent,Timesheet"))
        self.assertTrue(
            any(DEV[1] in line and "Opening balances" in line for line in lines[1:])
        )
        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV, lambda: tasky.export_timesheets_csv(team=1))

    def test_summary_adds_up_the_time_logs_by_person_and_project(self):
        def log(project, hours, days_ago=0):
            when = add_to_date(now_datetime(), days=-days_ago)
            self.as_user(DEV, lambda: make_timesheet(project, hours, when))

        log(self.project, 2)
        log(self.project, 1.5, days_ago=10)
        log(None, 1)

        def summary(user, **filters):
            return self.as_user(user, lambda: tasky.get_timesheet_summary(**filters))

        # the lead sees the logs on their project, not the developer's other work
        team = summary(LEAD, team=1)
        self.assertEqual(team["hours"], 3.5)
        self.assertEqual(
            team["people"], [{"user": DEV[0], "full_name": DEV[1], "hours": 3.5}]
        )
        self.assertEqual([p["project"] for p in team["projects"]], [self.project])
        # only the logs in the chosen dates count
        self.assertEqual(summary(LEAD, team=1, from_date=nowdate())["hours"], 2)

        mine = summary(DEV)
        self.assertEqual(mine["hours"], 4.5)
        self.assertEqual(
            {p["project"]: p["hours"] for p in mine["projects"]},
            {self.project: 3.5, None: 1},
        )
        with self.assertRaises(frappe.PermissionError):
            summary(DEV, team=1)


class TestCompletedWork(WorkControlCase):
    def test_my_work_lists_what_was_completed_lately(self):
        task = self.make_task("Opening balances", add_days(nowdate(), 3))
        self.as_user(
            DEV,
            lambda: tasky.complete_task(task=task, hours_worked=2, notes="Imported"),
        )
        old = self.make_task("Chart of accounts", add_days(nowdate(), -50))
        frappe.db.set_value(
            "Task",
            old,
            {"status": "Completed", "completed_on": add_days(nowdate(), -40)},
        )
        ticket = make_ticket(subject="Report filter fixed", customer=CUSTOMER)
        make_assignment("HD Ticket", ticket.name, DEV[0])
        frappe.db.set_value(
            "HD Ticket",
            ticket.name,
            {
                "status": "Resolved",
                "status_category": "Resolved",
                "resolution_date": now_datetime(),
            },
        )

        result = self.as_user(DEV, work.get_my_work)

        done = {i["name"]: i for i in result["done"]}
        self.assertEqual(done[task]["hours"], 2)
        self.assertEqual(done[task]["done_on"], nowdate())
        self.assertIn(str(ticket.name), done)
        self.assertNotIn(old, done)
        self.assertEqual(result["counts"]["done"], len(result["done"]))
        self.assertNotIn(task, [i["name"] for i in result["items"]])

    def test_lead_sees_a_team_members_completed_work(self):
        task = self.make_task("Opening balances", add_days(nowdate(), 3))
        self.as_user(
            DEV, lambda: tasky.complete_task(task=task, hours_worked=1, notes="Done")
        )
        result = self.as_user(LEAD, lambda: work.get_my_work(user=DEV[0]))
        self.assertIn(task, [i["name"] for i in result["done"]])


class TestPullRequestsInWorkLists(WorkControlCase):
    def test_tasks_show_their_pull_requests_open_ones_first(self):
        task = self.make_task("Home dashboard", add_days(nowdate(), 2))
        merged_only = self.make_task("Old change", add_days(nowdate(), 2))
        make_pull_request(task, 4, state="Merged")
        make_pull_request(task, 5, ci_state="Passing")
        make_pull_request(merged_only, 3, state="Merged")

        items = {i["name"]: i for i in self.as_user(DEV, work.get_my_work)["items"]}

        prs = items[task]["pull_requests"]
        self.assertEqual([p["number"] for p in prs], [5, 4])
        self.assertEqual(prs[0]["ci_state"], "Passing")
        # a task whose PRs are merged is still recognisable as Git work
        self.assertEqual(items[merged_only]["pull_requests"][0]["state"], "Merged")
