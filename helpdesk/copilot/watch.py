# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The error watch (Phase 9): a new error on a customer's site becomes a ticket before the
customer reports it.

Every few minutes the hub asks each watched site for the error signatures it logged since the last
check, with the connector's own `get_deploy_status` (the top 10 by count; nothing changes on the
site). Each signature is one HDS Site Error row per site, counted while it lasts and new again after
`watch_new_after_days` without it. The first check of a site only records what is there (the
baseline).

A new error that reaches the count or the users (once in accounting, stock or payroll code) gets up
to 5 samples (`get_error_log`) and a ticket for the customer, linked to its known issue, and Copilot
investigates it like any ticket. A known issue already fixed changes that: a site without the fix
gets a ticket naming the missing fix and no investigation; a site with the fix gets a "came back"
ticket for a senior. The customer hears nothing from Copilot until a person replies (`held`).
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_to_date,
    escape_html,
    get_datetime,
    get_url,
    now_datetime,
    today,
)

from helpdesk.automation import automation_user
from helpdesk.copilot import known_issues
from helpdesk.copilot import settings as copilot_settings

SITE_ERROR = "HDS Site Error"
SOURCE = "Error watch"
SENSITIVE = re.compile(r"(^|[./\s])(accounts|stock|payroll)([./\s]|$)", re.I)
FAILURES_NOTED = 4  # checks failed in a row before the site card says so
MAX_SAMPLES = 5
# never a ticket: the connector's own errors (its MCP calls, logged as "MCP tool error: <tool>"
# with no app of their own), whatever the setting says
ALWAYS_IGNORED = ("helpdesk_client", "mcp tool error")
# Ignored Errors left blank (an existing site's settings get no default on migrate)
DEFAULT_IGNORED = ("session stopped",)


class WatchError(Exception):
    pass


def settings() -> dict:
    s = copilot_settings.get_settings()
    return {
        "minutes": max(int(s.get("watch_minutes") or 15), 5),
        "new_after": max(int(s.get("watch_new_after_days") or 14), 1),
        "min_count": max(int(s.get("watch_min_count") or 3), 1),
        "min_users": max(int(s.get("watch_min_users") or 2), 1),
        "site_cap": int(s.get("watch_site_daily_cap") or 3),
        "cap": int(s.get("watch_daily_cap") or 10),
        "ignored": list(ALWAYS_IGNORED)
        + (
            [
                line.strip().lower()
                for line in (s.get("watch_ignored") or "").splitlines()
                if line.strip()
            ]
            or list(DEFAULT_IGNORED)
        ),
    }


def enabled() -> bool:
    s = copilot_settings.get_settings()
    return bool(s.enabled and s.get("watch_enabled"))


def due_sites(minutes: int) -> list:
    """Site cards with a connection, of customers with Watch Errors and Copilot on, not checked lately."""
    customers = frappe.get_all(
        "HD Customer",
        filters={"custom_copilot_watch": 1, "custom_copilot_enabled": 1},
        pluck="name",
    )
    if not customers:
        return []
    cutoff = add_to_date(now_datetime(), minutes=-minutes)
    cards = frappe.get_all(
        "HDS Site Registry",
        filters={
            "customer_name": ["in", customers],
            "connection": ["is", "set"],
            "environment": ["!=", "Sandbox"],
        },
        fields=["name", "watch_checked_at"],
        order_by="watch_checked_at asc",
    )
    return [
        frappe.get_doc("HDS Site Registry", c.name)
        for c in cards
        if not c.watch_checked_at or get_datetime(c.watch_checked_at) <= cutoff
    ]


def run_due():
    """Cron: each watched site that is due is checked, one at a time."""
    if not enabled():
        return []
    rules = settings()
    checked = []
    for card in due_sites(rules["minutes"]):
        frappe.db.savepoint("copilot_watch_site")
        try:
            check_site(card, rules)
        except Exception as e:
            frappe.db.rollback(save_point="copilot_watch_site")  # nothing half counted
            failed(card, e)
        frappe.db.commit()  # one site at a time; a failure is kept too - nosemgrep
        checked.append(card.name)
    return checked


def _call(client, session: str, tool: str, args: dict):
    from helpdesk.copilot.verify import SiteUnreachable, _call

    try:
        return _call(client, session, tool, args)
    except SiteUnreachable as e:
        raise WatchError(str(e)) from e


def check_site(card, rules: dict | None = None):
    """Counts the site's errors since the last check; a new one past the threshold becomes a ticket."""
    from helpdesk.mcp_client import MCPClient

    rules = rules or settings()
    now = now_datetime()
    baseline = not card.get("watch_checked_at")
    since = add_days(now, -rules["new_after"]) if baseline else card.watch_checked_at
    client = MCPClient(card.connection)
    session = f"watch-{card.name}"
    status = _call(client, session, "get_deploy_status", {"since": str(since)})
    if not isinstance(status, dict):
        raise WatchError(
            _("The site's answer was not readable: {0}").format(str(status)[:200])
        )
    for top in (status.get("errors") or {}).get("top") or []:
        signature = str(top.get("signature") or "").strip()
        count = int(top.get("count") or 0)
        if not signature or count <= 0:
            continue
        row = note(card, signature, count, now, baseline, rules)
        if baseline:
            continue
        if row.known_issue:  # the issue counts where it is seen
            known_issues.record(
                signature, card.name, card.customer_name, count=count, seen=now
            )
        if row.status == "Watching":
            consider(card, row, client, session, rules)
        elif row.status == "Ticket":
            came_back_check(card, row, client, session)
    card.db_set(
        {"watch_checked_at": now, "watch_failures": 0, "watch_note": None},
        update_modified=False,
    )


def failed(card, error: Exception):
    """A site that could not be checked is tried again at the next check, from the same time."""
    failures = (
        frappe.db.get_value("HDS Site Registry", card.name, "watch_failures") or 0
    ) + 1
    values = {"watch_failures": failures}
    if failures == FAILURES_NOTED:
        values["watch_note"] = _(
            "The site did not answer the error watch {0} times in a row: {1}"
        ).format(failures, str(error)[:300])
    frappe.db.set_value("HDS Site Registry", card.name, values, update_modified=False)
    if not isinstance(error, WatchError):
        frappe.log_error(title=f"Copilot error watch failed on {card.name}")


def ignored(signature: str, rules: dict) -> bool:
    text = signature.lower()
    return any(pattern in text for pattern in rules["ignored"])


def note(card, signature: str, count: int, now, baseline: bool, rules: dict):
    """The site's row for the signature: counted; started again after the days without it."""
    key = known_issues.key_of(signature)
    name = frappe.db.get_value(
        SITE_ERROR, {"registry": card.name, "signature_key": key}
    )
    status = (
        "Ignored"
        if ignored(signature, rules)
        else ("Baseline" if baseline else "Watching")
    )
    if name:
        row = frappe.get_doc(SITE_ERROR, name)
        quiet_since = add_days(now, -rules["new_after"])
        if row.last_seen and get_datetime(row.last_seen) < quiet_since:
            # gone for the whole period: new again
            row.update(
                {
                    "status": "Ignored" if status == "Ignored" else "Watching",
                    "first_seen": now,
                    "count": 0,
                    "ticket": None,
                    "users": "",
                    "samples": None,
                }
            )
        row.count = (row.count or 0) + count
        row.last_seen = now
        row.save(ignore_permissions=True)
        return row
    return frappe.get_doc(
        {
            "doctype": SITE_ERROR,
            "registry": card.name,
            "customer": card.customer_name,
            "status": status,
            "count": count,
            "first_seen": now,
            "last_seen": now,
            "signature": signature[:1000],
            "signature_key": key,
            "app": known_issues.parts(signature)["app"][:140],
        }
    ).insert(ignore_permissions=True)


def sensitive(signature: str) -> bool:
    p = known_issues.parts(signature)
    return bool(SENSITIVE.search(p["method"]) or SENSITIVE.search(p["app"]))


def samples(client, session: str, row) -> list[dict]:
    """Up to 5 of the site's error logs with this signature: time, document, code lines, user."""
    from helpdesk.copilot.verify import signature

    method = known_issues.parts(row.signature)["method"]
    args = {
        "since": str(add_to_date(get_datetime(row.first_seen), minutes=-1)),
        "limit": 20,
    }
    if method:
        args["method"] = method
    try:
        entries = _call(client, session, "get_error_log", args)
    except WatchError:  # the ticket goes without samples rather than not at all
        return []
    wanted = known_issues.normalise(row.signature)
    found = []
    for entry in entries if isinstance(entries, list) else []:
        if (
            not isinstance(entry, dict)
            or known_issues.normalise(signature(entry)) != wanted
        ):
            continue
        found.append(
            {
                "time": str(entry.get("creation") or "")[:19],
                "document": "/".join(
                    str(entry[k])
                    for k in ("reference_doctype", "reference_name")
                    if entry.get(k)
                ),
                "frames": entry.get("top_frames") or [],
                "user": entry.get("owner") or "",
            }
        )
    return found


def _users(found: list[dict]) -> list[str]:
    return sorted({s["user"] for s in found if s.get("user")})


def consider(card, row, client, session: str, rules: dict):
    """A new error: a ticket once it is enough. A known issue already fixed: on a site with the
    fix it came back (a ticket at once); on a site without it, the ticket names the missing fix."""
    issue = known_issues.find(row.signature)
    fixed = (
        known_issues.has_fix(issue, card.name)
        if issue and issue.status == "Fixed"
        else None
    )
    if fixed is True:
        return open_ticket(card, row, client, session, issue, "came_back")
    enough = row.count >= rules["min_count"] or sensitive(row.signature)
    if not enough and row.count >= 2:  # two users can be enough: the site says who
        users = _users(samples(client, session, row))
        row.db_set("users", "\n".join(users), update_modified=False)
        enough = len(users) >= rules["min_users"]
    if enough:
        open_ticket(
            card,
            row,
            client,
            session,
            issue,
            "missing_fix" if fixed is False else "new",
        )


def came_back_check(card, row, client, session: str):
    """An error with a ticket already: once its known issue is fixed and the site has the fix, it
    happening again means the fix did not hold."""
    if not row.known_issue:
        return
    issue = frappe.get_doc(known_issues.KNOWN_ISSUE, row.known_issue)
    if issue.status != "Fixed" or not issue.fixed_at:
        return
    if get_datetime(row.last_seen) <= get_datetime(issue.fixed_at):
        return
    if known_issues.has_fix(issue, card.name) is True:
        open_ticket(card, row, client, session, issue, "came_back")


def capped(card, rules: dict) -> bool:
    """Today's watch tickets reached the cap, in all or for this site."""
    todays = frappe.get_all(
        "HD Ticket",
        filters={
            "custom_copilot_source": SOURCE,
            "creation": [">=", get_datetime(today())],
        },
        pluck="name",
    )
    if rules["cap"] and len(todays) >= rules["cap"]:
        return True
    return bool(
        rules["site_cap"]
        and todays
        and frappe.db.count(
            SITE_ERROR, {"registry": card.name, "ticket": ["in", todays]}
        )
        >= rules["site_cap"]
    )


def note_cap(card):
    """Past a cap: the error keeps being counted; the Agent Managers hear it once a day."""
    from helpdesk.copilot import approvals, assistant

    key = frappe.cache.make_key(f"copilot:watch-capped:{today()}")
    if not frappe.cache.set(key, 1, nx=True, ex=26 * 3600):
        return
    text = _(
        "The error watch reached its daily limit of tickets (at {0}); new errors are counted and wait for tomorrow."
    ).format(card.site_url or card.name)
    for person in approvals._managers():
        try:
            assistant.send(person, assistant.text_card(text, "warning"))
        except Exception:
            frappe.log_error(title="Copilot could not tell the error watch's limit")


KINDS = {
    "new": "Copilot noticed: {0}",
    "came_back": "Came back after the fix: {0}",
    "missing_fix": "Fixed elsewhere, not on this site yet: {0}",
}


def open_ticket(card, row, client, session: str, issue, kind: str):
    """The ticket for the customer, linked to the known issue; Copilot investigates unless the fix
    exists and only has to reach the site."""
    from helpdesk.copilot import assistant, runs

    rules = settings()
    if capped(card, rules):
        return note_cap(card)
    found = samples(client, session, row)
    users = _users(found) or [u for u in (row.users or "").splitlines() if u]
    if not row.known_issue:  # the site's count so far goes to the issue once
        issue = known_issues.record(
            row.signature,
            card.name,
            card.customer_name,
            count=row.count,
            seen=row.first_seen,
        )
    if kind == "came_back":
        issue.db_set(
            {"status": "Open", "came_back": (issue.came_back or 0) + 1},
            update_modified=False,
        )
    last = known_issues.parts(row.signature)["last"] or issue.title
    values = {
        "doctype": "HD Ticket",
        "subject": _(KINDS[kind]).format(last)[:140],
        "description": describe(card, row, issue, found, users, kind),
        "raised_by": assistant.customer_contact(card.customer_name)
        or automation_user(),
        "customer": card.customer_name,
        "custom_copilot_source": SOURCE,
        "custom_known_issue": issue.name,
    }
    if kind == "came_back":
        values["priority"] = "High"
    ticket = frappe.get_doc(values)
    ticket.flags.skip_acknowledgement = True  # the customer hears from a person first
    ticket.flags.no_copilot_run = kind == "missing_fix"  # the fix exists already
    ticket.insert(ignore_permissions=True)
    row.db_set(
        {
            "status": "Ticket",
            "ticket": ticket.name,
            "known_issue": issue.name,
            "users": "\n".join(users),
            "samples": json.dumps(found, indent=1),
        },
        update_modified=False,
    )
    known_issues.record(
        row.signature, card.name, card.customer_name, ticket=ticket.name
    )
    run = None
    if kind != "missing_fix":
        run = runs.start_run(ticket.name, actor=runs.SYSTEM)
    if kind == "came_back" and run:
        _to_a_senior(ticket.name, run)
    tell(card, ticket, run, kind)
    return ticket


def describe(card, row, issue, found: list[dict], users: list[str], kind: str) -> str:
    lines = [
        "<p>{0}</p>".format(
            escape_html(
                {
                    "new": _(
                        "Copilot noticed a new error on {0} before anyone reported it."
                    ),
                    "came_back": _(
                        "This error came back on {0} after its fix went live; a senior looks at it."
                    ),
                    "missing_fix": _(
                        "This error is fixed, but {0} does not run the fix yet; its release brings it."
                    ),
                }[kind].format(card.site_url or card.name)
            )
        ),
        "<p><b>{0}</b> {1}<br><b>{2}</b> {3}<br><b>{4}</b> {5}</p>".format(
            escape_html(_("Error:")),
            escape_html(row.signature),
            escape_html(_("Since:")),
            escape_html(str(row.first_seen)[:16]),
            escape_html(_("Times:")),
            row.count,
        ),
    ]
    if users:
        lines.append(
            "<p><b>{0}</b> {1}</p>".format(
                escape_html(_("Users:")), escape_html(", ".join(users[:10]))
            )
        )
    if found:
        items = "".join(
            "<li>{0} {1}<br><code>{2}</code></li>".format(
                escape_html(s["time"]),
                escape_html(s["document"]),
                escape_html(" ← ".join(s["frames"][-3:])),
            )
            for s in found[:MAX_SAMPLES]
        )
        lines.append(
            "<p><b>{0}</b></p><ul>{1}</ul>".format(escape_html(_("Samples:")), items)
        )
    if issue.status == "Fixed" or kind != "new":
        lines.append(
            "<p><b>{0}</b> {1} {2}</p>".format(
                escape_html(_("Known issue:")),
                escape_html(issue.name),
                escape_html(
                    _("fixed by {0} ({1})").format(
                        issue.fix_pull_request or issue.fix_title or "?",
                        (issue.merge_commit or "")[:12],
                    )
                    if issue.fix_pull_request or issue.merge_commit
                    else ""
                ),
            )
        )
    lines.append(
        "<p><i>{0}</i></p>".format(
            escape_html(
                _(
                    "Raised by Copilot's error watch. The customer hears nothing from Copilot until a person replies."
                )
            )
        )
    )
    return "".join(lines)


def _to_a_senior(ticket: str, run):
    from frappe.desk.form.assign_to import add as assign

    from helpdesk.copilot import approvals

    senior = approvals.pick_approver(run, True)
    if senior:
        try:
            assign({"assign_to": [senior], "doctype": "HD Ticket", "name": ticket})
        except Exception:
            frappe.log_error(title=f"Copilot could not assign {ticket} to a senior")


def tell(card, ticket, run, kind: str):
    """The customer's developer (else the Agent Managers) hears it in the Copilot chat; they then
    hear the diagnosis there too. Never stops the watch."""
    from helpdesk.copilot import approvals, assistant

    developer = frappe.db.get_value(
        "HD Customer", card.customer_name, "custom_assigned_developer"
    )
    people = (
        [developer]
        if developer and assistant.is_agent(developer)
        else approvals._managers()
    )
    reply = assistant.card(
        ticket.subject,
        [
            _("On {0}, for {1}.").format(
                card.site_url or card.name, card.customer_name
            ),
            _("Copilot is investigating; the diagnosis follows here.")
            if run
            else _(
                "No investigation: the fix exists and comes with the site's release."
            ),
        ],
        links=[(_("Open the ticket"), get_url(f"/helpdesk/tickets/{ticket.name}"))],
        tone="warning" if kind == "came_back" else "default",
    )
    for person in people:
        try:
            assistant.send(
                person,
                reply,
                ticket=ticket.name,
                run=run.name if run else None,
                action_status="Done",  # they are on this run's news from now on
                result=_("Error watch"),
            )
        except Exception:
            frappe.log_error(
                title=f"Copilot could not tell the chat about {ticket.name}"
            )


def held(ticket: str) -> bool:
    """A watch ticket says nothing to the customer until a person replied on it."""
    if frappe.db.get_value("HD Ticket", ticket, "custom_copilot_source") != SOURCE:
        return False
    return not frappe.db.exists(
        "Communication",
        {
            "reference_doctype": "HD Ticket",
            "reference_name": ticket,
            "sent_or_received": "Sent",
        },
    )
