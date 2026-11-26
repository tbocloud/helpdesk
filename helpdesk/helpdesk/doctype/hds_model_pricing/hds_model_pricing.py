# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from helpdesk import ai_engine


class HDSModelPricing(Document):
    def validate(self):
        """The model list (Phase 31): a model is called through a section or a provider account,
        its limit is never below 0, and a model a job uses stays allowed."""
        if flt(self.monthly_token_limit) < 0:
            frappe.throw(_("A monthly token limit cannot be below 0."))
        account = (self.ai_provider or "").strip()
        if (
            account
            and account not in ai_engine.SLOTS
            and not frappe.db.exists(ai_engine.PROVIDER_DOCTYPE, account)
        ):
            frappe.throw(
                _(
                    "{0} isn't a provider. Add it under AI models → Model settings first."
                ).format(account)
            )
        self.ai_provider = account
        if self.listed and not account:
            frappe.throw(_("Choose the provider this model is called through."))
        if not self.listed and not self.is_new():
            in_use = ai_engine.in_use_message(self.name)
            if in_use:
                frappe.throw(in_use)

    def on_update(self):
        frappe.cache.delete_value(ai_engine.MONTH_TOKENS_KEY.format(self.name))
