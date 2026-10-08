# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""Support hours a customer bought per period: an AMC, a support block or a retainer.

A customer may hold several contracts, but the Active ones may not overlap in
dates, so on any day at most one contract counts the hours logged for it (a
renewal can be entered ahead of time). Usage and alerts live in
helpdesk/support_contracts.py; see docs/support-contracts.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from helpdesk.support_contracts import ACTIVE, ONE_OFF_BLOCK

# changing any of these changes what has been used against what, so a usage
# alert already sent for the current period may no longer be true
ALERT_FIELDS = (
    "start_date",
    "end_date",
    "billing_period",
    "hours_per_period",
    "rollover_unused",
    "alert_threshold",
)


class HDSupportContract(Document):
    def validate(self):
        self.validate_dates()
        self.validate_hours()
        self.validate_alert_threshold()
        self.clear_rollover_for_block()
        self.validate_no_overlap()
        self.reset_alert_on_change()

    def validate_dates(self):
        if getdate(self.end_date) < getdate(self.start_date):
            frappe.throw(_("The end date can't be before the start date."))

    def validate_hours(self):
        if flt(self.hours_per_period) <= 0:
            frappe.throw(_("Enter how many hours the customer gets each period."))

    def validate_alert_threshold(self):
        if not 1 <= int(self.alert_threshold or 0) <= 100:
            frappe.throw(_("Set the alert between 1% and 100% of the hours used."))

    def clear_rollover_for_block(self):
        # a block is a single period, so there is nothing to roll into
        if self.billing_period == ONE_OFF_BLOCK:
            self.rollover_unused = 0

    def validate_no_overlap(self):
        if self.status != ACTIVE:
            return
        Contract = frappe.qb.DocType("HD Support Contract")
        clash = (
            frappe.qb.from_(Contract)
            .select(Contract.name, Contract.contract_name)
            .where(Contract.customer == self.customer)
            .where(Contract.status == ACTIVE)
            .where(Contract.name != (self.name or ""))
            .where(Contract.start_date <= self.end_date)
            .where(Contract.end_date >= self.start_date)
            .limit(1)
            .run(as_dict=True)
        )
        if clash:
            frappe.throw(
                _(
                    "{0} already has an active contract for these dates: {1}. End or cancel it first, or start this one after it."
                ).format(self.customer, clash[0].contract_name or clash[0].name)
            )

    def reset_alert_on_change(self):
        if self.is_new() or not any(self.has_value_changed(f) for f in ALERT_FIELDS):
            return
        self.alerted_period_start = None
        self.alerted_stage = None
