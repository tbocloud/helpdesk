# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HDCRMSettings(Document):
    def validate(self):
        self.normalize_site_url()
        self.validate_credentials()

    def normalize_site_url(self):
        url = (self.site_url or "").strip().rstrip("/")
        if url and not url.startswith(("https://", "http://")):
            url = f"https://{url}"
        self.site_url = url

    def validate_credentials(self):
        # validate runs before the password is stored: a new secret is plain text here,
        # a kept one is "*****"; both mean a secret is there
        if self.enabled and not (self.site_url and self.api_key and self.api_secret):
            frappe.throw(
                _(
                    "Add the CRM site URL, API key and API secret before turning the CRM connection on."
                )
            )
