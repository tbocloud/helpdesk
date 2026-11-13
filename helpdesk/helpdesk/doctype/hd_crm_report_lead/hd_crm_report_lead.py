# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

DOCTYPE = "HD CRM Report Lead"
# the columns the sync works out for each lead (helpdesk.crm_dashboard.sync.RowBuilder)
COLUMNS = (
    "source",
    "remote_name",
    "excluded",
    "company",
    "branch",
    "department",
    "team",
    "employee",
    "lead_owner",
    "status",
    "category",
    "lead_source",
    "expected_revenue",
    "won_value",
    "created_on",
    "created_month",
    "closed_on",
    "closing_days",
    "remote_modified",
    "raw",
)
CHUNK = 500


class HDCRMReportLead(Document):
    """The hub's reporting copy of one lead of a data source: its mapped fields as the source
    sent them (`raw`) and the columns the dashboards count by. Nobody edits it; the sync
    writes it in bulk and the source always wins (docs/crm-dashboard.md)."""

    @staticmethod
    def name_of(source: str, remote_name: str) -> str:
        return f"{source}::{remote_name}"

    @classmethod
    def write(cls, rows: list[dict]) -> None:
        """Make or replace these copies, in chunks: each row has every one of COLUMNS."""
        now = now_datetime()
        user = frappe.session.user
        fields = [
            "name",
            "creation",
            "modified",
            "owner",
            "modified_by",
            "docstatus",
            *COLUMNS,
        ]
        for start in range(0, len(rows), CHUNK):
            chunk = rows[start : start + CHUNK]
            names = [cls.name_of(r["source"], r["remote_name"]) for r in chunk]
            frappe.db.delete(DOCTYPE, {"name": ("in", names)})
            frappe.db.bulk_insert(
                DOCTYPE,
                fields,
                [
                    (name, now, now, user, user, 0, *(row[c] for c in COLUMNS))
                    for name, row in zip(names, chunk)
                ],
            )

    @classmethod
    def remove(cls, source: str, remote_names: list[str]) -> None:
        names = [cls.name_of(source, n) for n in remote_names]
        for start in range(0, len(names), CHUNK):
            frappe.db.delete(DOCTYPE, {"name": ("in", names[start : start + CHUNK])})
