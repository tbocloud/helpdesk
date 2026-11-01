"""The Customers and Contacts lists: one page of rows with the counts agents scan for.

Every read goes through frappe.get_list, so a row or a count only includes what the
viewer may see (e.g. tickets outside their teams are not counted).
"""

import frappe
from frappe import _

from helpdesk.api.home import OPEN_TICKET_CATEGORIES
from helpdesk.customer_health import AT_RISK, HEALTHY, WATCH, all_health, brief
from helpdesk.customer_health import sort_key as health_order
from helpdesk.utils import agent_only, aggregate

PAGE_LENGTH = 50
CLOSED_PROJECT_STATUSES = ("not in", ["Completed", "Cancelled"])
CUSTOMER_SORTS = {
    "name": "customer_name asc",
    "newest": "creation desc",
    # worst first, ordered in Python from the cached health (see by_health)
    "health": "customer_name asc",
}
# the Customers list's health filter; `attention` is at risk or watch
HEALTH_FILTERS = {
    AT_RISK: {AT_RISK},
    WATCH: {WATCH},
    HEALTHY: {HEALTHY},
    "attention": {AT_RISK, WATCH},
}
CUSTOMER_FIELDS = [
    "name",
    "customer_name",
    "domain",
    "image",
    "creation",
    "ticket_owner",
]
# the Customers list's owner filter: customers nobody owns yet, so managers fill the gaps
OWNER_FILTERS = {"none": {"ticket_owner": ("is", "not set")}}
CONTACT_SORTS = {"name": "full_name asc", "newest": "creation desc"}
OPEN_INVITATION = ("in", ["Pending", "Expired"])


@frappe.whitelist(methods=["GET"])
@agent_only
def get_customer_directory(
    search: str = "",
    sort: str = "name",
    start: int = 0,
    health: str = "",
    owner: str = "",
) -> dict:
    """A page of customers with their ticket owner, health, open tickets, active
    projects and ERP connection.

    `health` narrows to one status, or to `attention` (at risk or watch); `owner`
    to `none`, the customers without a ticket owner.
    """
    or_filters = search_filters(search, ["customer_name", "domain"])
    order_by = sort_order(sort, CUSTOMER_SORTS)
    if health and health not in HEALTH_FILTERS:
        frappe.throw(
            _("Filter health by one of: {0}").format(", ".join(HEALTH_FILTERS))
        )
    if owner and owner not in OWNER_FILTERS:
        frappe.throw(_("Filter owner by one of: {0}").format(", ".join(OWNER_FILTERS)))
    filters = OWNER_FILTERS.get(owner)
    healths = all_health()
    if sort == "health" or health:
        customers, has_more, total = by_health(
            healths, filters, or_filters, order_by, sort == "health", health, start
        )
    else:
        customers, has_more = page(
            "HD Customer",
            fields=CUSTOMER_FIELDS,
            or_filters=or_filters,
            order_by=order_by,
            start=start,
            filters=filters,
        )
        total = count("HD Customer", or_filters, filters)
    names = [c.name for c in customers]
    tickets = open_ticket_counts("customer", names)
    projects = active_project_counts(names)
    connections = connection_status(names)
    owners = agent_names({c.ticket_owner for c in customers} - {None})
    for c in customers:
        c["ticket_owner_name"] = owners.get(c.ticket_owner)
        c["health"] = brief(healths.get(c.name))
        c["open_tickets"] = tickets.get(c.name, 0)
        c["active_projects"] = projects.get(c.name, 0)
        c["connection"] = connections.get(c.name)
    return {"rows": customers, "has_more": has_more, "total": total}


def agent_names(agents: set[str]) -> dict[str, str]:
    """{agent: their name} for the ticket owners on a page."""
    if not agents:
        return {}
    rows = frappe.get_all(
        "HD Agent",
        filters={"name": ("in", list(agents))},
        fields=["name", "agent_name"],
    )
    return {r.name: r.agent_name or r.name for r in rows}


def by_health(
    healths: dict,
    filters: dict | None,
    or_filters: list | None,
    order_by: str,
    worst_first: bool,
    health: str,
    start: int,
) -> tuple[list[dict], bool, int]:
    """A page of the customers the viewer may read, narrowed and ordered by health.

    Health isn't a column, so this reads every matching customer (one query, no
    counts) and pages in Python.
    """
    rows = frappe.get_list(
        "HD Customer",
        fields=CUSTOMER_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        limit_page_length=0,
    )
    if health:
        wanted = HEALTH_FILTERS[health]
        rows = [r for r in rows if (healths.get(r.name) or {}).get("status") in wanted]
    if worst_first:
        # a stable sort keeps the name order among customers in the same health
        rows.sort(key=lambda r: health_order(healths.get(r.name)))
    start = max(int(start or 0), 0)
    end = start + PAGE_LENGTH
    return rows[start:end], len(rows) > end, len(rows)


@frappe.whitelist(methods=["GET"])
@agent_only
def get_contact_directory(search: str = "", sort: str = "name", start: int = 0) -> dict:
    """A page of contacts with their customers, open tickets and portal access."""
    or_filters = search_filters(search, ["full_name", "email_id", "mobile_no"])
    contacts, has_more = page(
        "Contact",
        fields=[
            "name",
            "full_name",
            "email_id",
            "mobile_no",
            "phone",
            "image",
            "user",
            "creation",
        ],
        or_filters=or_filters,
        order_by=sort_order(sort, CONTACT_SORTS),
        start=start,
    )
    names = [c.name for c in contacts]
    customers = contact_customers(names)
    tickets = open_ticket_counts("contact", names)
    invited = pending_invitations([c.name for c in contacts if not c.user])
    for c in contacts:
        c["mobile_no"] = c.mobile_no or c.phone
        c["customers"] = customers.get(c.name, [])
        c["open_tickets"] = tickets.get(c.name, 0)
        c["portal"] = portal_status(c, invited)
        del c["phone"]
    return {
        "rows": contacts,
        "has_more": has_more,
        "total": count("Contact", or_filters),
    }


def search_filters(search: str, fields: list[str]) -> list[list] | None:
    text = (search or "").strip()
    if not text:
        return None
    return [[field, "like", f"%{text}%"] for field in ["name", *fields]]


def sort_order(sort: str, sorts: dict[str, str]) -> str:
    if sort not in sorts:
        frappe.throw(_("Sort by one of: {0}").format(", ".join(sorts)))
    return sorts[sort]


def page(
    doctype: str,
    fields: list[str],
    or_filters: list | None,
    order_by: str,
    start: int,
    filters: dict | None = None,
) -> tuple[list[dict], bool]:
    """One page of rows, and whether there are more; asks for one extra row to know."""
    rows = frappe.get_list(
        doctype,
        fields=fields,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        limit_start=max(int(start or 0), 0),
        limit_page_length=PAGE_LENGTH + 1,
    )
    return rows[:PAGE_LENGTH], len(rows) > PAGE_LENGTH


def count(doctype: str, or_filters: list | None, filters: dict | None = None) -> int:
    rows = frappe.get_list(
        doctype,
        fields=[aggregate("count", "name", "total")],
        filters=filters,
        or_filters=or_filters,
    )
    return rows[0].total if rows else 0


def open_ticket_counts(field: str, names: list[str]) -> dict[str, int]:
    """Open and paused tickets per customer or contact, as `field` on the ticket says."""
    if not names:
        return {}
    rows = frappe.get_list(
        "HD Ticket",
        filters={field: ("in", names), "status_category": OPEN_TICKET_CATEGORIES},
        fields=[f"{field} as owner_name", aggregate("count", "name", "count")],
        group_by=field,
    )
    return {r.owner_name: r.count for r in rows}


def active_project_counts(customers: list[str]) -> dict[str, int]:
    """Projects per customer that are neither completed nor cancelled."""
    if not customers:
        return {}
    rows = frappe.get_list(
        "Project",
        filters={"customer": ("in", customers), "status": CLOSED_PROJECT_STATUSES},
        fields=["customer", aggregate("count", "name", "count")],
        group_by="customer",
    )
    return {r.customer: r.count for r in rows}


def connection_status(
    customers: list[str], ignore_permissions: bool = False
) -> dict[str, dict]:
    """Each customer's ERP connection: its status and site, the latest one if several.

    Customer health reads every customer's with `ignore_permissions`, as it is
    computed once for everyone (helpdesk/customer_health.py).
    """
    if not customers:
        return {}
    rows = frappe.get_list(
        "HDS Support Connection",
        filters={"customer_name": ("in", customers)},
        fields=["customer_name", "connection_status", "site_url"],
        order_by="modified desc",
        ignore_permissions=ignore_permissions,
    )
    result: dict[str, dict] = {}
    for r in rows:
        result.setdefault(
            r.customer_name,
            {"status": r.connection_status or "Pending", "site_url": r.site_url},
        )
    return result


def contact_customers(contacts: list[str]) -> dict[str, list[str]]:
    """The customers each contact belongs to, from the customers' member tables."""
    if not contacts:
        return {}
    rows = frappe.get_list(
        "HD Customer",
        filters=[["HD Customer Member", "contact_name", "in", contacts]],
        fields=["name", "`tabHD Customer Member`.contact_name as contact"],
        order_by="name asc",
    )
    result: dict[str, list[str]] = {}
    for r in rows:
        result.setdefault(r.contact, []).append(r.name)
    return result


def pending_invitations(contacts: list[str]) -> dict[str, str]:
    """The latest pending or expired helpdesk invitation per contact without a user.

    Read with get_all, as get_contact_info does for one contact: User Invitation
    is a core doctype agents may not read, and only the status of contacts the
    viewer could list goes out.
    """
    if not contacts:
        return {}
    rows = frappe.get_all(
        "User Invitation",
        filters={
            "contact": ("in", contacts),
            "app_name": "helpdesk",
            "status": OPEN_INVITATION,
        },
        fields=["contact", "status"],
        order_by="creation desc",
    )
    result: dict[str, str] = {}
    for r in rows:
        result.setdefault(r.contact, r.status)
    return result


def portal_status(contact: dict, invited: dict[str, str]) -> str | None:
    """`active` with a user, `invited` or `expired` with an open invitation, else None."""
    if contact.user:
        return "active"
    status = invited.get(contact.name)
    if not status:
        return None
    return "expired" if status == "Expired" else "invited"
