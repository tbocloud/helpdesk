# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HDPullRequest(Document):
    def validate(self):
        self.validate_unique_link()

    def validate_unique_link(self):
        """One row per PR and task; the database index backs this up for concurrent deliveries."""
        duplicate = frappe.db.exists(
            "HD Pull Request",
            {
                "repo": self.repo,
                "number": self.number,
                "task": self.task,
                "name": ("!=", self.name),
            },
        )
        if duplicate:
            frappe.throw(
                _("{0}#{1} is already linked to {2}.").format(
                    self.repo, self.number, self.task
                ),
                frappe.DuplicateEntryError,
            )


def on_doctype_update():
    frappe.db.add_unique(
        "HD Pull Request",
        ["repo", "number", "task"],
        constraint_name="unique_repo_number_task",
    )
