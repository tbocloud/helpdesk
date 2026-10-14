# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now


class HDIntakeLog(Document):
    """An incoming mail the intake rules kept from opening a ticket (docs/ticket-intake.md)."""

    @staticmethod
    def clear_old_logs(days=30):
        table = frappe.qb.DocType("HD Intake Log")
        frappe.db.delete(
            table, filters=(table.creation < (Now() - Interval(days=days)))
        )
