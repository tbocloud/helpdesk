# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

DEFAULT_DOCTYPES = ("HD Content Post",)


class HDFileStorageSettings(Document):
    def validate(self):
        self.set_default_doctypes()
        self.validate_required_when_enabled()
        self.clean_values()

    def set_default_doctypes(self):
        if not self.document_types:
            for doctype in DEFAULT_DOCTYPES:
                self.append("document_types", {"document_type": doctype})

    def validate_required_when_enabled(self):
        if not self.enabled:
            return
        missing = [
            _(self.meta.get_label(f))
            for f in ("bucket", "region", "access_key_id")
            if not self.get(f)
        ]
        if not self.get_password("secret_access_key", raise_exception=False):
            missing.append(_(self.meta.get_label("secret_access_key")))
        if missing:
            frappe.throw(
                _("To store files in S3, fill in: {0}").format(", ".join(missing))
            )

    def clean_values(self):
        for f in ("bucket", "region", "access_key_id", "endpoint_url"):
            if self.get(f):
                self.set(f, self.get(f).strip())
        if self.key_prefix:
            self.key_prefix = self.key_prefix.strip().strip("/")
