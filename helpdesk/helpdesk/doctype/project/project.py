# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from helpdesk.divisions import active_division, can_see_division, check_division_for
from helpdesk.tasky.permissions import hidden_departments

# set by Create project on the lead's documents strip (docs/proposals.md)
PLAN_LINK = (
    "custom_crm_lead",
    "custom_crm_plan",
    "custom_crm_proposal",
    "custom_crm_acting_user",
)


class Project(Document):
    def before_insert(self):
        self.set_default_division()

    def validate(self):
        self.validate_dates()
        self.validate_department()
        self.validate_division()
        self.protect_plan_link()

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

    def protect_plan_link(self):
        """The lead, plan, proposal and maker are written only by Create project
        (helpdesk.api.proposals), never by a save: the hub asks the ERP site about
        the plan as that maker."""
        before = None if self.is_new() else self.get_doc_before_save()
        for field in PLAN_LINK:
            # an unset link reads as None or "" depending on where the doc came from
            if (self.get(field) or None) != (
                (before.get(field) if before else None) or None
            ):
                frappe.throw(
                    _("The project's plan link is set only by Create project."),
                    frappe.PermissionError,
                )

    def set_default_division(self):
        if not self.division:
            self.division = active_division()

    def validate_division(self):
        """Nobody moves a project into a division they aren't in (they'd lose it), and its
        lead and members are the division's people (docs/divisions.md)."""
        if not self.division:
            return
        if self.has_value_changed("division") and not can_see_division(self.division):
            frappe.throw(
                _("You aren't a member of the {0} division.").format(self.division),
                frappe.PermissionError,
            )
        if self.has_value_changed("division") or self.has_value_changed("project_lead"):
            check_division_for(self.division, [self.project_lead])
        if self.has_value_changed("division") or self.members_changed():
            check_division_for(self.division, [row.user for row in self.users])

    def members_changed(self) -> bool:
        before = self.get_doc_before_save()
        if not before:
            return True
        return {row.user for row in before.users} != {row.user for row in self.users}

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
