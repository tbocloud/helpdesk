# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from helpdesk.copilot.settings import seed_default_templates, validate_limits


class HDSCopilotSettings(Document):
    def validate(self):
        self.seed_default_templates()
        self.validate_limits()

    def seed_default_templates(self):
        seed_default_templates(self)

    def validate_limits(self):
        validate_limits(self)
