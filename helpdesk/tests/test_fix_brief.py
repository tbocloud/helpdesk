import json

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.fix_brief import get_fix_brief
from helpdesk.test_utils import create_user, make_ticket, run_as_user

TRIAGE = {
    "category": "Data",
    "priority": "Medium",
    "complexity": "Dev",
    "summary": "The customer reports duplicate sales invoices.",
    "likely_cause": "A custom script may submit the invoice twice.",
    "steps_to_reproduce": [
        "Open the Sales Invoice list",
        "Filter by customer FRET INTERIORS",
    ],
    "key_doctypes": ["Sales Invoice"],
    "investigation_steps": ["Check the naming series"],
}


class TestFixBrief(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)

    def test_brief_carries_the_report_steps_and_triage(self):
        ticket = make_ticket(
            subject="Double entry bills",
            description="<p>Some bills are entered twice.</p>",
        )
        ticket.db_set("custom_triage_data", json.dumps(TRIAGE))

        brief = get_fix_brief(ticket.name)

        markdown = brief["markdown"]
        self.assertEqual(brief["filename"], f"ticket-{ticket.name}-fix-brief.md")
        self.assertIn(
            f"# Fix brief: ticket #{ticket.name}: Double entry bills", markdown
        )
        self.assertIn("## Instructions for the AI agent", markdown)
        self.assertIn("Never change the customer's production site", markdown)
        self.assertIn("> Some bills are entered twice.", markdown)
        self.assertIn("1. Open the Sales Invoice list", markdown)
        self.assertIn("2. Filter by customer FRET INTERIORS", markdown)
        self.assertIn("**Likely cause:** A custom script", markdown)
        self.assertIn(f"Refs ticket #{ticket.name}", markdown)

    def test_a_bare_ticket_still_gets_a_usable_brief(self):
        ticket = make_ticket(subject="Printer issue", description="")

        markdown = get_fix_brief(ticket.name)["markdown"]

        self.assertIn("## Instructions for the AI agent", markdown)
        self.assertIn("## Done when", markdown)
        self.assertNotIn("## Steps to reproduce", markdown)
        self.assertNotIn("## AI triage", markdown)

    def test_only_agents_get_a_brief(self):
        ticket = make_ticket(subject="Printer issue")
        outsider = create_user("fix-brief-outsider@example.com").name
        with self.assertRaises(frappe.PermissionError):
            run_as_user(outsider, lambda: get_fix_brief(ticket.name))


class TestBriefTaskReference(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)

    def test_brief_names_the_ticket_task_so_a_pull_request_links(self):
        from helpdesk.test_utils import make_project, make_task

        ticket = make_ticket(subject="Report shows wrong totals")
        project = make_project("Brief Reference Project").name
        task = make_task(project, "Fix the totals", hd_ticket=ticket.name)

        markdown = get_fix_brief(ticket.name)["markdown"]

        self.assertIn(f"Closes {task.name}", markdown)
        self.assertNotIn("Refs ticket #", markdown)

