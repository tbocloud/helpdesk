"""Home: the state of the whole business on one screen.

Everyone gets their own open work. People who can see the overview (project
managers, project leads, admins) also get tickets, work at risk, projects and
team load; admins also get the health of the systems the hub depends on.
Lists go through `frappe.get_list`, so nobody sees records they couldn't open.
"""

from collections import Counter

import frappe
from frappe.utils import get_datetime, getdate, now_datetime, nowdate

from helpdesk.api.work import (
    _assignees,
    can_see_overview,
    get_my_work,
    get_overview,
    get_project_portfolio,
)
from helpdesk.tasky.permissions import is_tasky_admin
from helpdesk.utils import agent_only

LIST_LIMIT = 8
CUSTOMER_LIMIT = 6
PEOPLE_LIMIT = 10
OPEN_TICKET_CATEGORIES = ("in", ["Open", "Paused"])
OPEN_CHAT_STATUSES = ("in", ["Open", "Pending"])


@frappe.whitelist()
@agent_only
def get_home() -> dict:
    mine = get_my_work()
    return {
        "mine": {"counts": mine["counts"], "items": mine["items"][:LIST_LIMIT]},
        "company": _company() if can_see_overview() else None,
        "systems": _systems() if is_tasky_admin() else None,
    }


def _company() -> dict:
    overview = get_overview()
    portfolio = get_project_portfolio("Open")
    projects = sorted(portfolio["projects"], key=_project_order)
    return {
        "tickets": _ticket_summary(),
        "work": overview["counts"],
        "attention": _attention(overview["buckets"]),
        "projects": [_project(card) for card in projects[:LIST_LIMIT]],
        "project_count": len(projects),
        "people": [_person(p) for p in portfolio["people"] if not p["is_free"]][
            :PEOPLE_LIMIT
        ],
        "people_free": portfolio["totals"]["people_free"],
    }


def _ticket_summary() -> dict:
    now = now_datetime()
    open_tickets = frappe.get_list(
        "HD Ticket",
        filters={"status_category": OPEN_TICKET_CATEGORIES},
        fields=["customer", "status_category", "resolution_by", "_assign"],
        limit_page_length=0,
    )
    by_customer = Counter(t.customer or "" for t in open_tickets)
    return {
        "open": len(open_tickets),
        "new_today": len(
            frappe.get_list(
                "HD Ticket",
                filters={"creation": (">=", getdate(nowdate()))},
                pluck="name",
                limit_page_length=0,
            )
        ),
        "unassigned": sum(1 for t in open_tickets if not _assignees(t._assign)),
        # paused tickets (waiting on the customer or a task) don't run the SLA clock
        "sla_breached": sum(
            1
            for t in open_tickets
            if t.status_category == "Open"
            and t.resolution_by
            and get_datetime(t.resolution_by) < now
        ),
        "by_customer": [
            {"customer": customer or None, "open": count}
            for customer, count in by_customer.most_common(CUSTOMER_LIMIT)
        ],
    }


def _attention(buckets: dict) -> list[dict]:
    """Overdue work first, then work likely to slip; each item once."""
    seen = set()
    items = []
    for item in buckets["overdue"] + buckets["at_risk"]:
        key = (item["kind"], item["name"])
        if key not in seen:
            seen.add(key)
            items.append(item)
    return items[:LIST_LIMIT]


def _project_order(card: dict):
    # projects in trouble first, then the ones that end soonest
    return (
        -card["counts"]["overdue"],
        card["expected_end_date"] or "9999-12-31",
        card["project_name"].lower(),
    )


def _project(card: dict) -> dict:
    return {
        "name": card["name"],
        "project_name": card["project_name"],
        "customer": card["customer"],
        "lead": card["lead"],
        "lead_name": card["lead_name"],
        "progress": card["progress"],
        "open": card["counts"]["open"],
        "overdue": card["counts"]["overdue"],
        "expected_end_date": card["expected_end_date"],
        "next_milestone": card["next_milestone"],
    }


def _person(person: dict) -> dict:
    return {
        "user": person["user"],
        "full_name": person["full_name"],
        "open": person["open"],
        "working": person["working"],
        "projects": [p["project_name"] for p in person["projects"][:3]],
    }


def _systems() -> dict:
    """What the hub depends on: customer ERPs, mailboxes, Teams, TBO Chat and the AI."""
    today = getdate(nowdate())
    return {
        "connections": frappe.get_all(
            "HDS Support Connection",
            fields=[
                "name",
                "customer_name",
                "site_url",
                "connection_status",
                "last_error",
                "last_health_check",
            ],
            order_by="customer_name asc",
        ),
        "mailboxes": frappe.get_all(
            "Email Account",
            filters={"email_server": ("is", "set")},
            fields=["name", "email_id", "enable_incoming", "no_failed"],
            order_by="email_id asc",
        ),
        "teams": {
            "enabled": bool(frappe.db.get_single_value("HD Chat Settings", "enabled")),
            "platform": frappe.db.get_single_value("HD Chat Settings", "platform"),
        },
        "chat": {
            "enabled": bool(
                frappe.db.get_single_value("HD Chatwoot Settings", "enabled")
            ),
            "open": frappe.db.count(
                "HD Chat Conversation", {"status": OPEN_CHAT_STATUSES}
            ),
        },
        "ai": {
            "calls_today": frappe.db.count(
                "HDS AI Usage Log", {"creation": (">=", today)}
            ),
            "triage_failed": frappe.db.count(
                "HD Ticket",
                {
                    "status_category": OPEN_TICKET_CATEGORIES,
                    "custom_triage_status": "Failed",
                },
            ),
        },
    }
