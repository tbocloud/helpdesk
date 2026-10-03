import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import make_ticket


class TestTicketDelete(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)

    def test_ai_cost_records_do_not_block_deleting_a_ticket(self):
        ticket = make_ticket(subject="You have 25 new notifications")
        usage = frappe.get_doc(
            {
                "doctype": "HDS AI Usage Log",
                "ticket": ticket.name,
                "model": "test-model",
                "input_tokens": 1200,
                "output_tokens": 800,
            }
        ).insert(ignore_permissions=True)

        frappe.delete_doc("HD Ticket", ticket.name, ignore_permissions=True)

        self.assertFalse(frappe.db.exists("HD Ticket", ticket.name))
        # the cost stays on record
        self.assertEqual(
            frappe.db.get_value("HDS AI Usage Log", usage.name, "input_tokens"), 1200
        )
