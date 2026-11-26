import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from helpdesk.setup.install import get_custom_fields


def execute():
    """Phase 22: Copilot's first and second developer start as the customer's ticket owner and
    backup ticket owner, so nobody types them twice; after this they are set on their own. The
    new settings start at their defaults: risk alerts also to the coordinators, and new tickets
    to the coordinators in Teams and TBO Support.
    The fields are made first: the patches run before after_migrate adds custom fields."""
    create_custom_fields({"HD Customer": get_custom_fields()["HD Customer"]})
    # a new field's default never reaches settings saved before it (an unset tick reads as 0)
    for field, value in (
        ("risk_alert_coordinators", 1),
        ("new_ticket_notice", "Teams and TBO Support"),
    ):
        if not frappe.db.exists(
            "Singles", {"doctype": "HDS Copilot Settings", "field": field}
        ):
            frappe.db.set_single_value("HDS Copilot Settings", field, value)
    for row in frappe.get_all(
        "HD Customer",
        fields=[
            "name",
            "ticket_owner",
            "backup_ticket_owner",
            "custom_assigned_developer",
            "custom_first_developer",
            "custom_second_developer",
        ],
    ):
        values = {}
        first = row.ticket_owner or row.custom_assigned_developer
        if first and not row.custom_first_developer:
            values["custom_first_developer"] = first
        if row.backup_ticket_owner and not row.custom_second_developer:
            values["custom_second_developer"] = row.backup_ticket_owner
        if values:
            frappe.db.set_value("HD Customer", row.name, values, update_modified=False)
