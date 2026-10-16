"""Customers both ways between helpdesk (HD Customer) and the TBO CRM.

On the CRM side a customer is an ERPNext Customer, or a CRM Organization while Frappe
CRM is installed there; both are read. New ones from helpdesk become CRM Organizations
(an ERPNext Customer needs a group and territory the hub can't choose). Once Frappe CRM
is gone from the site, nothing is created there: the ERPNext Customer is the system of
record, so helpdesk-only customers are only counted for someone to add there.

Only what's missing is created: an HD Customer the CRM doesn't have becomes a CRM
Organization, and a CRM Organization or Customer helpdesk doesn't have becomes an HD
Customer.
Names are matched ignoring case and surrounding spaces; existing records are never
changed or deleted.
"""

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError

CUSTOMERS_LABEL = "Customers:"


def key(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def sync_customers() -> dict:
    client = CRMClient.from_settings()
    result = {
        "created_in_crm": [],
        "created_in_helpdesk": [],
        "only_in_helpdesk": [],
        "failed": [],
    }
    # ERPNext Customers, plus CRM Organizations while Frappe CRM is on the site; both
    # come into helpdesk
    has_organizations = client.has_doctype("CRM Organization")
    organizations = (
        client.organizations() if has_organizations else []
    ) + client.erp_customers()
    in_crm = {key(o.get("organization_name") or o.get("name")) for o in organizations}
    customers = frappe.get_all("HD Customer", fields=["name", "domain"])
    in_helpdesk = {key(c.name) for c in customers}

    for customer in customers:
        if key(customer.name) in in_crm:
            continue
        if not has_organizations:
            result["only_in_helpdesk"].append(customer.name)
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
    text = (
        CUSTOMERS_LABEL
        + " "
        + _("{0} added to the CRM, {1} added to helpdesk.").format(
            len(result["created_in_crm"]), len(result["created_in_helpdesk"])
        )
    )
    if result["only_in_helpdesk"]:
        text += " " + _(
            "{0} only in helpdesk; add them as Customers on the CRM site: {1}"
        ).format(
            len(result["only_in_helpdesk"]),
            ", ".join(result["only_in_helpdesk"][:10]),
        )
    if result["failed"]:
        text += " " + _("Failed: {0}").format("; ".join(result["failed"])[:600])
    previous = frappe.db.get_single_value("HD CRM Settings", "last_sync_result") or ""
    # keep the users' part; replace any customers' part an overlapping run left behind
    users_part = previous.split(CUSTOMERS_LABEL)[0].strip()
    frappe.db.set_single_value(
        "HD CRM Settings", "last_sync_result", f"{users_part} {text}".strip()
    )


def fill_ticket_owners() -> dict:
    """Once, on request: customers without a ticket owner get the Account Manager that
    ERPNext on the CRM site names for them, when that person is an active agent here
    (matched by email, ignoring case). Owners already set are never changed.

    CRM Organizations have no account owner, so only ERPNext Customers count.
    """
    from helpdesk.helpdesk.doctype.hd_customer.hd_customer import active_agents

    # {customer: the account managers of the ERPNext Customers with that name}; two
    # Customers can share a name, and with different managers neither is picked
    managers: dict[str, set[str]] = {}
    for c in CRMClient.from_settings().customer_account_managers():
        manager = (c.get("account_manager") or "").strip().casefold()
        if manager:
            managers.setdefault(
                key(c.get("customer_name") or c.get("name")), set()
            ).add(manager)
    agents = {
        agent.casefold(): agent
        for agent in active_agents(
            frappe.get_all("HD Agent", pluck="name", limit_page_length=0)
        )
    }
    result = {"filled": [], "not_an_agent": [], "ambiguous": []}
    unowned = frappe.get_all(
        "HD Customer",
        filters={"ticket_owner": ("is", "not set")},
        pluck="name",
        limit_page_length=0,
    )
    for customer in unowned:
        found = managers.get(key(customer))
        if not found:
            continue
        if len(found) > 1:
            result["ambiguous"].append(customer)
            continue
        agent = agents.get(next(iter(found)))
        if not agent:
            result["not_an_agent"].append(customer)
            continue
        if fill_empty_owner(customer, agent):
            result["filled"].append(customer)
    return result


def fill_customer_domains(apply: bool = False) -> dict:
    """Customers without a Domain get their CRM website's domain, once, on request; with
    `apply` False nothing changes (the Settings preview). Matched by name like the
    customer sync. Left empty: two CRM records with different websites (`ambiguous`),
    a public mail domain (`public`), and a domain another customer already has
    (`taken`), since a domain must point at one customer (docs/ticket-intake.md)."""
    from helpdesk.helpdesk.doctype.hd_customer.hd_customer import (
        clear_domain_cache,
        customer_domains,
        normalize_domain,
        public_email_domains,
    )

    client = CRMClient.from_settings()
    websites: dict[str, set[str]] = {}
    for org in client.organizations() + client.erp_customers():
        domain = normalize_domain(org.get("website"))
        if domain:
            name = org.get("organization_name") or org.get("name")
            websites.setdefault(key(name), set()).add(domain)
    customers = frappe.get_all(
        "HD Customer",
        fields=["name", "domain", "email_domains"],
        limit_page_length=0,
    )
    # {domain: customer}, including the ones this fill picks as it goes
    owners = {
        domain: c.name
        for c in customers
        for domain in customer_domains(c.domain, c.email_domains)
    }
    public = public_email_domains()
    result = {"fill": [], "ambiguous": [], "public": [], "taken": []}
    for customer in customers:
        found = websites.get(key(customer.name))
        if customer.domain or not found:
            continue
        domain = next(iter(found))
        row = {"customer": customer.name, "domain": domain}
        if len(found) > 1:
            result["ambiguous"].append({**row, "domain": ", ".join(sorted(found))})
        elif domain in public:
            result["public"].append(row)
        elif overlaps_another(domain, customer.name, owners):
            result["taken"].append(row)
        else:
            owners[domain] = customer.name
            result["fill"].append(row)
    if apply:
        result["fill"] = [row for row in result["fill"] if fill_empty_domain(**row)]
        clear_domain_cache()
    return result


def overlaps_another(domain: str, customer: str, owners: dict[str, str]) -> bool:
    """Whether another customer has `domain`, a parent of it or a subdomain of it: a
    sender there would then match both, and new tickets would find neither."""
    return any(
        owner != customer
        and (
            domain == other
            or domain.endswith("." + other)
            or other.endswith("." + domain)
        )
        for other, owner in owners.items()
    )


def fill_empty_domain(customer: str, domain: str) -> bool:
    """Set the domain only while it is still empty, so one typed in meanwhile stays."""
    table = frappe.qb.DocType("HD Customer")
    (
        frappe.qb.update(table)
        .set(table.domain, domain)
        .where(
            (table.name == customer) & (table.domain.isnull() | (table.domain == ""))
        )
        .run()
    )
    return frappe.db.get_value("HD Customer", customer, "domain") == domain


def fill_empty_owner(customer: str, agent: str) -> bool:
    """Set the owner only while it is still empty, so an owner someone set meanwhile
    stays; an active agent on an empty owner is all validate_ticket_owners would check."""
    table = frappe.qb.DocType("HD Customer")
    (
        frappe.qb.update(table)
        .set(table.ticket_owner, agent)
        .where(
            (table.name == customer)
            & (table.ticket_owner.isnull() | (table.ticket_owner == ""))
        )
        .run()
    )
    return frappe.db.get_value("HD Customer", customer, "ticket_owner") == agent
