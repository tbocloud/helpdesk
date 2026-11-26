# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HDSCopilotPullRequest(Document):
    """A developer's pull request handed to Copilot to take live (Phase 26): Copilot fixes what
    CodeRabbit and CI find, asks one approver, merges and deploys. Written only through
    helpdesk.copilot.pulls."""

    pass
