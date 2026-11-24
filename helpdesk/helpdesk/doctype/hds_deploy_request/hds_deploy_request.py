# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from helpdesk.copilot import deploy


class HDSDeployRequest(Document):
    """One Copilot deploy of a merged fix through Press: when, which sites, Press's progress and the check after; changed only by helpdesk.copilot.deploy."""

    def validate(self):
        deploy.keep_sites(self)
