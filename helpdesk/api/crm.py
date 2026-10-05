"""Settings → CRM: test the connection to the TBO CRM site and sync users and customers now."""

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError
from helpdesk.integrations.crm.customers import sync_customers
from helpdesk.integrations.crm.users import sync_users

ADMIN_ROLES = {"System Manager", "Agent Manager"}


def require_admin():
    # frappe.only_for is skipped in tests, so the roles are checked here
    if frappe.session.user != "Administrator" and not (
        ADMIN_ROLES & set(frappe.get_roles())
    ):
        frappe.throw(
            _("Only System Managers and Agent Managers can manage the CRM connection."),
            frappe.PermissionError,
        )


@frappe.whitelist(methods=["POST"])
def test_connection() -> dict:
    require_admin()
    try:
        user = CRMClient.from_settings().logged_user()
    except CRMError as e:
        return {"ok": False, "message": str(e)}
    return {
        "ok": True,
        "message": _("Connected as {0}.").format(user or _("the API user")),
    }


@frappe.whitelist(methods=["POST"])
def sync_now() -> dict:
    """Users both ways, then customers both ways (when switched on)."""
    require_admin()
    try:
        users = sync_users()
        customers = (
            sync_customers()
            if frappe.db.get_single_value("HD CRM Settings", "sync_customers")
            else {"failed": []}
        )
    except CRMError as e:
        return {"ok": False, "message": str(e)}
    return {
        "ok": not (users["failed"] or customers["failed"]),
        "message": frappe.db.get_single_value("HD CRM Settings", "last_sync_result"),
        "users": users,
        "customers": customers,
    }
