# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The pilot's controls and numbers (Phase 4): the monthly AI budget, the worker watch,
the Copilot Pilot report's numbers and the weekly pilot email.

The Copilot level per customer is in `settings.level_of`; docs/tbo-copilot.md, "Pilot".
"""

from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    escape_html,
    flt,
    get_datetime,
    get_first_day,
    get_url,
    getdate,
    now_datetime,
    time_diff_in_hours,
)

from helpdesk.copilot import settings as copilot_settings

RUN = "HDS Copilot Run"
USAGE = "HDS AI Usage Log"
BUDGET_KEY = "copilot:budget:{month}:{level}"
WATCH_KEY = "copilot:worker_watch"
WATCH_WAIT_MINUTES = 15
PILOT_TZ = "Asia/Riyadh"
PILOT_HOUR = 8  # Monday 08:00 Riyadh time
DIAGNOSED_KINDS = ("investigate", "followup")


def _once(key: str, seconds: int) -> bool:
    """True the first time `key` is seen in `seconds` (an atomic SET NX, so two workers never both send)."""
    return bool(
        frappe.cache.set(  # site-prefixed via make_key; set_value can't do NX - nosemgrep
            frappe.cache.make_key(key), 1, nx=True, ex=seconds
        )
    )


def _tell_managers(subject: str, doctype: str = "HDS Copilot Settings", name=None):
    from helpdesk.copilot.approvals import managers
    from helpdesk.work_reminders import notify_users

    notify_users(
        managers(),
        doctype,
        name or doctype,
        subject,
        escalate=True,
        once=False,
    )


# --- the monthly AI budget ----------------------------------------------------------------


def month_spend(now=None) -> float:
    """What Copilot's runs cost this calendar month, from the AI usage log."""
    start = get_first_day(getdate(now or now_datetime()))
    total = frappe.db.sql(
        """select coalesce(sum(estimated_cost_usd), 0) from `tabHDS AI Usage Log`
        where copilot_run is not null and copilot_run != '' and creation >= %s""",
        (start,),
    )[0][0]
    return flt(total)


def budget_allows_work() -> bool:
    """False once the month's spend reaches the budget (0: no budget). The Agent Managers
    hear once a month at 80% and once at 100%."""
    budget = flt(copilot_settings.get_settings().get("monthly_ai_budget_usd"))
    if budget <= 0:
        return True
    spent = month_spend()
    month = getdate().strftime("%Y-%m")
    for level, share in ((100, 1.0), (80, 0.8)):
        if spent >= budget * share:
            if _once(BUDGET_KEY.format(month=month, level=level), 40 * 86400):
                if level == 100:
                    subject = _(
                        "Copilot's monthly AI budget is used up: ${0} of ${1}. No new work goes to a worker until next month, or until the budget is raised in HDS Copilot Settings."
                    ).format(round(spent, 2), round(budget, 2))
                else:
                    subject = _(
                        "Copilot has used 80% of its monthly AI budget: ${0} of ${1}."
                    ).format(round(spent, 2), round(budget, 2))
                _tell_managers(subject)
            break
    return spent < budget


# --- the worker watch ----------------------------------------------------------------------


def waiting_runs(now=None) -> list[dict]:
    """Runs no worker has claimed for WATCH_WAIT_MINUTES: queued investigations, and
    fixes asked for but never picked up."""
    cutoff = (now or now_datetime()) - timedelta(minutes=WATCH_WAIT_MINUTES)
    queued = frappe.get_all(
        RUN,
        filters={"state": "Queued", "queued_at": ["<", cutoff]},
        fields=["name", "ticket", "queued_at as since"],
    )
    fixes = frappe.db.sql(
        """select r.name, r.ticket, max(e.creation) as since
        from `tabHDS Copilot Run` r join `tabHDS Copilot Event` e
            on e.run = r.name and e.event_type = 'fix_requested'
        where r.fix_status = 'Queued'
        group by r.name, r.ticket
        having max(e.creation) < %s""",
        (cutoff,),
        as_dict=True,
    )
    return queued + fixes


def watch_workers():
    """Every 10 minutes: when runs wait and no worker claims them, the Agent Managers are
    told, once an hour while it lasts."""
    if not copilot_settings.is_enabled():
        return
    waiting = waiting_runs()
    if not waiting or not budget_allows_work():
        return  # a used-up budget holds the work on purpose and has its own alert
    if not _once(WATCH_KEY, 3600):
        return
    oldest = min(get_datetime(row.since) for row in waiting)
    _tell_managers(
        _(
            "{0} Copilot runs have waited more than {1} minutes with no worker claiming them (the oldest since {2}). Check the worker server."
        ).format(len(waiting), WATCH_WAIT_MINUTES, str(oldest)[:16]),
        RUN,
        waiting[0].name,
    )


# --- the pilot's numbers -------------------------------------------------------------------


def week_of(value) -> str:
    """The Monday that starts the week of `value`, as YYYY-MM-DD."""
    day = getdate(value)
    return str(add_days(day, -day.weekday()))


def _median(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(median(values), 1) if values else None


def pilot_rows(from_date, to_date, customer: str | None = None) -> list[dict]:
    """One row per week and customer: diagnoses and their ratings, explanations, fixes,
    corrections, waits and AI cost, for runs queued between the two dates."""
    filters = {
        "queued_at": [
            "between",
            [get_datetime(from_date), get_datetime(f"{to_date} 23:59:59")],
        ],
        "kind": ["!=", "revert"],
    }
    if customer:
        filters["customer"] = customer
    runs = frappe.get_all(
        RUN,
        filters=filters,
        fields=[
            "name",
            "ticket",
            "customer",
            "kind",
            "state",
            "shadow",
            "root_cause_category",
            "review_verdict",
            "explanation_edited",
            "fix_requested",
            "pull_request",
            "merge_commit",
            "deployed_at",
            "change_set",
            "queued_at",
            "finished_at",
            "build_scope",
        ],
    )
    if not runs:
        return []
    names = [run.name for run in runs]
    approvals = frappe.get_all(
        "HDS Copilot Approval",
        filters={"run": ["in", names]},
        fields=["run", "status", "creation", "decided_at"],
    )
    change_sets = frappe.get_all(
        "HDS Copilot Change Set",
        filters={"run": ["in", names], "undo_of": ["is", "not set"]},
        fields=["run", "status", "applied_count", "skipped_count"],
    )
    undone_fixes = set(
        frappe.get_all(
            RUN, filters={"kind": "revert", "reverts": ["in", names]}, pluck="reverts"
        )
    )
    # an explanation was sent when the agent's reply moved the run to Answered
    answered = set(
        frappe.get_all(
            "HDS Copilot Event",
            filters={
                "run": ["in", names],
                "event_type": "state_change",
                "payload": ["like", '%"to": "Answered"%'],
            },
            pluck="run",
        )
    )
    tickets = list({run.ticket for run in runs})
    costs = {
        row.ticket: flt(row.usd)
        for row in frappe.get_all(
            USAGE,
            filters={
                "ticket": ["in", tickets],
                "creation": [
                    "between",
                    [get_datetime(from_date), get_datetime(f"{to_date} 23:59:59")],
                ],
            },
            fields=["ticket", "sum(estimated_cost_usd) as usd"],
            group_by="ticket",
        )
    }

    groups: dict[tuple, list] = {}
    for run in runs:
        groups.setdefault((week_of(run.queued_at), run.customer or ""), []).append(run)
    rows = []
    for (week, cust), group in sorted(groups.items()):
        names_in = {run.name for run in group}
        diagnosed = [
            r for r in group if r.root_cause_category and r.kind in DIAGNOSED_KINDS
        ]
        rated = [r for r in diagnosed if r.review_verdict]
        right = sum(1 for r in rated if r.review_verdict == "Right")
        partly = sum(1 for r in rated if r.review_verdict == "Partly")
        wrong = [r.name for r in rated if r.review_verdict == "Wrong"]
        sent = [r for r in group if r.name in answered]
        its_approvals = [a for a in approvals if a.run in names_in]
        its_changes = [c for c in change_sets if c.run in names_in]
        resolved = [
            time_diff_in_hours(r.finished_at, r.queued_at)
            for r in group
            if r.state in ("Resolved", "Closed", "Answered") and r.finished_at
        ]
        group_tickets = {r.ticket for r in group}
        cost = sum(costs.get(t, 0) for t in group_tickets)
        # Phase 8: Copilot's builds of approved customizations, and their cost next to the hours sold
        builds = [r for r in group if r.build_scope]
        build_hours = sum(
            flt((frappe.parse_json(r.build_scope) or {}).get("hours")) for r in builds
        )
        categories: dict[str, int] = {}
        for r in diagnosed:
            categories[r.root_cause_category] = (
                categories.get(r.root_cause_category, 0) + 1
            )
        rows.append(
            {
                "week": week,
                "customer": cust,
                "tickets": len(group_tickets),
                "diagnoses": len(diagnosed),
                "rated": len(rated),
                "right": right,
                "partly": partly,
                "wrong": len(wrong),
                # Partly counts half, as the stage 1 gate says
                "rating_rate": round((right + partly / 2) * 100 / len(rated), 1)
                if rated
                else None,
                "root_causes": ", ".join(
                    f"{name} {count}" for name, count in sorted(categories.items())
                ),
                "explanations_sent": len(sent),
                "median_edit": _median([flt(r.explanation_edited) for r in sent]),
                "fixes_asked": sum(1 for r in group if r.fix_requested),
                "fixes_opened": sum(1 for r in group if r.pull_request),
                "fixes_approved": sum(
                    1 for a in its_approvals if a.status in ("Approved", "Merged")
                ),
                "fixes_merged": sum(1 for r in group if r.merge_commit),
                "fixes_deployed": sum(1 for r in group if r.deployed_at),
                "fixes_undone": sum(1 for r in group if r.name in undone_fixes),
                "builds_started": len(builds),
                "builds_merged": sum(1 for r in builds if r.merge_commit),
                "builds_reopened": sum(1 for r in builds if r.state == "Escalated"),
                "build_hours": round(build_hours, 1),
                "build_ai_cost": round(
                    sum(costs.get(t, 0) for t in {r.ticket for r in builds}), 4
                ),
                "corrections_applied": sum(
                    1 for c in its_changes if c.status in ("Applied", "Undone")
                ),
                "records_skipped": sum(int(c.skipped_count or 0) for c in its_changes),
                "corrections_undone": sum(
                    1 for c in its_changes if c.status == "Undone"
                ),
                "refused": sum(1 for a in its_approvals if a.status == "Rejected"),
                "escalated": sum(
                    1 for r in group if r.state in ("Escalated", "Handed Over")
                ),
                "median_approval_hours": _median(
                    [
                        time_diff_in_hours(a.decided_at, a.creation)
                        for a in its_approvals
                        if a.decided_at
                    ]
                ),
                "median_resolution_hours": _median(resolved),
                "ai_cost": round(cost, 4),
                "ai_cost_per_ticket": round(cost / len(group_tickets), 4)
                if group_tickets
                else 0,
                "wrong_runs": ", ".join(wrong),
            }
        )
    return rows


# --- the weekly pilot email -------------------------------------------------------------------


def last_week(now=None) -> tuple:
    """Monday to Sunday of the week before `now`."""
    today = getdate(now or now_datetime())
    monday = add_days(today, -today.weekday() - 7)
    return monday, add_days(monday, 6)


def pilot_recipients() -> list[str]:
    from helpdesk.copilot.approvals import managers

    listed = (copilot_settings.get_settings().get("pilot_report_to") or "").replace(
        ",", "\n"
    )
    emails = [line.strip() for line in listed.splitlines() if "@" in line]
    return sorted(set(emails + managers()))


def send_weekly_email(now=None, force: bool = False):
    """Hourly: on Monday from 08:00 Riyadh time, once a week, last week's numbers to the
    owner and the Agent Managers."""
    settings = copilot_settings.get_settings()
    if not force and not (settings.enabled and settings.get("pilot_report_enabled")):
        return None
    local = (now or datetime.now(ZoneInfo(PILOT_TZ))).astimezone(ZoneInfo(PILOT_TZ))
    week_start, week_end = last_week(local.date())
    marker = str(week_start)
    if not force:
        if local.weekday() != 0 or local.hour < PILOT_HOUR:
            return None
        sent_for = frappe.db.get_single_value(
            "HDS Copilot Settings", "pilot_report_sent_for"
        )
        if sent_for == marker or not _once(f"copilot:pilot_email:{marker}", 600):
            return None  # sent already, or another worker is sending it now
    recipients = pilot_recipients()
    if not recipients:
        return None
    from helpdesk.copilot import releases

    rows = pilot_rows(week_start, week_end)
    frappe.sendmail(
        recipients=recipients,
        subject=_("Copilot pilot, week of {0}").format(
            frappe.utils.formatdate(week_start)
        ),
        template="new_notification",
        args={
            "body_content": weekly_email_html(rows, week_start, week_end)
            + releases.week_html(week_start, week_end),
            "doc_link": get_url(
                f"/app/query-report/Copilot Pilot?from_date={week_start}&to_date={week_end}"
            ),
        },
        header=[_("Copilot pilot"), "blue"],
    )
    frappe.db.set_single_value("HDS Copilot Settings", "pilot_report_sent_for", marker)
    return recipients


EMAIL_COLUMNS = (
    ("customer", "Customer"),
    ("diagnoses", "Diagnoses"),
    ("rating_rate", "Rated right %"),
    ("explanations_sent", "Explanations sent"),
    ("median_edit", "Median edit %"),
    ("fixes_merged", "Fixes merged"),
    ("fixes_deployed", "Deployed"),
    ("fixes_undone", "Undone"),
    ("builds_merged", "Builds merged"),
    ("corrections_applied", "Corrections"),
    ("median_approval_hours", "Approval wait (h)"),
    ("ai_cost", "AI cost ($)"),
)


def weekly_email_html(rows: list[dict], week_start, week_end) -> str:
    if not rows:
        return "<p>{0}</p>".format(
            escape_html(
                _("No Copilot runs from {0} to {1}.").format(week_start, week_end)
            )
        )
    head = "".join(
        f"<th style='text-align:left;padding:4px 8px'>{escape_html(_(label))}</th>"
        for _key, label in EMAIL_COLUMNS
    )
    body = "".join(
        "<tr>"
        + "".join(
            f"<td style='padding:4px 8px'>{escape_html(str(row.get(key) if row.get(key) is not None else '-'))}</td>"
            for key, _label in EMAIL_COLUMNS
        )
        + "</tr>"
        for row in rows
    )
    total_cost = round(sum(row["ai_cost"] for row in rows), 2)
    wrong = [name for row in rows for name in row["wrong_runs"].split(", ") if name]
    parts = [
        "<p>{0}</p>".format(
            escape_html(
                _("Copilot from {0} to {1}: {2} diagnoses, AI cost ${3}.").format(
                    week_start,
                    week_end,
                    sum(row["diagnoses"] for row in rows),
                    total_cost,
                )
            )
        ),
        f"<table style='border-collapse:collapse'><tr>{head}</tr>{body}</table>",
    ]
    if wrong:
        links = ", ".join(
            "<a href='{0}'>{1}</a>".format(
                get_url(f"/app/hds-copilot-run/{name}"), escape_html(name)
            )
            for name in wrong
        )
        parts.append(
            "<p>{0} {1}</p>".format(
                escape_html(_("Diagnoses rated Wrong, to look at:")), links
            )
        )
    return "".join(parts)
