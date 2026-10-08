# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""A task made from a ticket pauses the ticket by default, but can leave it running."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.work import WAITING_ON_TASK, create_task_from_ticket
from helpdesk.test_utils import hold_commits, make_project, make_status, make_ticket


class TestTaskFromTicketPause(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        make_status(WAITING_ON_TASK, category="Paused")
        self.project = make_project("Pause Test Project").name

    def test_the_ticket_waits_by_default(self):
        ticket = make_ticket(subject="Needs work")
        result = create_task_from_ticket(ticket.name, self.project)
        self.assertEqual(result["ticket_status"], WAITING_ON_TASK)
        self.assertEqual(frappe.db.get_value("Task", result["task"]["name"], "hd_ticket"), ticket.name)

    def test_the_ticket_keeps_running_when_asked(self):
        ticket = make_ticket(subject="Copilot run")
        before = ticket.status
        result = create_task_from_ticket(ticket.name, self.project, pause_ticket=False)
        self.assertEqual(result["ticket_status"], before)
        self.assertEqual(frappe.db.get_value("HD Ticket", ticket.name, "status"), before)
