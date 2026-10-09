# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Support connections, AI sessions and investigations stay within what the agent may see."""

from unittest.mock import patch

import frappe
from frappe.cache_manager import clear_doctype_map
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import support_hub
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    hold_commits,
    make_ai_support_session,
    make_support_connection,
    make_team,
    make_ticket,
    restrict_tickets_to_teams,
)

AGENT = "hub-perm-agent@example.com"


class HubPermissionCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(clear_doctype_map, "Assignment Rule", "HD Ticket")
        create_agent(AGENT)
        self.ours = create_customer("Hub Perm Ours").name
        self.theirs = create_customer("Hub Perm Theirs").name
        self.our_conn = make_support_connection(self.ours, site_url="https://ours.example.com").name
        self.their_conn = make_support_connection(self.theirs, site_url="https://theirs.example.com").name
        self.ticket = make_ticket(subject="Our ticket", customer=self.ours).name

    def restrict(self, ticket):
        team = make_team("Hub Perm Team", members=[create_agent("hub-perm-member@example.com").name])
        frappe.db.set_value("HD Ticket", ticket, "agent_group", team.name)
        restrict_tickets_to_teams(self)


class TestConnections(HubPermissionCase):
    def test_an_agent_sees_the_connections_of_customers_they_serve(self):
        frappe.set_user(AGENT)
        names = {c.name for c in support_hub.get_connections()}
        self.assertIn(self.our_conn, names)
        self.assertNotIn(self.their_conn, names)  # no ticket of theirs the agent can read

    def test_a_manager_sees_all(self):
        names = {c.name for c in support_hub.get_connections()}
        self.assertTrue({self.our_conn, self.their_conn} <= names)


class TestSessionsAndInvestigations(HubPermissionCase):
    def test_a_session_on_a_ticket_the_agent_cannot_read_is_refused(self):
        session = make_ai_support_session(self.ticket, self.our_conn).name
        self.restrict(self.ticket)
        frappe.set_user(AGENT)
        with self.assertRaises(frappe.PermissionError):
            support_hub.get_session_detail(session)

    @patch("helpdesk.session_manager.start_investigation", return_value="SESSION-1")
    def test_an_investigation_runs_only_on_the_tickets_own_customer_site(self, start):
        frappe.set_user(AGENT)
        with self.assertRaises(frappe.PermissionError):
            support_hub.start_investigation(self.ticket, self.their_conn)
        start.assert_not_called()
        self.assertEqual(support_hub.start_investigation(self.ticket, self.our_conn)["session"], "SESSION-1")

    @patch("helpdesk.session_manager.start_investigation", return_value="SESSION-1")
    def test_an_investigation_needs_a_readable_ticket(self, start):
        self.restrict(self.ticket)
        frappe.set_user(AGENT)
        with self.assertRaises(frappe.PermissionError):
            support_hub.start_investigation(self.ticket, self.our_conn)
        start.assert_not_called()
