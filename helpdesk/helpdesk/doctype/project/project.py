# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class Project(Document):
    def validate(self):
        self.validate_dates()

    def validate_dates(self):
        if (
            self.expected_start_date
            and self.expected_end_date
            and getdate(self.expected_end_date) < getdate(self.expected_start_date)
        ):
            frappe.throw(_("The end date can't be before the start date."))
