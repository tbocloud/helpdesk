# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A file attached to a project, and who on the project it is for.

The File (attached to the Project) holds the content and decides who may open
it; this record only adds the "For" list. "For" is a label plus a notification,
not a restriction: everyone who can read the project sees every file.
See docs/project-files.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_fullname

from helpdesk.tasky.permissions import get_project_team


class HDProjectFile(Document):
    def validate(self):
        """Check the file is really attached to the project and the "for" list is valid."""
        self.validate_file()
        self.validate_for_users()

    def on_update(self):
        """Tell anyone newly added to the "for" list."""
        self.notify_new_assignees()

    def validate_file(self):
        """Refuse to save unless `file` is attached to this project."""
        attached = frappe.db.get_value(
            "File", self.file, ["attached_to_doctype", "attached_to_name"]
        )
        if not attached or tuple(attached) != ("Project", self.project):
            frappe.throw(
                _("This file isn't attached to project {0}.").format(self.project)
            )

    def validate_for_users(self):
        """Drop blank and duplicate rows from `for_users`, and refuse anyone not on the project team."""
        team = set(get_project_team(self.project))
        seen = set()
        rows = []
        for row in self.for_users:
            if not row.user or row.user in seen:
                continue
            if row.user not in team:
                frappe.throw(
                    _(
                        "{0} isn't on this project. Pick people from the project team."
                    ).format(row.user)
                )
            seen.add(row.user)
            rows.append(row)
        self.for_users = rows

    def assignees(self) -> list[str]:
        """The users this file is for."""
        return [row.user for row in self.for_users]

    def notify_new_assignees(self):
        """Notify whoever was just added to `for_users`, not people already there."""
        from helpdesk.work_reminders import notify_users

        before = self.get_doc_before_save()
        previous = set(before.assignees()) if before else set()
        new = [
            u
            for u in self.assignees()
            if u not in previous and u != frappe.session.user
        ]
        if not new:
            return
        project_name = (
            frappe.db.get_value("Project", self.project, "project_name") or self.project
        )
        notify_users(
            new,
            self.doctype,
            self.name,
            _("{0} shared {1} with you in {2}").format(
                get_fullname(frappe.session.user), self.file_name, project_name
            ),
            link=f"/projects/{self.project}/files",
        )
