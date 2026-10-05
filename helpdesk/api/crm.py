"""Settings → CRM: test the connection to the TBO CRM site and sync users now."""

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError
from helpdesk.integrations.crm.users import helpdesk_users, sync_users

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


@frappe.whitelist()
def get_overview() -> dict:
    require_admin()
    return {"helpdesk_users": len(helpdesk_users())}


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
def sync_users_now() -> dict:
    require_admin()
    try:
        result = sync_users()
    except CRMError as e:
        return {"ok": False, "message": str(e)}
    return {
        "ok": not result["failed"],
        "message": frappe.db.get_single_value("HD CRM Settings", "last_sync_result"),
        **result,
    }
