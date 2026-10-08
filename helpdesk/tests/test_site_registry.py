# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Site Registry: which site a ticket belongs to."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot.registry import apps_for, registry_for_ticket
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_site_registry,
    make_support_connection,
    make_ticket,
)


class TestSiteRegistry(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.customer = create_customer("Registry Co").name
        self.conn = make_support_connection(self.customer).name

    def test_the_ticket_connection_wins_over_the_customer_row(self):
        make_site_registry(self.customer)
        by_conn = make_site_registry(self.customer, connection=self.conn)
        ticket = make_ticket(subject="Registry", customer=self.customer)
        ticket.db_set("custom_qcs_connection", self.conn)
        self.assertEqual(registry_for_ticket(ticket.name).name, by_conn.name)

    def test_falls_back_to_the_customer_production_site(self):
        make_site_registry(self.customer, environment="UAT")
        prod = make_site_registry(self.customer)
        ticket = make_ticket(subject="Registry", customer=self.customer)
        self.assertEqual(registry_for_ticket(ticket.name).name, prod.name)

    def test_none_when_the_customer_has_no_site(self):
        ticket = make_ticket(subject="Registry", customer=self.customer)
        self.assertIsNone(registry_for_ticket(ticket.name))

    def test_one_production_site_per_customer_and_connection(self):
        make_site_registry(self.customer, connection=self.conn)
        with self.assertRaises(frappe.ValidationError):
            make_site_registry(self.customer, connection=self.conn)
        # a second environment is fine
        make_site_registry(self.customer, connection=self.conn, environment="UAT")

    def test_apps_are_handed_over_as_plain_dicts(self):
        reg = make_site_registry(
            self.customer,
            apps=[{"app": "hydrotech", "repository": "teambackoffice/hydrotech", "branch": "main"}],
            site_url="https://erp.hydrotech.example/",
        )
        self.assertEqual(reg.site_url, "https://erp.hydrotech.example")
        self.assertEqual(apps_for(reg)[0]["repository"], "teambackoffice/hydrotech")
        self.assertEqual(apps_for(reg)[0]["drift_status"], "Unknown")
