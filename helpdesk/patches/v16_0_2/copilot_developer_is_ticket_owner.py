import frappe

from helpdesk.helpdesk.doctype.hd_customer.hd_customer import active_agents


def execute():
    """Phase 12: Copilot's developer is the customer's ticket owner. A customer with no owner
    but with Copilot's older Assigned Developer gets that developer as its owner, when they
    are an active agent. Set directly: the patch is not a person who may set owners."""
    rows = frappe.get_all(
        "HD Customer",
        filters={
            "custom_assigned_developer": ["is", "set"],
            "ticket_owner": ["is", "not set"],
        },
        fields=["name", "custom_assigned_developer"],
    )
    agents = active_agents([row.custom_assigned_developer for row in rows])
    for row in rows:
        if row.custom_assigned_developer in agents:
            frappe.db.set_value(
                "HD Customer",
                row.name,
                "ticket_owner",
                row.custom_assigned_developer,
                update_modified=False,
            )
