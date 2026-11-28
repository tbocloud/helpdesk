import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import employee_handover as handover_api
from helpdesk.test_utils import (
    hold_commits,
    make_access_entry,
    make_assigned_task,
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    run_as_user,
)

MANAGER = "handover.manager@handover.example"
LEAVER = "handover.leaver@handover.example"
TAKER = "handover.taker@handover.example"
COLLEAGUE = "handover.colleague@handover.example"


class TestEmployeeHandover(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(MANAGER, "Handover Manager", roles=("Project Manager",))
        for user, name in (
            (LEAVER, "Handover Leaver"),
            (TAKER, "Handover Taker"),
            (COLLEAGUE, "Handover Colleague"),
        ):
            make_tasky_user(user, name)
        self.project = make_project(
            "Handover Project",
            members=[(MANAGER, "Project Manager"), (LEAVER, "Developer")],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAVER)
        self.task = make_assigned_task(self.project, "Finish the API", LEAVER, MANAGER)
        make_assignment("Task", self.task, COLLEAGUE)
        self.done = make_task(self.project, "Already done", status="Completed").name
        make_assignment("Task", self.done, LEAVER)
        self.loose = make_task(None, "Renew the domain").name
        make_assignment("Task", self.loose, LEAVER)
        make_access_entry(self.project, password="x", user=LEAVER)

    def preview(self, user=MANAGER):
        return run_as_user(user, lambda: handover_api.get_handover_preview(LEAVER))

    def complete(self, user=MANAGER, **kwargs):
        kwargs.setdefault(
            "projects",
            [
                {
                    "project": self.project,
                    "new_owner": TAKER,
                    "note": "Repo is on GitHub",
                }
            ],
        )
        kwargs.setdefault("default_owner", COLLEAGUE)
        return run_as_user(
            user, lambda: handover_api.complete_handover(LEAVER, **kwargs)
        )

    def test_the_preview_shows_what_they_hold(self):
        data = self.preview()
        row = next(p for p in data["projects"] if p["project"] == self.project)
        self.assertEqual(
            (row["role"], row["is_lead"], row["open_tasks"], row["access_entries"]),
            ("Developer", True, 1, 1),
        )
        # they lead it, so a manager of the project is suggested
        self.assertEqual(row["suggested_owner"], MANAGER)
        self.assertEqual(data["other_tasks"], 1)
        people = run_as_user(MANAGER, handover_api.get_people)
        self.assertIn(LEAVER, [p["name"] for p in people["people"]])
        self.assertIn(TAKER, [p["name"] for p in people["takers"]])

    def test_completing_moves_tasks_team_place_and_lead(self):
        result = self.complete()
        self.assertEqual(result["projects"][0]["tasks_moved"], 1)
        self.assertEqual(result["other_tasks_moved"], 1)
        task = frappe.get_doc("Task", self.task)
        self.assertEqual(sorted(task.assignees()), sorted([COLLEAGUE, TAKER]))
        # a closed task stays as it was
        self.assertIn(LEAVER, frappe.get_doc("Task", self.done).assignees())
        self.assertEqual(frappe.get_doc("Task", self.loose).assignees(), [COLLEAGUE])
        project = frappe.get_doc("Project", self.project)
        members = {u.user: u.custom_role for u in project.users}
        self.assertNotIn(LEAVER, members)
        self.assertEqual(members[TAKER], "Developer")
        self.assertEqual(project.project_lead, TAKER)
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_name": self.project,
                    "content": ("like", "%Repo is on GitHub%"),
                },
            )
        )
        doc = frappe.get_doc("HD Employee Handover", result["name"])
        self.assertEqual((doc.status, doc.completed_by), ("Done", MANAGER))
        self.assertFalse(self.preview()["projects"])

    def test_only_managers_and_heads_may_hand_over(self):
        for call in (lambda: self.preview(COLLEAGUE), lambda: self.complete(COLLEAGUE)):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_the_leaver_cannot_take_their_own_work(self):
        with self.assertRaises(frappe.ValidationError):
            self.complete(default_owner=LEAVER)

    def test_a_project_they_are_not_on_is_refused(self):
        other = make_project("Someone Else's Project").name
        with self.assertRaises(frappe.ValidationError):
            self.complete(projects=[{"project": other, "new_owner": TAKER}])
