# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.consts import TRIAGE_CATEGORIES


class HDIntakeSettings(Document):
    """Settings → Ticket intake: mail rules, routing after triage, customer detection
    and the feedback request on close (docs/ticket-intake.md)."""

    def validate(self):
        self.validate_rules()
        self.validate_routes()

    def validate_rules(self):
        for rule in self.rules:
            rule.label = (rule.label or "").strip()
            if not (rule.sender_pattern or rule.subject_pattern):
                frappe.throw(
                    _("Rule “{0}”: add a sender, a subject pattern or both.").format(
                        rule.label
                    )
                )
            if rule.subject_pattern:
                try:
                    re.compile(rule.subject_pattern)
                except re.error as e:
                    frappe.throw(
                        _(
                            "Rule “{0}”: the subject pattern isn't a valid regular expression ({1})."
                        ).format(rule.label, str(e))
                    )

    def validate_routes(self):
        seen = set()
        for route in self.routes:
            if route.category not in TRIAGE_CATEGORIES:
                frappe.throw(
                    _("“{0}” isn't a triage category. Use one of: {1}.").format(
                        route.category, ", ".join(TRIAGE_CATEGORIES)
                    )
                )
            if route.category in seen:
                frappe.throw(
                    _("The category {0} is routed twice; keep one row.").format(
                        route.category
                    )
                )
            seen.add(route.category)
