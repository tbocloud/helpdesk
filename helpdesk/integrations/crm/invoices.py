"""A customer's billable time → a draft Sales Invoice in ERPNext on the CRM site.

The hub has no ERPNext: the invoice is created over REST (CRMClient) on the CRM site,
always as a draft, with the company, item, taxes and rate from Settings → CRM →
Invoicing. The time logs it settles are marked in the same transaction, after the CRM
site accepted the invoice, so no time log is billed twice. See
docs/timesheet-invoicing.md.

Which time counts is the support hours rule (helpdesk.support_contracts.billable_logs):
billable time logs of timesheets that aren't cancelled, for the customer's projects
and ticket tasks, by the day the work was done.

With a support contract and "extra hours" (the default), the contract's included hours
for the period cover the earliest work first, and only what goes beyond them is billed,
at the contract's rate per extra hour. Every time log of the period is marked, the
covered ones too, so later time in the same period is billed in full.
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate

from helpdesk.integrations.crm.client import CRMClient, CRMError
from helpdesk.integrations.crm.customers import key
from helpdesk.support_contracts import (
    billable_logs,
    contract_periods,
    contract_usage,
    get_contracts,
    in_dates,
    names_of,
    period_label,
)

EXTRA = "Extra hours"
ALL = "All billable hours"
MODES = {"extra": EXTRA, "all": ALL}
LINKED = "Linked"
UNLINKED = "Unlinked"
CANCELLED_CONTRACT = "Cancelled"
CANCELLED_INVOICE = 2
STATUS_CACHE_SECONDS = 300
MONTHS_OFFERED = 6
CONTRACT_PERIODS_OFFERED = 12
# what the invoice lists show of an HD Customer Invoice
INVOICE_FIELDS = (
    "name",
    "customer",
    "invoice",
    "invoice_url",
    "status",
    "posting_date",
    "currency",
    "amount",
    "period_start",
    "period_end",
    "mode",
    "hours_billed",
    "hours_covered",
)


class CustomerNotInERPNext(frappe.ValidationError):
    """The HD Customer has no ERPNext Customer of the same name on the CRM site."""


# --- settings ---


def invoicing_settings():
    settings = frappe.get_single("HD CRM Settings")
    if not (
        settings.invoice_company
        and settings.invoice_item
        and flt(settings.invoice_hourly_rate) > 0
        and settings.invoice_currency
    ):
        frappe.throw(
            _(
                "Set up invoicing first: Settings → CRM → Invoicing (company, item and hourly rate)."
            )
        )
    return settings


# --- periods ---


def period_choices(customer: str, today) -> list[dict]:
    """The customer's contract periods so far (newest first), then recent calendar months."""
    choices = []
    for contract in get_contracts(customer=customer):
        if contract.status == CANCELLED_CONTRACT:
            continue
        for first, last in contract_periods(
            contract.start_date, contract.end_date, contract.billing_period
        ):
            if first <= today:
                choices.append(
                    {
                        "start": str(first),
                        "end": str(last),
                        "contract": contract.name,
                        "contract_name": contract.contract_name,
                    }
                )
    choices.sort(key=lambda c: c["start"], reverse=True)
    choices = choices[:CONTRACT_PERIODS_OFFERED]
    for back in range(MONTHS_OFFERED):
        month = getdate(add_months(get_first_day(today), -back))
        choices.append(
            {
                "start": str(month),
                "end": str(get_last_day(month)),
                "contract": None,
                "contract_name": None,
            }
        )
    return choices


def default_period(choices: list[dict], today) -> dict:
    """The latest contract period that has ended, else today's; last month without one."""
    contract_choices = [c for c in choices if c["contract"]]
    ended = [c for c in contract_choices if getdate(c["end"]) < today]
    if ended or contract_choices:
        return (ended or contract_choices)[0]
    return next(c for c in choices if getdate(c["end"]) < today)


def matching_contract(customer: str, start, end, today):
    """(contract, its period's usage) when [start, end] is exactly one of the customer's
    contract periods, else (None, None); and whether any contract overlaps the dates."""
    contracts = [
        c
        for c in get_contracts(customer=customer)
        if c.status != CANCELLED_CONTRACT
        and getdate(c.start_date) <= end
        and getdate(c.end_date) >= start
    ]
    for contract in contracts:
        for period in contract_usage([contract], today)[contract.name]:
            if period["start"] == str(start) and period["end"] == str(end):
                return contract, period, True
    return None, None, bool(contracts)


# --- time logs ---


def unbilled_logs(customer: str, start, end) -> list:
    """The customer's billable time logs in the dates that no invoice settles yet,
    oldest first."""
    query, x = billable_logs()
    detail = x["detail"]
    return (
        in_dates(query, detail, start, end)
        .select(
            detail.name,
            detail.hours,
            detail.from_time,
            x["project"].as_("project"),
            detail.task,
            x["task"].subject.as_("task_subject"),
        )
        .where(x["customer"] == customer)
        .where(Coalesce(detail.custom_billed_invoice, "") == "")
        .where(detail.hours > 0)
        .orderby(detail.from_time)
        .orderby(detail.name)
        .run(as_dict=True)
    )


def covered_before(contract: str, start) -> float:
    """Hours of a contract period that earlier invoices already counted as included."""
    Invoice = frappe.qb.DocType("HD Customer Invoice")
    total = (
        frappe.qb.from_(Invoice)
        .select(Sum(Invoice.hours_covered))
        .where(Invoice.contract == contract)
        .where(Invoice.period_start == getdate(start))
        .where(Invoice.status == LINKED)
        .run()
    )
    return flt(total[0][0]) if total else 0.0


def split_covered(logs: list, free_hours: float) -> list[tuple]:
    """(log, hours billed) for each log: the included hours cover the earliest work first."""
    billed = []
    for log in logs:
        covered = min(flt(log.hours), free_hours)
        free_hours -= covered
        billed.append((log, flt(log.hours) - covered))
    return billed


def invoice_lines(billed: list[tuple], by_task: bool, rate: float, label: str):
    """One line per project (or project and task), most hours first."""
    projects = names_of("Project", "project_name", {log.project for log, _h in billed})
    groups: dict[tuple, dict] = {}
    for log, hours in billed:
        if hours <= 0:
            continue
        group_key = (log.project or "", (log.task or "") if by_task else "")
        if group_key not in groups:
            title = projects.get(log.project) if log.project else None
            title = title or _("Support work outside projects")
            if by_task and log.task:
                title = f"{title} · {log.task_subject or log.task}"
            groups[group_key] = {
                "project": log.project or None,
                "task": (log.task or None) if by_task else None,
                "label": title,
                "hours": 0.0,
            }
        groups[group_key]["hours"] += hours
    lines = []
    for line in groups.values():
        line["hours"] = round(line["hours"], 2)
        if line["hours"] <= 0:
            continue
        line["rate"] = rate
        line["amount"] = round(line["hours"] * rate, 2)
        line["description"] = _("{0}: support hours, {1}").format(line["label"], label)
        lines.append(line)
    lines.sort(key=lambda r: (-r["hours"], r["label"]))
    return lines


# --- preview ---


def build_preview(
    customer: str, start, end, mode: str, by_task: bool, settings
) -> tuple[dict, list[str]]:
    """The invoice the dates would make, and the names of the time logs it settles."""
    today = getdate(nowdate())
    start, end = getdate(start), getdate(end)
    if end < start:
        frappe.throw(_("The period ends before it starts."))
    contract, period, has_contract = matching_contract(customer, start, end, today)
    if mode == EXTRA and has_contract and not contract:
        frappe.throw(
            _(
                "To bill only the hours beyond the contract, pick one of the contract's periods. Or bill all billable hours."
            )
        )
    logs = unbilled_logs(customer, start, end)
    included_left = 0.0
    if mode == EXTRA and contract:
        included_left = max(
            period["allowance"] - covered_before(contract.name, start), 0
        )
    billed = split_covered(logs, included_left)
    rate, currency, rate_from = pick_rate(contract, settings)
    label = period_label({"start": start, "end": end})
    lines = invoice_lines(billed, by_task, rate, label)
    hours_logged = round(sum(flt(log.hours) for log in logs), 2)
    hours_covered = round(sum(flt(log.hours) - hours for log, hours in billed), 2)
    hours_billed = round(sum(line["hours"] for line in lines), 2)
    preview = {
        "customer": customer,
        "start": str(start),
        "end": str(end),
        "period_label": label,
        "mode": "extra" if mode == EXTRA and contract else "all",
        "contract": {
            "name": contract.name,
            "contract_name": contract.contract_name,
            "allowance": period["allowance"],
            "included_left": round(included_left, 2),
        }
        if contract
        else None,
        "rate": rate,
        "rate_from": rate_from,
        "currency": currency,
        "hours_logged": hours_logged,
        "hours_covered": hours_covered,
        "hours_billed": hours_billed,
        "amount": round(sum(line["amount"] for line in lines), 2),
        "lines": lines,
    }
    return preview, [log.name for log in logs]


def pick_rate(contract, settings) -> tuple[float, str, str]:
    """The contract's rate per extra hour when it has one, else the default rate."""
    if contract and flt(contract.rate_per_extra_hour) > 0:
        return (
            flt(contract.rate_per_extra_hour),
            contract.currency or settings.invoice_currency,
            "contract",
        )
    return flt(settings.invoice_hourly_rate), settings.invoice_currency, "default"


def get_preview(
    customer: str, start=None, end=None, mode: str = "extra", by_task: bool = False
) -> dict:
    settings = invoicing_settings()
    today = getdate(nowdate())
    choices = period_choices(customer, today)
    if not (start and end):
        chosen = default_period(choices, today)
        start, end = chosen["start"], chosen["end"]
    preview, _logs = build_preview(
        customer, start, end, MODES.get(mode, EXTRA), by_task, settings
    )
    return {**preview, "periods": choices}


# --- create ---


def create_draft(
    customer: str,
    start,
    end,
    mode: str = "extra",
    by_task: bool = False,
    expected_hours: float | None = None,
) -> dict:
    """Create the draft in ERPNext, then record it and mark its time logs.

    The time logs are locked first, so a second request for the same time waits and
    then finds them billed. Nothing is marked unless the CRM site created the invoice;
    if marking fails after that, the new draft is deleted again.
    """
    settings = invoicing_settings()
    mode = MODES.get(mode, EXTRA)
    preview, log_names = build_preview(customer, start, end, mode, by_task, settings)
    if not preview["lines"]:
        frappe.throw(_("There's no unbilled billable time to invoice in this period."))
    if expected_hours is not None and flt(expected_hours, 2) != preview["hours_billed"]:
        frappe.throw(
            _(
                "The hours changed since the preview ({0} h now). Check the preview again, then create the invoice."
            ).format(preview["hours_billed"])
        )
    lock_logs(log_names)
    client = CRMClient.from_settings()
    erp_customer = find_erp_customer(client, customer)
    created = client.create_sales_invoice(
        sales_invoice(client, settings, erp_customer, preview)
    )
    try:
        record = record_invoice(settings, preview, created["name"], mode)
        mark_logs(log_names, record.name)
    except Exception:
        try:
            client.delete_sales_invoice(created["name"])
        except CRMError:
            frappe.log_error(
                title=f"Couldn't delete draft invoice {created['name']}",
                message=frappe.get_traceback(),
            )
        raise
    return invoice_row(record)


def lock_logs(names: list[str]):
    """Lock the time logs; stop if another invoice took any of them meanwhile."""
    Detail = frappe.qb.DocType("Timesheet Detail")
    rows = (
        frappe.qb.from_(Detail)
        .select(Detail.name, Detail.custom_billed_invoice)
        .where(Detail.name.isin(names))
        .for_update()
        .run(as_dict=True)
    )
    if len(rows) != len(names) or any(r.custom_billed_invoice for r in rows):
        frappe.throw(
            _(
                "Some of this time was just invoiced or changed. Check the preview again."
            )
        )


def find_erp_customer(client, customer: str) -> str:
    """The ERPNext Customer on the CRM site with the HD Customer's name (as the customer sync matches)."""
    wanted = key(customer)
    for row in client.customers():
        if wanted in (key(row.get("customer_name")), key(row.get("name"))):
            return row["name"]
    frappe.throw(
        _(
            "{0} isn't a customer in ERPNext on the CRM site. Create the customer there with the same name (or convert its CRM organization), then create the invoice again."
        ).format(customer),
        CustomerNotInERPNext,
    )


def sales_invoice(client, settings, erp_customer: str, preview: dict) -> dict:
    today = nowdate()
    item = {
        "item_code": settings.invoice_item,
        "income_account": settings.invoice_income_account or None,
        "cost_center": settings.invoice_cost_center or None,
    }
    invoice = {
        "customer": erp_customer,
        "company": settings.invoice_company,
        "posting_date": today,
        "due_date": today,
        "currency": preview["currency"],
        "remarks": _("Support hours for {0}, {1}. Created from TBO Support.").format(
            preview["customer"], preview["period_label"]
        ),
        "items": [
            {
                **{k: v for k, v in item.items() if v},
                "description": line["description"],
                "qty": line["hours"],
                "rate": line["rate"],
            }
            for line in preview["lines"]
        ],
    }
    if settings.invoice_cost_center:
        invoice["cost_center"] = settings.invoice_cost_center
    if settings.invoice_taxes_template:
        invoice["taxes_and_charges"] = settings.invoice_taxes_template
        invoice["taxes"] = client.template_taxes(settings.invoice_taxes_template)
    return invoice


def record_invoice(settings, preview: dict, invoice: str, mode: str):
    contract = preview["contract"]
    return frappe.get_doc(
        {
            "doctype": "HD Customer Invoice",
            "customer": preview["customer"],
            "invoice": invoice,
            "invoice_url": f"{settings.site_url.rstrip('/')}/app/sales-invoice/{quote(invoice)}",
            "status": LINKED,
            "company": settings.invoice_company,
            "posting_date": nowdate(),
            "currency": preview["currency"],
            "amount": preview["amount"],
            "period_start": preview["start"],
            "period_end": preview["end"],
            "mode": EXTRA if preview["mode"] == "extra" else ALL,
            "contract": contract["name"] if contract else None,
            "hours_logged": preview["hours_logged"],
            "hours_covered": preview["hours_covered"],
            "hours_billed": preview["hours_billed"],
        }
    ).insert(ignore_permissions=True)


def mark_logs(names: list[str], record: str | None):
    """Point the time logs at the invoice record, or free them with None."""
    Detail = frappe.qb.DocType("Timesheet Detail")
    (
        frappe.qb.update(Detail)
        .set(Detail.custom_billed_invoice, record)
        .set(Detail.custom_billed_on, nowdate() if record else None)
        .where(Detail.name.isin(names))
        .run()
    )


# --- list, status and unlink ---


def invoice_row(record) -> dict:
    return {field: record.get(field) for field in INVOICE_FIELDS}


def list_invoices(customer: str | None, limit: int) -> dict:
    filters = {"customer": customer} if customer else {}
    rows = frappe.qb.get_query(
        "HD Customer Invoice",
        fields=list(INVOICE_FIELDS),
        filters=filters,
        order_by="creation desc",
        limit=limit + 1,
    ).run(as_dict=True)
    return {"rows": rows[:limit], "has_more": len(rows) > limit}


def remote_statuses(names: list[str]) -> dict[str, str]:
    """{hub record: the invoice's status in ERPNext}: Draft, Cancelled, Paid, Unpaid,
    Overdue…, or "Not found" when it was deleted there. Cached for a few minutes."""
    Invoice = frappe.qb.DocType("HD Customer Invoice")
    records = (
        frappe.qb.from_(Invoice)
        .select(Invoice.name, Invoice.invoice)
        .where(Invoice.name.isin(names or [""]))
        .where(Invoice.status == LINKED)
        .run(as_dict=True)
    )
    statuses, missing = {}, []
    for record in records:
        cached = frappe.cache.get_value(status_key(record.invoice), expires=True)
        if cached:
            statuses[record.name] = cached
        else:
            missing.append(record)
    if missing:
        found = {
            row.get("name"): erp_status(row)
            for row in CRMClient.from_settings().sales_invoices(
                [r.invoice for r in missing]
            )
        }
        for record in missing:
            status = found.get(record.invoice) or "Not found"
            frappe.cache.set_value(
                status_key(record.invoice), status, expires_in_sec=STATUS_CACHE_SECONDS
            )
            statuses[record.name] = status
    return statuses


def erp_status(row: dict) -> str:
    if row.get("docstatus") == 0:
        return "Draft"
    if row.get("docstatus") == CANCELLED_INVOICE:
        return "Cancelled"
    return row.get("status") or "Submitted"


def status_key(invoice: str) -> str:
    return f"hd_customer_invoice_status:{invoice}"


def unlink(name: str) -> dict:
    """Free the time logs of an invoice that was deleted or cancelled in ERPNext."""
    record = frappe.get_doc("HD Customer Invoice", name)
    if record.status == UNLINKED:
        frappe.throw(_("This invoice is already unlinked."))
    remote = CRMClient.from_settings().get_doc("Sales Invoice", record.invoice)
    if remote and remote.get("docstatus") != CANCELLED_INVOICE:
        frappe.throw(
            _(
                "{0} is still in ERPNext ({1}). Delete or cancel it there first, then unlink it."
            ).format(record.invoice, erp_status(remote))
        )
    Detail = frappe.qb.DocType("Timesheet Detail")
    names = (
        frappe.qb.from_(Detail)
        .select(Detail.name)
        .where(Detail.custom_billed_invoice == record.name)
        .run(pluck=True)
    )
    if names:
        mark_logs(names, None)
    record.status = UNLINKED
    record.save(ignore_permissions=True)
    frappe.cache.delete_value(status_key(record.invoice))
    return invoice_row(record)
