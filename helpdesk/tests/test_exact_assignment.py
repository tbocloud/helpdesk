"""Who a task or ticket is assigned to is matched exactly, never with a LIKE on `_assign`,
where `_` and `%` in a user ID are wildcards (jane_doe@ would match janexdoe@; Frappe
keeps user IDs lowercase)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import (
    call_as_user,
    hold_commits,
    make_assigned_task,
    make_assigned_ticket,
    make_project,
    make_tasky_user,
)

PM = ("leena.varghese@exact-assign.example", "Leena Varghese")
UNDERSCORE = ("jane_doe@exact-assign.example", "Jane Doe")
LOOKALIKE = ("janexdoe@exact-assign.example", "Jane Xavier Doe")


class TestExactAssignment(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*UNDERSCORE)
        make_tasky_user(*LOOKALIKE)
        # each has a task in a project they aren't members of
        self.project = make_project(
            "Galom International Trading - ERP Rollout", owner=PM[0]
        ).name
        self.mine = make_assigned_task(self.project, "HR setup", UNDERSCORE[0], PM[0])
        self.other_project = make_project("Metta Bank - Reports", owner=PM[0]).name
        self.theirs = make_assigned_task(
            self.other_project, "Bank report to Metta", LOOKALIKE[0], PM[0]
        )
        self.my_ticket = make_assigned_ticket("Login fails", UNDERSCORE[0])
        self.their_ticket = make_assigned_ticket("Report is slow", LOOKALIKE[0])

    def as_jane(self, method: str, **kwargs):
        return call_as_user(UNDERSCORE[0], method, **kwargs)

    def test_my_tasks_and_my_board(self):
        tasks = self.as_jane("helpdesk.tasky.api.get_my_tasks")
        self.assertEqual({t["name"] for t in tasks}, {self.mine})
        board = self.as_jane("helpdesk.tasky.api.get_kanban_tasks")["columns"]
        self.assertEqual(
            {t["name"] for column in board.values() for t in column}, {self.mine}
        )

    def test_my_work(self):
        items = self.as_jane("helpdesk.api.work.get_my_work")["items"]
        names = {i["name"] for i in items}
        self.assertIn(self.mine, names)
        self.assertIn(self.my_ticket, names)
        self.assertNotIn(self.theirs, names)
        self.assertNotIn(self.their_ticket, names)

    def test_sidebar_counts(self):
        counts = self.as_jane("helpdesk.api.sidebar.get_nav_counts")
        self.assertEqual(counts["my_tasks"], 1)
        self.assertEqual(counts["tickets"], 1)
        self.assertEqual(counts["my_work"], 2)

    def test_projects_seen_through_an_assigned_task(self):
        projects = self.as_jane("helpdesk.tasky.api.get_projects")
        self.assertEqual({p["name"] for p in projects}, {self.project})
        self.assertFalse(
            frappe.has_permission(
                "Project", "read", doc=self.other_project, user=UNDERSCORE[0]
            )
        )
        self.assertTrue(
            frappe.has_permission(
                "Project", "read", doc=self.other_project, user=LOOKALIKE[0]
            )
        )

    def test_ticket_list_assigned_to_filter(self):
        for value in (f"%{UNDERSCORE[0]}%", "%@me%"):
            with self.subTest(value=value):
                result = self.as_jane(
                    "helpdesk.api.doc.get_list_data",
                    doctype="HD Ticket",
                    filters=[["_assign", "like", value]],
                    page_length=100,
                )
                names = {str(row["name"]) for row in result["data"]}
                self.assertIn(self.my_ticket, names)
                self.assertNotIn(self.their_ticket, names)
                self.assertEqual(result["total_count"], len(names))
