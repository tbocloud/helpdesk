# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

"""Smoke tests for the tasky Project Manager -> developer permission flow.

Runs a realistic engagement through the whitelisted tasky API as each user.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.tasky import api
from helpdesk.test_utils import (
    create_customer,
    create_user,
    make_project,
    make_tasky_user,
)

# Keep all names here so the scenario can be re-cast in one place.
CUSTOMER = "Al Noor Trading LLC"
OTHER_CUSTOMER = "Gulf Star Logistics"
PM = ("fatima.rahman@tasky-smoke.example", "Fatima Rahman")
OTHER_PM = ("omar.khalid@tasky-smoke.example", "Omar Khalid")
DEV_A = ("arjun.menon@tasky-smoke.example", "Arjun Menon")
DEV_B = ("sara.haddad@tasky-smoke.example", "Sara Haddad")
OUTSIDER = ("li.wei@tasky-smoke.example", "Li Wei")


class TestTaskyPermissions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        for (email, name), roles in [
            (PM, ("Project Manager",)),
            (OTHER_PM, ("Project Manager",)),
            (DEV_A, ()),
            (DEV_B, ()),
            (OUTSIDER, ()),
        ]:
            make_tasky_user(email, name, roles)
        frappe.db.commit()  # nosemgrep

    def setUp(self):
        # the tasky API commits; keep each test's data inside its own transaction
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")

        create_customer(CUSTOMER)
        self.project = self.as_user(
            PM,
            api.create_project,
            project_name=f"{CUSTOMER} - ERP Implementation",
            customer=CUSTOMER,
            members=json.dumps(
                [
                    {"user": DEV_A[0], "custom_role": "Developer"},
                    {"user": DEV_B[0], "custom_role": "Developer"},
                ]
            ),
        )["name"]
        self.task_a = self.as_user(
            PM,
            api.add_task,
            project=self.project,
            task_name="Configure chart of accounts",
            phase="Setup",
            assigned_to=DEV_A[0],
        )["name"]
        self.task_b = self.as_user(
            PM,
            api.add_task,
            project=self.project,
            task_name="Migrate opening stock",
            phase="Data Migration",
            assigned_to=DEV_B[0],
        )["name"]

    def as_user(self, user, fn, **kwargs):
        frappe.set_user(user[0])
        try:
            return fn(**kwargs)
        finally:
            frappe.set_user("Administrator")

    # --- projects ---

    def test_creator_is_project_manager_of_new_project(self):
        detail = self.as_user(PM, api.get_project_detail, project=self.project)
        self.assertTrue(detail["can_manage"])
        self.assertEqual(detail["customer"], CUSTOMER)
        roles = {
            u.user: u.custom_role for u in frappe.get_doc("Project", self.project).users
        }
        self.assertEqual(roles[PM[0]], "Project Manager")

    def test_developer_cannot_create_project(self):
        with self.assertRaises(frappe.PermissionError):
            self.as_user(
                DEV_A, api.create_project, project_name=f"{CUSTOMER} - Side Project"
            )

    def test_members_see_project_but_cannot_manage_it(self):
        projects = {p["name"]: p for p in self.as_user(DEV_A, api.get_projects)}
        self.assertIn(self.project, projects)
        self.assertFalse(projects[self.project]["can_manage"])
        with self.assertRaises(frappe.PermissionError):
            self.as_user(
                DEV_A, api.add_task, project=self.project, task_name="Sneaky task"
            )

    def test_outsider_and_other_pm_cannot_see_project(self):
        make_project(f"{OTHER_CUSTOMER} - Support Rollout", owner=OTHER_PM[0])
        for user in (OUTSIDER, OTHER_PM):
            names = [p["name"] for p in self.as_user(user, api.get_projects)]
            self.assertNotIn(self.project, names)
            with self.assertRaises(frappe.PermissionError):
                self.as_user(user, api.get_project_detail, project=self.project)

    # --- tasks ---

    def test_developer_sees_only_assigned_tasks(self):
        mine = [t["name"] for t in self.as_user(DEV_A, api.get_my_tasks)]
        self.assertEqual(mine, [self.task_a])

        board = self.as_user(DEV_A, api.get_kanban_tasks, project=self.project)
        on_board = [t["name"] for col in board["columns"].values() for t in col]
        self.assertEqual(on_board, [self.task_a])

        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV_A, api.get_task_detail, task=self.task_b)

    def test_project_manager_sees_all_project_tasks(self):
        board = self.as_user(PM, api.get_kanban_tasks, project=self.project)
        on_board = {t["name"] for col in board["columns"].values() for t in col}
        self.assertEqual(on_board, {self.task_a, self.task_b})

    def test_dashboard_stats_follow_visibility(self):
        self.assertEqual(
            self.as_user(PM, api.get_project_dashboard, project=self.project)["stats"][
                "total"
            ],
            2,
        )
        self.assertEqual(
            self.as_user(DEV_A, api.get_project_dashboard, project=self.project)[
                "stats"
            ]["total"],
            1,
        )

    def test_developer_can_work_own_task_only(self):
        self.as_user(DEV_A, api.move_task, task=self.task_a, new_status="Working")
        self.assertEqual(frappe.db.get_value("Task", self.task_a, "status"), "Working")

        for fn, kwargs in [
            (api.move_task, {"task": self.task_b, "new_status": "Working"}),
            (api.update_task_status, {"task": self.task_b, "status": "Completed"}),
            (api.start_timer, {"task": self.task_b}),
        ]:
            with self.assertRaises(frappe.PermissionError):
                self.as_user(DEV_A, fn, **kwargs)
        self.assertEqual(frappe.db.get_value("Task", self.task_b, "status"), "Open")

    # --- timesheets ---

    def test_completing_task_logs_timesheet_visible_to_pm(self):
        self.as_user(
            DEV_A,
            api.complete_task,
            task=self.task_a,
            hours_worked=3,
            notes="Accounts mapped",
        )
        timesheet = frappe.db.get_value(
            "Timesheet Detail", {"task": self.task_a}, "parent"
        )
        self.assertTrue(timesheet)
        self.assertEqual(frappe.db.get_value("Timesheet", timesheet, "total_hours"), 3)

        self.assertIn(
            timesheet,
            self.as_user(PM, frappe.get_list, doctype="Timesheet", pluck="name"),
        )
        self.assertNotIn(
            timesheet,
            self.as_user(DEV_B, frappe.get_list, doctype="Timesheet", pluck="name"),
        )

    # --- templates ---

    def test_templates_are_for_project_managers(self):
        created = self.as_user(
            PM,
            api.create_template,
            template_name=f"{CUSTOMER} Rollout",
            tasks=json.dumps(
                [{"task_name": "Kick-off workshop", "phase_name": "Discovery"}]
            ),
        )
        self.assertTrue(created["name"])
        with self.assertRaises(frappe.PermissionError):
            self.as_user(DEV_A, api.get_templates)

    # --- manual tasks ---

    def test_pm_adds_manual_task_for_a_member(self):
        task = self.as_user(
            PM,
            api.add_task,
            project=self.project,
            task_name="Set up tax templates",
            description="VAT 5% and zero-rated",
            assigned_to=DEV_B[0],
            due_date="2026-10-15",
        )
        self.assertEqual(task["assignees"], [DEV_B[0]])
        self.assertEqual(
            frappe.db.get_value("Task", task["name"], "description"),
            "VAT 5% and zero-rated",
        )
        self.assertIn(
            task["name"], [t["name"] for t in self.as_user(DEV_B, api.get_my_tasks)]
        )

    def test_assigning_an_agent_from_outside_adds_them_to_the_team(self):
        task = self.as_user(
            PM,
            api.add_task,
            project=self.project,
            task_name="Stock ageing report",
            assigned_to=OUTSIDER[0],
        )
        roles = {
            u.user: u.custom_role for u in frappe.get_doc("Project", self.project).users
        }
        self.assertEqual(roles[OUTSIDER[0]], "Developer")
        self.assertEqual(task["assignees"], [OUTSIDER[0]])

    def test_manual_task_cannot_go_to_someone_who_is_not_an_agent(self):
        create_user("vendor.contact@tasky-smoke.example")
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                PM,
                api.add_task,
                project=self.project,
                task_name="Sneaky",
                assigned_to="vendor.contact@tasky-smoke.example",
            )

    # --- project lead ---

    def test_lead_creates_and_assigns_tasks_and_sees_all(self):
        self.as_user(
            PM, lambda: api.set_project_lead(project=self.project, user=DEV_A[0])
        )
        task = self.as_user(
            DEV_A,
            api.add_task,
            project=self.project,
            task_name="Review tax setup",
            assigned_to=DEV_B[0],
        )
        self.assertEqual(task["assignees"], [DEV_B[0]])

        board = self.as_user(DEV_A, api.get_kanban_tasks, project=self.project)
        on_board = {t["name"] for col in board["columns"].values() for t in col}
        self.assertTrue({self.task_a, self.task_b, task["name"]} <= on_board)

        detail = self.as_user(DEV_A, api.get_project_detail, project=self.project)
        self.assertTrue(detail["can_manage"])
        self.assertFalse(detail["can_change_lead"])

    def test_lead_cannot_create_projects_or_change_the_lead(self):
        self.as_user(
            PM, lambda: api.set_project_lead(project=self.project, user=DEV_A[0])
        )
        for fn, kwargs in [
            (api.create_project, {"project_name": f"{CUSTOMER} - Lead Project"}),
            (lambda: api.set_project_lead(project=self.project, user=DEV_A[0]), {}),
            (api.rotate_project_lead, {"project": self.project}),
        ]:
            with self.assertRaises(frappe.PermissionError):
                self.as_user(DEV_A, fn, **kwargs)

    def test_other_members_still_cannot_add_tasks(self):
        self.as_user(
            PM, lambda: api.set_project_lead(project=self.project, user=DEV_A[0])
        )
        with self.assertRaises(frappe.PermissionError):
            self.as_user(
                DEV_B, api.add_task, project=self.project, task_name="Not mine"
            )

    def test_rotation_cycles_through_developers(self):
        leads = [
            self.as_user(PM, api.rotate_project_lead, project=self.project)[
                "project_lead"
            ]
            for _ in range(3)
        ]
        self.assertEqual(leads, [DEV_A[0], DEV_B[0], DEV_A[0]])
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_doctype": "Project",
                    "reference_name": self.project,
                    "content": ("like", "%Project lead changed%"),
                },
            )
        )

    def test_lead_must_be_a_member(self):
        with self.assertRaises(frappe.ValidationError):
            self.as_user(
                PM, lambda: api.set_project_lead(project=self.project, user=OUTSIDER[0])
            )

    # --- editing a project ---

    def edit(self, user, **values):
        payload = {
            "project": self.project,
            "project_name": f"{CUSTOMER} - ERP Implementation",
            **values,
        }
        return self.as_user(user, lambda: api.update_project(**payload))

    def test_pm_edits_details_members_and_lead(self):
        members = json.dumps(
            [
                {"user": DEV_A[0], "custom_role": "Developer"},
                {"user": PM[0], "custom_role": "Project Manager"},
            ]
        )
        self.edit(
            PM,
            project_name=f"{CUSTOMER} - Phase 2",
            priority="High",
            members=members,
            project_lead=DEV_A[0],
        )
        doc = frappe.get_doc("Project", self.project)
        self.assertEqual(doc.project_name, f"{CUSTOMER} - Phase 2")
        self.assertEqual(doc.priority, "High")
        self.assertEqual(doc.project_lead, DEV_A[0])
        self.assertNotIn(DEV_B[0], [u.user for u in doc.users])

    def test_only_managers_can_edit(self):
        self.as_user(
            PM, lambda: api.set_project_lead(project=self.project, user=DEV_A[0])
        )
        for user in (DEV_A, DEV_B, OUTSIDER):
            with self.assertRaises(frappe.PermissionError):
                self.edit(user, priority="Low")

    def test_duplicate_name_rejected(self):
        make_project(f"{OTHER_CUSTOMER} - Existing")
        with self.assertRaises(frappe.ValidationError):
            self.edit(PM, project_name=f"{OTHER_CUSTOMER} - Existing")

    def test_manager_cannot_remove_themselves(self):
        self.edit(
            PM, members=json.dumps([{"user": DEV_A[0], "custom_role": "Developer"}])
        )
        roles = {
            u.user: u.custom_role for u in frappe.get_doc("Project", self.project).users
        }
        self.assertEqual(roles.get(PM[0]), "Project Manager")

    def test_end_date_cannot_precede_start_date(self):
        with self.assertRaises(frappe.ValidationError):
            self.edit(
                PM, expected_start_date="2026-10-10", expected_end_date="2026-10-01"
            )
        self.edit(PM, expected_start_date="2026-10-01", expected_end_date="2026-10-31")
        doc = frappe.get_doc("Project", self.project)
        self.assertEqual(str(doc.expected_end_date), "2026-10-31")
