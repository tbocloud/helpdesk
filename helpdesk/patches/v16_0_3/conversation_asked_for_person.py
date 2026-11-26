# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Testing fixes 2: the chats already handed over to a person (they hold a hand-over message) are
marked, so Copilot stays out of their tickets from now on too."""

import frappe


def execute():
    handed_over = frappe.get_all(
        "HDS Conversation Message",
        filters={"kind": "Hand-over"},
        pluck="conversation",
        distinct=True,
    )
    for name in set(handed_over):
        if frappe.db.exists("HDS Conversation", name):
            frappe.db.set_value(
                "HDS Conversation",
                name,
                "asked_for_person",
                1,
                update_modified=False,
            )
