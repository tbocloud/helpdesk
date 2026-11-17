"""The division overview and reports: every figure per division, from the records themselves
(docs/divisions.md, "Overview and reports").

- Hub records (members, projects, tasks, hours) are counted here.
- Leads come from the reporting copy (`HD CRM Report Lead`) of the division's ERP site,
  which its source's sync keeps (docs/divisions.md, "ERP sites").
- Customers and quotations are read from the division's ERP site, at most every
  `ERP_TTL` seconds; a site that can't answer is named and its figures left out, never
  shown as zero.
- Money is in the reporting currency (Settings → Divisions), at each ERP site's rate.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import (
    add_days,
    add_months,
    cint,
    flt,
    get_first_day,
    getdate,
    nowdate,
)

from helpdesk.divisions import DIVISION, MEMBER, overview_divisions
from helpdesk.integrations.crm.client import CRMError

ERP_TTL = 600
CACHE_PREFIX = "hd_division_erp"
QUOTATION_PAGE = 500
# at most this many quotations of one period are read from a site
QUOTATION_LIMIT = 20000
WON_QUOTATIONS = ("Ordered", "Partially Ordered")
LOST_QUOTATIONS = ("Lost", "Expired", "Cancelled")
DONE_TASKS = ("Completed", "Cancelled", "Template")
WON_LEADS = ("Won", "Converted")


# ---------- scope and period ----------


def scope(division: str | None) -> list[str]:
    """The divisions to count: `division`, or every one the person may see."""
    allowed = overview_divisions()
    if not allowed:
        frappe.throw(
            _("The division overview is for Super Admins and division managers."),
            frappe.PermissionError,
        )
    if not division:
        return allowed
    if division not in allowed:
        frappe.throw(
            _("You can't see the {0} division's figures.").format(division),
            frappe.PermissionError,
        )
    return [division]


def period(from_date: str | None, to_date: str | None) -> tuple:
    """(start, end) dates; this year so far when not given."""
    end = getdate(to_date or nowdate())
    start = getdate(from_date) if from_date else getdate(f"{end.year}-01-01")
    if start > end:
        frappe.throw(_("The start date is after the end date."))
    return start, end


def months(start, end) -> list[str]:
    out, month = [], get_first_day(start)
    while month <= end:
        out.append(month.strftime("%Y-%m"))
        month = add_months(month, 1)
    return out


def divisions_meta(divisions: list[str]) -> list[dict]:
    rows = frappe.get_all(
        DIVISION,
        filters={"name": ("in", divisions)},
        fields=["name", "division_name", "country", "currency", "crm_source"],
        order_by="division_name asc",
    )
    for row in rows:
        row.rate = (
            flt(frappe.db.get_value("HD CRM Source", row.crm_source, "exchange_rate"))
            if row.crm_source
            else 0
        )
    return rows


def division_options() -> list[dict]:
    """What the division filter offers: every division the person may see."""
    return [
        {"name": d.name, "division_name": d.division_name}
        for d in divisions_meta(overview_divisions())
    ]


def reporting_currency() -> str | None:
    return frappe.db.get_single_value("HD CRM Settings", "dashboard_currency")


# ---------- hub records ----------


def people_counts(divisions: list[str]) -> dict[str, int]:
    member = frappe.qb.DocType(MEMBER)
    return dict(
        frappe.qb.from_(member)
        .select(member.parent, Count(member.user).distinct())
        .where((member.parenttype == DIVISION) & member.parent.isin(divisions))
        .groupby(member.parent)
        .run()
    )


def project_counts(divisions: list[str]) -> dict[str, dict[str, int]]:
    """{division: {status: projects}}"""
    project = frappe.qb.DocType("Project")
    out = defaultdict(dict)
    for division, status, count in (
        frappe.qb.from_(project)
        .select(project.division, project.status, Count("*"))
        .where(project.division.isin(divisions))
        .groupby(project.division, project.status)
        .run()
    ):
        out[division][status] = count
    return out


def task_counts(divisions: list[str], start, end) -> dict[str, dict[str, int]]:
    """{division: {pending, overdue, done}}: open tasks, the ones past their end date, and
    the ones completed in the period."""
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    today = getdate(nowdate())
    out = defaultdict(lambda: {"pending": 0, "overdue": 0, "done": 0})
    for division, status, end_date, completed_on in (
        frappe.qb.from_(task)
        .join(project)
        .on(project.name == task.project)
        .select(project.division, task.status, task.exp_end_date, task.completed_on)
        .where(project.division.isin(divisions))
        .run()
    ):
        figures = out[division]
        if status not in DONE_TASKS:
            figures["pending"] += 1
            if end_date and getdate(end_date) < today:
                figures["overdue"] += 1
        elif (
            status == "Completed"
            and completed_on
            and start <= getdate(completed_on) <= end
        ):
            figures["done"] += 1
    return out


def productivity(divisions: list[str], start, end) -> list[dict]:
    """Per member of the divisions: tasks done in the period, open and overdue tasks given
    to them, and hours logged on the divisions' projects."""
    member = frappe.qb.DocType(MEMBER)
    rows = {
        (division, user): {
            "division": division,
            "user": user,
            "full_name": frappe.utils.get_fullname(user),
            "role": role,
            "done": 0,
            "open": 0,
            "overdue": 0,
            "hours": 0.0,
        }
        for division, user, role in frappe.qb.from_(member)
        .select(member.parent, member.user, member.role)
        .where((member.parenttype == DIVISION) & member.parent.isin(divisions))
        .run()
    }
    task = frappe.qb.DocType("Task")
    project = frappe.qb.DocType("Project")
    todo = frappe.qb.DocType("ToDo")
    today = getdate(nowdate())
    for division, user, status, end_date, completed_on in (
        frappe.qb.from_(todo)
        .join(task)
        .on(task.name == todo.reference_name)
        .join(project)
        .on(project.name == task.project)
        .select(
            project.division,
            todo.allocated_to,
            task.status,
            task.exp_end_date,
            task.completed_on,
        )
        .where(
            (todo.reference_type == "Task")
            & (todo.status != "Cancelled")
            & project.division.isin(divisions)
        )
        .run()
    ):
        row = rows.get((division, user))
        if not row:
            continue
        if status not in DONE_TASKS:
            row["open"] += 1
            if end_date and getdate(end_date) < today:
                row["overdue"] += 1
        elif (
            status == "Completed"
            and completed_on
            and start <= getdate(completed_on) <= end
        ):
            row["done"] += 1
    sheet = frappe.qb.DocType("Timesheet")
    log = frappe.qb.DocType("Timesheet Detail")
    for division, user, hours in (
        frappe.qb.from_(log)
        .join(sheet)
        .on(sheet.name == log.parent)
        .join(project)
        .on(project.name == log.project)
        .select(project.division, sheet.owner, Sum(log.hours))
        .where(
            (sheet.docstatus < 2)
            & project.division.isin(divisions)
            & (log.from_time >= start)
            & (log.from_time < add_days(end, 1))
        )
        .groupby(project.division, sheet.owner)
        .run()
    ):
        row = rows.get((division, user))
        if row:
            row["hours"] = round(flt(hours), 1)
    return sorted(
        rows.values(), key=lambda r: (-r["done"], -r["hours"], r["full_name"])
    )


# ---------- leads (the ERP sites' reporting copy) ----------


def lead_figures(meta: list[dict], start, end) -> dict[str, dict]:
    """{division: {total, won, lost, open, won_value, by_month: {month: {total, won}}}}"""
    sources = {d.crm_source: d.name for d in meta if d.crm_source}
    out = {
        d.name: {
            "total": 0,
            "won": 0,
            "lost": 0,
            "open": 0,
            "won_value": 0.0,
            "by_month": {},
        }
        for d in meta
    }
    if not sources:
        return out
    lead = frappe.qb.DocType("HD CRM Report Lead")
    for source, category, month, count, won_value in (
        frappe.qb.from_(lead)
        .select(
            lead.source,
            lead.category,
            lead.created_month,
            Count("*"),
            Sum(lead.won_value),
        )
        .where(
            lead.source.isin(list(sources))
            & (lead.created_on >= start)
            & (lead.created_on <= end)
        )
        .groupby(lead.source, lead.category, lead.created_month)
        .run()
    ):
        figures = out[sources[source]]
        month_figures = figures["by_month"].setdefault(month, {"total": 0, "won": 0})
        figures["total"] += count
        month_figures["total"] += count
        if category in WON_LEADS:
            figures["won"] += count
            month_figures["won"] += count
            figures["won_value"] += flt(won_value)
        elif category == "Lost":
            figures["lost"] += count
        elif category == "Open":
            figures["open"] += count
    return out


# ---------- customers and quotations (live from the ERP sites) ----------


def erp_figures(meta: list[dict], start, end) -> dict[str, dict]:
    """{division: {customers, quotations, quotation_value, won, won_value, lost,
    by_status, by_month, error}}; a division without an ERP site has `error` set."""
    return {d.name: erp_figures_of(d, start, end) for d in meta}


def erp_figures_of(division: dict, start, end) -> dict:
    if not division.crm_source:
        return {"error": _("No ERP site is linked to this division.")}
    key = f"{CACHE_PREFIX}:{division.crm_source}:{start}:{end}"
    cached = frappe.cache.get_value(key, expires=True)
    if cached is not None:
        return cached
    try:
        figures = read_erp(division, start, end)
    except CRMError as e:
        # not cached: the next look tries the site again
        return {"error": str(e)}
    frappe.cache.set_value(key, figures, expires_in_sec=ERP_TTL)
    return figures


def read_erp(division: dict, start, end) -> dict:
    client = frappe.get_doc("HD CRM Source", division.crm_source).client()
    customers = cint(
        client.call(
            "frappe.client.get_count",
            doctype="Customer",
            # a GET sends its params as a query string: a dict would go as its keys alone
            filters=json.dumps({"disabled": 0}),
        )
    )
    figures = {
        "customers": customers,
        "quotations": 0,
        "quotation_value": 0.0,
        "won": 0,
        "won_value": 0.0,
        "lost": 0,
        "by_status": {},
        "by_month": {},
        "error": None,
    }
    filters = [
        ["transaction_date", ">=", str(start)],
        ["transaction_date", "<=", str(end)],
        ["docstatus", "<", 2],
    ]
    for start_at in range(0, QUOTATION_LIMIT, QUOTATION_PAGE):
        page = client.get_page(
            "Quotation",
            fields=["name", "status", "transaction_date", "base_grand_total"],
            filters=filters,
            order_by="transaction_date asc, name asc",
            start=start_at,
            page_length=QUOTATION_PAGE,
        )
        for quotation in page:
            add_quotation(figures, quotation, division.rate)
        if len(page) < QUOTATION_PAGE:
            break
    return figures


def add_quotation(figures: dict, quotation: dict, rate: float):
    status = quotation.get("status") or "Draft"
    value = flt(quotation.get("base_grand_total")) * rate
    month = str(quotation.get("transaction_date") or "")[:7]
    month_figures = figures["by_month"].setdefault(month, {"count": 0, "value": 0.0})
    figures["quotations"] += 1
    figures["quotation_value"] += value
    figures["by_status"][status] = figures["by_status"].get(status, 0) + 1
    month_figures["count"] += 1
    month_figures["value"] += value
    if status in WON_QUOTATIONS:
        figures["won"] += 1
        figures["won_value"] += value
    elif status in LOST_QUOTATIONS:
        figures["lost"] += 1


# ---------- the figures of one look ----------


def collect(division: str | None, from_date: str | None, to_date: str | None) -> dict:
    """Everything the overview and the reports show, per division."""
    divisions = scope(division)
    start, end = period(from_date, to_date)
    meta = divisions_meta(divisions)
    return {
        "start": start,
        "end": end,
        "months": months(start, end),
        "currency": reporting_currency(),
        "divisions": meta,
        "people": people_counts(divisions),
        "projects": project_counts(divisions),
        "tasks": task_counts(divisions, start, end),
        "leads": lead_figures(meta, start, end),
        "erp": erp_figures(meta, start, end),
        "productivity": productivity(divisions, start, end),
    }


def rate(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def overview(division: str | None, from_date: str | None, to_date: str | None) -> dict:
    data = collect(division, from_date, to_date)
    erp_ok = {d: f for d, f in data["erp"].items() if not f.get("error")}
    leads = data["leads"].values()
    total_leads = sum(f["total"] for f in leads)
    won_leads = sum(f["won"] for f in leads)
    projects = data["projects"].values()
    rows = [division_row(data, d) for d in data["divisions"]]
    return {
        "options": division_options(),
        "currency": data["currency"],
        "from_date": data["start"],
        "to_date": data["end"],
        "months": data["months"],
        "kpis": {
            "divisions": len(data["divisions"]),
            "employees": sum(data["people"].values()),
            "leads": total_leads,
            "customers": sum(f["customers"] for f in erp_ok.values())
            if erp_ok
            else None,
            "quotations": sum(f["quotations"] for f in erp_ok.values())
            if erp_ok
            else None,
            "projects": sum(sum(p.values()) for p in projects),
            "sales_value": sum(f["won_value"] for f in erp_ok.values())
            if erp_ok
            else None,
            "pending_activities": sum(t["pending"] for t in data["tasks"].values()),
            "active_projects": sum(p.get("Open", 0) for p in projects),
            "conversion_rate": rate(won_leads, total_leads),
        },
        "rows": rows,
        "monthly": monthly(data),
        "project_status": {
            r["division_name"]: data["projects"].get(r["name"], {}) for r in rows
        },
        "top_people": data["productivity"][:10],
        "errors": [
            {"division": d.division_name, "error": data["erp"][d.name]["error"]}
            for d in data["divisions"]
            if data["erp"][d.name].get("error")
        ],
    }


def division_row(data: dict, d: dict) -> dict:
    leads = data["leads"][d.name]
    erp = data["erp"][d.name]
    projects = data["projects"].get(d.name, {})
    tasks = data["tasks"][d.name]
    erp_ok = not erp.get("error")
    return {
        "name": d.name,
        "division_name": d.division_name,
        "country": d.country,
        "currency": d.currency,
        "employees": data["people"].get(d.name, 0),
        "leads": leads["total"],
        "won_leads": leads["won"],
        "lost_leads": leads["lost"],
        "open_leads": leads["open"],
        "conversion_rate": rate(leads["won"], leads["total"]),
        "customers": erp.get("customers") if erp_ok else None,
        "quotations": erp.get("quotations") if erp_ok else None,
        "won_quotations": erp.get("won") if erp_ok else None,
        "lost_quotations": erp.get("lost") if erp_ok else None,
        "quotation_value": erp.get("quotation_value") if erp_ok else None,
        "sales_value": erp.get("won_value") if erp_ok else None,
        "quotation_conversion": rate(erp.get("won", 0), erp.get("quotations", 0))
        if erp_ok
        else None,
        "projects": sum(projects.values()),
        "active_projects": projects.get("Open", 0),
        "completed_projects": projects.get("Completed", 0),
        "on_hold_projects": projects.get("On hold", 0),
        "pending_tasks": tasks["pending"],
        "overdue_tasks": tasks["overdue"],
        "done_tasks": tasks["done"],
        "erp_error": erp.get("error"),
    }


def monthly(data: dict) -> list[dict]:
    """Per month and division: leads, won leads, quotations and their value."""
    out = []
    for month in data["months"]:
        for d in data["divisions"]:
            leads = data["leads"][d.name]["by_month"].get(month, {})
            erp = data["erp"][d.name]
            quotes = (erp.get("by_month") or {}).get(month, {})
            out.append(
                {
                    "month": month,
                    "division": d.name,
                    "division_name": d.division_name,
                    "leads": leads.get("total", 0),
                    "won_leads": leads.get("won", 0),
                    "conversion_rate": rate(leads.get("won", 0), leads.get("total", 0)),
                    "quotations": quotes.get("count", 0)
                    if not erp.get("error")
                    else None,
                    "quotation_value": quotes.get("value", 0.0)
                    if not erp.get("error")
                    else None,
                }
            )
    return out


# ---------- reports ----------


def col(key: str, label: str, kind: str = "int") -> dict:
    """A report column; kind is text, int, money, percent or hours."""
    return {"key": key, "label": label, "kind": kind}


def division_col() -> dict:
    return col("division_name", _("Division"), "text")


def country_col() -> dict:
    return col("country", _("Country"), "text")


def lead_report(data: dict) -> tuple[list, list]:
    return [
        division_col(),
        country_col(),
        col("leads", _("Leads")),
        col("open_leads", _("Open")),
        col("won_leads", _("Won or converted")),
        col("lost_leads", _("Lost")),
        col("conversion_rate", _("Conversion"), "percent"),
    ], [division_row(data, d) for d in data["divisions"]]


def customer_report(data: dict) -> tuple[list, list]:
    by_country = {}
    for row in (division_row(data, d) for d in data["divisions"]):
        country = by_country.setdefault(
            row["country"],
            {
                "country": row["country"],
                "divisions": [],
                "customers": 0,
                "projects": 0,
                "active_projects": 0,
            },
        )
        country["divisions"].append(row["division_name"])
        # a site that couldn't answer leaves the country's customers unknown
        if country["customers"] is not None:
            country["customers"] = (
                None
                if row["customers"] is None
                else country["customers"] + row["customers"]
            )
        country["projects"] += row["projects"]
        country["active_projects"] += row["active_projects"]
    for country in by_country.values():
        country["divisions"] = ", ".join(country["divisions"])
    return [
        country_col(),
        col("divisions", _("Divisions"), "text"),
        col("customers", _("Customers")),
        col("projects", _("Projects")),
        col("active_projects", _("Active projects")),
    ], sorted(by_country.values(), key=lambda r: r["country"] or "")


def quotation_report(data: dict) -> tuple[list, list]:
    return [
        division_col(),
        col("quotations", _("Quotations")),
        col("won_quotations", _("Ordered")),
        col("lost_quotations", _("Lost or expired")),
        col("quotation_value", _("Quoted value"), "money"),
        col("quotation_conversion", _("Conversion"), "percent"),
    ], [division_row(data, d) for d in data["divisions"]]


def sales_report(data: dict) -> tuple[list, list]:
    rows = [division_row(data, d) for d in data["divisions"]]
    for row in rows:
        won = row["won_quotations"]
        row["average_deal"] = (
            row["sales_value"] / won if won and row["sales_value"] is not None else None
        )
    return [
        division_col(),
        country_col(),
        col("won_leads", _("Won leads")),
        col("won_quotations", _("Ordered quotations")),
        col("sales_value", _("Sales value"), "money"),
        col("average_deal", _("Average deal"), "money"),
    ], rows


def project_report(data: dict) -> tuple[list, list]:
    return [
        division_col(),
        col("projects", _("Projects")),
        col("active_projects", _("Open")),
        col("on_hold_projects", _("On hold")),
        col("completed_projects", _("Completed")),
        col("done_tasks", _("Tasks done in the period")),
        col("overdue_tasks", _("Overdue tasks")),
    ], [division_row(data, d) for d in data["divisions"]]


def productivity_report(data: dict) -> tuple[list, list]:
    names = {d.name: d.division_name for d in data["divisions"]}
    rows = [{**r, "division_name": names[r["division"]]} for r in data["productivity"]]
    return [
        col("full_name", _("Employee"), "text"),
        division_col(),
        col("role", _("Role"), "text"),
        col("done", _("Tasks done")),
        col("open", _("Open tasks")),
        col("overdue", _("Overdue")),
        col("hours", _("Hours logged"), "hours"),
    ], rows


def monthly_report(data: dict) -> tuple[list, list]:
    by_month = {}
    for row in monthly(data):
        month = by_month.setdefault(
            row["month"],
            {
                "month": row["month"],
                "leads": 0,
                "won_leads": 0,
                "quotations": 0,
                "quotation_value": 0.0,
            },
        )
        month["leads"] += row["leads"]
        month["won_leads"] += row["won_leads"]
        month["quotations"] += row["quotations"] or 0
        month["quotation_value"] += row["quotation_value"] or 0
    for month in by_month.values():
        month["conversion_rate"] = rate(month["won_leads"], month["leads"])
    return [
        col("month", _("Month"), "text"),
        col("leads", _("Leads")),
        col("won_leads", _("Won leads")),
        col("conversion_rate", _("Conversion"), "percent"),
        col("quotations", _("Quotations")),
        col("quotation_value", _("Quoted value"), "money"),
    ], list(by_month.values())


def conversion_report(data: dict) -> tuple[list, list]:
    return [
        col("month", _("Month"), "text"),
        division_col(),
        col("leads", _("Leads")),
        col("won_leads", _("Won or converted")),
        col("conversion_rate", _("Conversion"), "percent"),
    ], monthly(data)


def pending_report(data: dict) -> tuple[list, list]:
    return [
        division_col(),
        col("pending_tasks", _("Open tasks")),
        col("overdue_tasks", _("Overdue tasks")),
        col("open_leads", _("Open leads")),
    ], [division_row(data, d) for d in data["divisions"]]


# key: (title, builder), in the page's order; titles are translated when shown
REPORTS = {
    "leads": ("Division-wise leads", lead_report),
    "customers": ("Country-wise customers", customer_report),
    "quotations": ("Division-wise quotations", quotation_report),
    "sales": ("Sales performance", sales_report),
    "projects": ("Project status", project_report),
    "productivity": ("Employee productivity", productivity_report),
    "monthly": ("Monthly business performance", monthly_report),
    "conversion": ("Lead conversion", conversion_report),
    "pending": ("Pending activities", pending_report),
}


def report_list() -> list[dict]:
    return [{"key": key, "title": _(title)} for key, (title, _build) in REPORTS.items()]


def report(
    key: str, division: str | None, from_date: str | None, to_date: str | None
) -> dict:
    if key not in REPORTS:
        frappe.throw(_("There's no report {0}.").format(key))
    title, build = REPORTS[key]
    data = collect(division, from_date, to_date)
    columns, rows = build(data)
    return {
        "title": _(title),
        "columns": columns,
        "rows": rows,
        "currency": data["currency"],
        "from_date": data["start"],
        "to_date": data["end"],
        "errors": [
            {"division": d.division_name, "error": data["erp"][d.name]["error"]}
            for d in data["divisions"]
            if data["erp"][d.name].get("error")
        ],
    }
