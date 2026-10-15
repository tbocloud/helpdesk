# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""One person's stand-up for one working day: see helpdesk.standup and docs/standup.md.

The name comes from the person and the day, so a run that fills drafts twice, or a
person saving while the run creates theirs, still leaves one stand-up.
"""

from frappe.model.document import Document


class HDStandup(Document):
    def autoname(self):
        self.name = self.record_name(self.user, self.date)

    @staticmethod
    def record_name(user: str, day) -> str:
        from helpdesk.standup import standup_name

        return standup_name(user, day)
