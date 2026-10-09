# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from helpdesk.integrations.crm.client import CRMClient, CRMError

INVOICING_FIELDS = (
    "invoice_company",
    "invoice_item",
    "invoice_taxes_template",
    "invoice_income_account",
    "invoice_cost_center",
    "invoice_hourly_rate",
    "invoice_currency",
)
# cleared when the company is, which turns invoicing off
COMPANY_FIELDS = (
    "invoice_item",
    "invoice_taxes_template",
    "invoice_income_account",
    "invoice_cost_center",
)


class HDCRMSettings(Document):
    def validate(self):
        self.normalize_site_url()
        self.validate_credentials()
        self.validate_invoicing()

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

    def validate_invoicing(self):
        """Invoicing is on once a company is set; then its records must exist on the CRM site.

        Only checked when an invoicing field changes, so saving other settings never
        waits on the CRM site.
        """
        for field in INVOICING_FIELDS:
            if isinstance(self.get(field), str):
                self.set(field, self.get(field).strip())
        if not self.invoicing_changed():
            return
        if not self.invoice_company:
            self.clear_company_records()
            return
        if not self.invoice_item:
            frappe.throw(_("Pick the item the support hours are billed as."))
        if flt(self.invoice_hourly_rate) <= 0 or not self.invoice_currency:
            frappe.throw(_("Set the default hourly rate and its currency."))
        try:
            problem = self.invoicing_problem(CRMClient.from_settings(self))
        except CRMError as e:
            frappe.throw(
                _("Couldn't check the invoicing settings on the CRM site: {0}").format(
                    str(e)
                )
            )
        if problem:
            frappe.throw(problem)

    def clear_company_records(self):
        """No company turns invoicing off; the item, template, account and cost center
        are records of a company on the CRM site, so they go with it."""
        for field in COMPANY_FIELDS:
            self.set(field, None)

    def invoicing_changed(self) -> bool:
        # a Single reads an unset field back as None or "", and the rate as 0 or 0.0
        previous = self.get_doc_before_save()
        if not previous:
            return True
        return any(
            self.comparable(f, previous.get(f)) != self.comparable(f, self.get(f))
            for f in INVOICING_FIELDS
        )

    @staticmethod
    def comparable(fieldname: str, value):
        return flt(value) if fieldname == "invoice_hourly_rate" else value or ""

    def invoicing_problem(self, client) -> str | None:
        """What on the CRM site doesn't match the invoicing settings, if anything."""
        company = self.invoice_company
        if company not in {c.get("name") for c in client.companies()}:
            return _("There's no company {0} in ERPNext on the CRM site.").format(
                company
            )
        if self.invoice_item not in {i.get("name") for i in client.service_items()}:
            return _(
                "{0} isn't an enabled service item (a sales item that isn't stocked) on the CRM site."
            ).format(self.invoice_item)
        checks = (
            (self.invoice_taxes_template, client.taxes_templates, _("taxes template")),
            (self.invoice_income_account, client.income_accounts, _("income account")),
            (self.invoice_cost_center, client.cost_centers, _("cost center")),
        )
        for value, options, label in checks:
            if value and value not in {o.get("name") for o in options(company)}:
                return _("{0} isn't an enabled {1} of {2} on the CRM site.").format(
                    value, label, company
                )
        return None
