# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Adding a customer to Copilot from the helpdesk screens (Phase 30).

A customer is added on its own: its Copilot switches (Copilot Enabled, the level, Watch Errors) and
a site card per site. `checks` says, in the order a person sets a customer up, what the customer
still lacks before Copilot can work for it. Changes go through the documents' own permissions and
validation, so these screens allow exactly what Desk allows.
"""

import json

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, get_fullname, now_datetime, pretty_date

from helpdesk.client_api import capabilities
from helpdesk.copilot import people
from helpdesk.copilot import settings as copilot_settings

CUSTOMER = "HD Customer"
CARD = "HDS Site Registry"
CONNECTION = "HDS Support Connection"
TICKET = "HD Ticket"
PRODUCTION = "Production"
ENVIRONMENTS = ("Production", "UAT", "Sandbox")
# the switches a person may change here, and the customer fields they are
SWITCHES = {
    "enabled": "custom_copilot_enabled",
    "level": "custom_copilot_level",
    "watch": "custom_copilot_watch",
}
# the site card fields a person types; apps, Error Watch and sync times are written by Copilot
CARD_FIELDS = (
    "customer_name",
    "environment",
    "connection",
    "site_url",
    "press_site",
    "press_release_group",
    "shared_group",
)
# counted for "ready", in the order a customer is set up; "press" is needed from the Fix level only
READY = ("connection", "client", "card", "apps", "people", "enabled")
SHORT = {
    "connection": "Connection",
    "client": "New client app",
    "card": "Production site card",
    "apps": "Apps read",
    "people": "Someone gets the work",
    "enabled": "Copilot Enabled",
    "press": "Press site and group",
}
DONE, MISSING, LATER = "done", "missing", "later"
TICKET_DAYS = 30


# --- reading -----------------------------------------------------------------------------------


def _connections(customers: list[str]) -> dict[str, list[dict]]:
    rows = frappe.get_all(
        CONNECTION,
        filters={"customer_name": ["in", customers]},
        fields=[
            "name",
            "customer_name",
            "site_url",
            "connection_status",
            "last_health_check",
            "client_version",
            "client_capabilities",
        ],
        order_by="creation asc",
    )
    found = {}
    for row in rows:
        found.setdefault(row.customer_name, []).append(
            {
                "name": row.name,
                "site_url": row.site_url or "",
                "status": row.connection_status or "Pending",
                "checked": pretty_date(row.last_health_check)
                if row.last_health_check
                else "",
                # a client that reports what it can do is one with Copilot's changes (it also
                # lists its apps, which the older client cannot)
                "new_client": bool(capabilities(row)),
                "client_version": row.client_version or "",
            }
        )
    return found


def _cards(customers: list[str]) -> dict[str, list[dict]]:
    rows = frappe.get_all(
        CARD,
        filters={"customer_name": ["in", customers]},
        fields=["name", *CARD_FIELDS, "last_synced"],
        order_by="creation asc",
    )
    apps = {}
    if rows:
        for app in frappe.get_all(
            "HDS Site App",
            filters={"parenttype": CARD, "parent": ["in", [r.name for r in rows]]},
            fields=["parent", "app", "branch", "deployed_commit", "drift_status"],
            order_by="idx asc",
        ):
            apps.setdefault(app.parent, []).append(
                {
                    "app": app.app,
                    "branch": app.branch or "",
                    "commit": (app.deployed_commit or "")[:12],
                    "drift": app.drift_status or "Unknown",
                }
            )
    found = {}
    for row in rows:
        found.setdefault(row.customer_name, []).append(
            {
                "name": row.name,
                "environment": row.environment,
                "connection": row.connection or "",
                "site_url": row.site_url or "",
                "press_site": row.press_site or "",
                "press_release_group": row.press_release_group or "",
                "shared_group": bool(row.shared_group),
                "apps": apps.get(row.name, []),
                "apps_read": pretty_date(row.last_synced) if row.last_synced else "",
            }
        )
    return found


def _tickets(customers: list[str]) -> dict[str, int]:
    """New tickets in the last 30 days, per customer."""
    if not customers:
        return {}
    t = frappe.qb.DocType(TICKET)
    rows = (
        frappe.qb.from_(t)
        .select(t.customer, Count(t.name).as_("n"))
        .where(t.customer.isin(customers))
        .where(t.creation >= add_days(now_datetime(), -TICKET_DAYS))
        .groupby(t.customer)
    ).run(as_dict=True)
    return {r.customer: int(r.n or 0) for r in rows}


def _set_level(customer: str) -> str:
    """The level set for the customer (its own, else the default), before shadow mode holds it."""
    level = frappe.db.get_value(CUSTOMER, customer, "custom_copilot_level")
    if level not in copilot_settings.LEVELS:
        level = copilot_settings.get_settings().get("default_copilot_level")
    return level if level in copilot_settings.LEVELS else copilot_settings.DIAGNOSE


def _check(key: str, state: str, detail: str) -> dict:
    return {"key": key, "label": _(SHORT[key]), "state": state, "detail": detail}


def checks(customer: str, enabled: bool, conns: list[dict], cards: list[dict]) -> list:
    """What the customer has and lacks, in the order a person sets it up."""
    connected = next((c for c in conns if c["status"] == "Connected"), None)
    production = next((c for c in cards if c["environment"] == PRODUCTION), None)
    found = []

    if connected:
        found.append(
            _check(
                "connection",
                DONE,
                _("{0} is Connected").format(connected["site_url"])
                + (
                    _(" (checked {0})").format(connected["checked"])
                    if connected["checked"]
                    else ""
                ),
            )
        )
    elif conns:
        found.append(
            _check(
                "connection",
                MISSING,
                _("{0} is {1}: it must be Connected").format(
                    conns[0]["site_url"], _(conns[0]["status"])
                ),
            )
        )
    else:
        found.append(
            _check(
                "connection",
                MISSING,
                _("No connection: connect the customer's ERP site first"),
            )
        )

    if not connected:
        found.append(_check("client", LATER, _("After the connection")))
    elif connected["new_client"]:
        found.append(
            _check(
                "client",
                DONE,
                _("helpdesk_client {0}").format(connected["client_version"]).strip(),
            )
        )
    else:
        found.append(
            _check(
                "client",
                MISSING,
                _(
                    "The site runs an older helpdesk_client. DevOps updates it to the release with Copilot's changes"
                ),
            )
        )

    found.append(
        _check(
            "card",
            DONE if production else MISSING,
            _("{0}, Production").format(production["site_url"] or production["name"])
            if production
            else _("Add the Production site card below"),
        )
    )

    if not production:
        found.append(_check("apps", LATER, _("After the site card")))
    elif production["apps"]:
        found.append(
            _check(
                "apps",
                DONE,
                _("{0} apps, read {1}").format(
                    len(production["apps"]), production["apps_read"] or _("earlier")
                ),
            )
        )
    else:
        found.append(_check("apps", MISSING, _("Use Read apps on the site card")))

    developers = people.developers(customer)
    found.append(
        _check(
            "people",
            DONE if developers else MISSING,
            ", ".join(get_fullname(u) for u in developers)
            if developers
            else _(
                "Set a Ticket Owner on the customer, or a Developer in Copilot People"
            ),
        )
    )

    found.append(
        _check(
            "enabled",
            DONE if enabled else MISSING,
            _("On: every new ticket starts a Copilot run")
            if enabled
            else _("Switch it on last, when the lines above are done"),
        )
    )

    fix_level = copilot_settings.LEVELS.index(
        _set_level(customer)
    ) >= copilot_settings.LEVELS.index(copilot_settings.FIX)
    if production and production["press_site"] and production["press_release_group"]:
        found.append(
            _check(
                "press",
                DONE,
                _("Fixes can be deployed to {0}").format(production["press_site"]),
            )
        )
    else:
        found.append(
            _check(
                "press",
                MISSING if fix_level else LATER,
                _("Needed at the Fix level: fill them on the Production site card")
                if fix_level
                else _("Needed from the Fix level only, not for diagnosis"),
            )
        )
    return found


def _ready(found: list[dict]) -> dict:
    counted = [c for c in found if c["key"] in READY]
    done = sum(1 for c in counted if c["state"] == DONE)
    return {
        "done": done,
        "of": len(READY),
        "needs": [c["label"] for c in counted if c["state"] != DONE],
    }


def _work_goes_to(customer: str) -> dict:
    """Who Copilot's work for the customer goes to, and where that comes from."""
    own = people.groups(people.DEVELOPER, "customer", customer)
    if own and own[0]["where"] == "owner":
        developers_from = "owner"
    elif own:
        developers_from = "customer"
    else:
        developers_from = "common"
    approvers = [
        u
        for group in people.groups(people.FIX_APPROVER, "customer", customer)
        for u in group["users"]
    ]

    def names(users):
        return [{"user": u, "name": get_fullname(u)} for u in users]

    return {
        "developers": names(people.developers(customer)),
        "developers_from": developers_from,
        "fix_approvers": names(approvers),
        "coordinators": names(people.coordinators(customer)),
        "coordinators_from": people.coordinators_from(customer),
    }


def customer_setup(customer: str) -> dict:
    """Everything the customer page's Copilot tab shows, and what the person may change."""
    frappe.has_permission(CUSTOMER, "read", customer, throw=True)
    doc = frappe.get_doc(CUSTOMER, customer)
    conns = _connections([customer]).get(customer, [])
    cards = _cards([customer]).get(customer, [])
    enabled = bool(doc.get("custom_copilot_enabled"))
    found = checks(customer, enabled, conns, cards)
    settings = copilot_settings.get_settings()
    default_level = settings.get("default_copilot_level")
    return {
        "customer": customer,
        "switches": {
            "enabled": enabled,
            "level": doc.get("custom_copilot_level") or "",
            "watch": bool(doc.get("custom_copilot_watch")),
        },
        "levels": list(copilot_settings.LEVELS),
        "default_level": default_level
        if default_level in copilot_settings.LEVELS
        else copilot_settings.DIAGNOSE,
        "copilot": {
            "enabled": copilot_settings.is_enabled(),
            "shadow": copilot_settings.is_shadow(),
        },
        "work_goes_to": _work_goes_to(customer),
        "connections": conns,
        "cards": cards,
        "checks": found,
        "ready": _ready(found),
        "can": {
            "switches": bool(frappe.has_permission(CUSTOMER, "write", customer)),
            "add_card": bool(frappe.has_permission(CARD, "create")),
            "edit_card": bool(frappe.has_permission(CARD, "write")),
        },
    }


def customers(show: str = "all") -> list[dict]:
    """The Copilot board's Customers tab: every customer with a connection or a site card."""
    if show not in ("all", "on", "not_ready"):
        frappe.throw(_("Unknown filter {0}").format(show))
    names = sorted(
        set(frappe.get_all(CONNECTION, pluck="customer_name", distinct=True))
        | set(frappe.get_all(CARD, pluck="customer_name", distinct=True))
    )
    names = [n for n in names if n]
    if not names:
        return []
    switches = {
        r.name: r
        for r in frappe.get_all(
            CUSTOMER,
            filters={"name": ["in", names]},
            fields=["name", *SWITCHES.values()],
        )
    }
    conns, cards, tickets = _connections(names), _cards(names), _tickets(names)
    # many customers, the same people: read each person once (people._cache)
    frappe.flags.copilot_people_cache = {}
    try:
        rows = _rows(names, switches, conns, cards, tickets)
    finally:
        frappe.flags.copilot_people_cache = None
    if show == "on":
        rows = [r for r in rows if r["enabled"]]
    elif show == "not_ready":
        rows = [r for r in rows if r["ready"]["needs"]]
    rows.sort(key=lambda r: (-r["tickets"], r["customer"].lower()))
    return rows


def _rows(names, switches, conns, cards, tickets) -> list[dict]:
    rows = []
    for name in names:
        if name not in switches:
            continue
        enabled = bool(switches[name].custom_copilot_enabled)
        found = checks(name, enabled, conns.get(name, []), cards.get(name, []))
        ready = _ready(found)
        sites = list(
            dict.fromkeys(
                [c["site_url"] for c in conns.get(name, []) if c["site_url"]]
                + [c["site_url"] for c in cards.get(name, []) if c["site_url"]]
            )
        )
        rows.append(
            {
                "customer": name,
                "sites": sites,
                "enabled": enabled,
                "level": switches[name].custom_copilot_level or "",
                "cards": len(cards.get(name, [])),
                "production_card": any(
                    c["environment"] == PRODUCTION for c in cards.get(name, [])
                ),
                "ready": ready,
                "tickets": tickets.get(name, 0),
            }
        )
    return rows


# --- changing ----------------------------------------------------------------------------------


def save_switches(customer: str, values: dict) -> dict:
    """Copilot Enabled, the level and Watch Errors, through the customer's own save."""
    frappe.has_permission(CUSTOMER, "write", customer, throw=True)
    doc = frappe.get_doc(CUSTOMER, customer)
    for key, value in values.items():
        if key not in SWITCHES:
            frappe.throw(_("{0} cannot be changed here").format(key))
        if key == "level":
            value = value or ""
            if value and value not in copilot_settings.LEVELS:
                frappe.throw(_("Unknown Copilot level {0}").format(value))
        else:
            value = 1 if frappe.utils.sbool(value) else 0
        doc.set(SWITCHES[key], value)
    doc.save()
    return customer_setup(customer)


def _clean_card(values: dict) -> dict:
    clean = {}
    for field in CARD_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if field == "shared_group":
            value = 1 if frappe.utils.sbool(value) else 0
        elif isinstance(value, str):
            value = value.strip()
        clean[field] = value
    if "environment" in clean and clean["environment"] not in ENVIRONMENTS:
        frappe.throw(_("Unknown environment {0}").format(clean["environment"]))
    return clean


def save_site_card(values: dict, name: str | None = None) -> dict:
    """Adds a site card, or changes one, through its own validation (one Production site each)."""
    ignored = set(values) - set(CARD_FIELDS)
    if ignored:
        frappe.throw(_("{0} cannot be changed here").format(", ".join(sorted(ignored))))
    clean = _clean_card(values)
    if name:
        frappe.has_permission(CARD, "write", name, throw=True)
        doc = frappe.get_doc(CARD, name)
        if clean.get("customer_name", doc.customer_name) != doc.customer_name:
            frappe.throw(_("A site card stays with its customer"))
        doc.update(clean)
    else:
        frappe.has_permission(CARD, "create", throw=True)
        if not clean.get("customer_name"):
            frappe.throw(_("Choose the customer"))
        clean.setdefault("environment", PRODUCTION)
        doc = frappe.get_doc({"doctype": CARD, **clean})
    if doc.connection:
        conn_customer, conn_url = frappe.db.get_value(
            CONNECTION, doc.connection, ["customer_name", "site_url"]
        ) or (None, None)
        if conn_customer != doc.customer_name:
            frappe.throw(
                _("Connection {0} is not {1}'s").format(
                    doc.connection, doc.customer_name
                )
            )
        if not doc.site_url:
            doc.site_url = conn_url
    if not doc.site_url:
        frappe.throw(_("Fill in the site URL"))
    if name:
        doc.save()
    else:
        doc.insert()
    return customer_setup(doc.customer_name)


def read_apps(name: str, source: str) -> dict:
    """Reads the card's apps from the site (through its connection) or from Press, with a plain
    reason when that cannot work yet."""
    from helpdesk.copilot import registry

    if source not in ("site", "press"):
        frappe.throw(_("Unknown source {0}").format(source))
    frappe.has_permission(CARD, "write", name, throw=True)
    doc = frappe.get_doc(CARD, name)
    if source == "site":
        if not doc.connection:
            frappe.throw(
                _("This site card has no connection to read the site through.")
            )
        conn = frappe.get_doc(CONNECTION, doc.connection)
        if not capabilities(conn):
            frappe.throw(
                _(
                    "{0}'s site runs an older helpdesk_client, which cannot list its apps yet. Update the client, or use Read apps from Press."
                ).format(doc.customer_name)
            )
        result = registry.refresh_from_site(doc)
    else:
        if not doc.press_release_group:
            frappe.throw(_("Fill in the Press release group first (Edit)."))
        result = registry.refresh_from_press(doc)
    return {"result": result, "setup": customer_setup(doc.customer_name)}


def parse(values) -> dict:
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError:
            frappe.throw(_("values must be JSON"))
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"))
    return values
