# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document

DOCTYPE = "HD CRM Source User"


class HDCRMSourceUser(Document):
    """A desk user of a data source's site with their roles there, read by the sync
    (helpdesk.crm_dashboard.erp_roles). Read-only in the hub: the site is the master."""

    def autoname(self):
        self.name = self.key(self.source, self.email)

    @staticmethod
    def key(source: str, email: str) -> str:
        return f"{source}::{email}"
