"""Who takes a ticket today (Phase 12, docs/ticket-owners.md).

A new ticket goes to the first of these who is working today: the customer's ticket owner,
the backup owner (HDCustomer.ticket_owner_today), the least busy developer or support engineer
on the customer's project team, then the least busy agent of the team's assignment rule
(overrides/assignment_rule.py). Working today means an active agent, not a Sales Employee,
not on approved leave (a half day still counts as working) and not set to Unavailable.

When nobody can take it, the ticket waits unassigned and the customer's project coordinators
are asked to assign someone. Each morning, after the leave sync, the open tickets of people
on leave move along the same chain, and go back when they return if nobody worked on them
meanwhile. Each step leaves a line in the ticket's chat, so everyone sees why.
"""

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import remove as remove_assignment
from frappe.utils import add_days, add_to_date, formatdate, get_fullname, now_datetime

from helpdesk.automation import automation_user

# Project User.custom_role values whose members take the customer's tickets
PROJECT_TEAM_ROLES = ("Developer", "Support Engineer")
# status categories of tickets someone still has to work on
OPEN_CATEGORIES = ("Open", "Paused")
# a new ticket still unassigned after this long is brought to the coordinators
ASK_AFTER_MINUTES = 5
# once per ticket; its creation time too, so a number used again after a deletion asks again
ASKED_KEY = "ticket-nobody-free:{0}:{1}"


# --- who is working --------------------------------------------------------------------------


def working_today(users, day=None) -> set[str]:
    """The `users` who can take a ticket on `day` (today)."""
    from helpdesk.content_team import is_sales_employee
    from helpdesk.helpdesk.doctype.hd_customer.hd_customer import active_agents
    from helpdesk.overrides.assignment_rule import get_agents_by_category
    from helpdesk.work_calendar import on_leave

    users = [u for u in dict.fromkeys(users or []) if u]
    if not users:
        return set()
    working = {u for u in active_agents(users) if not is_sales_employee(u)}
    away = set(on_leave(day, users))
    return working - away - get_agents_by_category("Unavailable")


def absence(user: str, day=None) -> dict:
    """Why `user` is not taking tickets: {"away", "until" (the last day of their leave),
    "reason": leave, inactive or unavailable}."""
    from helpdesk.content_team import is_sales_employee
    from helpdesk.helpdesk.doctype.hd_customer.hd_customer import active_agents
    from helpdesk.overrides.assignment_rule import get_agents_by_category
    from helpdesk.work_calendar import on_leave

    leave = on_leave(day, [user])
    if user in leave:
        return {"away": user, "until": leave[user], "reason": "leave"}
    if user not in active_agents([user]) or is_sales_employee(user):
        reason = "inactive"
    elif user in get_agents_by_category("Unavailable"):
        reason = "unavailable"
    else:
        reason = None
    return {"away": user, "until": None, "reason": reason}


def open_load(users) -> dict[str, int]:
    """Open ticket assignments per user, the measure the least busy is picked by."""
    return {
        user: frappe.db.count(
            "ToDo",
            {"reference_type": "HD Ticket", "allocated_to": user, "status": "Open"},
        )
        for user in users
    }


def least_busy(users) -> str | None:
    users = list(dict.fromkeys(u for u in users if u))
    if not users:
        return None
    load = open_load(users)
    return min(users, key=lambda user: (load[user], user))


# --- the customer's people -----------------------------------------------------------------------


def customer_projects(customer: str | None) -> list[str]:
    """The customer's open projects, latest first."""
    if not customer:
        return []
    return frappe.get_all(
        "Project",
        filters={"customer": customer, "status": "Open"},
        pluck="name",
        order_by="modified desc",
    )


def project_members(projects: list[str], roles) -> list[str]:
    if not projects:
        return []
    return list(
        dict.fromkeys(
            frappe.get_all(
                "Project User",
                filters={
                    "parenttype": "Project",
                    "parent": ["in", projects],
                    "custom_role": ["in", list(roles)],
                    "user": ["is", "set"],
                },
                pluck="user",
                order_by="idx asc",
            )
        )
    )


def coordinators(customer: str | None) -> list[str]:
    """The Project Coordinators of the customer's open projects."""
    from helpdesk.tasky.permissions import COORDINATOR_PROJECT_ROLE

    return project_members(customer_projects(customer), (COORDINATOR_PROJECT_ROLE,))


def admins() -> list[str]:
    """The enabled people with an admin role (tasky.permissions.ADMIN_ROLES)."""
    from helpdesk.tasky.permissions import ADMIN_ROLES

    users = frappe.get_all(
        "Has Role",
        filters={"role": ["in", list(ADMIN_ROLES)], "parenttype": "User"},
        pluck="parent",
        distinct=True,
    )
    return sorted(
        u
        for u in users
        if u not in ("Administrator", "Guest")
        and frappe.db.get_value("User", u, "enabled")
    )


def developer_of(customer: str | None) -> str | None:
    """The customer's developer for Copilot's hand-overs, approvals and news: whoever takes
    the customer's tickets today (the owner, else the backup, else the project team), else the
    older Copilot "Assigned Developer" field when they are not on leave."""
    if not customer:
        return None
    found = pick(customer)
    if found:
        return found["user"]
    from helpdesk.work_calendar import on_leave

    legacy = frappe.db.get_value("HD Customer", customer, "custom_assigned_developer")
    if legacy and legacy not in on_leave(users=[legacy]):
        return legacy
    return None


# --- the chain -----------------------------------------------------------------------------------


def pick(customer) -> dict | None:
    """The first of the customer's owner, backup and project team who is working today:
    {"user", "step": owner, backup or project, "backup": not the owner, "away", "until",
    "reason"}. None when none of them is, and the team's assignment rule decides."""
    doc = (
        frappe.get_doc("HD Customer", customer)
        if isinstance(customer, str)
        else customer
    )
    return doc.ticket_owner_today() or from_project_team(doc)


def from_project_team(customer) -> dict | None:
    """The least busy developer or support engineer on the customer's project team who is
    working today."""
    team = project_members(customer_projects(customer.name), PROJECT_TEAM_ROLES)
    working = working_today(team)
    user = least_busy([u for u in team if u in working])
    if not user:
        return None
    why = (
        absence(customer.ticket_owner)
        if customer.ticket_owner
        else {"away": None, "until": None, "reason": None}
    )
    return {"user": user, "step": "project", "backup": True, **why}


def why_text(found: dict) -> str:
    """Why someone other than the owner took it, in a few words, or ""."""
    away = found.get("away")
    if not away:
        return ""
    name = get_fullname(away)
    if found.get("reason") == "leave" and found.get("until"):
        return _("{0} is on leave until {1}").format(
            name, formatdate(found["until"], "EEE d MMM")
        )
    if found.get("reason") == "unavailable":
        return _("{0} is set to Unavailable").format(name)
    if found.get("reason") == "inactive":
        return _("{0} is inactive").format(name)
    return ""


def chat_line(ticket: str, text: str):
    """A line in the ticket's chat (a note, not news for Teams). Never stops the caller."""
    from helpdesk.copilot import thread

    thread.post(str(ticket), {"title": "", "lines": [text], "tone": "note"})


def tell_chat_about(ticket: str, found: dict, customer: str):
    """The assignment of a new ticket, and why, in its chat."""
    name = get_fullname(found["user"])
    why = why_text(found)
    if found["step"] == "owner":
        text = _("Assigned to {0}, {1}'s ticket owner.").format(name, customer)
    elif found["step"] == "backup":
        text = _("Assigned to {0}, {1}'s backup ticket owner, because {2}.").format(
            name, customer, why
        )
    elif why:
        text = _(
            "Assigned to {0}, the least busy on {1}'s project team, because {2}."
        ).format(name, customer, why)
    else:
        text = _("Assigned to {0}, the least busy on {1}'s project team.").format(
            name, customer
        )
    chat_line(ticket, text)


# --- nobody free ----------------------------------------------------------------------------------


def ask_for_unassigned():
    """Scheduler: a customer's open ticket nobody has taken a few minutes after it came in
    (everyone who could take it is away) goes to the customer's coordinators, else the
    admins, working today. Once per ticket."""
    since = add_days(now_datetime(), -2)
    before = add_to_date(now_datetime(), minutes=-ASK_AFTER_MINUTES)
    for row in frappe.get_all(
        "HD Ticket",
        filters={
            "status_category": "Open",
            "customer": ["is", "set"],
            "creation": ["between", [since, before]],
        },
        fields=["name", "customer", "subject", "_assign"],
    ):
        if frappe.parse_json(row._assign or "[]"):
            continue
        ask_coordinators(row.name, row.customer, row.subject)


def ask_coordinators(ticket: str, customer: str, subject: str = "") -> list[str]:
    """Ask the customer's coordinators (else the admins) working today to assign someone;
    once per ticket. Returns who was asked."""
    from helpdesk.work_reminders import notify_users

    key = ASKED_KEY.format(ticket, frappe.db.get_value("HD Ticket", ticket, "creation"))
    if frappe.cache.get_value(key, expires=True):
        return []
    people = []
    for group in (coordinators(customer), admins()):
        working = working_today(group)
        people = [u for u in group if u in working]
        if people:
            break
    if not people:
        return []
    frappe.cache.set_value(key, 1, expires_in_sec=7 * 24 * 3600)
    notify_users(
        people,
        "HD Ticket",
        ticket,
        _(
            "Nobody is free to take ticket #{0} from {1}: {2}. Everyone who usually takes it is away; please assign someone."
        ).format(ticket, customer, subject),
        notification_type="Reminder",
    )
    chat_line(
        ticket,
        _(
            "Nobody who usually takes this ticket is working today; {0} asked to assign someone."
        ).format(", ".join(get_fullname(u) for u in people)),
    )
    return people


# --- leave: moving tickets and giving them back ---------------------------------------------------------


def daily():
    """Scheduler, after the morning leave sync: give back what the returning people had, then
    move the tickets of people on leave today."""
    give_back()
    hand_over_from_leave()


def hand_over_from_leave(day=None) -> list[dict]:
    """Every open ticket whose assignees are all on leave today goes to the next in the chain
    (owner, backup, project team, the team's rule); when nobody is free, the coordinators
    are asked. Returns [{"ticket", "from", "to"}]."""
    from helpdesk.work_calendar import on_leave

    away = on_leave(day)
    if not away:
        return []
    moved = []
    tickets = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "HD Ticket",
            "status": "Open",
            "allocated_to": ["in", list(away)],
        },
        pluck="reference_name",
        distinct=True,
    )
    for name in tickets:
        ticket = frappe.get_doc("HD Ticket", name)
        if ticket.status_category not in OPEN_CATEGORIES:
            continue
        assignees = _open_assignees(name)
        if not assignees or any(user not in away for user in assignees):
            continue  # someone working still has it
        try:
            to = _move(ticket, assignees, away)
        except Exception:
            frappe.log_error(title=f"Could not move ticket {name} from people on leave")
            continue
        moved.append({"ticket": name, "from": assignees, "to": to})
    return moved


def _open_assignees(ticket: str) -> list[str]:
    return frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "HD Ticket",
            "reference_name": str(ticket),
            "status": "Open",
        },
        pluck="allocated_to",
    )


def _move(ticket, assignees: list[str], away: dict) -> str | None:
    """Give `ticket` to the next person in the chain instead of `assignees` (all away)."""
    first = assignees[0]
    until = away.get(first)
    found = pick(ticket.customer) if ticket.customer else None
    for user in assignees:
        remove_assignment("HD Ticket", ticket.name, user, ignore_permissions=True)
    if found:
        to = found["user"]
        add_assignment(
            {
                "assign_to": [to],
                "doctype": "HD Ticket",
                "name": ticket.name,
                "assigned_by": automation_user(),
            },
            ignore_permissions=True,
        )
    else:
        # the team's assignment rule, which only picks people working today
        from frappe.automation.doctype.assignment_rule.assignment_rule import apply

        apply(frappe.get_doc("HD Ticket", ticket.name))
        now = _open_assignees(ticket.name)
        to = now[0] if now else None
    if not ticket.get("custom_away_assignee"):
        frappe.db.set_value(
            "HD Ticket",
            ticket.name,
            {"custom_away_assignee": first, "custom_moved_on": now_datetime()},
            update_modified=False,
        )
    why = _("{0} is on leave until {1}").format(
        get_fullname(first), formatdate(until, "EEE d MMM")
    )
    if to:
        _log(ticket.name, _("moved to {0}: {1}").format(get_fullname(to), why))
        chat_line(ticket.name, _("Moved to {0}: {1}.").format(get_fullname(to), why))
        from helpdesk.work_reminders import notify_users

        notify_users(
            [to],
            "HD Ticket",
            ticket.name,
            _("Ticket #{0} from {1} moved to you while {2}: {3}").format(
                ticket.name, ticket.customer or _("no customer"), why, ticket.subject
            ),
            notification_type="New Ticket",
        )
    else:
        _log(ticket.name, _("unassigned: {0}, and nobody is free").format(why))
        chat_line(
            ticket.name, _("Unassigned: {0}, and nobody else is free.").format(why)
        )
        if ticket.customer:
            ask_coordinators(ticket.name, ticket.customer, ticket.subject)
    return to


def give_back(day=None) -> list[str]:
    """Tickets moved away from someone on leave go back to them once they work again, if
    nobody worked on the ticket since; otherwise they stay. Returns the tickets given back."""
    back = []
    for row in frappe.get_all(
        "HD Ticket",
        filters={"custom_away_assignee": ["is", "set"]},
        fields=["name", "status_category", "custom_away_assignee", "custom_moved_on"],
    ):
        person = row.custom_away_assignee
        if row.status_category in OPEN_CATEGORIES and person not in working_today(
            [person], day
        ):
            continue  # still away
        if row.status_category in OPEN_CATEGORIES and not worked_on_since(
            row.name, row.custom_moved_on
        ):
            for user in _open_assignees(row.name):
                remove_assignment("HD Ticket", row.name, user, ignore_permissions=True)
            add_assignment(
                {
                    "assign_to": [person],
                    "doctype": "HD Ticket",
                    "name": row.name,
                    "assigned_by": automation_user(),
                },
                ignore_permissions=True,
            )
            _log(
                row.name,
                _("given back to {0}, who is back").format(get_fullname(person)),
            )
            chat_line(
                row.name,
                _(
                    "Back with {0}: they are working again and nobody worked on it meanwhile."
                ).format(get_fullname(person)),
            )
            back.append(row.name)
        frappe.db.set_value(
            "HD Ticket",
            row.name,
            {"custom_away_assignee": None, "custom_moved_on": None},
            update_modified=False,
        )
    return back


def worked_on_since(ticket: str, since) -> bool:
    """Whether a person replied, commented or wrote in the ticket's chat since `since`."""
    if not since:
        return True
    bot = automation_user()
    # Copilot's own updates to the customer are sent as the automation user
    if frappe.db.exists(
        "Communication",
        {
            "reference_doctype": "HD Ticket",
            "reference_name": str(ticket),
            "sent_or_received": "Sent",
            "creation": [">", since],
            "owner": ["!=", bot],
        },
    ):
        return True
    if frappe.db.exists(
        "HD Ticket Comment",
        {
            "reference_ticket": str(ticket),
            "creation": [">", since],
            "commented_by": ["!=", bot],
        },
    ):
        return True
    chat = frappe.db.get_value("HDS Copilot Chat", {"ticket": str(ticket)})
    return bool(
        chat
        and frappe.db.exists(
            "HDS Copilot Chat Message",
            {"chat": chat, "direction": "In", "creation": [">", since]},
        )
    )


def _log(ticket: str, action: str):
    from helpdesk.helpdesk.doctype.hd_ticket_activity.hd_ticket_activity import (
        log_ticket_activity,
    )

    activity = log_ticket_activity(ticket, action)
    activity.db_set("owner", automation_user(), update_modified=False)
