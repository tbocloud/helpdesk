# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HDWorkSettings(Document):
    def validate(self):
        self.validate_max_task_days()

    def on_update(self):
        self.sync_saturdays_off()

    def sync_saturdays_off(self):
        """A changed rule reaches the SLA holiday lists now, not tomorrow."""
        from helpdesk.work_calendar import sync_saturdays_off

        if self.has_value_changed("saturdays_off") or self.has_value_changed(
            "weekly_off"
        ):
            frappe.clear_document_cache("HD Work Settings", "HD Work Settings")
            sync_saturdays_off()

    def validate_max_task_days(self):
        if self.max_task_days is not None and not 1 <= self.max_task_days <= 120:
            frappe.throw(
                _("The longest estimate must be between 1 and 120 working days.")
            )
