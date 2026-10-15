# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""Settings → Stand-up (docs/standup.md). The three times are Data fields, not Time:
Frappe gives a new document's Time fields the current time instead of their default
(see HD Follow Up Settings' afternoon nudge)."""

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.helpdesk.doctype.hd_chat_settings.hd_chat_settings import HDChatSettings
from helpdesk.helpdesk.doctype.hd_follow_up_settings.hd_follow_up_settings import (
    HDFollowUpSettings,
)

TIME_FIELDS = ("open_at", "remind_at", "post_at")


class HDStandupSettings(Document):
    def validate(self):
        self.validate_times()
        self.validate_departments()

    def validate_times(self):
        """Stored as "09:00", in order: drafts open, then the reminder, then the post."""
        times = []
        for fieldname in TIME_FIELDS:
            parsed = HDFollowUpSettings.parse_digest_times(
                self.normalized_time(self.get(fieldname))
            )
            if not parsed or len(parsed) != 1:
                frappe.throw(
                    _("{0}: write one 24-hour time, e.g. 09:00.").format(
                        _(self.meta.get_label(fieldname))
                    )
                )
            self.set(fieldname, parsed[0])
            times.append(parsed[0])
        if not times[0] < times[1] < times[2]:
            frappe.throw(
                _(
                    "The times must be in order: drafts open, then the reminder, then the summary."
                )
            )

    def validate_departments(self):
        """Each department once; a channel URL must be a Teams workflow's."""
        seen = set()
        for row in self.departments:
            if row.department in seen:
                frappe.throw(
                    _("{0} is listed twice under Departments.").format(row.department)
                )
            seen.add(row.department)
            raw = row.channel_webhook or ""
            # an unchanged password field holds "*****"
            if not raw or row.is_dummy_password(raw):
                continue
            row.channel_webhook = raw.strip()
            problem = HDChatSettings.teams_url_problem(row.channel_webhook)
            if problem:
                frappe.throw(_("{0}'s channel: {1}").format(row.department, problem))

    @staticmethod
    def normalized_time(value) -> str:
        """ "09:00:00" and " 9:00" → "9:00"; the follow-up parser does the rest."""
        value = str(value or "").strip()
        return value[:-3] if value.count(":") == 2 else value
