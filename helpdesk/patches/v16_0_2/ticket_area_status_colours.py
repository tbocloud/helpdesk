"""The ticket area's colours (Phase 15): red only means late, so Open is no longer red.

Only a status still on the colour it was installed with changes; one an admin chose stays as it is.
"""

import frappe

# status: (installed with, now)
COLOURS = {
    "Open": ("Red", "Blue"),
    "Replied": ("Blue", "Amber"),
    "Waiting on Task": ("Orange", "Amber"),
}


def execute():
    for status, (installed, now) in COLOURS.items():
        if frappe.db.get_value("HD Ticket Status", status, "color") == installed:
            frappe.db.set_value(
                "HD Ticket Status", status, "color", now, update_modified=False
            )
