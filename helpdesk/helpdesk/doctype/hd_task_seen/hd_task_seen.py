# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""When a person last opened a task; written by helpdesk.tasky.new_assignments."""

import frappe
from frappe.model.document import Document


class HDTaskSeen(Document):
    pass


def on_doctype_update():
    frappe.db.add_unique(
        "HD Task Seen", ["user", "task"], constraint_name="unique_user_task"
    )
