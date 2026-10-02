# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document

TEAMS_WEBHOOK_FIELDS = ("teams_direct_webhook", "teams_channel_webhook")
# Teams Workflows (Power Automate) URLs, old and new hosts
WORKFLOW_HOSTS = ("logic.azure.com", "powerplatform.com")
# retired Office 365 connector webhooks still post to channels, without a signature
LEGACY_WEBHOOK_HOST = "webhook.office.com"


class HDChatSettings(Document):
    def validate(self):
        self.validate_slack_channel()
        self.validate_teams_urls()

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

    def validate_teams_urls(self):
        """Catches a pasted Teams message link or a cut-off URL here, not as an HTTP error later."""
        for fieldname in TEAMS_WEBHOOK_FIELDS:
            value = (self.get(fieldname) or "").strip()
            # unchanged password fields hold "*****"
            if not value or self.is_dummy_password(value):
                continue
            label = self.meta.get_label(fieldname)
            self.set(fieldname, value)
            problem = self.teams_url_problem(value)
            if problem:
                frappe.throw(_("{0}: {1}").format(label, problem))

    @staticmethod
    def teams_url_problem(url: str) -> str | None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host.endswith("teams.microsoft.com"):
            return _(
                "this is a link to a Teams message, not the workflow's URL. In Power Automate, open the flow, click its trigger and copy the HTTP URL."
            )
        if parsed.scheme != "https" or not host:
            return _("paste the full https:// URL of the workflow.")
        if host.endswith(LEGACY_WEBHOOK_HOST):
            return None
        if not host.endswith(WORKFLOW_HOSTS):
            return _(
                "this doesn't look like a Teams Workflows (Power Automate) URL. Copy the HTTP URL from the flow's trigger."
            )
        if "sig=" not in parsed.query:
            return _(
                "the URL is cut off: it must end with &sp=…&sv=…&sig=…. Copy it again from the flow's trigger."
            )
        return None
