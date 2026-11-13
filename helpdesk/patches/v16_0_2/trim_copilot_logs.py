# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""TBO Copilot Phase 21: the Copilot logs already written keep identifiers and fingerprints,
never text or results, like the rows written from now on (helpdesk.copilot.audit)."""

import json

import frappe

from helpdesk.copilot import audit

BATCH = 500


def execute():
    trim("HDS Copilot Call Log", {"arguments": "arguments", "result": "result"})
    trim(
        "HDS Remote Audit Log",
        {
            "arguments": "arguments",
            "result": "result_summary",
            "error": "error_message",
        },
    )


def trim(doctype: str, fields: dict):
    if not frappe.db.table_exists(doctype):
        return
    table = frappe.qb.DocType(doctype)
    start = 0
    while True:
        rows = (
            frappe.qb.from_(table)
            .select(table.name, *[table[f] for f in fields.values()])
            .orderby(table.name)
            .limit(BATCH)
            .offset(start)
            .run(as_dict=True)
        )
        if not rows:
            break
        for row in rows:
            values = {
                fields["arguments"]: audit.safe_arguments(
                    parsed(row[fields["arguments"]])
                ),
                fields["result"]: audit.result_size(row[fields["result"]]),
            }
            if "error" in fields:
                values[fields["error"]] = audit.error_line(row[fields["error"]])
            frappe.db.set_value(doctype, row.name, values, update_modified=False)
        start += BATCH


def parsed(text):
    """The stored arguments as a dict; text that is not JSON (or was cut at 2,000 characters) is
    kept as one fingerprint."""
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {"text": text}
    return value if isinstance(value, dict) else {"value": value}
