# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# the base URLs an AI key is sent to
KEYED_URL_FIELDS = ("ai_base_url", "openai_base_url", "gateway_url")


class HDSHubSettings(Document):
    def onload(self):
        """Monitoring shows when the watcher was last heard from (its heartbeat lives in the cache,
        not in a field)."""
        from helpdesk import monitor

        try:
            self.set_onload("watcher_status", monitor.status("watcher"))
        except Exception:
            frappe.log_error(title="Watcher status not read for HDS Hub Settings")

    def validate(self):
        from helpdesk.ai_engine import check_job_rows

        self.validate_ai_base_urls()
        check_job_rows(self)

    def validate_ai_base_urls(self):
        """An AI key only goes over https. Messages start with the field's label,
        so Settings → AI providers shows them under that field."""
        for fieldname in KEYED_URL_FIELDS:
            value = (self.get(fieldname) or "").strip().rstrip("/")
            # plain http only to this machine, for a local test gateway
            local = fieldname == "gateway_url" and value.startswith(
                ("http://localhost", "http://127.0.0.1")
            )
            if value and not value.startswith("https://") and not local:
                frappe.throw(
                    _(
                        "{0}: use an https:// address, so the API key isn't sent in the clear."
                    ).format(_(self.meta.get_label(fieldname)))
                )
            self.set(fieldname, value)
