import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk.api.home import get_home
from helpdesk.test_utils import (
    create_customer,
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
)

LEAD = ("lead.home@home-dashboard.example", "Asha Kurian")
DEV = ("dev.home@home-dashboard.example", "Vivek Nair")
CUSTOMER = "Home Dashboard Traders"


class TestHome(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        make_tasky_user(*LEAD)
        make_tasky_user(*DEV)
        self.project = make_project(
            f"{CUSTOMER} - Rollout",
            members=[(LEAD[0], "Developer"), (DEV[0], "Developer")],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])
        self.overdue = make_task(
            self.project, "Import opening stock", add_days(nowdate(), -2)
        ).name
        make_assignment("Task", self.overdue, DEV[0])

    def as_user(self, user):
        frappe.set_user(user[0])
        try:
            return get_home()
        finally:
            frappe.set_user("Administrator")

    def test_lead_sees_the_whole_business(self):
        breached = make_ticket(subject="Invoice totals wrong", customer=CUSTOMER)
        # assignment rules may have picked an agent; this ticket must be unassigned
        frappe.db.set_value(
            "HD Ticket",
            breached.name,
            {
                "resolution_by": add_to_date(now_datetime(), hours=-3),
                "_assign": None,
            },
        )

        home = self.as_user(LEAD)

        company = home["company"]
        self.assertIsNotNone(company)
        self.assertIn(self.overdue, [i["name"] for i in company["attention"]])
        self.assertIn(self.project, [p["name"] for p in company["projects"]])
        project = next(p for p in company["projects"] if p["name"] == self.project)
        self.assertEqual(project["overdue"], 1)
        tickets = company["tickets"]
        self.assertGreaterEqual(tickets["sla_breached"], 1)
        self.assertGreaterEqual(tickets["unassigned"], 1)
        self.assertGreaterEqual(tickets["new_today"], 1)
        self.assertIn(CUSTOMER, [r["customer"] for r in tickets["by_customer"]])
        # a project lead is not an admin
        self.assertIsNone(home["systems"])

    def test_developer_sees_only_their_own_work(self):
        home = self.as_user(DEV)

        self.assertIsNone(home["company"])
        self.assertIsNone(home["systems"])
        self.assertEqual(home["mine"]["counts"]["overdue"], 1)
        self.assertEqual([i["name"] for i in home["mine"]["items"]], [self.overdue])

    def test_admins_also_see_system_health(self):
        home = get_home()

        systems = home["systems"]
        self.assertIsNotNone(systems)
        for key in ("connections", "mailboxes", "teams", "chat", "ai"):
            self.assertIn(key, systems)
