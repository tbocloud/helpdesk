# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDLeave(Document):
    """Approved leave synced from the CRM site; see helpdesk.integrations.crm.holidays."""
