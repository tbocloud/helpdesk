# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

DOCTYPE = "HD Lead Mirror"
# column on the copy: where it is in the ERP's list row ("row") or lead ("lead"), by the key there
FROM_ROW = {
    "lead_name": "lead_name",
    "company_name": "company_name",
    "mobile_no": "mobile_no",
    "email_id": "email_id",
    "tbo_stage": "tbo_stage",
    "lead_owner": "lead_owner",
    "department": "tbo_department",
    "product": "product",
    "score": "score",
    "industry": "industry",
    "state": "state",
    "district": "district",
    "org_size": "org_size",
    "next_follow_up": "next_follow_up",
    "last_call_result": "last_call_result",
}
FROM_LEAD = {
    "status": "status",
    "temperature": "tbo_temperature",
    "source": "source",
    "erp_created": "creation",
}


class HDLeadMirror(Document):
    """The hub's read-only copy of one ERP lead (docs/lead-mirror.md). Nobody edits it by hand:
    the sync makes it with `upsert` and drops it with `remove`; the ERP always wins."""

    @classmethod
    def upsert(cls, entry: dict) -> "HDLeadMirror":
        """Make the copy of a lead from one `get_leads_bulk` entry, or bring it up to date.
        Safe to repeat: the same entry leaves the same copy."""
        name = entry["name"]
        doc = (
            frappe.get_doc(DOCTYPE, name)
            if frappe.db.exists(DOCTYPE, name)
            else frappe.new_doc(DOCTYPE)
        )
        doc.update(cls.columns_of(entry))
        doc.erp_name = name
        doc.set("assignees", [{"user": user} for user in entry.get("assignees") or []])
        doc.flags.ignore_permissions = True
        doc.save()
        return doc

    @classmethod
    def remove(cls, name: str) -> None:
        """Drop the copy of a lead the ERP no longer has (deleted, or merged into another)."""
        if frappe.db.exists(DOCTYPE, name):
            frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)

    @classmethod
    def clear(cls) -> None:
        """Drop every copy, for a rebuild. The ERP is untouched."""
        frappe.db.delete("HD Lead Mirror Assignee", {"parenttype": DOCTYPE})
        frappe.db.delete(DOCTYPE)

    @staticmethod
    def columns_of(entry: dict) -> dict:
        row = entry.get("row") or {}
        lead = (entry.get("payload") or {}).get("lead") or {}
        columns = {column: row.get(key) for column, key in FROM_ROW.items()}
        columns.update({column: lead.get(key) for column, key in FROM_LEAD.items()})
        columns.update(
            score=int(columns["score"] or 0),
            erp_modified=entry.get("modified"),
            synced_at=now_datetime(),
            list_row=frappe.as_json(row),
            payload=frappe.as_json(entry.get("payload") or {}),
        )
        return columns
