# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Site Registry: which site a ticket belongs to."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.copilot import refresh_site_card_from_press
from helpdesk.copilot.registry import apps_for, refresh_from_site, registry_for_ticket
from helpdesk.test_utils import (
    FakePress,
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
            apps=[
                {
                    "app": "acme-live",
                    "repository": "teambackoffice/acme-live",
                    "branch": "main",
                }
            ],
            site_url="https://erp.acme-live.example/",
        )
        self.assertEqual(reg.site_url, "https://erp.acme-live.example")
        self.assertEqual(apps_for(reg)[0]["repository"], "teambackoffice/acme-live")
        self.assertEqual(apps_for(reg)[0]["drift_status"], "Unknown")


class TestRefreshFromSite(FrappeTestCase):
    """The site card lists every app the site runs, read through its connection."""

    def setUp(self):
        hold_commits(self)
        customer = create_customer("Registry Refresh Co").name
        self.registry = make_site_registry(
            customer,
            connection=make_support_connection(customer).name,
            apps=[
                {
                    "app": "tax_app",
                    "repository": "https://github.com/acme/tax_app",
                    "branch": "old",
                }
            ],
        )

    def reported(self, apps):
        client = patch("helpdesk.mcp_client.MCPClient")
        mocked = client.start()
        self.addCleanup(client.stop)
        mocked.return_value.call_tool.return_value = {
            "content": [{"type": "text", "text": json.dumps(apps)}]
        }

    def test_every_app_with_its_repository_branch_and_commit(self):
        self.reported(
            [
                {
                    "app": "erpnext",
                    "branch": "version-15",
                    "commit": "e" * 40,
                    "remotes": {"upstream": "https://github.com/frappe/erpnext"},
                    "dirty": False,
                },
                # a Press bench without .git: commit and branch only
                {"app": "tax_app", "branch": "acme-live", "commit": "k" * 40},
                {
                    "app": "billing_app",
                    "branch": "version-15.01",
                    "commit": "s" * 40,
                    "remotes": {"origin": "https://github.com/acme/billing-app"},
                    "dirty": True,
                },
            ]
        )

        found = refresh_from_site(self.registry)

        rows = {
            row.app: row
            for row in frappe.get_doc("HDS Site Registry", self.registry.name).apps
        }
        self.assertEqual(found, {"apps": 3, "drift": ["billing_app"]})
        self.assertEqual(
            rows["erpnext"].repository, "https://github.com/frappe/erpnext"
        )
        self.assertEqual(
            (rows["tax_app"].repository, rows["tax_app"].branch),
            ("https://github.com/acme/tax_app", "acme-live"),
        )
        self.assertEqual(rows["billing_app"].drift_status, "Drift")
        self.assertEqual(rows["erpnext"].drift_status, "In sync")

    def test_a_site_that_reports_nothing_changes_nothing(self):
        self.reported([])
        with self.assertRaises(frappe.ValidationError):
            refresh_from_site(self.registry)
        self.assertEqual(
            [
                row.branch
                for row in frappe.get_doc("HDS Site Registry", self.registry.name).apps
            ],
            ["old"],
        )


class TestRefreshFromPress(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.customer = create_customer("Registry Co").name
        self.press = FakePress(sites=("site1.example.com", "other.example.com"))
        self.press.install(self)
        self.press.apps.append(
            {
                "app": "erpnext",
                "source": "SRC-2",
                "hash": "e" * 40,
                "next_hash": "e" * 40,
            }
        )

    def test_presss_commits_and_the_other_sites_on_the_bench(self):
        card = make_site_registry(
            self.customer,
            press_site="site1.example.com",
            press_release_group="bench-1",
            apps=[
                {
                    "app": "demo_app",
                    "repository": "tbocloud/demo_app",
                    "branch": "main",
                    "deployed_commit": "c" * 40,
                }
            ],
        )

        found = refresh_site_card_from_press(card.name)

        card.reload()
        rows = {row.app: row for row in card.apps}
        self.assertEqual(found["drift"], ["demo_app"])
        # the commit the site itself reported stays; Press's differs, so it is drift
        self.assertEqual(
            (rows["demo_app"].deployed_commit, rows["demo_app"].drift_status),
            ("c" * 40, "Drift"),
        )
        self.assertEqual(
            (rows["erpnext"].deployed_commit, rows["erpnext"].drift_status),
            ("e" * 40, "In sync"),
        )
        self.assertEqual(card.group_sites, "other.example.com")
        self.assertTrue(card.last_synced)

    def test_a_card_without_a_bench_says_so(self):
        card = make_site_registry(self.customer)
        with self.assertRaises(frappe.ValidationError):
            refresh_site_card_from_press(card.name)
