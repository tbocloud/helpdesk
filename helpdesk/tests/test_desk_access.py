from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.desk_access import redirect_desk_to_helpdesk
from helpdesk.test_utils import create_user, make_tasky_user
from helpdesk.utils import is_agent

AGENT = ("desk.agent@desk-access.example", "Desk Agent")
MANAGER = ("desk.admin@desk-access.example", "Desk Admin")
OUTSIDER = "desk.outsider@desk-access.example"


class TestDeskAccess(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*AGENT)
        make_tasky_user(*MANAGER, roles=("System Manager",))
        previous = getattr(frappe.local, "request", None)
        self.addCleanup(setattr, frappe.local, "request", previous)
        frappe.flags.redirect_location = None

    def visit(self, user, path):
        frappe.local.request = SimpleNamespace(path=path)
        frappe.set_user(user)
        redirect_desk_to_helpdesk(frappe._dict())

    def test_agents_are_sent_to_helpdesk(self):
        for path in ("/app", "/app/hd-ticket", "/app/hds-hub-settings"):
            with self.assertRaises(frappe.Redirect) as caught:
                self.visit(AGENT[0], path)
            self.assertEqual(caught.exception.http_status_code, 302)
            self.assertEqual(frappe.flags.redirect_location, "/helpdesk")

    def test_system_managers_and_administrator_keep_desk(self):
        self.visit(MANAGER[0], "/app/hds-hub-settings")
        self.visit("Administrator", "/app")

    def test_other_pages_are_untouched(self):
        for path in ("/helpdesk/tickets", "/api/method/ping", "/application", "/login"):
            self.visit(AGENT[0], path)


class TestIsAgent(FrappeTestCase):
    """is_agent(user) answers for `user`, not for whoever is signed in."""

    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*AGENT)
        create_user(OUTSIDER)

    def test_answers_for_the_given_user(self):
        # signed in as Administrator, another user is not an admin by association
        frappe.set_user("Administrator")
        self.assertTrue(is_agent(AGENT[0]))
        self.assertFalse(is_agent(OUTSIDER))
        # signed in as a non-admin agent, Administrator still counts
        frappe.set_user(AGENT[0])
        self.assertTrue(is_agent("Administrator"))
        self.assertFalse(is_agent(OUTSIDER))
