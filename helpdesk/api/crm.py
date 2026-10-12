"""Settings → CRM: test the connection to the TBO CRM site, sync users, customers,
holidays and leave now, and read the invoicing and holiday list pickers from it."""

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError
from helpdesk.integrations.crm.customers import sync_customers
from helpdesk.integrations.crm.holidays import sync_holidays_and_leave
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


@frappe.whitelist()
def get_invoicing_options(company: str | None = None) -> dict:
    """The pickers of Settings → CRM → Invoicing, read live from ERPNext on the CRM site:
    companies and service items, and for `company` its taxes templates, income accounts
    and cost centers."""
    require_admin()
    try:
        client = CRMClient.from_settings()
        options = {
            "companies": client.companies(),
            "items": client.service_items(),
            "taxes_templates": [],
            "income_accounts": [],
            "cost_centers": [],
        }
        if company:
            options["taxes_templates"] = client.taxes_templates(company)
            options["income_accounts"] = client.income_accounts(company)
            options["cost_centers"] = client.cost_centers(company)
    except CRMError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, **options}


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


@frappe.whitelist()
def get_holiday_options() -> dict:
    """The holiday list picker of Settings → CRM, read live from ERPNext on the CRM site:
    every Holiday List with its dates, and each company's default list."""
    require_admin()
    try:
        client = CRMClient.from_settings()
        lists = sorted(
            client.holiday_lists(),
            key=lambda row: str(row.get("from_date") or ""),
            reverse=True,
        )
        companies = client.company_holiday_lists()
    except CRMError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "lists": lists, "companies": companies}


@frappe.whitelist(methods=["POST"])
def sync_holidays_now() -> dict:
    """Holidays and approved leave from the CRM site, now."""
    require_admin()
    result = sync_holidays_and_leave()
    return {
        "ok": result["ok"],
        "message": "\n".join(result["problems"])
        or frappe.db.get_single_value("HD CRM Settings", "holiday_sync_result"),
        "holidays": result["holidays"],
        "leave": result["leave"],
    }
