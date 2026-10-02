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
            raw = self.get(fieldname) or ""
            # unchanged password fields hold "*****"
            if raw and self.is_dummy_password(raw):
                continue
            # spaces alone would be stored as the URL and make Teams look set up
            value = raw.strip()
            self.set(fieldname, value)
            if not value:
                continue
            problem = self.teams_url_problem(value)
            if problem:
                frappe.throw(
                    _("{0}: {1}").format(self.meta.get_label(fieldname), problem)
                )

    @staticmethod
    def teams_url_problem(url: str) -> str | None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if HDChatSettings.on_domain(host, ("teams.microsoft.com",)):
            return _(
                "this is a link to a Teams message, not the workflow's URL. In Power Automate, open the flow, click its trigger and copy the HTTP URL."
            )
        if parsed.scheme != "https" or not host:
            return _("paste the full https:// URL of the workflow.")
        if HDChatSettings.on_domain(host, (LEGACY_WEBHOOK_HOST,)):
            return None
        if not HDChatSettings.on_domain(host, WORKFLOW_HOSTS):
            return _(
                "this doesn't look like a Teams Workflows (Power Automate) URL. Copy the HTTP URL from the flow's trigger."
            )
        if "sig=" not in parsed.query:
            return _(
                "the URL is cut off: it must end with &sp=…&sv=…&sig=…. Copy it again from the flow's trigger."
            )
        return None

    @staticmethod
    def on_domain(host: str, domains: tuple[str, ...]) -> bool:
        """`host` is one of `domains` or a subdomain of one (not just a name ending in it)."""
        return any(host == d or host.endswith("." + d) for d in domains)
