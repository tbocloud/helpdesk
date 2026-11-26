# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDMetaDailyInsight(Document):
    """One day of a client's Facebook Page or Instagram account numbers, written by the
    insights sync (docs/meta-insights.md). Named by project, platform and day, so a
    later sync of the same day updates the row instead of adding one."""

    def autoname(self):
        self.name = self.key(self.project, self.platform, self.day)

    @staticmethod
    def key(project: str, platform: str, day) -> str:
        return f"{project}-{platform}-{day}"
