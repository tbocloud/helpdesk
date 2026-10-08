# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.utils import normalize_site_url


class HDSSiteRegistry(Document):
    def validate(self):
        self.normalize_site_url()
        self.ensure_one_production_site()

    def normalize_site_url(self):
        if self.site_url:
            self.site_url = normalize_site_url(self.site_url)

    def ensure_one_production_site(self):
        """A customer (and a connection) has one Production site; other environments may repeat."""
        if self.environment != "Production":
            return
        filters = {
            "customer_name": self.customer_name,
            "environment": "Production",
            "name": ["!=", self.name],
        }
        if self.connection:
            filters["connection"] = self.connection
        other = frappe.db.get_value("HDS Site Registry", filters)
        if other:
            frappe.throw(
                _("{0} is already the Production site of {1}").format(other, self.customer_name)
            )
