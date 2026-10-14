"""After AI triage: priority, ticket type and team, unless a person already set them.

Triage stored its priority and category on the ticket but never used them, so every
ticket stayed Medium, of the default type and without a team (docs/ticket-intake.md,
Routing). Now, when Settings → Ticket intake has "Apply AI triage" on:

- **Priority**: the triage's, while the ticket still has a default priority and no
  person has changed it.
- **Ticket type**: the category's route, else the request type (question → Question,
  issue → Bug), while the ticket still has the default type and no person changed it.
  A customization is typed by `customization.record_triage_estimate`, which runs first.
- **Team**: the category's route, else the default team, while the ticket has none.

Saving with a team lets that team's Assignment Rule (round robin) assign the ticket.
It only assigns a ticket nobody has: the customer's ticket owner, assigned on insert
(docs/ticket-owners.md), keeps it, and so does anyone a person assigned. Routing never
takes an assignment away (`flags.keep_assignment`).
"""

import frappe
from frappe.utils import cint

from helpdesk.automation import automation_user
from helpdesk.consts import (
    ALERT_TICKET_TYPE,
    DEFAULT_TICKET_PRIORITY,
    DEFAULT_TICKET_TYPE,
)
from helpdesk.intake import OPEN_CATEGORIES, SETTINGS, save_as_automation

# the request type the triage reports → the ticket type it means
REQUEST_TICKET_TYPES = {"question": "Question", "issue": "Bug"}
# the triage's priority names → this site's, when the site has no such priority
TRIAGE_PRIORITIES = {"Critical": "Urgent"}
# HDTicket.handle_ticket_activity_update logs "set <label> to …" / "cleared <label>"
ACTIVITY_LABELS = {"priority": "priority", "ticket_type": "type", "agent_group": "team"}


def apply_triage(ticket_id: str, triage: dict) -> dict:
    """Route a triaged ticket; returns the fields it changed."""
    settings = frappe.get_cached_doc(SETTINGS)
    if not cint(settings.apply_triage):
        return {}
    ticket = frappe.get_doc("HD Ticket", ticket_id)
    if (
        ticket.ticket_type == ALERT_TICKET_TYPE
        or ticket.status_category not in OPEN_CATEGORIES
    ):
        return {}
    touched = set_by_people(ticket.name)
    route = next(
        (r for r in settings.routes if r.category == triage.get("category")), None
    )
    updates = {}

    priority = triage_priority(triage.get("priority"))
    if (
        priority
        and priority != ticket.priority
        and "priority" not in touched
        and is_default_priority(ticket)
    ):
        updates["priority"] = priority

    ticket_type = (route and route.ticket_type) or REQUEST_TICKET_TYPES.get(
        (triage.get("request_type") or "").lower()
    )
    if (
        ticket_type
        and ticket_type != ticket.ticket_type
        and "ticket_type" not in touched
        and is_default_ticket_type(ticket.ticket_type)
        and frappe.db.exists("HD Ticket Type", ticket_type)
    ):
        updates["ticket_type"] = ticket_type

    team = (route and route.team) or settings.default_team
    if (
        team
        and not ticket.agent_group
        and "agent_group" not in touched
        and not frappe.db.get_value("HD Team", team, "disabled")
    ):
        updates["agent_group"] = team

    if updates:
        ticket.update(updates)
        ticket.flags.keep_assignment = True
        save_as_automation(ticket)
    return updates


def triage_priority(value: str | None) -> str | None:
    if not value:
        return None
    if frappe.db.exists("HD Ticket Priority", value):
        return value
    mapped = TRIAGE_PRIORITIES.get(value)
    return mapped if mapped and frappe.db.exists("HD Ticket Priority", mapped) else None


def set_by_people(ticket: str) -> set[str]:
    """The routed fields someone other than the automation user changed after insert."""
    Activity = frappe.qb.DocType("HD Ticket Activity")
    actions = (
        frappe.qb.from_(Activity)
        .select(Activity.action)
        .where((Activity.ticket == str(ticket)) & (Activity.owner != automation_user()))
        .run(pluck=True)
    )
    return {
        field
        for field, label in ACTIVITY_LABELS.items()
        if any(
            (a or "").startswith((f"set {label} to ", f"cleared {label}"))
            for a in actions
        )
    }


def is_default_priority(ticket) -> bool:
    """Whether the priority is one the ticket got without anyone choosing it: empty,
    its type's, HD Settings', its SLA's default or Medium."""
    if not ticket.priority:
        return True
    defaults = {
        DEFAULT_TICKET_PRIORITY,
        frappe.db.get_single_value("HD Settings", "default_priority"),
        frappe.db.get_value("HD Ticket Type", ticket.ticket_type, "priority")
        if ticket.ticket_type
        else None,
        frappe.db.get_value(
            "HD Service Level Priority",
            {"parent": ticket.sla, "default_priority": 1},
            "priority",
        )
        if ticket.sla
        else None,
    }
    return ticket.priority in defaults


def is_default_ticket_type(ticket_type: str | None) -> bool:
    """Empty, Unspecified, or HD Settings' default type (Bug on the hub)."""
    return ticket_type in (
        None,
        "",
        DEFAULT_TICKET_TYPE,
        frappe.db.get_single_value("HD Settings", "default_ticket_type"),
    )
