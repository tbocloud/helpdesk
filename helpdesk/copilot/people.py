# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Who Copilot goes to (Phase 22). Every person comes from settings: the code names nobody and
picks nobody by a job role.

- **Each customer** (HD Customer → Copilot People): the first and second developer, an optional
  fix approver and the project coordinators.
- **Every customer** (HDS Copilot Settings → People): the project coordinators of customers with
  none of their own, the people risk alerts go to, and the infrastructure people (Senior tick).
- A customer's own setting wins. Where nobody is set anywhere, the Copilot approvers (also a
  setting) stand in.

Working today is TBO Support's own rule (helpdesk.ticket_assignment.working_today): an active
agent, not on approved leave, not set to Unavailable.

The chain for a customer's work: the person a project coordinator chose for the ticket, then (for
a fix) the customer's fix approver, then the first developer, then the second. When neither
developer is working, the project coordinators get the work and choose who takes the ticket
(Assign to, or Keep), asked again each morning until one does. Every new ticket is told to the
project coordinators with the same Assign to (docs/tbo-copilot.md, "People").
"""

import frappe
from frappe import _
from frappe.utils import format_date, get_datetime, get_fullname, get_url, now_datetime

from helpdesk import ticket_assignment
from helpdesk.copilot import settings as copilot_settings

CUSTOMER = "HD Customer"
TICKET = "HD Ticket"
RUN = "HDS Copilot Run"
APPROVAL = "HDS Copilot Approval"
NOTICE_BOTH = "Teams and TBO Support"
NOTICE_PANEL = "TBO Support only"
NOTICE_OFF = "Off"
ASSIGN, KEEP = "people_assign", "people_keep"
VERBS = (ASSIGN, KEEP)
CHOICES_LIMIT = 50  # people offered in Assign to, least busy first
OPEN_CATEGORIES = ("Open", "Paused")


# --- settings ------------------------------------------------------------------------------


def _settings():
    return copilot_settings.get_settings()


def _enabled(users) -> list[str]:
    """`users` with an enabled account, in order, once each."""
    users = [u for u in dict.fromkeys(users or []) if u]
    if not users:
        return []
    found = set(
        frappe.get_all(
            "User", filters={"name": ["in", users], "enabled": 1}, pluck="name"
        )
    )
    return [u for u in users if u in found]


def _active(row) -> bool:
    return bool(row.get("user")) and row.get("active") not in (0, "0")


def _rows(rows) -> list[str]:
    return _enabled(row.user for row in rows or [] if _active(row))


def common_coordinators() -> list[str]:
    """The project coordinators of customers with none of their own."""
    return _rows(_settings().get("project_coordinators"))


def risk_people() -> list[str]:
    """Everyone told of risky work, for every customer."""
    return _rows(_settings().get("risk_alert_people"))


def _infra_rows() -> list:
    rows = [
        row for row in _settings().get("infrastructure_people") or [] if _active(row)
    ]
    enabled = set(_enabled(row.user for row in rows))
    return [row for row in rows if row.user in enabled]


def infra_people() -> list[str]:
    """Who approves Press, AWS and repair actions and hears the watcher (empty: not set)."""
    return list(dict.fromkeys(row.user for row in _infra_rows()))


def infra_seniors() -> list[str]:
    return list(dict.fromkeys(row.user for row in _infra_rows() if row.senior))


def stand_ins() -> list[str]:
    """Where nobody is set anywhere: the Copilot approvers (HDS Copilot Settings → Fix Approval)."""
    from helpdesk.copilot import approvals

    return approvals.approvers()


def of_customer(customer: str | None) -> dict:
    """The customer's people as set: {"first", "second", "fix_approver", "coordinators",
    "coordinators_from": customer or common}. An empty first or second developer is the
    customer's Ticket Owner (else Copilot's older Assigned Developer) or Backup Ticket Owner,
    also set on the customer; coordinators fall back to the common ones."""
    found = {
        "first": None,
        "second": None,
        "fix_approver": None,
        "coordinators": [],
        "coordinators_from": "common",
    }
    if customer and frappe.db.exists(CUSTOMER, customer):
        doc = frappe.get_doc(CUSTOMER, customer)
        for key, fields in (
            (
                "first",
                ("custom_first_developer", "ticket_owner", "custom_assigned_developer"),
            ),
            ("second", ("custom_second_developer", "backup_ticket_owner")),
            ("fix_approver", ("custom_fix_approver",)),
        ):
            user = next((doc.get(f) for f in fields if doc.get(f)), None)
            found[key] = user if user and _enabled([user]) else None
        own = _rows(doc.get("custom_copilot_coordinators"))
        if own:
            found["coordinators"], found["coordinators_from"] = own, "customer"
    if not found["coordinators"]:
        found["coordinators"] = common_coordinators()
    return found


# --- who is working --------------------------------------------------------------------------


def working(users) -> list[str]:
    """`users` who can take work today, in order: TBO Support's rule for agents (active, not on
    leave, not Unavailable); someone set in settings who is not an agent at all (a developer with
    no HD Agent) counts while their account is enabled and they are not on leave."""
    from helpdesk.work_calendar import on_leave

    users = [u for u in dict.fromkeys(users or []) if u]
    if not users:
        return []
    today = ticket_assignment.working_today(users)
    agents = set(
        frappe.get_all("HD Agent", filters={"name": ["in", users]}, pluck="name")
    )
    others = [u for u in _enabled(users) if u not in agents]
    if others:
        away = on_leave(users=others)
        today |= {u for u in others if u not in away}
    return [u for u in users if u in today]


def coordinators_today(customer: str | None) -> list[str]:
    """The customer's project coordinators working today, else the common ones working today."""
    people = of_customer(customer)
    found = working(people["coordinators"])
    if not found and people["coordinators_from"] == "customer":
        found = working(common_coordinators())
    return found


def away_text(user: str) -> str:
    why = ticket_assignment.absence(user)
    name = get_fullname(user)
    if why.get("reason") == "leave" and why.get("until"):
        return _("{0} is on leave until {1}").format(name, format_date(why["until"]))
    if why.get("reason") == "unavailable":
        return _("{0} is set to Unavailable").format(name)
    if why.get("reason") == "inactive":
        return _("{0} is not an active agent").format(name)
    return _("{0} is not working today").format(name)


def chosen(ticket: str | None) -> str | None:
    """The person a project coordinator chose for the ticket, if any."""
    if not ticket:
        return None
    return frappe.db.get_value(TICKET, str(ticket), "custom_copilot_person")


STEP_LABELS = {
    "chosen": "chosen by a project coordinator",
    "fix_approver": "fix approver",
    "first": "first developer",
    "second": "second developer",
}


def for_ticket(
    customer: str | None, ticket: str | None = None, fix: bool = False
) -> dict:
    """Who Copilot goes to for this customer's work today, and why.

    {"user", "step": chosen, fix_approver, first, second, coordinator or None, "why",
     "away": why each skipped person is away, "coordinators": those working today,
     "no_developer": neither developer can take it, so the coordinators choose}
    `fix`: the customer's fix approver comes before the developers."""
    people = of_customer(customer)
    steps = []
    person = chosen(ticket)
    if person:
        steps.append(("chosen", person))
    if fix and people["fix_approver"]:
        steps.append(("fix_approver", people["fix_approver"]))
    steps += [("first", people["first"]), ("second", people["second"])]
    away, tried = [], set()
    for step, user in steps:
        if not user or user in tried:
            continue
        tried.add(user)
        if working([user]):
            why = _(STEP_LABELS[step])
            if away:
                why = "{0} ({1})".format(why, "; ".join(away))
            return {
                "user": user,
                "step": step,
                "why": why,
                "away": away,
                "coordinators": [],
                "no_developer": False,
            }
        away.append(away_text(user))
    coordinators = coordinators_today(customer)
    lead = ticket_assignment.least_busy(coordinators)
    if away:
        why = _("project coordinator ({0})").format("; ".join(away))
    else:
        why = _("project coordinator (the customer has no developer set)")
    return {
        "user": lead,
        "step": "coordinator" if lead else None,
        "why": why
        if lead
        else _("nobody: no developer or project coordinator is working today"),
        "away": away,
        "coordinators": coordinators,
        "no_developer": True,
    }


def developer(customer: str | None, ticket: str | None = None) -> str | None:
    """The developer who takes the customer's work today (chosen, first or second), or None."""
    found = for_ticket(customer, ticket)
    return found["user"] if found["step"] in ("chosen", "first", "second") else None


def may_approve(customer: str | None, ticket: str | None = None) -> set[str]:
    """Who the settings let approve this customer's fixes, besides the Copilot approvers."""
    people = of_customer(customer)
    found = {
        people["first"],
        people["second"],
        people["fix_approver"],
        chosen(ticket),
        *people["coordinators"],
    }
    return {u for u in found if u}


def need_a_person(customer: str | None) -> list[str]:
    """Who hears that Copilot needs a person and nobody on the ticket can: the project
    coordinators working today, else the Copilot approvers working today, else all of them."""
    return (
        coordinators_today(customer)
        or working(stand_ins())
        or of_customer(customer)["coordinators"]
        or stand_ins()
    )


# --- telling people --------------------------------------------------------------------------


def _ticket_url(ticket: str) -> str:
    return get_url(f"/helpdesk/tickets/{ticket}")


def deliver(
    people, reply: dict, subject: str, ticket: str | None = None, panel_only=False
):
    """A card to each person (Teams when the bot reaches them, else the TBO Support panel), and a
    TBO Support notification. Returns who got it."""
    from helpdesk.copilot import assistant
    from helpdesk.work_reminders import helpdesk_path, new_notification, notify_users

    doctype, name = (
        (TICKET, str(ticket))
        if ticket
        else ("HDS Copilot Settings", "HDS Copilot Settings")
    )
    told = []
    for person in dict.fromkeys(people or []):
        used = assistant.send(
            person, reply, channel="Web" if panel_only else None, ticket=ticket
        )
        if used == "Teams":
            new_notification(
                person,
                doctype,
                name,
                subject,
                helpdesk_path(doctype, name),
                deliver=False,
            )
        else:
            notify_users([person], doctype, name, subject, once=False)
        told.append(person)
    return told


def _came_in_by(doc) -> str:
    if doc.get("custom_copilot_source"):
        return _("Copilot's error watch")
    if doc.get("via_customer_portal"):
        return _("the customer portal or the ERP's Support button")
    return _("email")


def _open_assignees(ticket: str) -> list[str]:
    return ticket_assignment._open_assignees(str(ticket))


def choices(exclude=()) -> list[list[str]]:
    """Assign to: active agents working today, least busy first, with their open tickets."""
    agents = frappe.get_all("HD Agent", filters={"is_active": 1}, pluck="name")
    people = [u for u in working(agents) if u not in exclude]
    load = ticket_assignment.open_load(people)
    people.sort(key=lambda u: (load[u], get_fullname(u) or u))
    return [
        [_("{0} ({1} open)").format(get_fullname(u), load[u]), u]
        for u in people[:CHOICES_LIMIT]
    ]


def notice_card(doc, found: dict, sent_at: str) -> dict:
    """The coordinators' card for a ticket: what came in, who has it and why, and Assign to."""
    from helpdesk.copilot import assistant

    holders = _open_assignees(doc.name)
    holding = ", ".join(get_fullname(u) for u in holders) or _("nobody yet")
    if found["no_developer"]:
        title = _("Ticket #{0} from {1}: both developers are away").format(
            doc.name, doc.customer or _("an unknown customer")
        )
        lines = [
            doc.subject or "",
            "; ".join(found["away"]) or _("The customer has no developer set."),
            _(
                "Choose who takes it. Until you do, Copilot brings its work on this ticket to you."
            ),
        ]
    else:
        title = _("New ticket #{0} from {1}").format(
            doc.name, doc.customer or _("an unknown customer")
        )
        lines = [doc.subject or ""]
    actions = [
        assistant.button(_("Assign"), ASSIGN, "positive", ticket=doc.name, at=sent_at)
    ]
    if holders:
        actions.append(
            assistant.button(
                _("Keep {0}").format(holding), KEEP, ticket=doc.name, at=sent_at
            )
        )
    return assistant.card(
        title,
        lines,
        facts=[
            (_("Priority"), doc.priority),
            (_("Came in by"), _came_in_by(doc)),
            (_("With"), holding),
            (
                _("Copilot goes to"),
                get_fullname(found["user"]) if found["user"] else _("nobody yet"),
            ),
            (_("Why"), found["why"]),
        ],
        links=[(_("Open the ticket"), _ticket_url(doc.name))],
        actions=actions,
        inputs=[
            {
                "id": "person",
                "type": "choice",
                "label": _("Assign to"),
                "choices": choices(),
            }
        ],
        tone="warning" if found["no_developer"] else "default",
    )


def _configured(customer: str | None) -> bool:
    """Copilot's people are set for this customer: coordinators (its own or common), or a developer."""
    people = of_customer(customer)
    return bool(people["coordinators"] or people["first"] or people["second"])


def on_ticket_insert(doc, method=None):
    """Hook: a new ticket's project coordinators hear of it, or choose who takes it."""
    try:
        if not _configured(doc.customer):
            return  # no Copilot people are set: nobody to tell
        frappe.enqueue(
            "helpdesk.copilot.people.tell_coordinators",
            queue="short",
            ticket=doc.name,
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )
    except Exception:
        frappe.log_error(
            title=f"Copilot could not tell the coordinators about ticket {doc.name}"
        )


def tell_coordinators(ticket: str, again: bool = False) -> list[str]:
    """Background: the coordinators' card for a ticket (A5), the choice when both developers are
    away (A1). Returns who was told."""
    settings = _settings()
    mode = settings.get("new_ticket_notice") or NOTICE_BOTH
    doc = frappe.get_doc(TICKET, str(ticket))
    found = for_ticket(doc.customer, doc.name)
    if mode == NOTICE_OFF and not found["no_developer"]:
        return []
    people = (
        coordinators_today(doc.customer)
        or of_customer(doc.customer)["coordinators"]
        or working(stand_ins())
        or stand_ins()
    )
    people = [p for p in people if p not in (doc.raised_by, doc.owner)]
    if not people:
        return []
    reply = notice_card(doc, found, str(now_datetime()))
    subject = reply["title"]
    if again:
        subject = _("Still waiting: {0}").format(subject)
    told = deliver(people, reply, subject, doc.name, panel_only=mode == NOTICE_PANEL)
    if found["no_developer"]:
        doc.db_set("custom_copilot_waiting", 1, update_modified=False)
        if not again:
            ticket_assignment.chat_line(
                doc.name,
                _("Both developers are away; {0} asked to choose who takes it.").format(
                    ", ".join(get_fullname(u) for u in told)
                ),
            )
    return told


def ask_again():
    """06:45: tickets whose coordinators have not chosen yet are asked again; a ticket whose
    developer is back stops waiting."""
    for name in frappe.get_all(
        TICKET,
        filters={
            "custom_copilot_waiting": 1,
            "status_category": ["in", list(OPEN_CATEGORIES)],
        },
        pluck="name",
    ):
        try:
            doc = frappe.get_doc(TICKET, name)
            if not for_ticket(doc.customer, doc.name)["no_developer"]:
                doc.db_set("custom_copilot_waiting", 0, update_modified=False)
                continue
            tell_coordinators(name, again=True)
        except Exception:
            frappe.log_error(title=f"Copilot could not ask again about ticket {name}")
    frappe.db.set_value(
        TICKET,
        {
            "custom_copilot_waiting": 1,
            "status_category": ["not in", list(OPEN_CATEGORIES)],
        },
        "custom_copilot_waiting",
        0,
        update_modified=False,
    )


# --- the coordinator's choice ----------------------------------------------------------------


def may_assign(user: str, customer: str | None) -> bool:
    """A project coordinator of the customer (its own, else the common ones), or a Copilot approver."""
    return user in of_customer(customer)["coordinators"] or user in stand_ins()


def _decided_card(ticket: str, note: str) -> dict:
    from helpdesk.copilot import assistant

    return assistant.card(
        _("Ticket #{0}").format(ticket),
        [note],
        links=[(_("Open the ticket"), _ticket_url(ticket))],
        tone="good",
    )


def press(user: str, channel: str, verb: str, data: dict, inputs: dict) -> dict:
    """Assign or Keep on a coordinator's card; the first choice stands."""
    from helpdesk.copilot import assistant

    ticket = str(data.get("ticket") or "")
    if not ticket or not frappe.db.exists(TICKET, ticket):
        return {
            "replies": [assistant.text_card(_("That ticket no longer exists."))],
            "card": None,
        }
    customer = frappe.db.get_value(TICKET, ticket, "customer")
    if not may_assign(user, customer):
        return {
            "replies": [
                assistant.text_card(
                    _(
                        "Only this customer's project coordinators choose who takes its tickets."
                    ),
                    "warning",
                )
            ],
            "card": None,
        }
    row = frappe.db.get_value(
        TICKET,
        ticket,
        ["custom_copilot_person_at", "custom_copilot_person_note"],
        as_dict=True,
        for_update=True,
    )
    sent_at = data.get("at")
    if (
        row.custom_copilot_person_at
        and sent_at
        and get_datetime(row.custom_copilot_person_at) >= get_datetime(sent_at)
    ):
        # someone chose after this card went out: theirs stands
        return {
            "replies": [assistant.text_card(row.custom_copilot_person_note or "")],
            "card": _decided_card(ticket, row.custom_copilot_person_note or ""),
        }
    if verb == KEEP:
        holders = _open_assignees(ticket)
        if not holders:
            return {
                "replies": [
                    assistant.text_card(
                        _("Nobody has it yet; choose someone."), "warning"
                    )
                ],
                "card": None,
            }
        note = choose(ticket, holders[0], user, keep=True)
    else:
        person = str((inputs or {}).get("person") or "").strip()
        if not person:
            return {
                "replies": [
                    assistant.text_card(_("Choose a person first."), "warning")
                ],
                "card": None,
            }
        if not frappe.db.get_value("HD Agent", {"name": person, "is_active": 1}):
            return {
                "replies": [
                    assistant.text_card(
                        _("{0} is not an active agent.").format(person), "warning"
                    )
                ],
                "card": None,
            }
        note = choose(ticket, person, user)
    return {
        "replies": [assistant.text_card(note, "good")],
        "card": _decided_card(ticket, note),
    }


def choose(ticket: str, person: str, by: str, keep: bool = False) -> str:
    """The coordinator's choice: the ticket (and its Copilot task) goes to `person`, Copilot's
    approvals and news for it follow, and the ticket's chat says so. Returns that line."""
    from helpdesk.copilot import assistant
    from helpdesk.utils import add_assignment, remove_assignment

    ticket = str(ticket)
    waiting = frappe.db.get_value(TICKET, ticket, "custom_copilot_waiting")
    template = (
        _("Kept with {0} by project coordinator {1}")
        if keep
        else _("Assigned to {0} by project coordinator {1}")
    )
    note = template.format(get_fullname(person), get_fullname(by))
    if waiting:
        note = "{0}: {1}".format(note, _("both developers are away"))
    if not keep:
        holders = _open_assignees(ticket)
        for other in holders:
            if other != person:
                remove_assignment(TICKET, ticket, other, ignore_permissions=True)
        if person not in holders:
            add_assignment(
                {
                    "assign_to": [person],
                    "doctype": TICKET,
                    "name": ticket,
                    "description": note[:500],
                    "assigned_by": by,
                },
                ignore_permissions=True,
            )
    frappe.db.set_value(
        TICKET,
        ticket,
        {
            "custom_copilot_person": person,
            "custom_copilot_person_note": note,
            "custom_copilot_person_at": now_datetime(),
            "custom_copilot_waiting": 0,
        },
        update_modified=False,
    )
    _give_task(ticket, person, by, note)
    moved = _move_approvals(ticket, person)
    ticket_assignment.chat_line(ticket, note)
    if person != by:
        subject = frappe.db.get_value(TICKET, ticket, "subject") or ""
        deliver(
            [person],
            assistant.card(
                _("Ticket #{0} is yours").format(ticket),
                [subject, note, *moved],
                links=[(_("Open the ticket"), _ticket_url(ticket))],
            ),
            _("Ticket #{0} is yours: {1}").format(ticket, note),
            ticket,
        )
    return note


def _give_task(ticket: str, person: str, by: str, note: str):
    """The ticket's open Copilot tasks go to the person too."""
    from helpdesk.utils import add_assignment

    for task in frappe.get_all(
        RUN,
        filters={"ticket": ticket, "task": ["is", "set"]},
        pluck="task",
        distinct=True,
    ):
        if frappe.db.get_value("Task", task, "status") in ("Completed", "Cancelled"):
            continue
        if person in (
            frappe.parse_json(frappe.db.get_value("Task", task, "_assign") or "[]")
            or []
        ):
            continue
        add_assignment(
            {
                "assign_to": [person],
                "doctype": "Task",
                "name": task,
                "description": note[:500],
                "assigned_by": by,
            },
            ignore_permissions=True,
        )


def _move_approvals(ticket: str, person: str) -> list[str]:
    """A fix waiting for approval moves to the person when they may approve it; else it stays,
    and the returned line says why."""
    from helpdesk.copilot import approvals

    lines = []
    for name in frappe.get_all(
        APPROVAL, filters={"ticket": ticket, "status": "Pending"}, pluck="name"
    ):
        approval = frappe.get_doc(APPROVAL, name)
        if approval.assigned_to == person:
            continue
        refusal = approvals.may_decide(approval, person)
        if refusal:
            lines.append(
                _("The fix waiting for approval stays with {0}: {1}").format(
                    get_fullname(approval.assigned_to)
                    if approval.assigned_to
                    else _("the approvers"),
                    refusal,
                )
            )
            continue
        approval.db_set(
            {"assigned_to": person, "assigned_at": now_datetime()},
            update_modified=False,
        )
        approvals.announce(
            approval,
            _("A Copilot fix waits for your approval on ticket {0}").format(ticket),
        )
        lines.append(_("The fix waiting for approval is yours to decide."))
    return lines


def add_to_ticket(ticket: str, person: str, why: str):
    """Adds a person to the ticket's assignment, keeping whoever has it."""
    from helpdesk.utils import add_assignment

    if person in _open_assignees(ticket):
        return
    add_assignment(
        {
            "assign_to": [person],
            "doctype": TICKET,
            "name": str(ticket),
            "description": why[:500],
            "assigned_by": "Administrator",
        },
        ignore_permissions=True,
    )


# --- risk alerts -----------------------------------------------------------------------------


def alert_risk(
    title: str,
    lines=(),
    ticket: str | None = None,
    customer: str | None = None,
    link: str | None = None,
    skip=(),
):
    """Risky work, for information: queued, so it never slows or stops the caller."""
    try:
        if not risk_people() and not _risk_to_coordinators():
            return
        frappe.enqueue(
            "helpdesk.copilot.people.send_risk_alert",
            queue="short",
            title=title,
            lines=[str(line) for line in lines if line],
            ticket=ticket,
            customer=customer,
            link=link,
            skip=list(skip),
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )
    except Exception:
        frappe.log_error(title="Copilot could not queue a risk alert")


def _risk_to_coordinators() -> bool:
    """The settings' tick `risk_alert_coordinators`: on by default (the Phase 22 patch switches it
    on for sites that had the settings before)."""
    return bool(_settings().get("risk_alert_coordinators"))


def risk_recipients(customer: str | None, ticket: str | None = None) -> list[str]:
    people = list(risk_people())
    if _risk_to_coordinators():
        if not customer and ticket:
            customer = frappe.db.get_value(TICKET, str(ticket), "customer")
        if customer:
            people += (
                coordinators_today(customer) or of_customer(customer)["coordinators"]
            )
    return list(dict.fromkeys(people))


def send_risk_alert(title, lines=(), ticket=None, customer=None, link=None, skip=()):
    """Background: the alert to the risk alert people and the project coordinators."""
    from helpdesk.copilot import assistant

    try:
        people = [p for p in risk_recipients(customer, ticket) if p not in (skip or ())]
        if not people:
            return []
        url = link or (_ticket_url(ticket) if ticket else None)
        reply = assistant.card(
            title,
            [*lines, _("For your information: who approves does not change.")],
            links=[(_("Open"), url)] if url else [],
            tone="warning",
        )
        return deliver(people, reply, title, ticket)
    except Exception:
        frappe.log_error(title="Copilot could not send a risk alert")
        return []


# --- infrastructure ----------------------------------------------------------------------------


def tell_infra(
    subject: str, doctype: str = "HDS Copilot Settings", name=None
) -> list[str]:
    """A watcher message for the infrastructure people (else the Copilot approvers)."""
    from helpdesk.work_reminders import notify_users

    people = infra_people() or stand_ins()
    notify_users(people, doctype, name or doctype, subject, escalate=True, once=False)
    return people


# --- the overview on the settings page --------------------------------------------------------


@frappe.whitelist()
def overview() -> dict:
    """Who Copilot goes to today for each customer, and every empty place."""
    frappe.has_permission("HDS Copilot Settings", "read", throw=True)
    warnings = []
    if not common_coordinators():
        warnings.append(
            _(
                "No common project coordinator: customers without their own have nobody to hear of new tickets."
            )
        )
    if not risk_people():
        warnings.append(_("Nobody is set in Risk Alerts Go To."))
    if not infra_people():
        warnings.append(
            _(
                "No infrastructure people: the Approvers decide Press, AWS and repair actions."
            )
        )
    if not stand_ins():
        warnings.append(
            _(
                "No Approvers: where nobody else is set, the Agent Managers are told, as before Phase 22."
            )
        )
    rows = []
    for customer in frappe.get_all(
        CUSTOMER, pluck="name", order_by="name asc", limit=500
    ):
        people = of_customer(customer)
        found = for_ticket(customer)
        empty = [
            label
            for key, label in (
                ("first", _("first developer")),
                ("second", _("second developer")),
            )
            if not people[key]
        ]
        if not people["coordinators"]:
            empty.append(_("project coordinator"))
        rows.append(
            {
                "customer": customer,
                "first": get_fullname(people["first"]) if people["first"] else "",
                "second": get_fullname(people["second"]) if people["second"] else "",
                "fix_approver": get_fullname(people["fix_approver"])
                if people["fix_approver"]
                else "",
                "coordinators": ", ".join(
                    get_fullname(u) for u in people["coordinators"]
                ),
                "coordinators_from": people["coordinators_from"],
                "today": get_fullname(found["user"]) if found["user"] else "",
                "why": found["why"],
                "empty": empty,
            }
        )
    return {
        "warnings": warnings,
        "common": {
            "coordinators": [get_fullname(u) for u in common_coordinators()],
            "risk": [get_fullname(u) for u in risk_people()],
            "infra": [get_fullname(u) for u in infra_people()],
        },
        "customers": rows,
    }
