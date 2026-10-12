# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A Scoreboard badge earned in one closed period (see helpdesk.competition and
docs/tbo-smart-api.md, Badges).

Written once by the daily close of periods; the name comes from the badge, the
person, the period and the department, so a second run finds the first and the
person is told once.
"""

import hashlib

from frappe.model.document import Document
from frappe.utils import getdate


class HDBadgeAward(Document):
    def autoname(self):
        self.name = self.record_name(
            self.badge, self.user, self.period_start, self.department
        )

    @staticmethod
    def record_name(badge: str, user: str, period_start, department=None) -> str:
        """One award per badge, person, period and department."""
        digest = hashlib.sha1(f"{user}:{department or ''}".encode()).hexdigest()[:10]
        return f"{badge}-{getdate(period_start)}-{digest}"
