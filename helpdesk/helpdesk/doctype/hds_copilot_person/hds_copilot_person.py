# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDSCopilotPerson(Document):
    """One person Copilot goes to, chosen in settings (a customer's project coordinators, the
    common coordinators, the people told about risky work); never named in the code."""

    pass
