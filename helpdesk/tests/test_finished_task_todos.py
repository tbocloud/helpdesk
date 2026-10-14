"""A finished task's ToDos close, a reopened one's come back (Task.close_assignments)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from helpdesk.patches.v16_0_2 import close_finished_task_todos
from helpdesk.tasky.permissions import get_assigners
from helpdesk.test_utils import (
    get_task_todos,
    hold_commits,
    make_assigned_task,
    make_done_task,
    make_project,
    make_tasky_user,
    save_task_as,
)

LEAD = ("lead.todos@finished-todos.example", "Nisha Varghese")
DEV = ("dev.todos@finished-todos.example", "Arjun Menon")


class TestFinishedTaskTodos(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        for user in (LEAD, DEV):
            make_tasky_user(*user)
        self.project = make_project(
            "Finished ToDos - Payroll", members=[(DEV[0], "Developer")], owner=LEAD[0]
        ).name
        self.task = make_assigned_task(
            self.project, "Payroll export", DEV[0], assigned_by=LEAD[0]
        )

    def assignees(self) -> list[str]:
        return frappe.get_doc("Task", self.task).assignees()

    def test_completing_closes_the_todo_and_keeps_who_did_it(self):
        save_task_as("Administrator", self.task, status="Completed")

        self.assertEqual(get_task_todos(self.task), [(DEV[0], "Closed")])
        # the Scoreboard and the Team page credit finished work through _assign
        self.assertEqual(self.assignees(), [DEV[0]])

    def test_cancelling_closes_the_todo_too(self):
        save_task_as("Administrator", self.task, status="Cancelled")

        self.assertEqual(get_task_todos(self.task), [(DEV[0], "Closed")])

    def test_reopening_gives_the_task_back_to_its_assignee(self):
        save_task_as("Administrator", self.task, status="Completed")
        save_task_as("Administrator", self.task, status="Open")

        self.assertEqual(get_task_todos(self.task), [(DEV[0], "Open")])
        self.assertEqual(self.assignees(), [DEV[0]])

        # completing and reopening again doesn't pile up ToDos
        save_task_as("Administrator", self.task, status="Completed")
        save_task_as("Administrator", self.task, status="Working")
        self.assertEqual(get_task_todos(self.task), [(DEV[0], "Open")])

    def test_the_assigner_is_still_known_after_closing(self):
        save_task_as("Administrator", self.task, status="Completed")

        self.assertEqual(get_assigners({self.task: DEV[0]}), {self.task: LEAD[0]})

    def test_moving_between_open_statuses_leaves_the_todo_alone(self):
        save_task_as("Administrator", self.task, status="Working")

        self.assertEqual(get_task_todos(self.task), [(DEV[0], "Open")])

    def test_the_patch_closes_stale_todos_and_can_run_again(self):
        # finished before the task closed its own ToDos: the status was set directly
        stale = make_done_task(self.project, "Old report", DEV[0], nowdate())
        self.assertEqual(get_task_todos(stale), [(DEV[0], "Open")])

        close_finished_task_todos.execute()
        self.assertEqual(get_task_todos(stale), [(DEV[0], "Closed")])
        self.assertEqual(get_task_todos(self.task), [(DEV[0], "Open")])

        close_finished_task_todos.execute()
        self.assertEqual(get_task_todos(stale), [(DEV[0], "Closed")])
        self.assertEqual(frappe.get_doc("Task", stale).assignees(), [DEV[0]])
