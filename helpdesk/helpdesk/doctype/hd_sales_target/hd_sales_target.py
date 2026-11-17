# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from helpdesk.sales_targets import (
    MAX_CRITERIA,
    VALUE_TYPES,
    has_own_targets,
    month_start,
)


class HDSalesTarget(Document):
    """One person's targets for one month (docs/sales-targets.md)."""

    def autoname(self):
        self.set_name_from_month()

    def validate(self):
        self.normalise_month()
        self.validate_employee()
        self.clean_criteria()
        self.validate_criteria()
        self.set_assigned_by()

    def set_name_from_month(self):
        # one set per person and month, kept so by the name itself
        self.normalise_month()
        self.name = f"{self.employee}::{self.month.strftime('%Y-%m')}"

    def normalise_month(self):
        self.month = month_start(self.month)

    def set_assigned_by(self):
        self.assigned_by = frappe.session.user

    def validate_employee(self):
        if not has_own_targets(self.employee):
            frappe.throw(
                _(
                    "{0} can't be given targets: they need the Presales Executive or Sales User role and an enabled account."
                ).format(frappe.bold(self.employee))
            )

    def clean_criteria(self):
        """Trims names and keeps only the field the value type uses."""
        for row in self.criteria:
            row.criterion = str(row.criterion or "").strip()
            if row.value_type == "Text":
                row.target_text = str(row.target_text or "").strip()
                row.target_value = None
            else:
                row.target_text = None
                blank = row.target_value is None or row.target_value == ""
                row.target_value = None if blank else flt(row.target_value)

    def validate_criteria(self):
        if not self.criteria:
            frappe.throw(_("Add at least one criterion."))
        if len(self.criteria) > MAX_CRITERIA:
            frappe.throw(_("Keep to {0} criteria or fewer.").format(MAX_CRITERIA))
        seen = set()
        for row in self.criteria:
            self.validate_criterion(row)
            key = row.criterion.casefold()
            if key in seen:
                frappe.throw(
                    _("{0} is listed twice. Keep one of them.").format(
                        frappe.bold(row.criterion)
                    )
                )
            seen.add(key)

    @staticmethod
    def validate_criterion(row):
        if not row.criterion:
            frappe.throw(_("Row {0}: give the criterion a name.").format(row.idx))
        if len(row.criterion) > 140:
            frappe.throw(
                _("Row {0}: keep the name under 140 characters.").format(row.idx)
            )
        if row.value_type not in VALUE_TYPES:
            frappe.throw(
                _("{0}: pick Amount, Number, Percent or Text.").format(row.criterion)
            )
        if row.value_type == "Text":
            if not row.target_text:
                frappe.throw(_("{0}: fill in the target.").format(row.criterion))
            return
        if row.target_value is None:
            frappe.throw(_("{0}: fill in the target.").format(row.criterion))
        if row.target_value < 0:
            frappe.throw(_("{0}: the target can't be below 0.").format(row.criterion))
        if row.value_type == "Percent" and row.target_value > 100:
            frappe.throw(_("{0}: a percent can't be over 100.").format(row.criterion))
