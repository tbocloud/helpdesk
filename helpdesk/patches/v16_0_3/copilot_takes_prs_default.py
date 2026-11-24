# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Phase 26: Copilot takes developers' pull requests live when they ask (on)."""

import frappe


def execute():
    stored = frappe.db.sql(
        "select value from tabSingles where doctype=%s and field=%s",
        ("HDS Copilot Settings", "copilot_takes_prs"),
    )
    if not stored:
        frappe.db.set_single_value("HDS Copilot Settings", "copilot_takes_prs", 1)
