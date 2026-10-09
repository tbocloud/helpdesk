# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A file attached to a project, the folder it sits in, and who on the project it is for.

The File (attached to the Project) holds the content and decides who may open
it; this record only adds the folder and the "For" list. "For" is a label plus a
notification, not a restriction: everyone who can read the project sees every
file. See docs/project-files.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_fullname

from helpdesk.tasky.permissions import get_project_team


class ProjectShare:
    """The "For" list that project files and folders share (HD Project File User rows)."""

    def validate_for_users(self):
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
        return [row.user for row in self.for_users]

    def new_assignees(self) -> list[str]:
        """People added to "For" by this save, except the person saving."""
        before = self.get_doc_before_save()
        previous = set(before.assignees()) if before else set()
        return [
            u
            for u in self.assignees()
            if u not in previous and u != frappe.session.user
        ]

    def project_title(self) -> str:
        return (
            frappe.db.get_value("Project", self.project, "project_name") or self.project
        )


class HDProjectFile(ProjectShare, Document):
    def validate(self):
        self.validate_file()
        self.validate_folder()
        self.validate_for_users()

    def on_update(self):
        self.notify_new_assignees()

    def validate_file(self):
        attached = frappe.db.get_value(
            "File", self.file, ["attached_to_doctype", "attached_to_name"]
        )
        if not attached or tuple(attached) != ("Project", self.project):
            frappe.throw(
                _("This file isn't attached to project {0}.").format(self.project)
            )

    def validate_folder(self):
        if not self.folder:
            self.folder = None
            return
        if frappe.db.get_value("HD Project Folder", self.folder, "project") != (
            self.project
        ):
            frappe.throw(
                _("That folder isn't part of project {0}.").format(self.project),
                frappe.PermissionError,
            )

    def notify_new_assignees(self):
        from helpdesk.work_reminders import notify_users

        new = self.new_assignees()
        if not new:
            return
        notify_users(
            new,
            self.doctype,
            self.name,
            _("{0} shared {1} with you in {2}").format(
                get_fullname(frappe.session.user),
                self.file_name,
                self.project_title(),
            ),
            link=f"/projects/{self.project}/files",
        )
