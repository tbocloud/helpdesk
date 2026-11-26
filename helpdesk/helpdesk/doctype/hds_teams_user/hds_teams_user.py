# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HDSTeamsUser(Document):
    """A person who talks to the TBO Copilot bot in Teams, matched to an agent by their Microsoft email."""

    def validate(self):
        # the bot acts as this user, so who it is changes only by the one-time link from the bot
        # (helpdesk.copilot.teams.link) or by a System Manager; an Agent Manager may still switch
        # a Teams account off
        if (
            not self.is_new()
            and self.has_value_changed("user")
            and "System Manager" not in frappe.get_roles()
        ):
            frappe.throw(
                _(
                    "Only a System Manager changes which TBO Support person a Teams account acts as."
                ),
                frappe.PermissionError,
            )
