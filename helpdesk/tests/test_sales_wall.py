"""The Sales Employee wall: a salesperson sees Leads and the Scoreboard, and no tasks,
projects, tickets or content (docs/departments.md)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.api import leads as leads_api
from helpdesk.api.auth import get_user
from helpdesk.content_team import SALES_EMPLOYEE_ROLE, ensure_role
from helpdesk.test_utils import (
    FakeCRM,
    create_customer,
    enable_leads,
    get_department_walls_as,
    hold_commits,
    make_assignment,
    make_content_post,
    make_project,
    make_sales_employee,
    make_task,
    make_tasky_user,
    make_team,
    make_ticket,
    set_department_wall_as,
)
from helpdesk.work_reminders import notify_users

CUSTOMER = "Sales Wall Traders"
SALES = ("shahana.sales@sales-wall.example", "Shahana Sales")
DEV = ("dev.sales@sales-wall.example", "Arun Dev")
MANAGER = ("manager.sales@sales-wall.example", "Meera Manager")
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class SalesWallCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        self.sales = make_sales_employee(*SALES)
        self.dev = make_tasky_user(*DEV)
        self.manager = make_tasky_user(*MANAGER, roles=("Agent Manager",))
        # left on a project's team, as someone moved to Sales would be
        self.project = make_project(
            "Sales wall rollout",
            members=[(self.sales, "Developer"), (self.dev, "Developer")],
        ).name
        self.task = make_task(self.project, "Configure GST", add_days(nowdate(), 3))
        self.task.db_set("owner", self.sales)

    def as_sales(self, fn):
        frappe.set_user(self.sales)
        try:
            return fn()
        finally:
            frappe.set_user("Administrator")


class TestWhatTheySee(SalesWallCase):
    def test_the_role_is_created_on_migrate_and_opens_leads(self):
        ensure_role()
        self.assertEqual(
            frappe.db.get_value("Role", SALES_EMPLOYEE_ROLE, "home_page"),
            "/helpdesk/leads",
        )

    def test_the_boot_gives_the_sales_screens_only(self):
        enable_leads(teams=("Some Other Sales Team",))
        boot = self.as_sales(get_user)
        self.assertTrue(boot["is_sales_employee"])
        # Leads for every salesperson, whatever the Leads teams say
        self.assertTrue(boot["can_use_leads"])
        self.assertFalse(boot["can_work_tickets"])
        self.assertFalse(boot["can_see_overview"])
        self.assertFalse(boot["in_content_team"])

    def test_managers_are_never_walled(self):
        frappe.get_doc("User", self.manager).add_roles(SALES_EMPLOYEE_ROLE)
        frappe.set_user(self.manager)
        boot = get_user()
        self.assertFalse(boot["is_sales_employee"])
        self.assertIn(self.project, frappe.get_list("Project", pluck="name"))


class TestServerRefusals(SalesWallCase):
    def test_no_projects_or_tasks_even_on_the_team(self):
        make_assignment("Task", self.task.name, self.dev)

        projects, tasks = self.as_sales(
            lambda: (
                frappe.get_list("Project", pluck="name"),
                frappe.get_list("Task", pluck="name"),
            )
        )
        self.assertEqual((projects, tasks), ([], []))
        for doctype, name in (("Project", self.project), ("Task", self.task.name)):
            with self.assertRaises(frappe.PermissionError):
                self.as_sales(
                    lambda d=doctype, n=name: frappe.get_doc(d, n).check_permission(
                        "read"
                    )
                )
        # a plain teammate still sees them
        frappe.set_user(self.dev)
        self.assertIn(self.project, frappe.get_list("Project", pluck="name"))

    def test_they_cant_create_a_project(self):
        def create():
            return frappe.get_doc(
                {"doctype": "Project", "project_name": "A salesperson's project"}
            ).insert()

        with self.assertRaises(frappe.PermissionError):
            self.as_sales(create)

    def test_no_tickets(self):
        ticket = make_ticket(subject="Invoice print is blank", customer=CUSTOMER)
        listed = self.as_sales(
            lambda: frappe.get_list(
                "HD Ticket", filters={"name": ticket.name}, pluck="name"
            )
        )
        self.assertEqual(listed, [])
        self.assertFalse(
            frappe.has_permission("HD Ticket", "read", doc=ticket, user=self.sales)
        )

    def test_no_content_even_on_a_posts_team(self):
        post = make_content_post("Onam offer", CUSTOMER, writer=self.sales)

        posts = self.as_sales(lambda: frappe.get_list("HD Content Post", pluck="name"))
        self.assertNotIn(post.name, posts)
        with self.assertRaises(frappe.PermissionError):
            self.as_sales(
                lambda: frappe.get_doc("HD Content Post", post.name).check_permission(
                    "read"
                )
            )
        # the post saved without giving them its task
        self.assertFalse(
            frappe.db.exists(
                "ToDo",
                {
                    "allocated_to": self.sales,
                    "reference_type": "Task",
                    "status": "Open",
                },
            )
        )

    def test_no_notices_about_work_they_cant_open(self):
        notify_users([self.sales, self.dev], "Task", self.task.name, "Due tomorrow")
        told = frappe.get_all(
            "HD Notification",
            filters={"reference_name": self.task.name, "message": "Due tomorrow"},
            pluck="user_to",
        )
        self.assertEqual(told, [self.dev])


class TestAssignments(SalesWallCase):
    def test_tasks_and_tickets_cant_be_given_to_them(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Sales team.*tasks"):
            make_assignment("Task", self.task.name, self.sales)
        ticket = make_ticket(subject="Login fails", customer=CUSTOMER)
        with self.assertRaisesRegex(frappe.ValidationError, "Sales team.*tickets"):
            make_assignment("HD Ticket", ticket.name, self.sales)
        # anyone else still takes it
        make_assignment("Task", self.task.name, self.dev)

    def test_work_they_held_before_the_wall_can_still_be_closed(self):
        frappe.get_doc("User", self.sales).remove_roles(SALES_EMPLOYEE_ROLE)
        make_assignment("Task", self.task.name, self.sales)
        frappe.get_doc("User", self.sales).add_roles(SALES_EMPLOYEE_ROLE)

        todo = frappe.get_doc(
            "ToDo",
            {"reference_name": self.task.name, "allocated_to": self.sales},
        )
        todo.status = "Closed"
        todo.save(ignore_permissions=True)

    def test_assignment_rules_pass_them_over(self):
        rule = frappe.get_doc(
            {
                "doctype": "Assignment Rule",
                "rule": "Round Robin",
                "users": [{"user": self.sales}, {"user": self.dev}],
            }
        )
        self.assertEqual(rule.get_user(frappe._dict()), self.dev)
        self.assertEqual(len(rule.users), 2)


class TestSettingTheWall(SalesWallCase):
    def test_managers_set_it_from_settings_agents(self):
        frappe.get_doc("User", self.dev).add_roles("ERP Employee")
        set_department_wall_as(self.manager, self.dev, SALES_EMPLOYEE_ROLE)
        self.assertEqual(
            get_department_walls_as(self.manager, self.dev), [SALES_EMPLOYEE_ROLE]
        )
        self.assertNotIn("ERP Employee", frappe.get_roles(self.dev))

        set_department_wall_as(self.manager, self.dev, "")
        self.assertEqual(get_department_walls_as(self.manager, self.dev), [])

    def test_nobody_else_can(self):
        with self.assertRaises(frappe.PermissionError):
            set_department_wall_as(self.sales, self.dev, SALES_EMPLOYEE_ROLE)


class TestLeadsStillWork(SalesWallCase):
    def setUp(self):
        super().setUp()
        # Leads only for a team they aren't in: the role is enough
        make_team("Sales Wall Telecallers", [self.dev])
        enable_leads(teams=("Sales Wall Telecallers",))
        self.crm = FakeCRM()
        self.crm.lead_answers["list_leads"] = {
            "rows": [{"name": "CRM-LEAD-0101", "lead_name": "Asha Traders"}],
            "total": 1,
        }
        self.crm.lead_answers["get_lead"] = {
            "lead": {"name": "CRM-LEAD-0101"},
            "timeline": [],
            "quotations": [],
            "proposals": [],
            "allowed_stages": ["Contacted"],
        }
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_salesperson_works_a_lead_end_to_end(self):
        def work():
            listed = leads_api.list_leads(view="mine")
            lead = leads_api.get_lead("CRM-LEAD-0101")
            leads_api.create_lead({"lead_name": "Bina Exports"})
            leads_api.set_stage("CRM-LEAD-0101", "Contacted", note="Called")
            leads_api.add_note("CRM-LEAD-0101", "Wants a demo")
            return listed, lead

        listed, lead = self.as_sales(work)
        self.assertEqual(listed["total"], 1)
        self.assertEqual(lead["lead"]["name"], "CRM-LEAD-0101")
        methods = [method for method, _post, _params in self.crm.lead_calls]
        self.assertEqual(
            methods, ["list_leads", "get_lead", "create_lead", "set_stage", "add_note"]
        )
        self.assertTrue(
            all(p["acting_user"] == self.sales for _m, _post, p in self.crm.lead_calls)
        )
