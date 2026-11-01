# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

PENDING = "Pending"
CONNECTED = "Connected"
EXPIRED = "Expired"
ERROR = "Error"


class HDMetaConnection(Document):
    def before_save(self):
        self.set_customer()

    def set_customer(self):
        """The project's HD Customer, when it names one."""
        from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
            project_customer_fields,
        )

        for field in project_customer_fields():
            value = frappe.db.get_value("Project", self.project, field)
            if value and frappe.db.exists("HD Customer", value):
                self.customer = value
                return

    def page_token(self) -> str | None:
        return self.get_password("page_access_token", raise_exception=False)

    def user_token(self) -> str | None:
        return self.get_password("user_access_token", raise_exception=False)

    def mark(self, status: str, error: str | None = None):
        """Records a status (and why) without touching modified or running hooks."""
        self.db_set({"status": status, "last_error": error}, update_modified=False)
