# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Phase 25: Copilot on infrastructure starts on, investigating and proposing; the places it may
change start empty and are listed by a person in Copilot settings ("Copilot May Change"). No site
or bench is named here: a site that runs this patch (the live TBO Support among them) must not
inherit the test bench's names."""

import frappe

SETTINGS = "HDS Copilot Settings"
DEFAULTS = {
    "infra_investigate": 1,
    "infra_propose": 1,
    "infra_dollar_cap": 1,
}


def execute():
    for field, value in DEFAULTS.items():
        stored = frappe.db.sql(
            "select value from tabSingles where doctype=%s and field=%s",
            (SETTINGS, field),
        )
        if not stored:
            frappe.db.set_single_value(SETTINGS, field, value)
