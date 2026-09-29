from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk import api
from helpdesk.test_utils import create_customer, make_support_connection

CUSTOMER = "Harbour Foods LLC"
SITE = "https://erp.harbourfoods.example"


class TestClientPairing(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        self.conn = make_support_connection(
            CUSTOMER, site_url=SITE, connection_status="Pending"
        ).name

    def pair(self, code, site_url=SITE):
        frappe.set_user("Guest")
        try:
            return api.pair_client(
                code=code,
                site_url=site_url,
                api_key="key123",
                api_secret="secret456",
                support_user="support@teambackoffice.com",
            )
        finally:
            frappe.set_user("Administrator")

    def registered(self):
        return patch.object(
            api,
            "_call_client",
            return_value={
                "site": "erp.harbourfoods.example",
                "support_user": "support@teambackoffice.com",
            },
        )

    def test_code_connects_the_site_without_copying_keys(self):
        code = api.create_pairing_code(self.conn)["code"]
        with self.registered() as call:
            result = self.pair(code.lower().replace("-", " "))

        self.assertEqual(result["status"], "connected")
        conn = frappe.get_doc("HDS Support Connection", self.conn)
        self.assertEqual(conn.connection_status, "Connected")
        self.assertEqual(conn.api_key, "key123")
        self.assertEqual(conn.get_password("api_secret"), "secret456")
        self.assertEqual(conn.support_user, "support@teambackoffice.com")
        self.assertFalse(conn.pairing_code_hash)
        self.assertTrue(call.call_args.args[2].endswith("api.register_connection"))

    def test_code_works_once(self):
        code = api.create_pairing_code(self.conn)["code"]
        with self.registered():
            self.pair(code)
            with self.assertRaises(frappe.AuthenticationError):
                self.pair(code)

    def test_expired_or_wrong_code_is_refused(self):
        code = api.create_pairing_code(self.conn)["code"]
        frappe.db.set_value(
            "HDS Support Connection",
            self.conn,
            "pairing_code_expires",
            add_to_date(now_datetime(), hours=-1),
        )
        with self.registered(), self.assertRaises(frappe.AuthenticationError):
            self.pair(code)
        with self.registered(), self.assertRaises(frappe.AuthenticationError):
            self.pair("AAAA-BBBB-CC")

    def test_code_only_works_for_its_own_site(self):
        code = api.create_pairing_code(self.conn)["code"]
        with self.registered(), self.assertRaises(frappe.AuthenticationError):
            self.pair(code, site_url="https://attacker.example")
        self.assertNotEqual(
            frappe.db.get_value("HDS Support Connection", self.conn, "api_key"),
            "key123",
        )

    def test_only_system_managers_create_codes(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            api.create_pairing_code(self.conn)
