"""How long a started task has been in its status, and the tasks a person gave out
(My Work's Assigned by me). See docs/workspace-pages.md "Status age" and
"Assigned by me"."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, nowdate

from helpdesk.test_utils import (
    call_as_user,
    create_customer,
    get_in_progress_as,
    hold_commits,
    make_assigned_task,
    make_project,
    make_started_task,
    make_tasky_user,
    record_status_change,
)

CUSTOMER = "Malabar Spice Traders"
LEAD = ("lead@task-aging.example", "Nikhil Das")
DEV = ("dev@task-aging.example", "Fathima Rizwana")
TEAMMATE = ("teammate@task-aging.example", "Anjali Menon")
MANAGER = ("manager@task-aging.example", "Arun Menon")


def days_ago(days: int) -> str:
    return f"{add_days(nowdate(), -days)} 10:00:00"


class TaskAgingCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        for user in (LEAD, DEV, TEAMMATE):
            make_tasky_user(*user)
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        self.project = make_project(
            f"{CUSTOMER} - ERP rollout",
            members=[
                (LEAD[0], "Developer"),
                (DEV[0], "Developer"),
                (TEAMMATE[0], "Developer"),
            ],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])


class TestStatusSince(TaskAgingCase):
    def since(self, task: str) -> str | None:
        items = call_as_user(DEV[0], "helpdesk.api.work.get_my_work")["items"]
        return next(i for i in items if i["name"] == task)["status_since"]

    def test_latest_move_into_the_current_status_counts(self):
        task = make_started_task(self.project, "Stock ledger fix", DEV[0])
        record_status_change(task, "Open", "Working", days_ago(9))
        record_status_change(task, "Working", "Pending Review", days_ago(5))
        record_status_change(task, "Pending Review", "Working", days_ago(3))
        self.assertEqual(get_datetime(self.since(task)), get_datetime(days_ago(3)))

        frappe.db.set_value("Task", task, "status", "Pending Review")
        self.assertEqual(get_datetime(self.since(task)), get_datetime(days_ago(5)))

    def test_without_history_the_expected_start_then_creation(self):
        planned = make_started_task(
            self.project,
            "Payroll export",
            DEV[0],
            exp_start_date=add_days(nowdate(), -4),
        )
        self.assertEqual(
            get_datetime(self.since(planned)),
            get_datetime(add_days(nowdate(), -4)),
        )

        unplanned = make_started_task(self.project, "Bank reconciliation", DEV[0])
        frappe.db.set_value(
            "Task", unplanned, "creation", days_ago(6), update_modified=False
        )
        self.assertEqual(get_datetime(self.since(unplanned)), get_datetime(days_ago(6)))

    def test_on_hold_counts_from_the_hold(self):
        task = make_started_task(
            self.project,
            "Price list import",
            DEV[0],
            status="On Hold",
            hold_since=add_days(nowdate(), -2),
            hold_reason="Waiting on customer",
        )
        record_status_change(task, "Working", "On Hold", days_ago(8))
        self.assertEqual(
            get_datetime(self.since(task)), get_datetime(add_days(nowdate(), -2))
        )

    def test_open_tasks_have_no_status_age(self):
        task = make_assigned_task(self.project, "Train users", DEV[0], LEAD[0])
        self.assertIsNone(self.since(task))

    def test_in_progress_rows_carry_it(self):
        task = make_started_task(self.project, "GST return", DEV[0])
        record_status_change(task, "Open", "Working", days_ago(7))
        tasks = [
            t
            for lane in get_in_progress_as(LEAD[0])["lanes"]
            for t in lane["tasks"]
            if t["name"] == task
        ]
        self.assertEqual(
            get_datetime(tasks[0]["status_since"]), get_datetime(days_ago(7))
        )


class TestAssignedBy(TaskAgingCase):
    def given_out(self, as_user, **kwargs) -> list[str]:
        result = call_as_user(as_user[0], "helpdesk.api.work.get_assigned_by", **kwargs)
        return [i["name"] for i in result["items"]]

    def test_only_open_tasks_the_person_gave_someone_else(self):
        given = make_assigned_task(self.project, "Customize invoice", DEV[0], LEAD[0])
        done = make_assigned_task(self.project, "Old report", DEV[0], LEAD[0])
        frappe.db.set_value("Task", done, "status", "Completed")
        cancelled = make_assigned_task(self.project, "Dropped idea", DEV[0], LEAD[0])
        frappe.db.set_value("Task", cancelled, "status", "Cancelled")
        own = make_assigned_task(self.project, "Own work", LEAD[0], LEAD[0])
        by_someone_else = make_assigned_task(
            self.project, "Teammate's ask", DEV[0], TEAMMATE[0]
        )

        result = call_as_user(LEAD[0], "helpdesk.api.work.get_assigned_by")
        names = [i["name"] for i in result["items"]]
        self.assertEqual(result["user"], LEAD[0])
        self.assertIn(given, names)
        for name in (done, cancelled, own, by_someone_else):
            self.assertNotIn(name, names)
        item = next(i for i in result["items"] if i["name"] == given)
        self.assertEqual(item["given_to"], [DEV[0]])
        self.assertNotIn("assigned_by", item)

    def test_someone_without_the_overview_cannot_ask_for_another_person(self):
        make_assigned_task(self.project, "Customize invoice", DEV[0], LEAD[0])
        self.assertEqual(self.given_out(DEV, user=DEV[0]), [])
        with self.assertRaises(frappe.PermissionError):
            self.given_out(DEV, user=LEAD[0])

    def test_a_manager_can_see_what_another_person_gave_out(self):
        given = make_assigned_task(self.project, "Customize invoice", DEV[0], LEAD[0])
        self.assertIn(given, self.given_out(MANAGER, user=LEAD[0]))
        self.assertNotIn(given, self.given_out(MANAGER))
