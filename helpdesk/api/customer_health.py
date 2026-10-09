"""A customer's health for the customer page (docs/customer-health.md)."""

import frappe

from helpdesk.customer_health import all_health, present
from helpdesk.utils import agent_only


@frappe.whitelist(methods=["GET"])
@agent_only
def get_customer_health(customer: str) -> dict | None:
    """The customer's status and every signal with its value, rule and link.

    None when the customer is newer than the cached health.
    """
    customer = str(customer)
    frappe.has_permission("HD Customer", "read", doc=customer, throw=True)
    health = all_health().get(customer)
    return present(health, customer) if health else None
