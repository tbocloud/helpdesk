import frappe
from frappe.permissions import add_permission, update_permission_property

DOCTYPE = "Business Health Check"
# The role for the TBO website's API user (docs/business-health-check.md).
API_ROLE = "Health Check API"


def execute():
    """The "Health Check API" role: Create / Read / Write on Business Health Check only,
    and no desk access. Safe to re-run; also enforces desk_access = 0 on an existing role.
    Fresh sites skip patches, so run it there with
    bench --site <site> execute helpdesk.patches.v16_0_2.setup_health_check_api_role.execute"""
    if frappe.db.exists("Role", API_ROLE):
        frappe.db.set_value("Role", API_ROLE, "desk_access", 0)
    else:
        frappe.get_doc(
            {"doctype": "Role", "role_name": API_ROLE, "desk_access": 0}
        ).insert(ignore_permissions=True)
    add_permission(DOCTYPE, API_ROLE, 0)  # adds read
    for ptype in ("create", "write"):
        update_permission_property(DOCTYPE, API_ROLE, 0, ptype, 1)
