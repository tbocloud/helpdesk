# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.helpdesk.doctype.hd_meeting.hd_meeting import MAX_DURATION, MIN_DURATION


class HDMeetingType(Document):
    def validate(self):
        self.validate_duration()

    def validate_duration(self):
        if not MIN_DURATION <= (self.default_duration or 0) <= MAX_DURATION:
            frappe.throw(
                _("A meeting is {0} to {1} minutes long.").format(
                    MIN_DURATION, MAX_DURATION
                )
            )
