# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from helpdesk.sales_targets import (
    KPI_CONFIRMED,
    KPI_DONE,
    MAX_CRITERIA,
    MEASURES,
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
        # ticking a KPI off or confirming it doesn't make that person the assigner
        if self.flags.kpi_only:
            return
        self.assigned_by = frappe.session.user

    def validate_employee(self):
        if not has_own_targets(self.employee):
            frappe.throw(
                _(
                    "{0} can't be given targets: they need the Presales Executive or Sales User role and an enabled account."
                ).format(frappe.bold(self.employee))
            )

    def clean_criteria(self):
        """Trims names and keeps only the fields the value type uses: a measure for a
        figure, the KPI state for a Text target."""
        for row in self.criteria:
            row.criterion = str(row.criterion or "").strip()
            if row.value_type == "Text":
                row.target_text = str(row.target_text or "").strip()
                row.target_value = None
                row.measure = ""
            else:
                row.target_text = None
                blank = row.target_value is None or row.target_value == ""
                row.target_value = None if blank else flt(row.target_value)
                row.measure = row.measure or ""
                row.kpi_status = row.kpi_note = ""
                row.kpi_done_on = row.kpi_confirmed_by = None

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
        if row.measure and MEASURES.get(row.measure) != row.value_type:
            frappe.throw(
                _("{0}: {1} can't count towards a {2} target.").format(
                    row.criterion, row.measure, row.value_type
                )
            )
        if row.target_value is None:
            frappe.throw(_("{0}: fill in the target.").format(row.criterion))
        if row.target_value < 0:
            frappe.throw(_("{0}: the target can't be below 0.").format(row.criterion))
        if row.value_type == "Percent" and row.target_value > 100:
            frappe.throw(_("{0}: a percent can't be over 100.").format(row.criterion))

    # ---------- a KPI (a Text target): ticked off by the person, confirmed by a head ----------

    def kpi_row(self, criterion: str):
        """The Text target named `criterion`, or an error the page can show."""
        for row in self.criteria:
            if row.value_type == "Text" and row.criterion == criterion:
                return row
        frappe.throw(
            _("{0} isn't a KPI on these targets.").format(frappe.bold(criterion))
        )

    def mark_kpi(self, criterion: str, done: bool, note: str = ""):
        """The person says they did it (with what they did), or takes that back. A
        confirmed KPI stays confirmed: only the head can undo that."""
        row = self.kpi_row(criterion)
        if row.kpi_status == KPI_CONFIRMED:
            frappe.throw(
                _("{0} is already confirmed. Ask your Sales Head to reopen it.").format(
                    frappe.bold(criterion)
                )
            )
        row.kpi_status = KPI_DONE if done else ""
        row.kpi_note = str(note or "").strip()[:1000] if done else ""
        row.kpi_done_on = now_datetime() if done else None
        self.flags.kpi_only = True

    def confirm_kpi(self, criterion: str, confirmed: bool, user: str):
        """A head confirms a KPI marked done, or reopens a confirmed one (back to Done)."""
        row = self.kpi_row(criterion)
        if confirmed and row.kpi_status != KPI_DONE:
            frappe.throw(
                _("{0} isn't marked done yet, so there's nothing to confirm.").format(
                    frappe.bold(criterion)
                )
            )
        row.kpi_status = KPI_CONFIRMED if confirmed else KPI_DONE
        row.kpi_confirmed_by = user if confirmed else None
        self.flags.kpi_only = True

    def keep_kpi_state(self, before: dict):
        """After a head re-assigns: a KPI with the same name and wording keeps whether it
        was done or confirmed; reworded, it starts again. `before` is the old rows by name."""
        for row in self.criteria:
            old = before.get(row.criterion.casefold())
            if (
                row.value_type == "Text"
                and old
                and old.value_type == "Text"
                and (old.target_text or "").strip()
                == str(row.target_text or "").strip()
            ):
                row.kpi_status = old.kpi_status
                row.kpi_note = old.kpi_note
                row.kpi_done_on = old.kpi_done_on
                row.kpi_confirmed_by = old.kpi_confirmed_by
