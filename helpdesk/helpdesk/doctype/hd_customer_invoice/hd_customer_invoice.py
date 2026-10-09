# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A draft Sales Invoice created in ERPNext on the CRM site from a customer's billable
time. Created and unlinked only by helpdesk/integrations/crm/invoices.py; see
docs/timesheet-invoicing.md."""

from frappe.model.document import Document


class HDCustomerInvoice(Document):
    pass
