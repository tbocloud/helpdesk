# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

WAITING_ON_TASK = "Waiting on Task"


class Task(Document):
    def on_update(self):
        if self.status == "Completed" and self.has_value_changed("status"):
            self.notify_ticket_task_completed()

    def notify_ticket_task_completed(self):
        """Hand the linked support ticket back to the agent once the work is done."""
        if not self.hd_ticket or not frappe.db.exists("HD Ticket", self.hd_ticket):
            return
        ticket = frappe.get_doc("HD Ticket", self.hd_ticket)
        if ticket.status == WAITING_ON_TASK:
            ticket.status = "Open"
            ticket.save(ignore_permissions=True)
        done_by = (
            frappe.db.get_value("User", frappe.session.user, "full_name")
            or frappe.session.user
        )
        comment = frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": ticket.name,
                "content": _(
                    "Task {0} ({1}) was completed by {2}. Reply to the customer."
                ).format(
                    frappe.bold(self.name),
                    frappe.utils.escape_html(self.subject or ""),
                    done_by,
                ),
                "commented_by": frappe.session.user,
            }
        )
        comment.insert(ignore_permissions=True)
