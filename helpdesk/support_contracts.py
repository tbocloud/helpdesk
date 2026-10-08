"""Support contracts: the hours a customer bought per period, what was used, and alerts.

Used hours are the billable time logs (Timesheet Detail.custom_billable) of
timesheets that aren't cancelled, counted on the day the work was done, for:
- the customer's projects (the time log's project, else its task's project), and
- tasks raised from the customer's tickets (Task.hd_ticket), when no project
  says otherwise.

Periods start on the contract's start date and repeat every month, quarter or
year until its end date; a one-off block is one period. With roll-over, the
hours left at the end of a period are added to the next one (and keep rolling).

Every day the job expires contracts past their end date and alerts once per
period when the current period reaches the contract's alert threshold, and
again when it is used up. See docs/support-contracts.md.
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Date, NullIf, Sum
from frappe.utils import (
    add_days,
    add_months,
    escape_html,
    flt,
    formatdate,
    getdate,
    nowdate,
)

from helpdesk.work_reminders import notify_users
from helpdesk.work_summary import get_summary_recipients

ACTIVE = "Active"
EXPIRED = "Expired"
ONE_OFF_BLOCK = "One-off block"
PERIOD_MONTHS = {"Monthly": 1, "Quarterly": 3, "Yearly": 12}
CANCELLED_TIMESHEET = 2

# alert stages, stored on the contract with the period they were sent for
THRESHOLD = "Threshold"
OVERAGE = "Overage"

# how a period's usage reads; the UI colours them neutral, warning and danger
STAGE_OK = "ok"
STAGE_WARNING = "warning"
STAGE_OVER = "over"

CONTRACT_FIELDS = [
    "name",
    "contract_name",
    "customer",
    "contract_type",
    "status",
    "account_manager",
    "start_date",
    "end_date",
    "billing_period",
    "hours_per_period",
    "rollover_unused",
    "alert_threshold",
    "rate_per_extra_hour",
    "currency",
    "notes",
    "alerted_period_start",
    "alerted_stage",
]


# --- periods ---


def contract_periods(start, end, billing_period: str) -> list[tuple]:
    """Every (first day, last day) of a contract, in order; the last one ends with the contract."""
    start, end = getdate(start), getdate(end)
    months = PERIOD_MONTHS.get(billing_period)
    if not months:
        return [(start, end)]
    periods = []
    index = 0
    # stepping from the start date each time keeps a contract from the 31st on
    # the last day of shorter months instead of drifting to the 28th for good
    while (first := getdate(add_months(start, index * months))) <= end:
        last = getdate(add_days(add_months(start, (index + 1) * months), -1))
        periods.append((first, min(last, end)))
        index += 1
    return periods


def usage_by_period(contract, daily: dict, today=None) -> list[dict]:
    """Each period that has started, oldest first, with the hours used against it.

    `daily` maps a day to the billable hours logged for the customer that day.
    """
    today = getdate(today or nowdate())
    rolls_over = contract.rollover_unused and contract.billing_period != ONE_OFF_BLOCK
    periods, carried = [], 0.0
    for first, last in contract_periods(
        contract.start_date, contract.end_date, contract.billing_period
    ):
        if first > today:
            break
        used = sum(hours for day, hours in daily.items() if first <= day <= last)
        period = period_usage(contract, first, last, carried, used, today)
        periods.append(period)
        carried = max(period["remaining"], 0) if rolls_over else 0.0
    return periods


def period_usage(contract, first, last, carried: float, used: float, today) -> dict:
    included = flt(contract.hours_per_period)
    allowance = included + carried
    percent = round(100 * used / allowance, 1) if allowance else 0.0
    return {
        "start": str(first),
        "end": str(last),
        "included": round(included, 2),
        "carried_in": round(carried, 2),
        "allowance": round(allowance, 2),
        "used": round(used, 2),
        "remaining": round(allowance - used, 2),
        "percent": percent,
        "stage": usage_stage(percent, contract.alert_threshold),
        "is_current": first <= today <= last,
    }


def usage_stage(percent: float, threshold) -> str:
    if percent >= 100:
        return STAGE_OVER
    if percent >= int(threshold or 100):
        return STAGE_WARNING
    return STAGE_OK


def shown_period(periods: list[dict]) -> dict | None:
    """Today's period, or the latest one when the contract has ended."""
    return next((p for p in periods if p["is_current"]), None) or (
        periods[-1] if periods else None
    )


# --- hours logged ---


def billable_logs():
    """The billable time logs of timesheets that aren't cancelled, with the customer
    and project each one counts for. Returns the query and its expressions."""
    Detail = frappe.qb.DocType("Timesheet Detail")
    Sheet = frappe.qb.DocType("Timesheet")
    Task = frappe.qb.DocType("Task")
    LogProject = frappe.qb.DocType("Project").as_("log_project")
    TaskProject = frappe.qb.DocType("Project").as_("task_project")
    Ticket = frappe.qb.DocType("HD Ticket")
    customer = Coalesce(
        NullIf(LogProject.customer, ""),
        NullIf(TaskProject.customer, ""),
        NullIf(Ticket.customer, ""),
    )
    project = Coalesce(NullIf(Detail.project, ""), NullIf(Task.project, ""))
    query = (
        frappe.qb.from_(Detail)
        .join(Sheet)
        .on(Sheet.name == Detail.parent)
        .left_join(Task)
        .on(Task.name == Detail.task)
        .left_join(LogProject)
        .on(LogProject.name == Detail.project)
        .left_join(TaskProject)
        .on(TaskProject.name == Task.project)
        .left_join(Ticket)
        .on(Ticket.name == Task.hd_ticket)
        .where(Detail.parenttype == "Timesheet")
        .where(Sheet.docstatus != CANCELLED_TIMESHEET)
        .where(Detail.custom_billable == 1)
    )
    return query, {
        "detail": Detail,
        "sheet": Sheet,
        "task": Task,
        "customer": customer,
        "project": project,
    }


def in_dates(query, detail, start, end):
    return query.where(detail.from_time >= getdate(start)).where(
        detail.from_time < add_days(getdate(end), 1)
    )


def daily_billable_hours(customers, start, end) -> dict[str, dict]:
    """{customer: {day: hours}} for the customers between two dates, in one query."""
    customers = [c for c in customers if c]
    if not customers:
        return {}
    query, x = billable_logs()
    day = Date(x["detail"].from_time)
    rows = (
        in_dates(query, x["detail"], start, end)
        .select(
            x["customer"].as_("customer"),
            day.as_("day"),
            Sum(x["detail"].hours).as_("hours"),
        )
        .where(x["customer"].isin(customers))
        .groupby(x["customer"], day)
        .run(as_dict=True)
    )
    daily: dict[str, dict] = {}
    for row in rows:
        daily.setdefault(row.customer, {})[getdate(row.day)] = flt(row.hours)
    return daily


def usage_breakdown(customer: str, start, end, manager: bool) -> dict:
    """The period's billable hours by project, by ticket and (for managers) by person.

    Others see only the names of the projects and tickets they may read; the
    rest of the hours are grouped under one row without a name.
    """
    query, x = billable_logs()
    rows = (
        in_dates(query, x["detail"], start, end)
        .select(
            x["project"].as_("project"),
            x["task"].hd_ticket.as_("ticket"),
            x["sheet"].owner.as_("person"),
            Sum(x["detail"].hours).as_("hours"),
        )
        .where(x["customer"] == customer)
        .groupby(x["project"], x["task"].hd_ticket, x["sheet"].owner)
        .run(as_dict=True)
    )
    by_project, by_ticket, by_person = {}, {}, {}
    for row in rows:
        hours = flt(row.hours)
        add_to(by_project, row.project or "", hours)
        if row.ticket:
            add_to(by_ticket, str(row.ticket), hours)
        add_to(by_person, row.person, hours)
    return {
        "projects": ranked(
            by_project, readable_names("Project", "project_name", by_project, manager)
        ),
        "tickets": ranked(
            by_ticket, readable_names("HD Ticket", "subject", by_ticket, manager)
        ),
        "people": ranked(by_person, names_of("User", "full_name", by_person))
        if manager
        else None,
    }


def add_to(totals: dict, key, hours: float):
    totals[key] = totals.get(key, 0.0) + hours


def ranked(totals: dict, labels: dict) -> list[dict]:
    """Rows of {name, label, hours}, most hours first; names missing from
    `labels` (unreadable) are added up in one row with no name."""
    rows, hidden = [], 0.0
    for name, hours in totals.items():
        if name and name not in labels:
            hidden += hours
        else:
            rows.append(
                {
                    "name": name or None,
                    "label": labels.get(name),
                    "hours": round(hours, 2),
                }
            )
    rows.sort(key=lambda r: (-r["hours"], str(r["label"] or "")))
    if hidden:
        rows.append(
            {"name": None, "label": None, "hours": round(hidden, 2), "other": 1}
        )
    return rows


def readable_names(doctype: str, field: str, names, manager: bool) -> dict:
    """{name: title} for the records the viewer may read (managers read all)."""
    names = [n for n in names if n]
    if not names:
        return {}
    if manager:
        return names_of(doctype, field, names)
    return {
        str(r.name): r[field] or str(r.name)
        for r in frappe.get_list(
            doctype,
            filters={"name": ("in", names)},
            fields=["name", field],
            limit_page_length=0,
        )
    }


def names_of(doctype: str, field: str, names) -> dict:
    names = [n for n in names if n]
    if not names:
        return {}
    Table = frappe.qb.DocType(doctype)
    return {
        str(name): title or str(name)
        for name, title in frappe.qb.from_(Table)
        .select(Table.name, Table[field])
        .where(Table.name.isin(names))
        .run()
    }


# --- contracts ---


def get_contracts(**filters) -> list:
    return frappe.qb.get_query(
        "HD Support Contract",
        fields=CONTRACT_FIELDS,
        filters=filters,
        order_by="start_date desc",
    ).run(as_dict=True)


def current_contracts(today) -> list:
    """Active contracts whose dates cover today."""
    return get_contracts(
        status=ACTIVE, start_date=("<=", today), end_date=(">=", today)
    )


def contract_usage(contracts: list, today) -> dict[str, list[dict]]:
    """{contract name: periods so far} for many contracts, with one hours query."""
    if not contracts:
        return {}
    daily = daily_billable_hours(
        {c.customer for c in contracts},
        min(getdate(c.start_date) for c in contracts),
        min(today, max(getdate(c.end_date) for c in contracts)),
    )
    return {
        c.name: usage_by_period(c, daily.get(c.customer, {}), today) for c in contracts
    }


def period_label(period: dict) -> str:
    return _("{0} to {1}").format(
        formatdate(period["start"], "d MMM yyyy"),
        formatdate(period["end"], "d MMM yyyy"),
    )


# --- daily job ---


def send_support_hours_alerts():
    """Scheduler (daily): expire ended contracts, then alert on hours running out."""
    today = getdate(nowdate())
    expire_ended_contracts(today)
    contracts = current_contracts(today)
    usage = contract_usage(contracts, today)
    email_customers = bool(
        frappe.db.get_single_value("HD Work Settings", "support_hours_email_customer")
    )
    for contract in contracts:
        try:
            alert_contract(
                contract, shown_period(usage[contract.name]), email_customers
            )
        except Exception:  # noqa: BLE001 - one contract must not stop the others
            frappe.log_error(
                title=f"Support hours alert failed for {contract.name}",
                message=frappe.get_traceback(),
            )


def expire_ended_contracts(today):
    Contract = frappe.qb.DocType("HD Support Contract")
    (
        frappe.qb.update(Contract)
        .set(Contract.status, EXPIRED)
        .where(Contract.status == ACTIVE)
        .where(Contract.end_date < today)
        .run()
    )


def alert_contract(contract, period: dict | None, email_customers: bool):
    stage = alert_due(contract, period)
    if not stage:
        return
    notify_users(
        alert_recipients(contract),
        "HD Support Contract",
        contract.name,
        alert_subject(contract, period, stage),
        link=f"/customers/{quote(contract.customer)}#support-hours",
    )
    if email_customers:
        email_customer(contract, period, stage)
    frappe.db.set_value(
        "HD Support Contract",
        contract.name,
        {"alerted_period_start": period["start"], "alerted_stage": stage},
        update_modified=False,
    )


def alert_due(contract, period: dict | None) -> str | None:
    """The alert this period still needs: each stage once per period, the overage after the threshold."""
    if not period:
        return None
    sent_now = str(contract.alerted_period_start or "") == period["start"]
    if period["stage"] == STAGE_OVER:
        return None if sent_now and contract.alerted_stage == OVERAGE else OVERAGE
    if period["stage"] == STAGE_WARNING:
        return None if sent_now else THRESHOLD
    return None


def alert_recipients(contract) -> list[str]:
    """The account manager, the customer's project managers and leads, and the Agent Managers."""
    return [contract.account_manager, *get_summary_recipients(contract.customer)]


def alert_subject(contract, period: dict, stage: str) -> str:
    # stable within a period (no running totals), so notify_users sends it once
    if stage == OVERAGE:
        return _("{0} has used all its support hours for {1} ({2}).").format(
            contract.customer, period_label(period), contract.contract_name
        )
    return _("{0} has used {1}% of its support hours for {2} ({3}).").format(
        contract.customer,
        contract.alert_threshold,
        period_label(period),
        contract.contract_name,
    )


def email_customer(contract, period: dict, stage: str):
    from helpdesk.api.content_portal import portal_emails

    emails = portal_emails(contract.customer)
    if not emails:
        return
    name = escape_html(contract.contract_name)
    used = _("{0} of {1} hours used, {2}.").format(
        period["used"],
        period["allowance"],
        _("{0} hours left").format(period["remaining"])
        if period["remaining"] >= 0
        else _("{0} hours over").format(-period["remaining"]),
    )
    if stage == OVERAGE:
        subject = _("Your support hours for {0} are used up").format(
            period_label(period)
        )
        body = _(
            "You have used all the support hours in {0} for {1}. Further work this period is billed as extra hours."
        ).format(name, period_label(period))
    else:
        subject = _("You have used {0}% of your support hours").format(
            contract.alert_threshold
        )
        body = _("You have used {0}% of the support hours in {1} for {2}.").format(
            contract.alert_threshold, name, period_label(period)
        )
    frappe.sendmail(
        recipients=emails,
        subject=subject,
        message=f"<p>{_('Hello,')}</p><p>{body}</p><p>{used}</p>",
        reference_doctype="HD Support Contract",
        reference_name=contract.name,
    )
