# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Site Registry: which customer site (and which apps) a ticket belongs to."""

import frappe


def registry_for_ticket(ticket: str):
    """The Production site of a ticket: by its connection first, else by its customer; None if unknown."""
    connection, customer = frappe.db.get_value(
        "HD Ticket", ticket, ["custom_qcs_connection", "customer"]
    )
    name = None
    if connection:
        name = frappe.db.get_value(
            "HDS Site Registry", {"connection": connection, "environment": "Production"}
        )
    if not name and customer:
        name = frappe.db.get_value(
            "HDS Site Registry",
            {"customer_name": customer, "environment": "Production"},
        )
    return frappe.get_doc("HDS Site Registry", name) if name else None


def apps_for(registry) -> list[dict]:
    """The apps on a registered site, as plain dicts a worker can be handed."""
    return [
        {
            "app": row.app,
            "repository": row.repository,
            "branch": row.branch,
            "deployed_commit": row.deployed_commit,
            "drift_status": row.drift_status,
        }
        for row in registry.apps
    ]
