# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
POSITIVE_FIELDS = (
    "untouched_days",
    "review_days",
    "hold_days",
    "no_due_date_days",
    "unassigned_minutes",
    "customer_replied_hours",
    "awaiting_customer_days",
)


class HDFollowUpSettings(Document):
    def validate(self):
        self.validate_digest_times()
        self.validate_ladder()
        self.validate_thresholds()
        self.validate_sla_warnings()

    def validate_digest_times(self):
        """Stored as "09:30, 15:30", sorted and without repeats."""
        times = self.parse_digest_times(self.digest_times)
        if times is None:
            frappe.throw(
                _(
                    "Write the digest times as 24-hour times separated by commas, e.g. 09:30, 15:30."
                )
            )
        self.digest_times = ", ".join(times)

    def validate_ladder(self):
        days = [self.ladder_l1_days, self.ladder_l2_days, self.ladder_l3_days]
        if any((d or 0) < 1 for d in days) or days != sorted(days):
            frappe.throw(
                _(
                    "The ladder's days must be 1 or more, and each step at least as late as the one before."
                )
            )

    def validate_thresholds(self):
        for fieldname in POSITIVE_FIELDS:
            if (self.get(fieldname) or 0) < 1:
                frappe.throw(
                    _("{0} must be 1 or more.").format(
                        _(self.meta.get_label(fieldname))
                    )
                )

    def validate_sla_warnings(self):
        first, second = self.sla_first_warning or 0, self.sla_second_warning or 0
        if not 1 <= first < second <= 99:
            frappe.throw(
                _(
                    "SLA warnings are percentages between 1 and 99, the second later than the first."
                )
            )

    @staticmethod
    def parse_digest_times(value: str | None) -> list[str] | None:
        """["09:30", "15:30"] from "9:30, 15:30"; None when a part isn't a time."""
        times = set()
        for part in (value or "").split(","):
            part = part.strip()
            if not part:
                continue
            match = TIME_PATTERN.match(part)
            if not match:
                return None
            times.add(f"{int(match.group(1)):02d}:{match.group(2)}")
        return sorted(times)
