# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Who Copilot goes to. Every person comes from settings: the code names nobody and picks nobody
by a job role (docs/tbo-copilot.md, "People").

Phase 23 keeps everyone in one kind of table (HDS Copilot Role Person): a role, a person, a level
(Main, Fallback 1, 2, 3), Active and an optional Until date.
- **Every customer**: HDS Copilot Settings → People (`copilot_people`).
- **One customer**: HD Customer → Copilot People (`custom_copilot_people`), for the Developer, Fix
  Approver and Project Coordinator roles. A customer's rows come before the common ones.

For each role Copilot walks `CHAINS`: the customer's rows level by level, the common rows level
by level, then the next role, and takes the first group with someone working today (TBO Support's
rule: an active agent, not on approved leave, not Unavailable). An empty Developer is the
customer's Ticket Owner, then its Backup Ticket Owner. With no Leader set anywhere, the Agent
Managers are the last resort, and the settings page warns.
"""

import frappe
from frappe import _
from frappe.utils import (
    format_date,
    get_datetime,
    get_fullname,
    get_url,
    getdate,
    now_datetime,
    nowdate,
)

from helpdesk import ticket_assignment
from helpdesk.copilot import settings as copilot_settings

CUSTOMER = "HD Customer"
TICKET = "HD Ticket"
RUN = "HDS Copilot Run"
APPROVAL = "HDS Copilot Approval"
SETTINGS = "HDS Copilot Settings"
ROLE_PERSON = "HDS Copilot Role Person"
TABLE = "copilot_people"  # on the settings
CUSTOMER_TABLE = "custom_copilot_people"  # on each customer
MANAGER = "Agent Manager"
NOTICE_BOTH = "Teams and TBO Support"
NOTICE_PANEL = "TBO Support only"
NOTICE_OFF = "Off"
ASSIGN, KEEP = "people_assign", "people_keep"
VERBS = (ASSIGN, KEEP)
CHOICES_LIMIT = (
    100  # people offered in Assign to: the customer's people first, then the least busy
)
OPEN_CATEGORIES = ("Open", "Paused")

DEVELOPER = "Developer"
FIX_APPROVER = "Fix Approver"
COORDINATOR = "Project Coordinator"
SENIOR = "Senior"
LEADER = "Leader"
INFRA = "Infrastructure"
INFRA_SENIOR = "Infrastructure Senior"
RISK = "Risk Alerts"
DEPLOY = "Deploy Notices"
ROLES = (
    DEVELOPER,
    FIX_APPROVER,
    COORDINATOR,
    SENIOR,
    LEADER,
    INFRA,
    INFRA_SENIOR,
    RISK,
    DEPLOY,
)
CUSTOMER_ROLES = (DEVELOPER, FIX_APPROVER, COORDINATOR)
LEVELS = ("Main", "Fallback 1", "Fallback 2", "Fallback 3")
# roles whose people act in TBO Support (approve, assign, take tickets): only active agents count
ACTING = (DEVELOPER, FIX_APPROVER, COORDINATOR, SENIOR, LEADER, INFRA, INFRA_SENIOR)

# where Copilot looks for each role, in order: (role, "customer" or "common")
CHAINS = {
    DEVELOPER: (
        (DEVELOPER, "customer"),
        (DEVELOPER, "common"),
        (COORDINATOR, "customer"),
        (COORDINATOR, "common"),
        (LEADER, "common"),
    ),
    # the common Fix Approvers stand in for every customer after the customer's own people
    # Project Coordinators assign and are told; they never approve (the owner, 17 Nov 2026)
    FIX_APPROVER: (
        (FIX_APPROVER, "customer"),
        (DEVELOPER, "customer"),
        (DEVELOPER, "common"),
        (FIX_APPROVER, "common"),
        (SENIOR, "common"),
        (LEADER, "common"),
    ),
    COORDINATOR: (
        (COORDINATOR, "customer"),
        (COORDINATOR, "common"),
        (LEADER, "common"),
    ),
    SENIOR: ((SENIOR, "common"), (LEADER, "common")),
    LEADER: ((LEADER, "common"),),
    INFRA: ((INFRA, "common"), (INFRA_SENIOR, "common"), (LEADER, "common")),
    INFRA_SENIOR: ((INFRA_SENIOR, "common"), (LEADER, "common")),
    RISK: ((RISK, "common"), (LEADER, "common")),
    DEPLOY: (
        (DEPLOY, "common"),
        (INFRA, "common"),
        (INFRA_SENIOR, "common"),
        (LEADER, "common"),
    ),
}


# --- the table -------------------------------------------------------------------------------


def _settings():
    return copilot_settings.get_settings()


def _cache(key: str):
    """A dict that lives while the settings page's overview is built (many customers, the same
    people), else None."""
    store = frappe.flags.get("copilot_people_cache")
    if store is None:
        return None
    return store.setdefault(key, {})


def _enabled(users) -> list[str]:
    """`users` with an enabled account, in order, once each."""
    users = [u for u in dict.fromkeys(users or []) if u]
    if not users:
        return []
    cache = _cache("enabled")
    missing = [u for u in users if cache is None or u not in cache]
    found = (
        set(
            frappe.get_all(
                "User", filters={"name": ["in", missing], "enabled": 1}, pluck="name"
            )
        )
        if missing
        else set()
    )
    if cache is not None:
        cache.update({u: u in found for u in missing})
        return [u for u in users if cache[u]]
    return [u for u in users if u in found]


def _live(rows) -> list:
    """Rows that count today: a person, Active, and Until not passed."""
    today = getdate(nowdate())
    return [
        row
        for row in rows or []
        if row.get("person")
        and row.get("active") not in (0, "0")
        and (not row.get("until") or getdate(row.get("until")) >= today)
    ]


def _common_rows() -> list:
    return list(_settings().get(TABLE) or [])


def _customer_rows(customer: str | None) -> list:
    if not customer:
        return []
    cache = _cache("customer_rows")
    if cache is not None and customer in cache:
        return cache[customer]
    rows = frappe.get_all(
        ROLE_PERSON,
        filters={
            "parenttype": CUSTOMER,
            "parentfield": CUSTOMER_TABLE,
            "parent": customer,
        },
        fields=["role", "person", "level", "active", "until", "idx"],
        order_by="idx asc",
    )
    if cache is not None:
        cache[customer] = rows
    return rows


def _by_level(rows, role: str, where: str) -> list[dict]:
    found = []
    for level in LEVELS:
        users = _enabled(
            row.get("person")
            for row in rows
            if row.get("role") == role and (row.get("level") or LEVELS[0]) == level
        )
        if users:
            found.append({"role": role, "where": where, "level": level, "users": users})
    return found


def agent_managers() -> list[str]:
    """The enabled Agent Managers: the last resort only while no Leader is set."""
    users = frappe.get_all(
        "Has Role", filters={"role": MANAGER, "parenttype": "User"}, pluck="parent"
    )
    return sorted(
        set(
            frappe.get_all(
                "User",
                filters={"name": ["in", users or [""]], "enabled": 1},
                pluck="name",
            )
        )
    )


def _owner_groups(customer: str) -> list[dict]:
    """A customer with no Developer of its own: its Ticket Owner (else Copilot's older Assigned
    Developer), then its Backup Ticket Owner."""
    row = (
        frappe.db.get_value(
            CUSTOMER,
            customer,
            ["ticket_owner", "backup_ticket_owner", "custom_assigned_developer"],
            as_dict=True,
        )
        or {}
    )
    found = []
    main = _enabled([row.get("ticket_owner") or row.get("custom_assigned_developer")])
    if main:
        found.append(
            {"role": DEVELOPER, "where": "owner", "level": LEVELS[0], "users": main}
        )
    backup = [u for u in _enabled([row.get("backup_ticket_owner")]) if u not in main]
    if backup:
        found.append(
            {"role": DEVELOPER, "where": "owner", "level": LEVELS[1], "users": backup}
        )
    return found


def groups(role: str, where: str, customer: str | None = None) -> list[dict]:
    """The people set for `role` in one place, level by level: [{"role", "where", "level",
    "users"}]. `where` is "customer" (a customer's own rows; for Developer, its ticket owners when
    it has none) or "common"."""
    if where == "customer":
        if not customer or role not in CUSTOMER_ROLES:
            return []
        found = _by_level(_live(_customer_rows(customer)), role, "customer")
        if not found and role == DEVELOPER:
            found = _owner_groups(customer)
        return found
    found = _by_level(_live(_common_rows()), role, "common")
    if not found and role == LEADER:
        managers = agent_managers()
        if managers:
            found = [
                {
                    "role": LEADER,
                    "where": "agent managers",
                    "level": LEVELS[0],
                    "users": managers,
                }
            ]
    return found


def chain_groups(role: str, customer: str | None = None, steps=None) -> list[dict]:
    """Every group Copilot would look at for `role`, in order."""
    found = []
    for step_role, where in steps or CHAINS[role]:
        found += groups(step_role, where, customer)
    return found


def everyone(role: str, customer: str | None = None) -> list[str]:
    """Everyone set for `role` (the customer's rows, then the common ones), working or not."""
    return list(
        dict.fromkeys(
            user
            for where in ("customer", "common")
            for group in groups(role, where, customer)
            for user in group["users"]
        )
    )


def in_chain(role: str, customer: str | None = None) -> set[str]:
    """Everyone the table and its fallbacks may put on `role`'s work: they may act on it."""
    return {user for group in chain_groups(role, customer) for user in group["users"]}


# --- who is working --------------------------------------------------------------------------


def working(users, acting: bool = True) -> list[str]:
    """`users` who can take work today, in order: TBO Support's rule (an active agent, not on
    approved leave, not Unavailable). For a role that only hears news (`acting` False), someone
    who is not an agent counts while their account is enabled and they are not on leave."""
    users = [u for u in dict.fromkeys(users or []) if u]
    if not users:
        return []
    cache = _cache("working" if acting else "hearing")
    missing = [u for u in users if cache is None or u not in cache]
    today = ticket_assignment.working_today(missing) if missing else set()
    if missing and not acting:
        from helpdesk.work_calendar import on_leave

        agents = set(
            frappe.get_all("HD Agent", filters={"name": ["in", missing]}, pluck="name")
        )
        others = [u for u in _enabled(missing) if u not in agents]
        if others:
            away = on_leave(users=others)
            today |= {u for u in others if u not in away}
    if cache is not None:
        cache.update({u: u in today for u in missing})
        return [u for u in users if cache[u]]
    return [u for u in users if u in today]


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


def resolve(
    role: str,
    customer: str | None = None,
    exclude=(),
    allowed=None,
    steps=None,
    anyone: bool = True,
) -> dict:
    """Who gets `role`'s work today: everyone working in the first group of its chain that has
    someone working. {"users", "role", "where", "level", "away": why each skipped person is away,
    "working": True}. `exclude`: never these (a fix's authors); `allowed`: only these (the
    seniors, for a sensitive fix). With nobody working anywhere and `anyone`, the first group with
    anybody at all, so the work is never lost ("working": False)."""
    first, away, seen = None, [], set()
    for group in chain_groups(role, customer, steps):
        users = [
            u
            for u in group["users"]
            if u not in (exclude or ()) and (allowed is None or u in allowed)
        ]
        if not users:
            continue
        on = working(users, acting=group["role"] in ACTING)
        if on:
            return {**group, "users": on, "away": away, "working": True}
        first = first or {**group, "users": users}
        for user in users:
            if user not in seen:
                seen.add(user)
                away.append(away_text(user))
    if anyone and first:
        return {**first, "away": away, "working": False}
    return {
        "users": [],
        "role": None,
        "where": None,
        "level": None,
        "away": away,
        "working": False,
    }


def label(found: dict) -> str:
    """Why Copilot went to this group, in a few words."""
    role, where, level = found.get("role"), found.get("where"), found.get("level")
    if not role:
        return _("nobody is set")
    if where == "owner":
        return (
            _("the customer's ticket owner")
            if level == LEVELS[0]
            else _("the customer's backup ticket owner")
        )
    if where == "agent managers":
        return _("an Agent Manager (no Leader is set)")
    level_text = _(level) if level != LEVELS[0] else ""
    text = _(role).lower() if role != LEADER else _("leader")
    if where == "common" and role in CUSTOMER_ROLES:
        text = _("{0} for every customer").format(text)
    return "{0} ({1})".format(text, level_text) if level_text else text


# --- the roles, as the rest of Copilot asks for them -----------------------------------------


def leaders() -> list[str]:
    """Everyone set as Leader (else the Agent Managers): the last resort for every message."""
    return [u for group in groups(LEADER, "common") for u in group["users"]]


def set_leaders() -> list[str]:
    """Only the people set as Leader: not the Agent Managers who stand in when none is (for news,
    which the Leaders asked for and the managers did not)."""
    return [
        u
        for group in groups(LEADER, "common")
        if group.get("where") != "agent managers"
        for u in group["users"]
    ]


def leaders_today() -> list[str]:
    """The Leaders working today (else all of them)."""
    return resolve(LEADER)["users"]


def seniors() -> list[str]:
    """Who may decide what needs a senior: the Seniors; with none set, the Leaders (else the
    Agent Managers)."""
    found = [u for group in groups(SENIOR, "common") for u in group["users"]]
    return found or leaders()


def stand_in_approvers() -> list[str]:
    """The common Fix Approvers: they stand in for every customer."""
    return [u for group in groups(FIX_APPROVER, "common") for u in group["users"]]


def infra_people() -> list[str]:
    """Everyone set in Infrastructure or Infrastructure Senior (empty: not set)."""
    return list(dict.fromkeys(everyone(INFRA) + everyone(INFRA_SENIOR)))


def infra_seniors() -> list[str]:
    return everyone(INFRA_SENIOR)


def notice_people(role: str) -> list[str]:
    """For a role that only hears news (Risk Alerts, Deploy Notices): everyone set in it, else
    the next role in its chain."""
    return everyone(role) or resolve(role)["users"]


def coordinators(customer: str | None) -> list[str]:
    """The customer's project coordinators as set (its own, else the common ones), working or not."""
    own = [
        u for group in groups(COORDINATOR, "customer", customer) for u in group["users"]
    ]
    return own or [u for group in groups(COORDINATOR, "common") for u in group["users"]]


def coordinators_from(customer: str | None) -> str:
    return "customer" if groups(COORDINATOR, "customer", customer) else "common"


def coordinators_today(customer: str | None) -> list[str]:
    """The customer's project coordinators working today (Main first, then the fallbacks; its
    own, then the common ones). Never a Leader: see `need_a_person`."""
    return resolve(
        COORDINATOR,
        customer,
        steps=((COORDINATOR, "customer"), (COORDINATOR, "common")),
        anyone=False,
    )["users"]


def developers(customer: str | None) -> list[str]:
    """The customer's developers as set, in order (its own rows, else its ticket owners; then
    the common ones)."""
    return list(
        dict.fromkeys(
            u
            for group in chain_groups(
                DEVELOPER, customer, ((DEVELOPER, "customer"), (DEVELOPER, "common"))
            )
            for u in group["users"]
        )
    )


def of_customer(customer: str | None) -> dict:
    """The customer's people as set: {"developers", "fix_approvers", "coordinators",
    "coordinators_from"}."""
    return {
        "developers": developers(customer),
        "fix_approvers": [
            u
            for group in groups(FIX_APPROVER, "customer", customer)
            for u in group["users"]
        ],
        "coordinators": coordinators(customer),
        "coordinators_from": coordinators_from(customer),
    }


def chosen(ticket: str | None) -> str | None:
    """The person a project coordinator chose for the ticket, if any."""
    if not ticket:
        return None
    return frappe.db.get_value(TICKET, str(ticket), "custom_copilot_person")


def for_ticket(
    customer: str | None, ticket: str | None = None, fix: bool = False
) -> dict:
    """Who Copilot goes to for this customer's work today, and why.

    {"user", "step": chosen, fix_approver, developer, coordinator, leader or None, "why",
     "away": why each skipped person is away, "coordinators": those who choose when no developer
     can take it, "no_developer": no developer can take it, "developer_set": anyone is set as a
     developer at all}. `fix`: the customer's fix approver comes before the developers."""
    away = []
    person = chosen(ticket)
    if person:
        if working([person]):
            return {
                "user": person,
                "step": "chosen",
                "why": _("chosen by a project coordinator"),
                "away": [],
                "coordinators": [],
                "no_developer": False,
                "developer_set": True,
            }
        away.append(away_text(person))
    steps = ((DEVELOPER, "customer"), (DEVELOPER, "common"))
    if fix:
        steps = ((FIX_APPROVER, "customer"), *steps)
    found = resolve(DEVELOPER, customer, steps=steps, anyone=False)
    away += found["away"]
    if found["users"]:
        why = label(found)
        if away:
            why = "{0} ({1})".format(why, "; ".join(away))
        return {
            "user": ticket_assignment.least_busy(found["users"]),
            "step": "fix_approver" if found["role"] == FIX_APPROVER else "developer",
            "why": why,
            "away": away,
            "coordinators": [],
            "no_developer": False,
            "developer_set": True,
        }
    developer_set = bool(developers(customer))
    choosers = resolve(COORDINATOR, customer, anyone=False)
    lead = ticket_assignment.least_busy(choosers["users"])
    if lead:
        why = label(choosers)
        why = "{0} ({1})".format(
            why,
            "; ".join(away)
            if away
            else _("the customer has no developer set")
            if not developer_set
            else _("no developer is working today"),
        )
    else:
        why = (
            _("nobody: no developer, project coordinator or leader is working today")
            if developer_set or choosers["away"]
            else _("nobody is set: no developer, project coordinator or leader")
        )
    return {
        "user": lead,
        "step": ("leader" if choosers["role"] == LEADER else "coordinator")
        if lead
        else None,
        "why": why,
        "away": away,
        "coordinators": choosers["users"],
        "no_developer": True,
        "developer_set": developer_set,
    }


def developer(customer: str | None, ticket: str | None = None) -> str | None:
    """The developer who takes the customer's work today (chosen, or a developer), or None."""
    found = for_ticket(customer, ticket)
    return found["user"] if found["step"] in ("chosen", "developer") else None


def may_approve(customer: str | None, ticket: str | None = None) -> set[str]:
    """Who the table and its fallbacks may put on this customer's fixes (and the person a
    coordinator chose, unless that is only a coordinator): they may decide them (Phase 23, A2;
    Phase 24: coordinators never approve)."""
    found = in_chain(FIX_APPROVER, customer)
    person = chosen_approver(ticket, customer)
    if person:
        found.add(person)
    return found


def chosen_approver(ticket: str | None, customer: str | None) -> str | None:
    """The person a coordinator chose for the ticket, when they may approve its fixes: anyone but
    a Project Coordinator who is nothing more on this customer's fixes (Phase 24: coordinators
    assign tickets and are told everything; they never approve, so choosing themselves does not
    make them the approver)."""
    person = chosen(ticket)
    if not person:
        return None
    if person in all_coordinators(customer) and person not in in_chain(
        FIX_APPROVER, customer
    ):
        return None
    return person


def all_coordinators(customer: str | None) -> set[str]:
    """Everyone set as a Project Coordinator for this customer or for every customer."""
    return {
        user
        for where in ("customer", "common")
        for group in groups(COORDINATOR, where, customer)
        for user in group["users"]
    }


def need_a_person(customer: str | None) -> list[str]:
    """Who hears that Copilot needs a person and nobody on the ticket can: the project
    coordinators working today, else a Leader; with nobody working, whoever is set."""
    return resolve(COORDINATOR, customer)["users"]


# --- telling people --------------------------------------------------------------------------


def _ticket_url(ticket: str) -> str:
    return get_url(f"/helpdesk/tickets/{ticket}")


def deliver(
    people,
    reply: dict,
    subject: str,
    ticket: str | None = None,
    panel_only=False,
    doctype: str | None = None,
    name: str | None = None,
    **links,
):
    """One message per person and event: the card (Teams when the bot reaches them, else the TBO
    Support panel), and a TBO Support notification that sends no chat message or email of its own
    when the card already went to Teams, or when `panel_only` keeps it in TBO Support. Returns who
    got it."""
    from helpdesk.copilot import assistant
    from helpdesk.work_reminders import helpdesk_path, new_notification, notify_users

    if not doctype:
        doctype, name = (TICKET, str(ticket)) if ticket else (SETTINGS, SETTINGS)
    told = []
    for person in dict.fromkeys(people or []):
        used = assistant.send(
            person,
            reply,
            channel="Web" if panel_only else None,
            **({"ticket": ticket} if ticket else {}),
            **links,
        )
        if used == "Teams" or panel_only:
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


def can_take_tickets(user: str) -> bool:
    """An active agent who works tickets (not a writer, designer, DM or sales employee)."""
    from helpdesk.content_team import sees_no_tickets

    return bool(
        frappe.db.get_value("HD Agent", {"name": user, "is_active": 1})
    ) and not sees_no_tickets(user)


def choices(customer: str | None = None, exclude=()) -> list[list[str]]:
    """Assign to: the customer's own people working today first (developers, then coordinators),
    then every other agent who works tickets and is working today, least busy first, each with
    their open tickets."""
    from helpdesk.content_team import sees_no_tickets

    agents = frappe.get_all("HD Agent", filters={"is_active": 1}, pluck="name")
    people = [u for u in working(agents) if u not in exclude and not sees_no_tickets(u)]
    load = ticket_assignment.open_load(people)
    own = [u for u in developers(customer) + coordinators(customer) if u in load]
    own = list(dict.fromkeys(own))
    rest = sorted(
        (u for u in people if u not in own),
        key=lambda u: (load[u], get_fullname(u) or u),
    )
    return [
        [_("{0} ({1} open)").format(get_fullname(u), load[u]), u]
        for u in (own + rest)[:CHOICES_LIMIT]
    ]


def notice_card(doc, found: dict, sent_at: str) -> dict:
    """The coordinators' card for a ticket: what came in, who has it and why, and Assign to."""
    from helpdesk.copilot import assistant

    holders = _open_assignees(doc.name)
    holding = ", ".join(get_fullname(u) for u in holders) or _("nobody yet")
    if found["no_developer"]:
        if found.get("developer_set"):
            title = _("Ticket #{0} from {1}: no developer is working today").format(
                doc.name, doc.customer or _("an unknown customer")
            )
            reason = "; ".join(found["away"]) or _("No developer is working today.")
        else:
            title = _("Ticket #{0} from {1}: no developer is set").format(
                doc.name, doc.customer or _("an unknown customer")
            )
            reason = _(
                "The customer has no developer set (HD Customer → Copilot People, or its Ticket Owner)."
            )
        lines = [
            doc.subject or "",
            reason,
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
                _("Keep {0}").format(get_fullname(holders[0])),
                KEEP,
                ticket=doc.name,
                at=sent_at,
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
                "choices": choices(doc.customer),
            }
        ],
        tone="warning" if found["no_developer"] else "default",
    )


def _configured(customer: str | None) -> bool:
    """Someone is set to hear of this customer's tickets: a project coordinator (its own or a
    common one), or a developer."""
    return bool(coordinators(customer) or developers(customer))


def on_ticket_insert(doc, method=None):
    """Hook: a new ticket's project coordinators hear of it, or choose who takes it, and the
    Leaders see it in TBO Support's panel (Phase 24). The error watch's own tickets are left to the
    infrastructure people."""
    try:
        if not doc.get("custom_copilot_source"):
            frappe.enqueue(
                "helpdesk.copilot.people.tell_leaders_of_ticket",
                queue="short",
                ticket=doc.name,
                enqueue_after_commit=True,
                now=frappe.flags.in_test,
            )
        if doc.get("custom_copilot_source") or not _configured(doc.customer):
            return
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


def tell_leaders_of_ticket(ticket: str) -> list[str]:
    """Background: every new ticket of every customer, in the Leaders' TBO Support panel, never
    Teams (the owner, 17 Nov 2026). Returns who was told."""
    from helpdesk.work_reminders import notify_users

    leaders = set_leaders()
    if not leaders:
        return []
    doc = (
        frappe.db.get_value(TICKET, str(ticket), ["subject", "customer"], as_dict=True)
        or frappe._dict()
    )
    text = _("New ticket #{0} for {1}: {2}").format(
        ticket, doc.customer or _("no customer"), doc.subject or ""
    )
    notify_users(
        leaders,
        TICKET,
        str(ticket),
        text[:300],
        notification_type="New Ticket",
        deliver=False,
    )
    return leaders


def tell_coordinators(ticket: str, again: bool = False) -> list[str]:
    """Background: the coordinators' card for a ticket, and the choice when no developer can take
    it. A new ticket is told only to project coordinators actually set; the choice, with nobody
    set, goes to a Leader. Asked again, only people working today are asked (nothing on days
    off). Returns who was told."""
    settings = _settings()
    mode = settings.get("new_ticket_notice") or NOTICE_BOTH
    doc = frappe.get_doc(TICKET, str(ticket))
    found = for_ticket(doc.customer, doc.name)
    if found["no_developer"] and _taken(doc.name):
        # TBO Support already gave it to someone working today (its project team): nobody needs to
        # choose
        found = {**found, "no_developer": False}
    if mode == NOTICE_OFF and not found["no_developer"]:
        return []
    if found["no_developer"]:
        people = found["coordinators"] or (
            [] if again else resolve(COORDINATOR, doc.customer)["users"]
        )
    else:
        people = coordinators_today(doc.customer) or coordinators(doc.customer)
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
                (
                    _(
                        "No developer is working today; {0} asked to choose who takes it."
                    )
                    if found.get("developer_set")
                    else _(
                        "The customer has no developer set; {0} asked to choose who takes it."
                    )
                ).format(", ".join(get_fullname(u) for u in told)),
            )
    return told


def _taken(ticket: str) -> bool:
    """Someone working today has the ticket (a normal assignment on the ticket page ends the
    wait)."""
    return bool(working(_open_assignees(ticket)))


def ask_again():
    """06:45: tickets whose coordinators have not chosen yet are asked again; a ticket whose
    developer is back, or that someone working today was given, stops waiting."""
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
            if _taken(name) or not for_ticket(doc.customer, doc.name)["no_developer"]:
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
    """The customer's project coordinators (its own, the common ones) and the Leaders: everyone
    the table may ask to choose."""
    return user in in_chain(COORDINATOR, customer)


def _decided_card(ticket: str, note: str) -> dict:
    """The choice made, and Change: another person can still be chosen (Phase 23, A15)."""
    from helpdesk.copilot import assistant

    customer = frappe.db.get_value(TICKET, str(ticket), "customer")
    return assistant.card(
        _("Ticket #{0}").format(ticket),
        [note],
        links=[(_("Open the ticket"), _ticket_url(ticket))],
        actions=[
            assistant.button(
                _("Change"), ASSIGN, ticket=str(ticket), at=str(now_datetime())
            )
        ],
        inputs=[
            {
                "id": "person",
                "type": "choice",
                "label": _("Assign to"),
                "choices": choices(customer),
            }
        ],
        tone="good",
    )


def on_ticket_assigned(doc, method=None):
    """ToDo after_insert: a ticket given to someone by hand (not by a coordinator's card) ends the
    coordinator's choice and the wait for one; Copilot follows the new assignee's chain again."""
    if doc.reference_type != TICKET or frappe.flags.get("copilot_choosing"):
        return
    try:
        row = frappe.db.get_value(
            TICKET,
            doc.reference_name,
            ["custom_copilot_person", "custom_copilot_waiting"],
            as_dict=True,
        )
        if not row or (
            not row.custom_copilot_waiting
            and (
                not row.custom_copilot_person
                or row.custom_copilot_person == doc.allocated_to
            )
        ):
            return
        values = {"custom_copilot_waiting": 0}
        # someone added beside the chosen person (a helper, "Talk to a person") keeps the
        # choice; only a ticket taken away from them ends it (review of Phase 23)
        if (
            row.custom_copilot_person
            and row.custom_copilot_person != doc.allocated_to
            and row.custom_copilot_person not in _open_assignees(doc.reference_name)
        ):
            values.update(
                {
                    "custom_copilot_person": None,
                    "custom_copilot_person_note": None,
                    "custom_copilot_person_at": None,
                }
            )
        frappe.db.set_value(TICKET, doc.reference_name, values, update_modified=False)
    except Exception:
        frappe.log_error(
            title=f"Copilot could not follow the assignment of {doc.reference_name}"
        )


def press(user: str, channel: str, verb: str, data: dict, inputs: dict) -> dict:
    """Assign or Keep on a coordinator's card; the first choice stands."""
    from helpdesk.copilot import assistant

    def refuse(text):
        return {"replies": [assistant.text_card(text, "warning")], "card": None}

    ticket = str(data.get("ticket") or "")
    if not ticket or not frappe.db.exists(TICKET, ticket):
        return {
            "replies": [assistant.text_card(_("That ticket no longer exists."))],
            "card": None,
        }
    customer = frappe.db.get_value(TICKET, ticket, "customer")
    if not may_assign(user, customer):
        return refuse(
            _(
                "Only this customer's project coordinators and the leaders choose who takes its tickets."
            )
        )
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
            return refuse(_("Nobody has it yet; choose someone."))
        person, keep = holders[0], True
    else:
        person, keep = str((inputs or {}).get("person") or "").strip(), False
        if not person:
            return refuse(_("Choose a person first."))
        if not can_take_tickets(person):
            return refuse(
                _(
                    "{0} does not work tickets (not an active agent, or in a team that does not)."
                ).format(get_fullname(person) or person)
            )
    try:
        note = choose(ticket, person, user, keep=keep)
    except frappe.ValidationError as e:
        frappe.db.rollback()
        return refuse(str(e) or _("TBO Support refused that choice."))
    return {
        "replies": [assistant.text_card(note, "good")],
        "card": _decided_card(ticket, note),
    }


def _role_word(user: str, customer: str | None) -> str:
    """How the person who chose is named in the ticket's chat."""
    if user in coordinators(customer):
        return _("project coordinator")
    if user in leaders():
        return _("leader")
    return _("stand-in")


def choose(ticket: str, person: str, by: str, keep: bool = False) -> str:
    """The coordinator's choice: the ticket (and its Copilot task) goes to `person`, Copilot's
    approvals and news for it follow, and the ticket's chat says so. Returns that line."""
    from helpdesk.copilot import assistant
    from helpdesk.utils import add_assignment, remove_assignment

    ticket = str(ticket)
    waiting, customer = frappe.db.get_value(
        TICKET, ticket, ["custom_copilot_waiting", "customer"]
    )
    template = (
        _("Kept with {0} by {1} {2}") if keep else _("Assigned to {0} by {1} {2}")
    )
    note = template.format(
        get_fullname(person), _role_word(by, customer), get_fullname(by)
    )
    if waiting:
        note = "{0}: {1}".format(note, _("no developer could take it"))
    if not keep:
        holders = _open_assignees(ticket)
        for other in holders:
            if other != person:
                remove_assignment(TICKET, ticket, other, ignore_permissions=True)
        if person not in holders:
            frappe.flags.copilot_choosing = True
            try:
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
            finally:
                frappe.flags.copilot_choosing = False
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
    approval: bool = True,
):
    """Risky work, for information: queued, so it never slows or stops the caller."""
    try:
        frappe.enqueue(
            "helpdesk.copilot.people.send_risk_alert",
            queue="short",
            title=title,
            lines=[str(line) for line in lines if line],
            ticket=ticket,
            customer=customer,
            link=link,
            skip=list(skip),
            approval=approval,
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
    """Risk Alerts (else a Leader), and with the tick the customer's project coordinators."""
    people = list(notice_people(RISK))
    if _risk_to_coordinators():
        if not customer and ticket:
            customer = frappe.db.get_value(TICKET, str(ticket), "customer")
        if customer:
            people += coordinators_today(customer) or coordinators(customer)
    return list(dict.fromkeys(people))


def send_risk_alert(
    title, lines=(), ticket=None, customer=None, link=None, skip=(), approval=True
):
    """Background: the alert to the risk alert people and the project coordinators. `approval`:
    the alert is about something someone approves (else no line about who approves)."""
    from helpdesk.copilot import assistant

    try:
        people = [p for p in risk_recipients(customer, ticket) if p not in (skip or ())]
        if not people:
            return []
        url = link or (_ticket_url(ticket) if ticket else None)
        reply = assistant.card(
            title,
            [*lines, _("For your information: who approves does not change.")]
            if approval
            else [*lines, _("For your information.")],
            links=[(_("Open"), url)] if url else [],
            tone="warning",
        )
        return deliver(people, reply, title, ticket)
    except Exception:
        frappe.log_error(title="Copilot could not send a risk alert")
        return []


# --- infrastructure ----------------------------------------------------------------------------


def tell_infra(subject: str, doctype: str = SETTINGS, name=None) -> list[str]:
    """A watcher message for the infrastructure people working today (else Infrastructure
    Senior, else a Leader)."""
    from helpdesk.work_reminders import notify_users

    people = resolve(INFRA)["users"]
    notify_users(people, doctype, name or doctype, subject, escalate=True, once=False)
    return people


# --- moving today's settings (the Phase 23 patch, and tests written before it) ----------------


def rows_from_old_settings(values) -> list[dict]:
    """Phase 22's tables on the settings as rows of the People table."""

    def people(field):
        return [
            row
            for row in (values.get(field) or [])
            if row.get("user") and row.get("active") not in (0, "0")
        ]

    found = []
    for row in people("project_coordinators"):
        found.append({"role": COORDINATOR, "person": row.get("user")})
    for row in people("approvers"):
        if row.get("senior"):
            found.append({"role": SENIOR, "person": row.get("user")})
        found.append({"role": FIX_APPROVER, "person": row.get("user")})
    for row in people("infrastructure_people"):
        found.append(
            {
                "role": INFRA_SENIOR if row.get("senior") else INFRA,
                "person": row.get("user"),
            }
        )
    for row in people("risk_alert_people"):
        found.append({"role": RISK, "person": row.get("user")})
    for row in people("deploy_notice_people"):
        found.append({"role": DEPLOY, "person": row.get("user")})
    return [{"level": LEVELS[0], "active": 1, **row} for row in found]


def rows_from_old_customer(row) -> list[dict]:
    """Phase 22's fields on a customer as rows of its Copilot People. The developers are copied
    only when they differ from the ticket owners (an empty Developer follows the owners)."""
    found = []
    owner = row.get("ticket_owner") or row.get("custom_assigned_developer")
    backup = row.get("backup_ticket_owner")
    # an empty Phase 22 developer was the owner (or the backup): once one differs, both are
    # copied, or the other would be lost (review of Phase 23)
    first = row.get("custom_first_developer") or owner
    second = row.get("custom_second_developer") or backup
    if (first and first != owner) or (second and second != backup):
        if first:
            found.append({"role": DEVELOPER, "person": first, "level": LEVELS[0]})
        if second and second != first:
            found.append({"role": DEVELOPER, "person": second, "level": LEVELS[1]})
    if row.get("custom_fix_approver"):
        found.append(
            {
                "role": FIX_APPROVER,
                "person": row.get("custom_fix_approver"),
                "level": LEVELS[0],
            }
        )
    for coordinator in row.get("coordinators") or []:
        found.append({"role": COORDINATOR, "person": coordinator, "level": LEVELS[0]})
    return [{"active": 1, **r} for r in found]


# --- a customer's rows -------------------------------------------------------------------------


CUSTOMER_COPILOT_FIELDS = (
    "custom_copilot_enabled",
    "custom_copilot_level",
    "custom_copilot_watch",
)


def _customer_copilot(doc) -> tuple:
    """What a customer's Copilot settings say: on or off, how far, who; for telling a change. As
    text, so a form's "0" or "2026-12-01" equals the stored 0 or date."""

    def plain(value) -> str:
        return "" if value is None else str(value)

    return (
        tuple(plain(doc.get(field)) for field in CUSTOMER_COPILOT_FIELDS),
        tuple(
            tuple(
                plain(row.get(key))
                for key in ("role", "person", "level", "active", "until")
            )
            for row in doc.get(CUSTOMER_TABLE) or []
        ),
    )


def validate_customer(doc, method=None):
    """HD Customer validate: its Copilot People hold only the customer's own roles, and only TBO
    Support's agents change its Copilot settings (a customer's own manager may edit the rest of
    their record, never how far Copilot goes or who approves its fixes)."""
    from helpdesk.utils import is_agent

    before = None if doc.is_new() else doc.get_doc_before_save()
    if (
        before
        and _customer_copilot(before) != _customer_copilot(doc)
        and not is_agent()
    ):
        frappe.throw(
            _("Only TBO Support agents change a customer's Copilot settings."),
            frappe.PermissionError,
        )
    for row in doc.get(CUSTOMER_TABLE) or []:
        if row.role and row.role not in CUSTOMER_ROLES:
            frappe.throw(
                _(
                    "Row {0}: {1} is set once for every customer, in HDS Copilot Settings → People. A customer's own Copilot People are Developer, Fix Approver and Project Coordinator."
                ).format(row.idx, _(row.role))
            )


# --- hand over someone's places -----------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def hand_over_places(
    from_user: str,
    to_user: str,
    customer: str | None = None,
    dry_run: bool | int | str = 1,
) -> dict:
    """Someone leaves or changes job: every row they hold (in the settings and on customers, or on
    one customer) goes to `to_user`, and their waiting fix approvals move along the chain. With
    `dry_run` it only counts."""
    frappe.has_permission(SETTINGS, "write", throw=True)
    dry_run = frappe.utils.cint(dry_run)
    if not from_user or not to_user or from_user == to_user:
        frappe.throw(_("Choose two different people."))
    if not _enabled([to_user]):
        frappe.throw(_("{0} has no enabled account.").format(to_user))
    filters = {"person": from_user, "parenttype": ["in", [SETTINGS, CUSTOMER]]}
    if customer:
        filters.update({"parenttype": CUSTOMER, "parent": customer})
    rows = frappe.get_all(
        ROLE_PERSON,
        filters=filters,
        fields=["name", "parent", "parenttype", "parentfield", "role", "level"],
    )
    pending = frappe.get_all(
        APPROVAL,
        filters={"assigned_to": from_user, "status": "Pending"},
        fields=["name", "ticket"],
    )
    if customer:
        pending = [
            p
            for p in pending
            if frappe.db.get_value(TICKET, p.ticket, "customer") == customer
        ]
    counts = {"rows": len(rows), "approvals": len(pending), "moved": 0, "removed": 0}
    if dry_run:
        return counts
    full_name = get_fullname(to_user)
    for row in rows:
        twin = frappe.db.exists(
            ROLE_PERSON,
            {
                "parent": row.parent,
                "parenttype": row.parenttype,
                "parentfield": row.parentfield,
                "role": row.role,
                "level": row.level,
                "person": to_user,
            },
        )
        if twin:
            frappe.db.delete(ROLE_PERSON, {"name": row.name})
            counts["removed"] += 1
        else:
            frappe.db.set_value(
                ROLE_PERSON,
                row.name,
                {"person": to_user, "full_name": full_name},
                update_modified=False,
            )
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    counts["moved"] = _move_from(pending, from_user)
    text = _(
        "{0}'s places in Copilot People ({1} rows, {2} waiting approvals) were handed over to {3} by {4}."
    ).format(
        get_fullname(from_user),
        counts["rows"],
        counts["approvals"],
        full_name,
        get_fullname(frappe.session.user),
    )
    frappe.get_doc(SETTINGS, SETTINGS).add_comment("Info", text)
    for parent in {r.parent for r in rows if r.parenttype == CUSTOMER}:
        frappe.get_doc(CUSTOMER, parent).add_comment("Info", text)
    return counts


def _move_from(pending, from_user: str) -> int:
    """Waiting fix approvals of someone who left go to the next person the chain gives."""
    from helpdesk.copilot import approvals

    moved = 0
    for row in pending:
        approval = frappe.get_doc(APPROVAL, row.name)
        run = frappe.get_doc(RUN, approval.run)
        successor = approvals.pick_approver(
            run,
            bool(approval.sensitive),
            exclude={from_user},
            copilot_only=bool(
                (frappe.parse_json(approval.payload or "{}") or {}).get("copilot_only")
            ),
        )
        if not successor:
            continue
        approval.db_set(
            {"assigned_to": successor, "assigned_at": now_datetime()},
            update_modified=False,
        )
        approvals.announce(
            approval,
            _("A Copilot fix waits for your approval on ticket {0}").format(
                approval.ticket
            ),
        )
        moved += 1
    return moved


# --- the overview on the settings page --------------------------------------------------------


def _names(users) -> str:
    return ", ".join(get_fullname(u) for u in users)


def _describe(group_list) -> str:
    """'A, B (Main); C (Fallback 1)'."""
    return "; ".join(
        "{0} ({1})".format(_names(g["users"]), _(g["level"])) for g in group_list
    )


def _warnings(customers: list[str]) -> list[str]:
    warnings = []
    missing = {
        COORDINATOR: _(
            "No common Project Coordinator: customers without their own hear nothing of new tickets, and a Leader chooses when no developer can take one."
        ),
        SENIOR: _(
            "No Senior: the Leaders decide sensitive fixes, corrections and Deploy Now."
        ),
        INFRA: _(
            "No Infrastructure people: Press, AWS and repair actions and the watcher go to Infrastructure Senior, else a Leader."
        ),
        RISK: _("Nobody in Risk Alerts: they go to a Leader."),
        DEPLOY: _(
            "Nobody in Deploy Notices: they go to the Infrastructure people, else a Leader."
        ),
    }
    for role, text in missing.items():
        if not groups(role, "common"):
            warnings.append(text)
    if not [g for g in groups(LEADER, "common") if g["where"] == "common"]:
        warnings.append(
            _(
                "No Leader: the Agent Managers are the last resort for every message. Set a Leader in the People table."
            )
        )
    # people who cannot act where they are set
    rows = [("", r) for r in _common_rows()]
    for customer in customers:
        rows += [(customer, r) for r in _customer_rows(customer)]
    acting = {r.get("person") for _c, r in rows if r.get("role") in ACTING}
    agents = set(
        frappe.get_all(
            "HD Agent",
            filters={"name": ["in", list(acting) or [""]], "is_active": 1},
            pluck="name",
        )
    )
    for person in sorted(u for u in acting if u and u not in agents):
        warnings.append(
            _(
                "{0} is set in a role that acts in TBO Support but is not an active agent: Copilot skips them."
            ).format(get_fullname(person) or person)
        )
    today = getdate(nowdate())
    ended = sorted(
        {
            (c, r.get("person"), r.get("role"))
            for c, r in rows
            if r.get("until") and getdate(r.get("until")) < today
        }
    )
    for customer, person, role in ended:
        warnings.append(
            _("{0}'s cover as {1}{2} has ended; remove the row.").format(
                get_fullname(person) or person,
                _(role),
                " " + _("for {0}").format(customer) if customer else "",
            )
        )
    disabled = sorted(
        {r.get("person") for _c, r in rows if r.get("person")}
        - set(_enabled(r.get("person") for _c, r in rows))
    )
    for person in disabled:
        warnings.append(
            _("{0} is set in Copilot People but their account is disabled.").format(
                person
            )
        )
    return warnings


@frappe.whitelist()
def overview() -> dict:
    """Who Copilot goes to today, for every role and for each customer that uses Copilot or has
    its own people, and every empty place."""
    frappe.has_permission(SETTINGS, "read", throw=True)
    frappe.flags.copilot_people_cache = {}
    try:
        with_rows = set(
            frappe.get_all(
                ROLE_PERSON,
                filters={"parenttype": CUSTOMER, "parentfield": CUSTOMER_TABLE},
                pluck="parent",
                distinct=True,
            )
        )
        enabled = set(
            frappe.get_all(
                CUSTOMER, filters={"custom_copilot_enabled": 1}, pluck="name"
            )
        )
        customers = sorted(with_rows | enabled)
        common = []
        for role in ROLES:
            found = resolve(role, anyone=False)
            common.append(
                {
                    "role": _(role),
                    "set": _describe(
                        [g for g in groups(role, "common") if g["where"] == "common"]
                    ),
                    "today": _names(found["users"]),
                    "why": label(found)
                    if found["users"]
                    else _("nobody working today"),
                }
            )
        rows = []
        for customer in customers:
            found = for_ticket(customer)
            developer_groups = groups(DEVELOPER, "customer", customer)
            empty = []
            if not developer_groups:
                empty.append(_("developer"))
            if not groups(COORDINATOR, "customer", customer) and not groups(
                COORDINATOR, "common"
            ):
                empty.append(_("project coordinator"))
            rows.append(
                {
                    "customer": customer,
                    "copilot": customer in enabled,
                    "developers": _describe(developer_groups),
                    "developers_from": developer_groups[0]["where"]
                    if developer_groups
                    else "",
                    "fix_approvers": _describe(
                        groups(FIX_APPROVER, "customer", customer)
                    ),
                    "coordinators": _names(coordinators(customer)),
                    "coordinators_from": coordinators_from(customer),
                    "today": get_fullname(found["user"]) if found["user"] else "",
                    "why": found["why"],
                    "empty": empty,
                }
            )
        return {
            "warnings": _warnings(customers),
            "common": common,
            "customers": rows,
        }
    finally:
        frappe.flags.copilot_people_cache = None
