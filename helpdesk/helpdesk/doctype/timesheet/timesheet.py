# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import add_to_date, flt

STATUS_BY_DOCSTATUS = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


class Timesheet(Document):
    def validate(self):
        self.set_time_log_end_times()
        self.set_total_hours()
        self.set_status()

    def on_cancel(self):
        self.set_cancelled_status()

    def set_time_log_end_times(self):
        for log in self.time_logs:
            if log.from_time and log.hours:
                log.to_time = add_to_date(log.from_time, hours=flt(log.hours))

    def set_total_hours(self):
        self.total_hours = sum(flt(log.hours) for log in self.time_logs)

    def set_status(self):
        self.status = STATUS_BY_DOCSTATUS[self.docstatus]

    def set_cancelled_status(self):
        # validate() doesn't run on cancel, so persist the status directly
        self.db_set("status", "Cancelled")
