# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""The company's departments. Projects belong to one, and the Projects page groups
them by department in this order (Settings → Departments edits the list)."""

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Max

# TBO's departments, in the order the owner wants them listed
DEFAULT_DEPARTMENTS = ("ERP", "Digital", "Creative", "GrowthX", "Internal / R&D")


class HDDepartment(Document):
    def before_insert(self):
        self.clean_name()
        self.set_sort_order()

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
    return added
