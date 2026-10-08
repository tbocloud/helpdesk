"""Support hours per customer: the customer page's Support hours tab and the
managers' Support hours page (docs/support-contracts.md).

Agent Managers, System Managers and project managers manage contracts and see
every customer; other agents see the support hours of customers whose projects
they are on, without the hours per person (timesheets are private to their
owner and the people who run the project).
"""

import csv
import io

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from helpdesk.support_contracts import (
    ACTIVE,
    contract_usage,
    current_contracts,
    get_contracts,
    period_label,
    shown_period,
    usage_breakdown,
)
from helpdesk.tasky.permissions import is_project_manager
from helpdesk.utils import agent_only

# what the Support hours page filters on
STAGES = ("warning", "over")
CONTRACT_TYPES = ("AMC", "Support block", "Retainer")


def can_manage_contracts(user: str | None = None) -> bool:
    """Agent Managers, System Managers and project managers."""
    return is_project_manager(user)


def check_customer_access(customer: str):
    if can_manage_contracts():
        return
    on_a_project = frappe.get_list(
        "Project", filters={"customer": customer}, pluck="name", limit_page_length=1
    )
    if not on_a_project:
        frappe.throw(
            _(
                "Only managers and people on this customer's projects can see its support hours."
            ),
            frappe.PermissionError,
        )


def check_manager():
    if not can_manage_contracts():
        frappe.throw(
            _(
                "Only Agent Managers and project managers can see every customer's support hours."
            ),
            frappe.PermissionError,
        )


@frappe.whitelist()
@agent_only
def get_customer_support_hours(customer: str, contract: str | None = None) -> dict:
    """A customer's contracts, and for one of them (today's, unless `contract`
    names another) its periods so far and the shown period's hours by project,
    ticket and person."""
    customer = str(customer)
    check_customer_access(customer)
    manager = can_manage_contracts()
    today = getdate(nowdate())
    contracts = get_contracts(customer=customer)
    selected = pick_contract(contracts, contract, today)
    periods = contract_usage([selected], today)[selected.name] if selected else []
    period = shown_period(periods)
    return {
        "can_manage": manager,
        "contracts": [contract_summary(c) for c in contracts],
        "contract": selected,
        "period": period,
        "periods": list(reversed(periods)),
        "breakdown": usage_breakdown(customer, period["start"], period["end"], manager)
        if period
        else None,
    }


def pick_contract(contracts: list, name: str | None, today):
    if name:
        return next((c for c in contracts if c.name == name), None)
    covering = [
        c
        for c in contracts
        if c.status == ACTIVE and getdate(c.start_date) <= today <= getdate(c.end_date)
    ]
    # else the next one to start, else the latest
    upcoming = [
        c for c in contracts if c.status == ACTIVE and getdate(c.start_date) > today
    ]
    return (
        covering or sorted(upcoming, key=lambda c: c.start_date) or contracts or [None]
    )[0]


def contract_summary(contract) -> dict:
    return {
        key: contract[key]
        for key in (
            "name",
            "contract_name",
            "contract_type",
            "status",
            "start_date",
            "end_date",
        )
    }


@frappe.whitelist()
@agent_only
def get_support_hours(
    contract_type: str | None = None, stage: str | None = None
) -> dict:
    """Every contract running today with its current period, most used first."""
    check_manager()
    # the counts follow the type filter, so the stage tiles add up to what's listed
    rows = filter_rows(support_hours_rows(), contract_type, None)
    return {
        "rows": filter_rows(rows, None, stage),
        "total": len(rows),
        "counts": {s: sum(1 for r in rows if r["stage"] == s) for s in STAGES},
    }


@frappe.whitelist()
@agent_only
def download_support_hours(contract_type: str | None = None, stage: str | None = None):
    """The Support hours page as a CSV file."""
    check_manager()
    rows = filter_rows(support_hours_rows(), contract_type, stage)
    frappe.response["filename"] = f"support-hours-{nowdate()}.csv"
    frappe.response["filecontent"] = to_csv(rows)
    frappe.response["type"] = "download"


def support_hours_rows() -> list[dict]:
    today = getdate(nowdate())
    contracts = current_contracts(today)
    usage = contract_usage(contracts, today)
    rows = []
    for contract in contracts:
        period = shown_period(usage[contract.name])
        if period:
            rows.append(
                {
                    **contract_summary(contract),
                    "customer": contract.customer,
                    "billing_period": contract.billing_period,
                    "alert_threshold": contract.alert_threshold,
                    "rate_per_extra_hour": contract.rate_per_extra_hour,
                    "currency": contract.currency,
                    **period,
                }
            )
    return sorted(rows, key=lambda r: (-r["percent"], r["customer"].lower()))


def filter_rows(rows: list[dict], contract_type: str | None, stage: str | None):
    if contract_type and contract_type in CONTRACT_TYPES:
        rows = [r for r in rows if r["contract_type"] == contract_type]
    if stage and stage in STAGES:
        rows = [r for r in rows if r["stage"] == stage]
    return rows


CSV_COLUMNS = (
    ("customer", "Customer"),
    ("contract_name", "Contract"),
    ("contract_type", "Type"),
    ("billing_period", "Billing period"),
    ("period", "Current period"),
    ("allowance", "Hours included"),
    ("carried_in", "Rolled over"),
    ("used", "Hours used"),
    ("remaining", "Hours left"),
    ("extra_hours", "Extra hours"),
    ("percent", "% used"),
    ("rate_per_extra_hour", "Rate per extra hour"),
    ("currency", "Currency"),
)


def to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([_(label) for _key, label in CSV_COLUMNS])
    for row in rows:
        values = {
            **row,
            "period": period_label(row),
            "remaining": max(row["remaining"], 0),
            "extra_hours": max(-row["remaining"], 0),
            "rate_per_extra_hour": row["rate_per_extra_hour"] or "",
            "currency": row["currency"] or "",
        }
        writer.writerow([values[key] for key, _label in CSV_COLUMNS])
    return out.getvalue()
