# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""The champion of one closed period, for one department or the whole team
(see helpdesk.team_dashboard and docs/team-dashboard.md).

Written once by the scheduler when the period closes, so the champions history
doesn't move when tasks are edited later. People read it through
helpdesk.api.team_dashboard, which decides who may see what.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class HDTeamChampion(Document):
    def autoname(self):
        self.name = self.record_name(
            self.period_type, self.period_start, self.department
        )

    def validate(self):
        self.validate_period()

    def validate_period(self):
        if getdate(self.period_end) < getdate(self.period_start):
            frappe.throw(_("The period can't end before it starts."))

    @staticmethod
    def record_name(period_type: str, period_start, department: str | None) -> str:
        """One record per period and department: a second run finds the first."""
        scope = HDTeamChampion.slug(department) if department else "whole_team"
        return f"{HDTeamChampion.slug(period_type)}-{getdate(period_start)}-{scope}"

    @staticmethod
    def slug(text: str) -> str:
        # department names may hold "/" or "&" ("Internal / R&D"), which don't belong in a name
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
