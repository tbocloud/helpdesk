# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDSCopilotRolePerson(Document):
    """One person in one of Copilot's roles (Phase 23): main or a fallback, for every customer
    (HDS Copilot Settings → People) or for one customer (HD Customer → Copilot People). Nobody is
    named in the code; helpdesk.copilot.people reads these rows."""

    pass
