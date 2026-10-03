# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from helpdesk.teams_meetings import TOKEN_CACHE_KEY


class HDMeetingSettings(Document):
    def on_update(self):
        self.forget_token()

    def forget_token(self):
        """A changed app gets a fresh Graph token instead of the old app's."""
        previous = self.get_doc_before_save()
        if previous and previous.connected_app:
            frappe.cache.delete_value(TOKEN_CACHE_KEY.format(previous.connected_app))
