import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import sales_team as api
from helpdesk.sales_team import SalesTeamForbiddenError
from helpdesk.test_utils import (
    hold_commits,
    make_presales_executive,
    make_sales_head,
    make_tasky_user,
)

HEAD = "head@salesteam.example"
PERSON = "presales@salesteam.example"
NEWCOMER = "newcomer@salesteam.example"
ADMIN = "admin@salesteam.example"


class TestSalesTeam(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_sales_head(HEAD, "Hana Head")
        make_presales_executive(PERSON, "Priya Presales")
        make_tasky_user(NEWCOMER, "Nina Newcomer", roles=("ERP Employee",))
        make_tasky_user(ADMIN, "Adam Admin", roles=("Sales User", "Agent Manager"))
        frappe.set_user(HEAD)

    def members(self) -> dict[str, list[str]]:
        return {m["user"]: m["roles"] for m in api.get_team()["members"]}

    def test_a_sales_head_sees_the_team_and_who_can_join(self):
        team = api.get_team()
        self.assertEqual(self.members()[PERSON], ["Presales Executive"])
        self.assertNotIn(HEAD, self.members())
        joinable = [c["user"] for c in team["candidates"]]
        self.assertIn(NEWCOMER, joinable)
        self.assertNotIn(PERSON, joinable)

    def test_adding_as_sales_employee_replaces_the_other_wall(self):
        api.set_member_roles(NEWCOMER, ["Sales Employee", "Sales User"])
        self.assertEqual(self.members()[NEWCOMER], ["Sales User", "Sales Employee"])
        roles = frappe.get_roles(NEWCOMER)
        self.assertNotIn("ERP Employee", roles)
        self.assertIn("Agent", roles)

    def test_removing_takes_the_team_roles_and_keeps_the_account(self):
        api.set_member_roles(PERSON, [])
        self.assertNotIn(PERSON, self.members())
        self.assertTrue(frappe.db.get_value("User", PERSON, "enabled"))
        self.assertIn("Agent", frappe.get_roles(PERSON))

    def test_only_team_roles_can_be_given(self):
        with self.assertRaises(frappe.ValidationError):
            api.set_member_roles(PERSON, ["System Manager"])

    def test_an_inactive_agent_cannot_join(self):
        frappe.db.set_value("HD Agent", NEWCOMER, "is_active", 0)
        with self.assertRaises(frappe.ValidationError):
            api.set_member_roles(NEWCOMER, ["Sales User"])

    def test_a_sales_head_cannot_change_an_admin(self):
        with self.assertRaises(SalesTeamForbiddenError):
            api.set_member_roles(ADMIN, [])

    def test_only_a_sales_head_manages_the_team(self):
        frappe.set_user(PERSON)
        with self.assertRaises(SalesTeamForbiddenError):
            api.get_team()
        with self.assertRaises(SalesTeamForbiddenError):
            api.set_member_roles(NEWCOMER, ["Sales User"])
