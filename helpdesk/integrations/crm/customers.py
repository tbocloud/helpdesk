"""Customers both ways between helpdesk (HD Customer) and the TBO CRM (CRM Organization).

Only what's missing is created: an HD Customer the CRM doesn't have becomes a CRM
Organization, and a CRM Organization helpdesk doesn't have becomes an HD Customer.
Names are matched ignoring case and surrounding spaces; existing records are never
changed or deleted.
"""

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError


def key(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def sync_customers() -> dict:
    client = CRMClient.from_settings()
    result = {"created_in_crm": [], "created_in_helpdesk": [], "failed": []}
    organizations = client.organizations()
    in_crm = {key(o.get("organization_name") or o.get("name")) for o in organizations}
    customers = frappe.get_all("HD Customer", fields=["name", "domain"])
    in_helpdesk = {key(c.name) for c in customers}

    for customer in customers:
        if key(customer.name) in in_crm:
            continue
        try:
            client.create_organization(customer.name, customer.domain)
            result["created_in_crm"].append(customer.name)
        except CRMError as e:
            result["failed"].append(f"{customer.name}: {str(e)}")

    for org in organizations:
        name = " ".join((org.get("organization_name") or org.get("name") or "").split())
        if not name or key(name) in in_helpdesk:
            continue
        try:
            frappe.get_doc(
                {
                    "doctype": "HD Customer",
                    "customer_name": name,
                    "domain": org.get("website") or None,
                }
            ).insert(ignore_permissions=True)
            in_helpdesk.add(key(name))
            result["created_in_helpdesk"].append(name)
        except frappe.ValidationError as e:
            result["failed"].append(f"{name}: {str(e)}")

    record(result)
    return result


def record(result: dict):
    """Add the customer counts to the last sync result the user sync just wrote."""
    text = _("Customers: {0} added to the CRM, {1} added to helpdesk.").format(
        len(result["created_in_crm"]), len(result["created_in_helpdesk"])
    )
    if result["failed"]:
        text += " " + _("Failed: {0}").format("; ".join(result["failed"])[:600])
    previous = frappe.db.get_single_value("HD CRM Settings", "last_sync_result") or ""
    frappe.db.set_single_value(
        "HD CRM Settings", "last_sync_result", f"{previous} {text}".strip()
    )
