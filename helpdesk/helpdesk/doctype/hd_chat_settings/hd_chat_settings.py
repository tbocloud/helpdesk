# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HDChatSettings(Document):
    def validate(self):
        self.validate_slack_channel()

    def validate_slack_channel(self):
        channel = (self.slack_escalation_channel or "").strip()
        # chat.postMessage needs the ID; a "#name" silently fails for private channels
        if channel.startswith("#"):
            frappe.throw(
                _(
                    "Use the channel ID (e.g. C0123ABCD), not its name. It's under the channel's details in Slack."
                )
            )
        self.slack_escalation_channel = channel
