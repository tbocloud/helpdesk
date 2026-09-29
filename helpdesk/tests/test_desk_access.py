from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.desk_access import redirect_desk_to_helpdesk
from helpdesk.test_utils import make_tasky_user

AGENT = ("desk.agent@desk-access.example", "Desk Agent")
MANAGER = ("desk.admin@desk-access.example", "Desk Admin")


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
