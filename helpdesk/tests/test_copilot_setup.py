# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Phase 30: adding a customer to Copilot from the helpdesk screens. The switches and site cards
change through the documents' own permissions and validation; the checklist says what is missing."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from helpdesk.api import copilot_setup as api
from helpdesk.copilot import setup
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    create_user,
    hold_commits,
    make_copilot_settings,
    make_site_registry,
    make_support_connection,
    make_ticket,
    run_as_user,
)

NEW_CLIENT = {
    "client_capabilities": json.dumps(["hub_api_v1"]),
    "client_version": "1.0.0",
}
APPS = [
    {
        "app": "frappe",
        "repository": "https://github.com/frappe/frappe",
        "branch": "version-15",
        "deployed_commit": "a1b2c3d4e5f6",
    }
]


class SetupCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        # no common Developer rows, so a customer's own people decide the "people" line
        make_copilot_settings(
            enabled=1, default_copilot_level="Diagnose only", copilot_people=[]
        )
        self.owner = create_agent("setup.owner@example.com", "Setup", "Owner").name
        self.agent = create_agent("setup.agent@example.com", "Setup", "Agent").name
        self.customer = create_customer("Setup Co").name
        self.conn = make_support_connection(
            self.customer, site_url="https://setup.example.com"
        ).name

    def states(self, customer=None) -> dict:
        found = setup.customer_setup(customer or self.customer)["checks"]
        return {c["key"]: c["state"] for c in found}

    def card(self, **values):
        return make_site_registry(
            self.customer,
            connection=self.conn,
            site_url="https://setup.example.com",
            **values,
        )


class TestChecklist(SetupCase):
    def test_a_new_customer_has_only_its_connection(self):
        result = setup.customer_setup(self.customer)

        self.assertEqual(
            self.states(),
            {
                "connection": "done",
                "client": "missing",
                "card": "missing",
                "apps": "later",
                "people": "missing",
                "enabled": "missing",
                "press": "later",
            },
        )
        self.assertEqual(result["ready"]["done"], 1)
        self.assertEqual(result["ready"]["of"], 6)
        self.assertIn("New client app", result["ready"]["needs"])

    def test_each_step_turns_its_line_green(self):
        frappe.db.set_value("HDS Support Connection", self.conn, NEW_CLIENT)
        frappe.db.set_value("HD Customer", self.customer, "ticket_owner", self.owner)
        self.card(apps=APPS, last_synced=now_datetime())
        frappe.db.set_value("HD Customer", self.customer, "custom_copilot_enabled", 1)

        result = setup.customer_setup(self.customer)

        self.assertEqual(result["ready"], {"done": 6, "of": 6, "needs": []})
        self.assertEqual(result["work_goes_to"]["developers"][0]["user"], self.owner)
        self.assertEqual(result["work_goes_to"]["developers_from"], "owner")

    def test_a_card_without_apps_asks_for_them(self):
        self.card()
        self.assertEqual(self.states()["apps"], "missing")

    def test_press_details_are_needed_from_the_fix_level(self):
        frappe.db.set_value("HD Customer", self.customer, "custom_copilot_level", "Fix")
        card = self.card()
        self.assertEqual(self.states()["press"], "missing")

        card.db_set(
            {"press_site": "setup.example.com", "press_release_group": "bench-1"}
        )
        self.assertEqual(self.states()["press"], "done")

    def test_a_customer_without_a_connected_site(self):
        bare = create_customer("Setup Bare Co").name
        states = self.states(bare)
        self.assertEqual(states["connection"], "missing")
        self.assertEqual(states["client"], "later")

        make_support_connection(bare, connection_status="Pending")
        self.assertEqual(self.states(bare)["connection"], "missing")


class TestSwitches(SetupCase):
    def test_only_the_three_switches_are_saved(self):
        result = setup.save_switches(
            self.customer, {"enabled": 1, "level": "Explain", "watch": "1"}
        )

        self.assertEqual(
            result["switches"], {"enabled": True, "level": "Explain", "watch": True}
        )
        self.assertEqual(
            frappe.db.get_value(
                "HD Customer",
                self.customer,
                [
                    "custom_copilot_enabled",
                    "custom_copilot_level",
                    "custom_copilot_watch",
                ],
            ),
            (1, "Explain", 1),
        )
        with self.assertRaises(frappe.ValidationError):
            setup.save_switches(self.customer, {"ticket_owner": self.agent})
        with self.assertRaises(frappe.ValidationError):
            setup.save_switches(self.customer, {"level": "Everything"})

    def test_a_blank_level_goes_back_to_the_default(self):
        setup.save_switches(self.customer, {"level": "Fix"})
        result = setup.save_switches(self.customer, {"level": ""})
        self.assertEqual(result["switches"]["level"], "")
        self.assertEqual(result["default_level"], "Diagnose only")

    def test_an_agent_sees_the_tab_but_cannot_change_it(self):
        result = run_as_user(self.agent, lambda: api.customer(self.customer))
        self.assertEqual(
            result["can"], {"switches": False, "add_card": False, "edit_card": False}
        )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                self.agent,
                lambda: api.save_switches(self.customer, json.dumps({"enabled": 1})),
            )
        self.assertFalse(
            frappe.db.get_value("HD Customer", self.customer, "custom_copilot_enabled")
        )

    def test_someone_who_is_not_an_agent_gets_nothing(self):
        outsider = create_user("setup.outsider@example.com").name
        with self.assertRaises(frappe.PermissionError):
            run_as_user(outsider, lambda: api.customer(self.customer))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(outsider, lambda: api.customers())


class TestSiteCards(SetupCase):
    def test_a_card_takes_its_url_from_the_connection_and_can_be_changed(self):
        result = setup.save_site_card(
            {
                "customer_name": self.customer,
                "connection": self.conn,
                "press_site": "  setup.example.com ",
            }
        )

        card = result["cards"][0]
        self.assertEqual(card["environment"], "Production")
        self.assertEqual(card["site_url"], "https://setup.example.com")
        self.assertEqual(card["press_site"], "setup.example.com")

        result = setup.save_site_card(
            {"press_release_group": "bench-0001", "shared_group": 1}, card["name"]
        )
        self.assertEqual(result["cards"][0]["press_release_group"], "bench-0001")
        self.assertTrue(result["cards"][0]["shared_group"])

    def test_a_second_production_card_is_refused(self):
        values = {"customer_name": self.customer, "connection": self.conn}
        setup.save_site_card(values)
        with self.assertRaises(frappe.ValidationError):
            setup.save_site_card(values)
        # another environment is fine
        result = setup.save_site_card({**values, "environment": "UAT"})
        self.assertEqual(len(result["cards"]), 2)

    def test_what_a_card_cannot_take(self):
        other = create_customer("Setup Other Co").name
        theirs = make_support_connection(other, site_url="https://other.example.com")
        with self.assertRaises(frappe.ValidationError):
            setup.save_site_card({"customer_name": self.customer, "apps": []})
        with self.assertRaises(frappe.ValidationError):
            setup.save_site_card(
                {"customer_name": self.customer, "connection": theirs.name}
            )
        with self.assertRaises(frappe.ValidationError):
            setup.save_site_card(
                {"customer_name": self.customer, "environment": "Moon"}
            )
        card = self.card()
        with self.assertRaises(frappe.ValidationError):
            setup.save_site_card({"customer_name": other}, card.name)

    def test_an_agent_cannot_add_a_card(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                self.agent,
                lambda: api.save_site_card(
                    json.dumps(
                        {"customer_name": self.customer, "connection": self.conn}
                    )
                ),
            )
        self.assertFalse(
            frappe.db.exists("HDS Site Registry", {"customer_name": self.customer})
        )


class TestReadingApps(SetupCase):
    def test_an_older_client_gets_a_plain_answer(self):
        card = self.card()
        with self.assertRaises(frappe.ValidationError) as caught:
            setup.read_apps(card.name, "site")
        self.assertIn("older helpdesk_client", str(caught.exception))

    def test_press_needs_the_release_group_first(self):
        card = self.card()
        with self.assertRaises(frappe.ValidationError) as caught:
            setup.read_apps(card.name, "press")
        self.assertIn("release group", str(caught.exception))

    def test_a_new_client_lists_its_apps(self):
        frappe.db.set_value("HDS Support Connection", self.conn, NEW_CLIENT)
        card = self.card()
        with patch(
            "helpdesk.copilot.registry.refresh_from_site",
            return_value={"apps": 1, "drift": []},
        ) as read:
            result = setup.read_apps(card.name, "site")
        read.assert_called_once()
        self.assertEqual(result["result"], {"apps": 1, "drift": []})
        self.assertEqual(result["setup"]["customer"], self.customer)


class TestBoard(SetupCase):
    def test_customers_with_a_connection_or_a_card_with_their_tickets(self):
        card_only = create_customer("Setup Card Co").name
        make_site_registry(card_only)
        nothing = create_customer("Setup Nothing Co").name
        make_ticket(subject="Recent", customer=self.customer)
        frappe.db.set_value("HD Customer", card_only, "custom_copilot_enabled", 1)

        rows = {r["customer"]: r for r in setup.customers()}

        self.assertIn(self.customer, rows)
        self.assertIn(card_only, rows)
        self.assertNotIn(nothing, rows)
        self.assertEqual(rows[self.customer]["tickets"], 1)
        self.assertEqual(rows[self.customer]["sites"], ["https://setup.example.com"])
        self.assertTrue(rows[card_only]["production_card"])

        on = [r["customer"] for r in setup.customers("on")]
        self.assertIn(card_only, on)
        self.assertNotIn(self.customer, on)
        with self.assertRaises(frappe.ValidationError):
            setup.customers("everything")
