# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document

TEXT_FIELDS = ("business_name", "contact_name", "phone", "email", "report_link")
PLACEHOLDER_NAME = "Unnamed business"


class BusinessHealthCheck(Document):
    """A finished Business Health Check from the TBO website: the client's basic details
    and a link to their report. The website creates it when the check is finished and
    updates it when the client leaves a phone number or email."""

    def validate(self):
        self.trim_text_fields()
        self.set_placeholder_business_name()

    def trim_text_fields(self):
        """Strip spaces around the website's values; a blank value becomes empty."""
        for field in TEXT_FIELDS:
            value = self.get(field)
            if isinstance(value, str):
                self.set(field, value.strip() or None)

    def set_placeholder_business_name(self):
        """Clients may skip their business name; the record still needs a title."""
        if not self.business_name:
            self.business_name = PLACEHOLDER_NAME
