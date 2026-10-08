from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import directory
from helpdesk.test_utils import (
    create_agent,
    create_contact,
    create_customer,
    hold_commits,
    make_project,
    make_support_connection,
    make_ticket,
    run_as_user,
)

AGENT = "directory.agent@directory.example"
CUSTOMER = "Directory Traders LLC"
OTHER = "Directory Other Co"
CONTACT_EMAIL = "meera.directory@directory.example"
INVITED_EMAIL = "arun.directory@directory.example"


class TestDirectory(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        create_agent(AGENT)
        self.contact = create_contact("Meera", CONTACT_EMAIL)["contact"]
        self.invited = create_contact("Arun", INVITED_EMAIL, user=False)["contact"]
        create_customer(
            CUSTOMER,
            [{"contact_name": self.contact}, {"contact_name": self.invited}],
        )
        frappe.db.set_value("HD Customer", CUSTOMER, "domain", "directory.example")
        create_customer(OTHER)

    def test_customer_counts(self):
        make_ticket(subject="Open one", customer=CUSTOMER, contact=self.contact)
        make_ticket(subject="Open two", customer=CUSTOMER)
        resolved = make_ticket(subject="Done", customer=CUSTOMER).name
        frappe.db.set_value("HD Ticket", resolved, "status_category", "Resolved")
        for name, status in (
            ("Live", "Open"),
            ("Paused", "On hold"),
            ("Old", "Completed"),
        ):
            # agents count the projects they can see, i.e. the ones they're on
            project = make_project(
                f"{CUSTOMER} {name}", members=[(AGENT, "Developer")]
            ).name
            frappe.db.set_value(
                "Project", project, {"customer": CUSTOMER, "status": status}
            )
        make_support_connection(CUSTOMER, site_url="https://erp.directory.example")

        result = run_as_user(
            AGENT, lambda: directory.get_customer_directory(search="Directory Traders")
        )

        self.assertEqual(result["total"], 1)
        self.assertFalse(result["has_more"])
        row = result["rows"][0]
        self.assertEqual(row["name"], CUSTOMER)
        self.assertEqual(row["open_tickets"], 2)
        self.assertEqual(row["active_projects"], 2)
        self.assertEqual(row["connection"]["status"], "Connected")

    def test_projects_the_agent_cannot_see_are_not_counted(self):
        project = make_project(f"{CUSTOMER} Hidden").name
        frappe.db.set_value("Project", project, "customer", CUSTOMER)

        result = run_as_user(
            AGENT, lambda: directory.get_customer_directory(search="Directory Traders")
        )

        self.assertEqual(result["rows"][0]["name"], CUSTOMER)
        self.assertEqual(result["rows"][0]["active_projects"], 0)

    def test_customer_search_matches_domain(self):
        result = run_as_user(
            AGENT, lambda: directory.get_customer_directory(search="directory.example")
        )

        self.assertEqual([r["name"] for r in result["rows"]], [CUSTOMER])

    def test_customer_without_work(self):
        result = run_as_user(
            AGENT, lambda: directory.get_customer_directory(search=OTHER)
        )

        row = result["rows"][0]
        self.assertEqual(row["open_tickets"], 0)
        self.assertEqual(row["active_projects"], 0)
        self.assertIsNone(row["connection"])

    def test_contact_rows(self):
        make_ticket(subject="Meera's", customer=CUSTOMER, contact=self.contact)
        frappe.get_doc(
            {
                "doctype": "User Invitation",
                "email": INVITED_EMAIL,
                "app_name": "helpdesk",
                "redirect_to_path": "/helpdesk",
                "roles": [{"role": "HD Customer"}],
                "customer": CUSTOMER,
                "contact": self.invited,
            }
        ).insert(ignore_permissions=True)

        result = run_as_user(
            AGENT, lambda: directory.get_contact_directory(search="directory.example")
        )

        # creating the users may add contacts of their own for the same emails,
        # so look up the two this test made rather than counting rows
        rows = {r["name"]: r for r in result["rows"]}
        self.assertIn(self.contact, rows)
        self.assertIn(self.invited, rows)
        self.assertEqual(rows[self.contact]["customers"], [CUSTOMER])
        self.assertEqual(rows[self.contact]["open_tickets"], 1)
        self.assertEqual(rows[self.contact]["portal"], "active")
        self.assertEqual(rows[self.invited]["portal"], "invited")
        self.assertEqual(rows[self.invited]["open_tickets"], 0)

    def test_paging(self):
        page_length = patch.object(directory, "PAGE_LENGTH", 1)
        page_length.start()
        self.addCleanup(page_length.stop)

        first = run_as_user(
            AGENT, lambda: directory.get_customer_directory(search="Directory")
        )
        second = run_as_user(
            AGENT, lambda: directory.get_customer_directory(search="Directory", start=1)
        )

        self.assertEqual(first["total"], 2)
        self.assertEqual(len(first["rows"]), 1)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertNotEqual(first["rows"][0]["name"], second["rows"][0]["name"])

    def test_unknown_sort(self):
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                AGENT, lambda: directory.get_customer_directory(sort="modified; drop")
            )

    def test_agents_only(self):
        frappe.set_user(CONTACT_EMAIL)
        with self.assertRaises(frappe.PermissionError):
            directory.get_contact_directory()
