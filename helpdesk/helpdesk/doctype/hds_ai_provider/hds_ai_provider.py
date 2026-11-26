# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk import ai_engine


class HDSAIProvider(Document):
    """An AI provider account and its key (docs/ai-models.md, Model settings)."""

    def validate(self):
        self.provider_name = (self.provider_name or "").strip()
        if self.provider_name in ai_engine.SLOTS:
            frappe.throw(
                _(
                    "{0} is the name of one of today's two sections. Choose another name."
                ).format(self.provider_name)
            )
        url = (self.base_url or "").strip().rstrip("/")
        if url and not url.startswith("https://"):
            frappe.throw(
                _("Use an https:// address, so the API key isn't sent in the clear.")
            )
        # Anthropic's own API needs no address, and AWS Bedrock is reached through the gateway
        if not url and self.api_style not in ("Anthropic", "AWS Bedrock"):
            frappe.throw(_("Give the provider's API address."))
        self.base_url = url

    def on_update(self):
        ai_engine.forget_provider(self.name)

    def on_trash(self):
        ai_engine.forget_provider(self.name)
