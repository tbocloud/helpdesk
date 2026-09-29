import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.patches.v16_0_2 import rename_qcs_connections
from helpdesk.test_utils import create_customer, make_support_connection


class TestRenameQcsConnections(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        create_customer("Galom Test Trading")

    def make(self, name, status):
        conn = make_support_connection("Galom Test Trading", connection_status=status)
        frappe.rename_doc("HDS Support Connection", conn.name, name, force=True)
        return name

    def test_pending_connection_becomes_tbo_and_series_moves_on(self):
        self.make("QCS-CONN-2031-00007", "Pending")
        connected = self.make("QCS-CONN-2031-00008", "Connected")

        rename_qcs_connections.execute()

        self.assertTrue(
            frappe.db.exists("HDS Support Connection", "TBO-CONN-2031-00007")
        )
        self.assertTrue(frappe.db.exists("HDS Support Connection", connected))
        self.assertEqual(frappe.db.get_value("Series", "TBO-CONN-2031-", "current"), 7)
