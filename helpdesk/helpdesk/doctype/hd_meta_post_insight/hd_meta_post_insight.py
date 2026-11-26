# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDMetaPostInsight(Document):
    """One Facebook or Instagram post and its lifetime numbers, written by the insights
    sync (docs/meta-insights.md). Named by platform and Meta's id, one row per post."""

    def autoname(self):
        self.name = self.key(self.platform, self.media_id)

    @staticmethod
    def key(platform: str, media_id: str) -> str:
        return f"{platform}-{media_id}"
