# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Copilot board (Phase 10): all of Copilot's work on one page, to look at, not to decide on.

Everything a ticket belongs to (runs, approvals, a release made for a ticket, a known issue's
tickets) is shown only when the person may read that ticket (`visible_tickets`, through HD Ticket's
own permission rules), so team restrictions hold here too. The worker and the AI budget are for
Agent Managers. Each item links to where it is decided: the ticket's Copilot dialog, the release,
the Teams card (docs/tbo-copilot.md, Copilot board).
"""

import contextlib

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    get_datetime,
    get_fullname,
    get_url,
    getdate,
    now_datetime,
    time_diff_in_hours,
)

from helpdesk.copilot import settings as copilot_settings

RUN = "HDS Copilot Run"
DEPLOY = "HDS Deploy Request"
WORKERS_SEEN = "copilot:workers-seen"
WORKER_ONLINE_MINUTES = 2  # the worker asks every 15 seconds
BOARD_EVENT = "helpdesk:copilot-board"  # a signal only: no ticket or run name
PER_COLUMN = 50

# the Work tab's columns, in order, and the run states each one holds
COLUMNS = (
    ("investigating", "Investigating", ("Queued", "Investigating")),
    ("customer", "With the customer", ("Explaining", "Answered")),
    ("fixing", "Fixing", ("Preparing Fix",)),
    ("approval", "Waiting for approval", ("Awaiting Approval",)),
    (
        "shipping",
        "Shipping",
        ("Approved", "Merging", "Merged", "Deploying", "Verifying", "Applying"),
    ),
    ("person", "Needs a person", ("Escalated", "Handed Over", "Failed", "Rejected")),
)
DONE = ("Resolved", "Closed")
# finished columns keep a run this long; the live ones keep it while it is the ticket's latest
STALE_DAYS = 30
RELEASE_PIPELINE = (
    "Waiting for CI",
    "Staging",
    "Waiting for approval",
    "Scheduled",
    "Waiting for Press",
    "Deploying",
    "Checking",
)
RELEASE_FINISHED = ("Succeeded", "Failed", "Rejected", "Cancelled")


def is_manager(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return user == "Administrator" or "Agent Manager" in frappe.get_roles(user)


def worker_seen(worker_id: str) -> None:
    """`claim_job` notes when each worker last asked for work; never stops the claim."""
    with contextlib.suppress(Exception):
        frappe.cache.hset(WORKERS_SEEN, worker_id[:140], str(now_datetime()))


def changed() -> None:
    """Any run's change: open boards refresh (they ask again with the person's own permissions)."""
    frappe.publish_realtime(BOARD_EVENT, {}, after_commit=True)


def visible_tickets(names) -> set[str]:
    """The tickets among `names` the session user may read (HD Ticket's own rules)."""
    names = list({str(n) for n in names if n})
    seen: set[str] = set()
    for start in range(0, len(names), 500):
        seen.update(
            frappe.get_list(
                "HD Ticket",
                filters={"name": ["in", names[start : start + 500]]},
                pluck="name",
                limit_page_length=0,
            )
        )
    return seen


def _hours(since) -> float | None:
    return round(time_diff_in_hours(now_datetime(), since), 1) if since else None


def _ticket_url(ticket: str) -> str:
    return get_url(f"/helpdesk/tickets/{ticket}")


# --- the top strip ------------------------------------------------------------------------------


def summary() -> dict:
    from helpdesk.copilot import pilot

    settings = copilot_settings.get_settings()
    result = {
        "enabled": bool(settings.enabled),
        "shadow_mode": bool(settings.shadow_mode),
        "watch_enabled": bool(settings.get("watch_enabled")),
        "queued": frappe.db.count(RUN, {"state": "Queued"}),
        "waiting_for_a_worker": len(pilot.waiting_runs()),
        "is_manager": is_manager(),
    }
    if result["is_manager"]:
        result["workers"] = workers()
        result["month_spend_usd"] = round(pilot.month_spend(), 2)
        result["month_budget_usd"] = float(settings.get("monthly_ai_budget_usd") or 0)
    return result


def workers() -> list[dict]:
    try:
        seen = frappe.cache.hgetall(WORKERS_SEEN) or {}
    except Exception:
        seen = {}
    rows = []
    for worker, at in seen.items():
        worker = worker.decode() if isinstance(worker, bytes) else str(worker)
        minutes = round(time_diff_in_hours(now_datetime(), get_datetime(at)) * 60, 1)
        rows.append(
            {
                "worker": worker,
                "last_seen": str(at)[:19],
                "minutes_ago": minutes,
                "online": minutes <= WORKER_ONLINE_MINUTES,
            }
        )
    return sorted(rows, key=lambda r: r["minutes_ago"])


# --- Work ----------------------------------------------------------------------------------------


def work(
    customer: str | None = None, mine: bool = False, source: str | None = None
) -> dict:
    """Each ticket's latest run, in its column; finished columns only for the last 30 days."""
    states = [state for _key, _label, held in COLUMNS for state in held]
    filters = {"state": ["in", states]}
    if customer:
        filters["customer"] = customer
    runs = frappe.get_all(
        RUN,
        filters=filters,
        fields=[
            "name",
            "ticket",
            "customer",
            "state",
            "kind",
            "root_cause_category",
            "fix_status",
            "approval",
            "task",
            "handed_over_to",
            "modified",
            "queued_at",
            "shadow",
        ],
        order_by="modified desc",
    )
    tickets = {
        t.name: t
        for t in frappe.get_all(
            "HD Ticket",
            filters={"name": ["in", list({r.ticket for r in runs}) or [""]]},
            fields=[
                "name",
                "subject",
                "custom_copilot_run",
                "custom_copilot_source",
                "_assign",
            ],
        )
    }
    readable = visible_tickets(tickets)
    stale = add_days(now_datetime(), -STALE_DAYS)
    user = frappe.session.user
    approvals = _approvals_of([r.approval for r in runs if r.approval])
    columns = {key: [] for key, _label, _held in COLUMNS}
    for run in runs:
        ticket = tickets.get(run.ticket)
        if not ticket or run.ticket not in readable:
            continue
        if ticket.custom_copilot_run and ticket.custom_copilot_run != run.name:
            continue  # an older run of the ticket
        key = next(k for k, _label, held in COLUMNS if run.state in held)
        if key == "person" and get_datetime(run.modified) < stale:
            continue
        if source and (ticket.custom_copilot_source or "") != source:
            continue
        approval = approvals.get(run.approval) if run.approval else None
        assigned = frappe.parse_json(ticket._assign or "[]") or []
        people = set(assigned)
        if approval and approval.status == "Pending" and approval.assigned_to:
            people.add(approval.assigned_to)
        if run.handed_over_to:
            people.add(run.handed_over_to)
        if mine and user not in people:
            continue
        columns[key].append(
            {
                "run": run.name,
                "ticket": run.ticket,
                "subject": ticket.subject,
                "customer": run.customer,
                "state": run.state,
                "kind": run.kind,
                "root_cause": run.root_cause_category,
                "fix_status": run.fix_status or "",
                "shadow": bool(run.shadow),
                "source": ticket.custom_copilot_source or "",
                "waited_hours": _hours(run.modified),
                "waits_on": waits_on(run, approval),
                "url": _ticket_url(run.ticket),
            }
        )
    week_start = getdate(now_datetime())
    week_start = add_days(week_start, -week_start.weekday())
    done = frappe.get_all(
        RUN,
        filters={
            "state": ["in", DONE],
            "finished_at": [">=", week_start],
            **({"customer": customer} if customer else {}),
        },
        pluck="ticket",
    )
    return {
        "columns": [
            {
                "key": key,
                "label": _(label),
                "count": len(columns[key]),
                "cards": columns[key][:PER_COLUMN],
                "more": max(len(columns[key]) - PER_COLUMN, 0),
            }
            for key, label, _held in COLUMNS
        ],
        "resolved_this_week": len(visible_tickets(done)),
    }


def _approvals_of(names) -> dict:
    return {
        a.name: a
        for a in frappe.get_all(
            "HDS Copilot Approval",
            filters={"name": ["in", list(names) or [""]]},
            fields=["name", "status", "assigned_to"],
        )
    }


def waits_on(run, approval=None) -> str:
    """Who or what the run waits on, in a few words."""
    state = run.state
    if state in ("Queued", "Investigating"):
        return _("a worker") if state == "Queued" else _("Copilot")
    if state == "Explaining":
        return _("an agent to send the explanation")
    if state == "Answered":
        return _("the customer")
    if state == "Preparing Fix":
        if run.fix_status in ("Queued", "Working"):
            return _("Copilot's fix")
        if run.fix_status == "Failed":
            return _("a developer (Copilot could not fix it)")
        if run.fix_status == "Opened":
            return _("the pull request's checks")
        return _("a developer, or Let Copilot fix it")
    if state == "Awaiting Approval":
        who = approval.assigned_to if approval else None
        return get_fullname(who) if who else _("an approver")
    if state == "Merged":
        return _("a deploy")
    if state in ("Approved", "Merging"):
        return _("the merge")
    if state in ("Deploying", "Verifying", "Applying"):
        return _("the deploy and its check")
    if run.handed_over_to:
        return get_fullname(run.handed_over_to)
    return _("a person")


# --- Approvals -----------------------------------------------------------------------------------


def approvals() -> list[dict]:
    """Every fix, correction and release waiting for a person, the longest wait first."""
    from helpdesk.copilot import approvals as copilot_approvals

    rows = []
    pending = frappe.get_all(
        "HDS Copilot Approval",
        filters={"status": "Pending"},
        fields=[
            "name",
            "run",
            "ticket",
            "kind",
            "assigned_to",
            "assigned_at",
            "risk_level",
            "sensitive",
            "snoozed_until",
            "escalated_at",
            "pr_url",
            "creation",
        ],
    )
    readable = visible_tickets(a.ticket for a in pending)
    for a in pending:
        if a.ticket not in readable:
            continue
        rows.append(
            {
                "type": a.kind or _("Code Change"),
                "name": a.name,
                "ticket": a.ticket,
                "subject": frappe.db.get_value("HD Ticket", a.ticket, "subject"),
                "assigned_to": a.assigned_to,
                "assigned_name": get_fullname(a.assigned_to) if a.assigned_to else "",
                "waited_hours": _hours(a.assigned_at or a.creation),
                "due_in_hours": copilot_approvals.due_in_hours(a),
                "escalated": bool(a.escalated_at),
                "snoozed_until": str(a.snoozed_until)[:16] if a.snoozed_until else "",
                "risk": a.risk_level or "",
                "sensitive": bool(a.sensitive),
                "link": _ticket_url(a.ticket),
                "pull_request": a.pr_url or "",
            }
        )
    for release in frappe.get_all(
        DEPLOY,
        filters={"status": "Waiting for approval"},
        fields=[
            "name",
            "ticket",
            "repository",
            "branch",
            "assigned_to",
            "assigned_at",
            "risk_level",
            "needs_senior",
            "creation",
        ],
    ):
        if release.ticket and release.ticket not in visible_tickets([release.ticket]):
            continue
        rows.append(
            {
                "type": _("Release"),
                "name": release.name,
                "ticket": release.ticket or "",
                "subject": "{0} {1}".format(
                    release.repository or "", release.branch or ""
                ),
                "assigned_to": release.assigned_to,
                "assigned_name": get_fullname(release.assigned_to)
                if release.assigned_to
                else "",
                "waited_hours": _hours(release.assigned_at or release.creation),
                "due_in_hours": None,
                "escalated": False,
                "snoozed_until": "",
                "risk": release.risk_level or "",
                "sensitive": bool(release.needs_senior),
                "link": get_url(f"/app/hds-deploy-request/{release.name}"),
                "pull_request": "",
            }
        )
    return sorted(rows, key=lambda r: -(r["waited_hours"] or 0))


# --- Releases ------------------------------------------------------------------------------------


def releases(days: int = 7) -> dict:
    """Releases and deploys in the pipeline, and those finished in the last `days` days."""
    since = add_days(now_datetime(), -max(int(days or 7), 1))
    fields = [
        "name",
        "status",
        "source",
        "repository",
        "branch",
        "ci_status",
        "staging_status",
        "ticket",
        "run",
        "when",
        "scheduled_for",
        "assigned_to",
        "decided_by",
        "finished_at",
        "error",
        "modified",
    ]
    found = frappe.get_all(
        DEPLOY,
        filters={"status": ["in", RELEASE_PIPELINE]},
        fields=fields,
        order_by="modified desc",
        limit=100,
    ) + frappe.get_all(
        DEPLOY,
        filters={"status": ["in", RELEASE_FINISHED], "modified": [">=", since]},
        fields=fields,
        order_by="modified desc",
        limit=100,
    )
    readable = visible_tickets(r.ticket for r in found if r.ticket)
    rows = []
    for r in found:
        if r.ticket and r.ticket not in readable:
            continue
        rows.append(
            {
                "name": r.name,
                "status": r.status,
                "source": r.source or "",
                "repository": r.repository or "",
                "branch": r.branch or "",
                "ci": r.ci_status or "",
                "check": r.staging_status or "",
                "ticket": r.ticket or "",
                "when": r.when or "",
                "scheduled_for": str(r.scheduled_for or "")[:16],
                "assigned_name": get_fullname(r.assigned_to) if r.assigned_to else "",
                "decided_name": get_fullname(r.decided_by) if r.decided_by else "",
                "finished_at": str(r.finished_at or "")[:16],
                "error": (r.error or "")[:300],
                "sites": frappe.get_all(
                    "HDS Deploy Site",
                    filters={"parent": r.name, "parenttype": DEPLOY},
                    fields=["site", "status"],
                ),
                "apps": [
                    {
                        "app": a.app,
                        "from": (a.from_commit or "")[:12],
                        "to": (a.to_commit or "")[:12],
                    }
                    for a in frappe.get_all(
                        "HDS Deploy App",
                        filters={"parent": r.name, "parenttype": DEPLOY},
                        fields=["app", "from_commit", "to_commit"],
                    )
                ],
                "link": get_url(f"/app/hds-deploy-request/{r.name}"),
            }
        )
    return {
        "pipeline": [r for r in rows if r["status"] in RELEASE_PIPELINE],
        "finished": [r for r in rows if r["status"] in RELEASE_FINISHED],
        "stages": list(RELEASE_PIPELINE),
    }


# --- Sites ---------------------------------------------------------------------------------------


def sites(customer: str | None = None) -> list[dict]:
    """Each customer site: its Copilot level, its apps and drift, the error watch, known issues."""
    filters = {"customer_name": customer} if customer else {}
    cards = frappe.get_all(
        "HDS Site Registry",
        filters=filters,
        fields=[
            "name",
            "customer_name",
            "environment",
            "site_url",
            "press_site",
            "connection",
            "last_synced",
            "watch_checked_at",
            "watch_failures",
            "watch_note",
        ],
        order_by="customer_name asc",
    )
    watched = set(
        frappe.get_all("HD Customer", filters={"custom_copilot_watch": 1}, pluck="name")
    )
    issue_rows = frappe.get_all(
        "HDS Known Issue Site",
        filters={"parenttype": "HDS Known Issue"},
        fields=["parent", "registry", "has_fix"],
    )
    issue_status = {
        i.name: i.status
        for i in frappe.get_all("HDS Known Issue", fields=["name", "status"])
    }
    rows = []
    for card in cards:
        mine = [r for r in issue_rows if r.registry == card.name]
        rows.append(
            {
                "name": card.name,
                "customer": card.customer_name,
                "environment": card.environment,
                "site": card.site_url or card.press_site or card.name,
                "connected": bool(card.connection),
                "level": copilot_settings.level_of(card.customer_name),
                "apps_read_at": str(card.last_synced or "")[:16],
                "apps": [
                    {
                        "app": a.app,
                        "branch": a.branch or "",
                        "commit": (a.deployed_commit or "")[:12],
                        "drift": a.drift_status or "Unknown",
                    }
                    for a in frappe.get_all(
                        "HDS Site App",
                        filters={
                            "parent": card.name,
                            "parenttype": "HDS Site Registry",
                        },
                        fields=["app", "branch", "deployed_commit", "drift_status"],
                        order_by="idx asc",
                    )
                ],
                "watch": {
                    "on": card.customer_name in watched,
                    "checked_at": str(card.watch_checked_at or "")[:16],
                    "failures": card.watch_failures or 0,
                    "note": card.watch_note or "",
                },
                "open_issues": sum(
                    1 for r in mine if issue_status.get(r.parent) == "Open"
                ),
                "missing_fixes": sum(
                    1
                    for r in mine
                    if issue_status.get(r.parent) == "Fixed" and r.has_fix == "No"
                ),
                "link": get_url(f"/app/hds-site-registry/{card.name}"),
            }
        )
    return rows


# --- Known issues --------------------------------------------------------------------------------


def known_issues(status: str | None = None) -> list[dict]:
    """Known issues, the latest seen first, with their sites; a ticket only when it may be read."""
    filters = {"status": status} if status else {}
    issues = frappe.get_all(
        "HDS Known Issue",
        filters=filters,
        fields=[
            "name",
            "title",
            "status",
            "app",
            "root_cause_category",
            "first_seen",
            "last_seen",
            "came_back",
            "fix_pull_request",
            "fix_title",
            "merge_commit",
            "fixed_at",
            "kb_article",
        ],
        order_by="last_seen desc",
        limit=100,
    )
    site_rows = frappe.get_all(
        "HDS Known Issue Site",
        filters={"parent": ["in", [i.name for i in issues] or [""]]},
        fields=[
            "parent",
            "registry",
            "customer",
            "count",
            "last_seen",
            "ticket",
            "has_fix",
        ],
    )
    readable = visible_tickets(r.ticket for r in site_rows if r.ticket)
    site_names = {
        c.name: c.site_url or c.name
        for c in frappe.get_all("HDS Site Registry", fields=["name", "site_url"])
    }
    rows = []
    for issue in issues:
        sites_seen = [
            {
                "site": site_names.get(r.registry, r.registry),
                "customer": r.customer or "",
                "count": r.count or 0,
                "last_seen": str(r.last_seen or "")[:16],
                "ticket": r.ticket if r.ticket in readable else "",
                "has_fix": r.has_fix or "",
            }
            for r in site_rows
            if r.parent == issue.name
        ]
        rows.append(
            {
                "name": issue.name,
                "title": issue.title,
                "status": issue.status,
                "app": issue.app or "",
                "root_cause": issue.root_cause_category or "",
                "first_seen": str(issue.first_seen or "")[:16],
                "last_seen": str(issue.last_seen or "")[:16],
                "came_back": issue.came_back or 0,
                "fix": {
                    "pull_request": issue.fix_pull_request or "",
                    "title": issue.fix_title or "",
                    "merge_commit": (issue.merge_commit or "")[:12],
                    "fixed_at": str(issue.fixed_at or "")[:16],
                }
                if issue.status == "Fixed"
                else None,
                "kb_article": issue.kb_article or "",
                "sites": sites_seen,
                "missing_fix": sum(1 for s in sites_seen if s["has_fix"] == "No"),
                "link": get_url(f"/app/hds-known-issue/{issue.name}"),
            }
        )
    return rows
