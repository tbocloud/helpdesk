# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import departments
from helpdesk.helpdesk.doctype.hd_department.hd_department import (
    DEFAULT_DEPARTMENTS,
    ensure_default_departments,
)
from helpdesk.setup.install import get_custom_fields
from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    hold_commits,
    make_department,
    make_project,
    make_task_template,
    make_tasky_user,
    run_as_user,
)

DESIGNER = ("designer@departments.example", "Meera Krishnan")
DEVELOPER = ("developer@departments.example", "Vishnu Das")
AGENT = ("agent@departments.example", "Anjali Varma")
USED = "Test Dept In Use"
SPARE = "Test Dept Spare"


class TestDepartments(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # after_migrate applies the custom fields to existing sites the same way
        create_custom_fields(get_custom_fields())

    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        for user in (DESIGNER, DEVELOPER, AGENT):
            make_tasky_user(*user)

    def test_seeding_adds_only_missing_departments(self):
        ensure_default_departments()
        frappe.delete_doc("HD Department", "GrowthX", force=True)

        self.assertEqual(ensure_default_departments(), ["GrowthX"])
        self.assertEqual(ensure_default_departments(), [])
        for name in DEFAULT_DEPARTMENTS:
            self.assertEqual(frappe.db.count("HD Department", {"name": name}), 1)

    def test_departments_are_listed_in_order_and_can_be_moved(self):
        make_department(USED)
        make_department(SPARE)
        names = [d.name for d in departments.get_departments()]
        self.assertLess(names.index(USED), names.index(SPARE))

        order = departments.move_department(SPARE, "up")
        self.assertEqual(order.index(SPARE) + 1, order.index(USED))
        names = [d.name for d in departments.get_departments()]
        self.assertEqual(names, order)

    def test_inactive_departments_are_hidden_unless_asked_for(self):
        make_department(SPARE)
        departments.set_department_active(SPARE, False)

        self.assertNotIn(SPARE, [d.name for d in departments.get_departments()])
        self.assertIn(
            SPARE,
            [d.name for d in departments.get_departments(include_inactive=True)],
        )

    def test_deleting_a_used_department_explains_what_to_do(self):
        make_department(USED)
        make_department(SPARE)
        project = make_project("Departments Website Revamp")
        project.db_set("custom_department", USED)

        with self.assertRaises(frappe.LinkExistsError) as raised:
            departments.delete_department(USED)
        self.assertIn("deactivate", str(raised.exception))
        self.assertTrue(frappe.db.exists("HD Department", USED))

        departments.delete_department(SPARE)
        self.assertFalse(frappe.db.exists("HD Department", SPARE))

    def test_renaming_moves_the_projects_along(self):
        make_department(USED)
        project = make_project("Departments Brand Refresh")
        project.db_set("custom_department", USED)

        new = departments.rename_department(USED, f"{USED} Renamed")["name"]
        self.assertEqual(
            frappe.db.get_value("Project", project.name, "custom_department"), new
        )

    def test_only_managers_change_departments(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(AGENT[0], lambda: departments.add_department(SPARE))
        self.assertFalse(frappe.db.exists("HD Department", SPARE))

    def test_projects_carry_their_department(self):
        make_department(USED)
        project = tasky.create_project(
            project_name="Departments Social Launch",
            expected_start_date="2026-10-01",
            expected_end_date="2026-10-31",
            department=USED,
        )["name"]

        listed = {p.name: p for p in tasky.get_projects()}
        self.assertEqual(listed[project].department, USED)
        self.assertEqual(tasky.get_project_detail(project)["department"], USED)

        tasky.update_project(project=project, project_name="Departments Social Launch")
        self.assertEqual(tasky.get_project_detail(project)["department"], USED)

    def test_an_inactive_department_cant_be_picked(self):
        make_department(SPARE, is_active=0)
        with self.assertRaises(frappe.ValidationError):
            tasky.create_project(
                project_name="Departments Inactive Pick",
                expected_start_date="2026-10-01",
                expected_end_date="2026-10-31",
                department=SPARE,
            )

    def test_graphic_design_tasks_go_to_the_graphic_designer(self):
        project = make_project(
            "Departments Festive Campaign",
            members=[(DEVELOPER[0], "Developer"), (DESIGNER[0], "Graphic Designer")],
        )
        template = make_task_template(
            "Departments Creative Template",
            [
                {
                    "task_name": "Design the festive poster",
                    "category": "Graphic Design",
                },
                {"task_name": "Design the story frames", "category": "Graphic Design"},
            ],
        )

        tasky.generate_checklist(project.name, template.name)

        for task in frappe.get_all("Task", {"project": project.name}, ["_assign"]):
            self.assertEqual(json.loads(task._assign), [DESIGNER[0]])
