# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.api import leads as leads_api
from helpdesk.integrations.crm.leads import LeadsError

TEXT_FIELDS = ("business_name", "contact_name", "phone", "email", "report_link")
PLACEHOLDER_NAME = "Unnamed business"
# how the ERP site words its refusal of a lead that shares an email or phone with another
# (the Leads page's lead form looks for the same words)
POSSIBLE_DUPLICATE = "possible duplicate"


class BusinessHealthCheck(Document):
    """A finished Business Health Check from the TBO website: the client's basic details
    and a link to their report. The website creates it when the check is finished and
    updates it when the client leaves a phone number or email. Create Lead turns it into
    an ERPNext Lead on the ERP site."""

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

    @frappe.whitelist(methods=["POST"])
    def create_lead(self, allow_duplicate: int | str | None = 0) -> dict:
        """An ERPNext Lead from this check, made on the ERP site as the signed-in person
        through the Leads page's create_lead, so the same Leads access and duplicate check
        apply. The report link goes on the lead as a note, and the lead's name is kept here.

        Returns {"lead", "noted"}, or {"duplicate": the ERP site's message} when another
        lead has the same email or phone: nothing is made until the person confirms with
        `allow_duplicate`."""
        self.reload()  # the saved record, not what the form sent
        self.check_permission("read")
        self.check_no_lead_yet()
        try:
            result = leads_api.create_lead(self.lead_details(), allow_duplicate)
        except LeadsError as e:
            if POSSIBLE_DUPLICATE not in str(e).casefold():
                raise
            frappe.clear_last_message()  # the form asks instead of showing an error
            return {"duplicate": str(e)}
        lead = result.get("name")
        if not lead:
            frappe.throw(_("The ERP site didn't say which lead it made. Check Leads."))
        self.db_set("lead", lead)
        return {"lead": lead, "noted": self.add_report_note(lead)}

    def check_no_lead_yet(self):
        if self.lead:
            frappe.throw(_("This check already has lead {0}.").format(self.lead))

    def lead_details(self) -> dict:
        """The lead's fields (the Leads page's create_lead keys); an unnamed business sends
        no company name."""
        company = None if self.business_name == PLACEHOLDER_NAME else self.business_name
        details = {
            "lead_name": self.contact_name or company or PLACEHOLDER_NAME,
            "company_name": company,
            "mobile_no": self.phone,
            "email_id": self.email,
        }
        return {key: value for key, value in details.items() if value}

    def add_report_note(self, lead: str) -> bool:
        """The report link on the lead's timeline, so Sales can open the report from the
        lead. The lead is made by now, so a failed note doesn't undo it: False, and the
        form says so."""
        note = _("Business Health Check {0}: {1}").format(self.name, self.report_link)
        try:
            leads_api.add_note(lead, note)
        except LeadsError:
            frappe.clear_last_message()
            return False
        return True
