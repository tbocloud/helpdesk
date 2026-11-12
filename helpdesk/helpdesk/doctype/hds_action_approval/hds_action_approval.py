# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDSActionApproval(Document):
    """One person's approval of one action (a Press action, an AWS change, a repair) with the
    exact thing that runs; requested, decided and marked executed only through
    helpdesk.copilot.actions."""

    pass
