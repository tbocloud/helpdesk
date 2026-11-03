# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.permissions import add_permission, update_permission_property

DOCTYPE = "Business Health Check"
# The role for the TBO website's API user (docs/business-health-check.md).
API_ROLE = "Health Check API"
TEXT_FIELDS = ("business_name", "contact_name", "phone", "email", "report_link")


class BusinessHealthCheck(Document):
    """A finished Business Health Check from the TBO website: the client's basic details
    and a link to their report. The website creates it when the check is finished and
    updates it when the client leaves a phone number or email."""

    def validate(self):
        for field in TEXT_FIELDS:
            value = self.get(field)
            if isinstance(value, str):
                self.set(field, value.strip() or None)
        if not self.business_name:
            self.business_name = "Unnamed business"


def setup_api_role():
    """Create the API role with Create / Read / Write on this DocType only. Safe to re-run."""
    if not frappe.db.exists("Role", API_ROLE):
        frappe.get_doc(
            {"doctype": "Role", "role_name": API_ROLE, "desk_access": 0}
        ).insert(ignore_permissions=True)
    add_permission(DOCTYPE, API_ROLE, 0)  # adds read
    for ptype in ("create", "write"):
        update_permission_property(DOCTYPE, API_ROLE, 0, ptype, 1)
