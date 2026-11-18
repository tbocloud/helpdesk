# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Phase 25: Copilot on infrastructure starts on, with the demo bench as the only place it may change."""

import frappe

SETTINGS = "HDS Copilot Settings"
DEFAULTS = {
    "infra_investigate": 1,
    "infra_propose": 1,
    "infra_dollar_cap": 1,
    "infra_may_change": "bench-0015\ndemo-tbo.tbocloud.in\ndemo-alpha.tbocloud.in\ndemo-beta.tbocloud.in",
}


def execute():
    for field, value in DEFAULTS.items():
        stored = frappe.db.sql(
            "select value from tabSingles where doctype=%s and field=%s",
            (SETTINGS, field),
        )
        if not stored:
            frappe.db.set_single_value(SETTINGS, field, value)
