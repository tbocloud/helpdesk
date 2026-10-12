# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""The company's departments. Projects belong to one, and the Projects page groups
them by department in this order (Settings → Departments edits the list)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Max

# TBO's departments, in the order the owner wants them listed
DEFAULT_DEPARTMENTS = ("ERP", "Digital", "Creative", "GrowthX", "Internal / R&D")
# the owner's two main groups: ERP with GrowthX and Internal / R&D, Digital with
# Creative (the Scoreboard ranks each group as well as each department)
DEFAULT_GROUPS = {"GrowthX": "ERP", "Internal / R&D": "ERP", "Creative": "Digital"}


class HDDepartment(Document):
    def before_insert(self):
        self.clean_name()
        self.set_sort_order()

    def validate(self):
        self.validate_parent_department()

    def validate_parent_department(self):
        """One level only: a sub-department belongs to a main department, and a
        main department with sub-departments can't become one itself."""
        if not self.parent_department:
            return
        if self.parent_department == self.name:
            frappe.throw(_("A department can't be part of itself."))
        if frappe.db.get_value(
            "HD Department", self.parent_department, "parent_department"
        ):
            frappe.throw(
                _(
                    "{0} is itself part of another department. Pick a main department."
                ).format(self.parent_department)
            )
        if not self.is_new() and frappe.db.exists(
            "HD Department", {"parent_department": self.name}
        ):
            frappe.throw(
                _("{0} has sub-departments, so it stays a main department.").format(
                    self.name
                )
            )

    def clean_name(self):
        self.department_name = (self.department_name or "").strip()

    def set_sort_order(self):
        """A new department goes to the end of the list unless placed explicitly."""
        if self.sort_order:
            return
        department = frappe.qb.DocType("HD Department")
        highest = frappe.qb.from_(department).select(Max(department.sort_order)).run()
        self.sort_order = (highest[0][0] or 0) + 1


def ensure_default_departments() -> list[str]:
    """Add the default departments a site doesn't have yet; returns the ones added.

    Existing departments (including renamed or deactivated ones) are left alone.
    """
    added = []
    for name in DEFAULT_DEPARTMENTS:
        if frappe.db.exists("HD Department", name):
            continue
        frappe.get_doc({"doctype": "HD Department", "department_name": name}).insert(
            ignore_permissions=True
        )
        added.append(name)
    set_default_groups()
    return added


def set_default_groups() -> list[str]:
    """Puts each default sub-department in its main department (DEFAULT_GROUPS)
    when both exist, the sub-department isn't in a group yet and the main one
    isn't a sub-department itself; returns the departments changed. Only an
    empty `parent_department` is filled, so running it twice changes nothing."""
    department = frappe.qb.DocType("HD Department")
    groups = dict(
        frappe.qb.from_(department)
        .select(department.name, department.parent_department)
        .where(department.name.isin([*DEFAULT_GROUPS, *DEFAULT_GROUPS.values()]))
        .run()
    )
    changed = []
    for name, parent in DEFAULT_GROUPS.items():
        if name not in groups or groups[name] or parent not in groups:
            continue
        if groups[parent]:
            continue
        doc = frappe.get_doc("HD Department", name)
        doc.parent_department = parent
        doc.save(ignore_permissions=True)
        changed.append(name)
    return changed
