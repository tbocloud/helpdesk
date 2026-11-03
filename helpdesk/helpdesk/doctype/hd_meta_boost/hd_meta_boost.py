# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, getdate

DRAFT = "Draft"
PENDING = "Pending approval"
ACTIVE = "Active"
PAUSED = "Paused"
COMPLETED = "Completed"
FAILED = "Failed"
REJECTED = "Rejected"
# running or able to run again: they count at their full budget against the monthly cap
LIVE = (ACTIVE, PAUSED)
# longest boost the hub starts; a longer one is several boosts
MAX_DAYS = 30


class HDMetaBoost(Document):
    def validate(self):
        self.check_dates()
        self.set_days_and_total()
        self.check_budget()

    def check_dates(self):
        if getdate(self.end_date) < getdate(self.start_date):
            frappe.throw(_("The boost can't end before it starts."))
        if self.is_new() and getdate(self.start_date) < getdate():
            frappe.throw(_("The start date can't be in the past."))

    def set_days_and_total(self):
        """A per-day budget is a ceiling of that amount for every day."""
        self.days = date_diff(self.end_date, self.start_date) + 1
        if self.days > MAX_DAYS:
            frappe.throw(
                _(
                    "A boost can run for at most {0} days. Start another after it ends."
                ).format(MAX_DAYS)
            )
        self.total_budget = (
            flt(self.budget_amount) * self.days
            if self.budget_type == "Per day"
            else flt(self.budget_amount)
        )

    def check_budget(self):
        if flt(self.budget_amount) <= 0:
            frappe.throw(_("Enter a budget above zero."))
