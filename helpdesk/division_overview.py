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


# ---------- lead status (the Lead status page) ----------

# the order the status groups are shown in; a status with no group is "Other"
LEAD_GROUPS = ("Open", "Won", "Converted", "Lost", "Other")


def lead_group(category: str | None) -> str:
    return category if category in LEAD_GROUPS else "Other"


def lead_status_rows(meta: list[dict], start, end) -> list[dict]:
    """The divisions' copied leads of the period, counted per division, status, salesperson,
    lead source and month: few enough rows to filter here, so the filters' choices can be
    every value of the period, not only those left after filtering."""
    sources = {d.crm_source: d.name for d in meta if d.crm_source}
    if not sources:
        return []
    lead = frappe.qb.DocType("HD CRM Report Lead")
    rows = (
        frappe.qb.from_(lead)
        .select(
            lead.source,
            lead.category,
            lead.status,
            lead.employee,
            lead.lead_source,
            lead.created_month,
            Count("*").as_("count"),
            Sum(lead.expected_revenue).as_("expected"),
            Sum(lead.won_value).as_("won_value"),
        )
        .where(
            lead.source.isin(list(sources))
            & (lead.created_on >= start)
            & (lead.created_on <= end)
        )
        .groupby(
            lead.source,
            lead.category,
            lead.status,
            lead.employee,
            lead.lead_source,
            lead.created_month,
        )
        .run(as_dict=True)
    )
    for row in rows:
        row.division = sources[row.source]
        row.group = lead_group(row.category)
        row.status = row.status or _("No status")
    return rows


def lead_counts() -> dict:
    return {"total": 0, **{g.lower(): 0 for g in LEAD_GROUPS}}


def add_lead(counts: dict, row: dict):
    counts["total"] += row["count"]
    counts[row["group"].lower()] += row["count"]


def with_conversion(counts: dict) -> dict:
    counts["conversion_rate"] = rate(counts["won"] + counts["converted"], counts["total"])
    return counts


def lead_status(
    division: str | None,
    from_date: str | None,
    to_date: str | None,
    group: str | None = None,
    status: str | None = None,
    employee: str | None = None,
    lead_source: str | None = None,
) -> dict:
    """Every lead status of the divisions' leads created in the period, per division, with
    the salespeople and lead sources behind them (docs/divisions.md, "Lead status")."""
    divisions = scope(division)
    start, end = period(from_date, to_date)
    meta = divisions_meta(divisions)
    all_rows = lead_status_rows(meta, start, end)
    rows = [
        r
        for r in all_rows
        if (not group or r.group == group)
        and (not status or r.status == status)
        and (not employee or (r.employee or "") == employee)
        and (not lead_source or (r.lead_source or "") == lead_source)
    ]

    totals = lead_counts()
    expected = won_value = 0.0
    by_division = {d.name: lead_counts() for d in meta}
    statuses: dict[str, dict] = {}
    people: dict[tuple, dict] = {}
    lead_sources: dict[str, dict] = {}
    by_month = {m: lead_counts() for m in months(start, end)}
    for r in rows:
        add_lead(totals, r)
        add_lead(by_division[r.division], r)
        if r.group == "Open":
            expected += flt(r.expected)
        won_value += flt(r.won_value)
        entry = statuses.setdefault(
            r.status, {"status": r.status, "group": r.group, "total": 0, "divisions": {}}
        )
        entry["total"] += r["count"]
        entry["divisions"][r.division] = entry["divisions"].get(r.division, 0) + r["count"]
        add_lead(
            people.setdefault(
                (r.division, r.employee or ""),
                {"division": r.division, "employee": r.employee or "", **lead_counts()},
            ),
            r,
        )
        add_lead(
            lead_sources.setdefault(
                r.lead_source or "", {"lead_source": r.lead_source or "", **lead_counts()}
            ),
            r,
        )
        if r.created_month in by_month:
            add_lead(by_month[r.created_month], r)

    names = {d.name: d.division_name for d in meta}
    employees = {r.employee for r in all_rows if r.employee}
    full_names = dict(
        frappe.get_all(
            "User",
            filters={"name": ("in", list(employees))},
            fields=["name", "full_name"],
            as_list=True,
        )
    ) if employees else {}
    order = {g: i for i, g in enumerate(LEAD_GROUPS)}
    for person in people.values():
        person["division_name"] = names[person["division"]]
        person["name"] = full_names.get(person["employee"]) or person["employee"]
        with_conversion(person)
    for source in lead_sources.values():
        with_conversion(source)

    return {
        "options": division_options(),
        "currency": reporting_currency(),
        "from_date": start,
        "to_date": end,
        "groups": list(LEAD_GROUPS),
        "kpis": {
            **with_conversion(totals),
            "open_value": expected,
            "won_value": won_value,
        },
        "divisions": [
            {
                "name": d.name,
                "division_name": d.division_name,
                "country": d.country,
                "has_site": bool(d.crm_source),
                "last_synced_on": frappe.db.get_value(
                    "HD CRM Source", d.crm_source, "last_synced_on"
                )
                if d.crm_source
                else None,
                **with_conversion(by_division[d.name]),
            }
            for d in meta
        ],
        "statuses": sorted(
            statuses.values(), key=lambda s: (order[s["group"]], -s["total"], s["status"])
        ),
        "people": sorted(people.values(), key=lambda p: (-p["total"], p["name"])),
        "lead_sources": sorted(
            lead_sources.values(), key=lambda s: (-s["total"], s["lead_source"])
        ),
        "monthly": [{"month": m, **c} for m, c in by_month.items()],
        # every value of the period, so a filter never hides its own other choices
        "filters": {
            "statuses": sorted({r.status for r in all_rows}),
            "employees": sorted(
                (
                    {"value": e, "label": full_names.get(e) or e}
                    for e in employees
                ),
                key=lambda e: e["label"].lower(),
            ),
            "lead_sources": sorted({r.lead_source for r in all_rows if r.lead_source}),
        },
    }


# ---------- the divisions home and a division's dashboard ----------

RUN_ROLES = ("Group Admin", "Division Admin")
LIVE_PROJECTS = ("Open", "On hold")


def admins_of(divisions: list[str]) -> dict[str, list[str]]:
    """{division: names of the people who run it (Group and Division Admins)}"""
    member = frappe.qb.DocType(MEMBER)
    out = defaultdict(list)
    for division, user in (
        frappe.qb.from_(member)
        .select(member.parent, member.user)
        .where(
            (member.parenttype == DIVISION)
            & member.parent.isin(divisions)
            & member.role.isin(RUN_ROLES)
        )
        .orderby(member.idx)
        .run()
    ):
        out[division].append(frappe.utils.get_fullname(user))
    return out


def site_health(meta: list[dict]) -> dict[str, dict]:
    """{source: its name, last sync and how it went}"""
    sources = [d.crm_source for d in meta if d.crm_source]
    if not sources:
        return {}
    return {
        s.name: s
        for s in frappe.get_all(
            "HD CRM Source",
            filters={"name": ("in", sources)},
            fields=["name", "enabled", "last_synced_on", "last_sync_status"],
        )
    }


def division_cards(from_date: str | None, to_date: str | None) -> dict:
    """One card per division the person may see: who runs it, its people, its ERP site's
    sync, its leads, projects and open work (the Divisions home)."""
    start, end = period(from_date, to_date)
    return {
        "from_date": start,
        "to_date": end,
        "currency": reporting_currency(),
        "cards": cards_for(scope(None), start, end),
    }


def cards_for(divisions: list[str], start, end) -> list[dict]:
    meta = divisions_meta(divisions)
    figures = {
        "leads": lead_figures(meta, start, end),
        "projects": project_counts(divisions),
        "tasks": task_counts(divisions, start, end),
        "people": people_counts(divisions),
        "admins": admins_of(divisions),
        "sites": site_health(meta),
    }
    return [division_card(d, figures) for d in meta]


def division_card(d: dict, figures: dict) -> dict:
    leads = figures["leads"][d.name]
    projects = figures["projects"].get(d.name, {})
    tasks = figures["tasks"][d.name]
    site = figures["sites"].get(d.crm_source) if d.crm_source else None
    return {
        "name": d.name,
        "division_name": d.division_name,
        "country": d.country,
        "currency": d.currency,
        "admins": figures["admins"].get(d.name, []),
        "people": figures["people"].get(d.name, 0),
        "site": {
            "name": site.name,
            "enabled": site.enabled,
            "last_synced_on": site.last_synced_on,
            "last_sync_status": site.last_sync_status,
        }
        if site
        else None,
        "leads": leads["total"],
        "open_leads": leads["open"],
        "won_leads": leads["won"],
        "lost_leads": leads["lost"],
        "conversion_rate": rate(leads["won"], leads["total"]),
        "won_value": leads["won_value"],
        "projects": sum(projects.values()),
        "active_projects": projects.get("Open", 0),
        "on_hold_projects": projects.get("On hold", 0),
        "pending_tasks": tasks["pending"],
        "overdue_tasks": tasks["overdue"],
        "done_tasks": tasks["done"],
    }


def division_dashboard(
    division: str, from_date: str | None, to_date: str | None
) -> dict:
    """One division's own dashboard: its card, profile, people with their work and leads,
    teams, departments, live projects and lead statuses."""
    if not division:
        frappe.throw(_("Pick a division."))
    scope(division)
    start, end = period(from_date, to_date)
    card = cards_for([division], start, end)[0]
    leads = lead_status(division, from_date, to_date)
    lead_people = {p["employee"]: p for p in leads["people"]}
    people = []
    for row in productivity([division], start, end):
        mine = lead_people.get(row["user"], {})
        people.append(
            {
                **row,
                "leads": mine.get("total", 0),
                "won_leads": mine.get("won", 0) + mine.get("converted", 0),
            }
        )
    profile = frappe.db.get_value(
        DIVISION,
        division,
        ["status", "workspace_url", "time_zone", "language", "crm_source"],
        as_dict=True,
    )
    return {
        "from_date": start,
        "to_date": end,
        "currency": reporting_currency(),
        "options": division_options(),
        "card": card,
        "profile": profile,
        "people": sorted(
            people, key=lambda p: (-p["leads"], -p["done"], p["full_name"])
        ),
        "teams": frappe.get_all(
            "HD Team", filters={"division": division}, pluck="name", order_by="name"
        ),
        "departments": frappe.get_all(
            "HD Department",
            filters={"division": division},
            pluck="department_name",
            order_by="department_name",
        ),
        "projects": frappe.get_all(
            "Project",
            filters={"division": division, "status": ("in", LIVE_PROJECTS)},
            fields=[
                "name",
                "project_name",
                "status",
                "project_lead",
                "expected_end_date",
            ],
            order_by="expected_end_date asc",
            limit=50,
        ),
        "lead_groups": {g: leads["kpis"][g.lower()] for g in LEAD_GROUPS},
        "statuses": leads["statuses"],
    }
