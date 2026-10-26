"""The Daily Sales Performance Report (docs/leads.md, "Daily report").

TBO Smart's `get_daily_report` counts what each salesperson did on one day; the hub holds
the targets (HD CRM Settings), measures the week against them, writes the plain text people
paste into WhatsApp, and sends the team's report to managers at 18:00 on working days.
"""

import math

import frappe
from frappe import _
from frappe.utils import add_days, cint, formatdate, getdate, today

from helpdesk.integrations.crm.leads import (
    LeadsError,
    call_if_deployed,
    can_use_leads,
    leads_on,
)

# the managers who get the 18:00 message (and, on the ERP site, see everyone)
RECIPIENT_ROLES = ("Sales Manager", "System Manager")
WEEK_DAYS = 6  # Monday to Saturday
BLOCK_BREAK = "\n\n──────────\n\n"
# (metric, HD CRM Settings field, default); leads is the daily target times the week's days
TARGET_FIELDS = (
    ("leads", "daily_lead_target", 10),
    ("meetings", "weekly_meeting_target", 10),
    ("proposals", "weekly_proposal_target", 5),
    ("follow_ups", "weekly_follow_up_target", 40),
)
SETTINGS = "HD CRM Settings"


def read_targets() -> dict:
    """The targets from HD CRM Settings, read live: `leads` is per day, the others per
    week. A negative or blank one is 0 (no target); a never-saved one is its default."""
    found = {}
    for metric, field, default in TARGET_FIELDS:
        value = frappe.db.get_single_value(SETTINGS, field)
        found[metric] = default if value is None else max(cint(value), 0)
    return found


def week_days(day) -> dict:
    """Working days of `day`'s week, Monday to Saturday, off days and holidays left
    out: how many have passed up to and including `day` (`elapsed`) and in all (`total`)."""
    from helpdesk.recurrence import working_day_checker

    day = getdate(day)
    monday = add_days(day, -day.weekday())
    is_working = working_day_checker(monday, add_days(monday, WEEK_DAYS))
    week = [add_days(monday, i) for i in range(WEEK_DAYS)]
    working = [d for d in week if is_working(d)]
    return {
        "elapsed": len([d for d in working if d <= day]),
        "total": len(working),
    }


def with_pace(person: dict, targets: dict, days: dict) -> dict:
    """`person` with `pace` (each targeted metric's week so far against what the working
    days passed call for) and `behind` (the metrics short of it, by how many). Weekly
    targets are pro-rated by working days elapsed; a day's new-lead target is multiplied
    by the week's working days."""
    week = person.get("week_to_date") or {}
    total = max(days["total"], 1)
    pace = {}
    behind = []
    for metric, _field, _default in TARGET_FIELDS:
        target = targets[metric]
        if not target:
            continue
        goal = target * total if metric == "leads" else target
        expected = goal * days["elapsed"] / total
        actual = cint(week.get(metric))
        short = max(math.ceil(expected - actual - 1e-9), 0)
        pace[metric] = {
            "actual": actual,
            "target": goal,
            "expected": round(expected, 1),
            "behind": short,
        }
        if short:
            behind.append({"metric": metric, "by": short})
    return {**person, "pace": pace, "behind": behind, "on_track": not behind}


def lead_title(lead: dict) -> str:
    return lead.get("lead_name") or lead.get("company_name") or lead.get("name") or ""


def person_lines(person: dict, day) -> list[str]:
    """One salesperson's report, line by line, in the owner's template. Plain text for
    WhatsApp: the wording is fixed, not translated."""
    names = [lead_title(lead) for lead in person.get("new_leads") or []]
    quotations = (person.get("new_quotations") or {}).get("count") or 0
    return [
        "📊 DAILY SALES PERFORMANCE REPORT",
        f"📅 Date: {formatdate(day, 'dd MMM yyyy')}",
        f"👤 Employee Name: {person.get('full_name') or person.get('user') or ''}",
        "",
        "📞 1. Daily Call Performance",
        f"• Total Calls Made: {cint(person.get('calls_total'))}",
        f"• Fresh Leads: {cint(person.get('fresh_leads'))}",
        f"• Follow-up Leads: {cint(person.get('follow_up_leads'))}",
        f"• Positive Leads: {len(person.get('positive_leads') or [])}",
        f"• New Quotations: {cint(quotations)}",
        "",
        "🎯 2. New Leads Generated",
        f"• Total New Leads: {len(names)}",
        "• Lead Names:",
        *([f"{i}. {name}" for i, name in enumerate(names, 1)] or ["—"]),
    ]


def person_text(person: dict, day) -> str:
    return "\n".join(person_lines(person, day))


def team_text(people: list[dict], day) -> str:
    return BLOCK_BREAK.join(person_text(p, day) for p in people)


def add_texts(report: dict) -> dict:
    """`report` with each person's `text` and the whole team's `team_text`."""
    day = report.get("date") or today()
    people = [{**p, "text": person_text(p, day)} for p in report.get("people") or []]
    return {**report, "people": people, "team_text": team_text(people, day)}


def sales_team_only(report: dict, keep=()) -> tuple[dict, bool]:
    """`report` with only the sales team's people, plus anyone in `keep`, and whether the
    hub has a sales team at all (content_team.only_sales_team)."""
    from helpdesk.content_team import only_sales_team

    people, team_empty = only_sales_team(
        report.get("people") or [], {k for k in keep if k}
    )
    return {**report, "people": people}, team_empty


def prepare(report: dict, owner: str | None = None) -> dict:
    """A report as the page gets it: only the sales team (and `owner`, picked on purpose,
    and the viewer when they aren't a manager), pace for each person, the targets, the
    text, and `team_empty` when nobody is picked as a salesperson yet."""
    own = (
        () if set(frappe.get_roles()) & set(RECIPIENT_ROLES) else (frappe.session.user,)
    )
    report, team_empty = sales_team_only(report, (owner, *own))
    targets = read_targets()
    days = week_days(report.get("date") or today())
    people = [with_pace(p, targets, days) for p in report.get("people") or []]
    return add_texts(
        {
            **report,
            "people": people,
            "targets": targets,
            "working_days": days,
            "team_empty": team_empty,
        }
    )


def recipients() -> list[str]:
    """Enabled users with a manager role who can use Leads, sorted."""
    users = set(
        frappe.get_all(
            "Has Role",
            filters={"role": ("in", RECIPIENT_ROLES), "parenttype": "User"},
            pluck="parent",
        )
    )
    users.discard("Administrator")
    enabled = set(
        frappe.get_all(
            "User", filters={"name": ("in", list(users)), "enabled": 1}, pluck="name"
        )
        if users
        else []
    )
    return sorted(u for u in enabled if can_use_leads(u))


def run():
    """18:00 on working days (hooks.py): every manager gets one message with the team's
    day. Quiet when the setting is off, it isn't a working day, or the ERP site's TBO
    Smart doesn't have the report yet."""
    from helpdesk.recurrence import working_day_checker

    if not cint(frappe.db.get_single_value(SETTINGS, "send_daily_sales_report")):
        return
    if not leads_on():
        return
    day = getdate(today())
    if not working_day_checker(day, day)(day):
        return
    for user in recipients():
        try:
            report = call_if_deployed(
                "get_daily_report", acting_user=user, date=str(day)
            )
            if report is None:
                return
            send_report(user, report)
        except LeadsError:
            # not a salesperson on the ERP site: nothing to tell them
            frappe.clear_last_message()
        except Exception:  # noqa: BLE001 - one person's message must not stop the rest
            frappe.log_error(title=f"Daily sales report failed for {user}")


def send_report(user: str, report: dict):
    """One message to `user`: chat when it is set up, else email."""
    from helpdesk.follow_ups import deliver_digest

    day = report.get("date") or today()
    people = sales_team_only(report)[0]["people"]
    if not people:
        return None
    sections = [
        (
            f"👤 {p.get('full_name') or p.get('user')}",
            [(line, None) for line in person_lines(p, day)[4:]],
        )
        for p in people
    ]
    subject = _("📊 Daily sales performance · {0}").format(
        formatdate(day, "dd MMM yyyy")
    )
    return deliver_digest(user, subject, sections)
