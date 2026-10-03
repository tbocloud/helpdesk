# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import auth, sidebar, work
from helpdesk.api.agent_home import agent_home
from helpdesk.test_utils import make_assignment, make_tasky_user, make_ticket
from helpdesk.utils import EMPLOYEE_ROLE, can_see_tickets

EMPLOYEE = ("devi.employee@employee-role.example", "Devi Employee")
SUPPORT = ("sam.support@employee-role.example", "Sam Support")


class TestHelpdeskEmployeeRole(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        from helpdesk.setup.install import add_employee_role

        add_employee_role()
        make_tasky_user(*EMPLOYEE, roles=(EMPLOYEE_ROLE,))
        make_tasky_user(*SUPPORT)
        self.ticket = make_ticket(
            subject="Printer on fire", raised_by="client@x.example"
        )
        make_assignment("HD Ticket", self.ticket.name, EMPLOYEE[0])

    def as_user(self, user, fn, *args, **kwargs):
        frappe.set_user(user[0])
        try:
            return fn(*args, **kwargs)
        finally:
            frappe.set_user("Administrator")

    def test_employee_sees_no_tickets(self):
        # not the setUp ticket: Frappe shares a document with whoever it is assigned to
        self.ticket = make_ticket(subject="Login broken", raised_by="client@x.example")
        self.assertFalse(can_see_tickets(EMPLOYEE[0]))
        self.assertFalse(
            self.as_user(
                EMPLOYEE, frappe.has_permission, "HD Ticket", "read", self.ticket.name
            )
        )
        listed = self.as_user(EMPLOYEE, frappe.get_list, "HD Ticket", pluck="name")
        self.assertNotIn(self.ticket.name, listed)

    def test_employee_ticket_screens_are_closed(self):
        with self.assertRaises(frappe.PermissionError):
            self.as_user(EMPLOYEE, agent_home.get_pending_tickets)
        # even an assigned ticket stays out of My Work and the sidebar counts
        my_work = self.as_user(EMPLOYEE, work.get_my_work)
        self.assertFalse([i for i in my_work["items"] if i["kind"] == "ticket"])
        self.assertEqual(self.as_user(EMPLOYEE, sidebar.get_nav_counts)["tickets"], 0)
        self.assertFalse(self.as_user(EMPLOYEE, auth.get_user)["can_see_tickets"])

    def test_support_agents_and_managers_are_unchanged(self):
        self.assertTrue(can_see_tickets(SUPPORT[0]))
        self.assertTrue(
            self.as_user(
                SUPPORT, frappe.has_permission, "HD Ticket", "read", self.ticket.name
            )
        )
        self.assertTrue(self.as_user(SUPPORT, auth.get_user)["can_see_tickets"])
        frappe.get_doc("User", EMPLOYEE[0]).add_roles("Agent Manager")
        self.assertTrue(can_see_tickets(EMPLOYEE[0]))
