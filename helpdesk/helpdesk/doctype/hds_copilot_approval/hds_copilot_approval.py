# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDSCopilotApproval(Document):
    """One person's approval of one Copilot fix at one commit; decided only through helpdesk.copilot.approvals."""

    pass
