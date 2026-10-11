# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""An assignee acknowledged a follow-up on their task or ticket: see
helpdesk.follow_ups.snooze and docs/follow-ups.md (Snooze).

One record per person and item (the name comes from them), and every save keeps the
rules, whoever saves it: the person is the item's assignee, there is a reason, and
the date is tomorrow to SNOOZE_MAX_DAYS ahead.
"""

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, nowdate

from helpdesk.work_reminders import _assignees

SNOOZE_MAX_DAYS = 7
MAX_REASON_LENGTH = 500


class HDFollowUpSnooze(Document):
    def autoname(self):
        self.name = self.record_name(
            self.user, self.reference_doctype, self.reference_name
        )

    def validate(self):
        self.validate_reason()
        self.validate_until()
        self.validate_assignee()

    @staticmethod
    def record_name(user: str, doctype: str, name) -> str:
        """One snooze per person and item: a second request finds the first."""
        key = f"{user}:{doctype}:{name}"
        return f"snooze-{hashlib.sha1(key.encode()).hexdigest()[:16]}"

    def validate_reason(self):
        self.reason = (self.reason or "").strip()
        if not self.reason:
            frappe.throw(_("Say why, so whoever runs the work knows."))
        if len(self.reason) > MAX_REASON_LENGTH:
            frappe.throw(_("Keep it under {0} characters.").format(MAX_REASON_LENGTH))

    def validate_until(self):
        today = getdate(nowdate())
        if not today < getdate(self.until) <= getdate(add_days(today, SNOOZE_MAX_DAYS)):
            frappe.throw(
                _("Snooze until a day from tomorrow to {0} days ahead.").format(
                    SNOOZE_MAX_DAYS
                )
            )

    def validate_assignee(self):
        raw = frappe.db.get_value(
            self.reference_doctype, self.reference_name, "_assign"
        )
        if self.user not in _assignees(raw):
            frappe.throw(
                _("Only the person it's assigned to can snooze its reminders.")
            )
