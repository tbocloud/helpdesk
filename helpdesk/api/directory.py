"""The Customers and Contacts lists: one page of rows with the counts agents scan for.

Every read goes through frappe.get_list, so a row or a count only includes what the
viewer may see (e.g. tickets outside their teams are not counted).
"""

import frappe
from frappe import _

from helpdesk.api.home import OPEN_TICKET_CATEGORIES
from helpdesk.utils import agent_only

PAGE_LENGTH = 50
CLOSED_PROJECT_STATUSES = ("not in", ["Completed", "Cancelled"])
CUSTOMER_SORTS = {"name": "customer_name asc", "newest": "creation desc"}
CONTACT_SORTS = {"name": "full_name asc", "newest": "creation desc"}
OPEN_INVITATION = ("in", ["Pending", "Expired"])


@frappe.whitelist(methods=["GET"])
@agent_only
def get_customer_directory(
    search: str = "", sort: str = "name", start: int = 0
) -> dict:
    """A page of customers with their open tickets, active projects and ERP connection."""
    or_filters = search_filters(search, ["customer_name", "domain"])
    customers, has_more = page(
        "HD Customer",
        fields=["name", "customer_name", "domain", "image", "creation"],
        or_filters=or_filters,
        order_by=sort_order(sort, CUSTOMER_SORTS),
        start=start,
    )
    names = [c.name for c in customers]
    tickets = open_ticket_counts("customer", names)
    projects = active_project_counts(names)
    connections = connection_status(names)
    for c in customers:
        c["open_tickets"] = tickets.get(c.name, 0)
        c["active_projects"] = projects.get(c.name, 0)
        c["connection"] = connections.get(c.name)
    return {
        "rows": customers,
        "has_more": has_more,
        "total": count("HD Customer", or_filters),
    }


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
) -> tuple[list[dict], bool]:
    """One page of rows, and whether there are more; asks for one extra row to know."""
    rows = frappe.get_list(
        doctype,
        fields=fields,
        or_filters=or_filters,
        order_by=order_by,
        limit_start=max(int(start or 0), 0),
        limit_page_length=PAGE_LENGTH + 1,
    )
    return rows[:PAGE_LENGTH], len(rows) > PAGE_LENGTH


def count(doctype: str, or_filters: list | None) -> int:
    rows = frappe.get_list(
        doctype, fields=["count(name) as total"], or_filters=or_filters
    )
    return rows[0].total if rows else 0


def open_ticket_counts(field: str, names: list[str]) -> dict[str, int]:
    """Open and paused tickets per customer or contact, as `field` on the ticket says."""
    if not names:
        return {}
    rows = frappe.get_list(
        "HD Ticket",
        filters={field: ("in", names), "status_category": OPEN_TICKET_CATEGORIES},
        fields=[f"{field} as owner_name", "count(name) as count"],
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
        fields=["customer", "count(name) as count"],
        group_by="customer",
    )
    return {r.customer: r.count for r in rows}


def connection_status(customers: list[str]) -> dict[str, dict]:
    """Each customer's ERP connection: its status and site, the latest one if several."""
    if not customers:
        return {}
    rows = frappe.get_list(
        "HDS Support Connection",
        filters={"customer_name": ("in", customers)},
        fields=["customer_name", "connection_status", "site_url"],
        order_by="modified desc",
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
