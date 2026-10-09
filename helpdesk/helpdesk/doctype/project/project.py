# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from helpdesk.tasky.permissions import hidden_departments


class Project(Document):
    def validate(self):
        self.validate_dates()
        self.validate_department()

    def on_trash(self):
        self.delete_file_folders()

    def delete_file_folders(self):
        from helpdesk.helpdesk.doctype.hd_project_folder.hd_project_folder import (
            FolderTree,
        )

        # deepest first, so no folder moves its subfolders up on the way out;
        # the files themselves go with the project's attachments
        for folder in reversed(FolderTree(self.name).order()):
            frappe.delete_doc("HD Project Folder", folder, ignore_permissions=True)

    def validate_dates(self):
        if (
            self.expected_start_date
            and self.expected_end_date
            and getdate(self.expected_end_date) < getdate(self.expected_start_date)
        ):
            frappe.throw(_("The end date can't be before the start date."))

    def validate_department(self):
        # a project may keep a department that was deactivated later, but not move into one
        department = self.get("custom_department")
        if not department or not self.has_value_changed("custom_department"):
            return
        # nobody puts a project where their own team can't see it (they'd lose it)
        if department in hidden_departments():
            frappe.throw(
                _("You can't put a project in the {0} department.").format(department),
                frappe.PermissionError,
            )
        if not frappe.db.get_value("HD Department", department, "is_active"):
            frappe.throw(
                _("{0} is no longer an active department. Pick another one.").format(
                    department
                )
            )
