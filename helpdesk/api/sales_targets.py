"""Monthly sales targets (docs/sales-targets.md): a Sales Head sets them on Sales targets, and
each Presales Executive or Sales User reads their own on Sales targets."""

import frappe
from frappe import _
from frappe.utils import get_fullname, nowdate

from helpdesk.sales_targets import (
    DEFAULT_CRITERIA,
    VALUE_TYPES,
    SalesTargetsForbiddenError,
    criteria_of,
    has_own_targets,
    month_start,
    require_assigner,
    target_people,
)

TARGET = "HD Sales Target"
MAX_PEOPLE = 200


@frappe.whitelist()
def get_team(month: str) -> dict:
    """Sales Heads: who may be given targets, and what each has for the month."""
    require_assigner()
    start = month_start(month)
    people = target_people()
    targets = targets_for(start, [p["user"] for p in people])
    for person in people:
        person["target"] = targets.get(person["user"])
    return {
        "month": start.strftime("%Y-%m"),
        "currency": currency(),
        "value_types": list(VALUE_TYPES),
        "defaults": [
            {"criterion": name, "value_type": kind} for name, kind in DEFAULT_CRITERIA
        ],
        "people": people,
    }


@frappe.whitelist(methods=["POST"])
def assign_targets(month: str, employees, criteria) -> dict:
    """Sales Heads: gives every one of `employees` these criteria for the month, replacing
    what they had for it. All or none: one invalid row saves nobody's."""
    require_assigner()
    start = month_start(month)
    employees = list(dict.fromkeys(frappe.parse_json(employees) or []))
    criteria = frappe.parse_json(criteria) or []
    if not employees:
        frappe.throw(_("Pick at least one person."))
    if len(employees) > MAX_PEOPLE:
        frappe.throw(_("Assign to {0} people or fewer at a time.").format(MAX_PEOPLE))
    # everyone is checked before anyone is saved
    refused = [e for e in employees if not has_own_targets(e)]
    if refused:
        frappe.throw(
            _(
                "{0} can't be given targets: they need the Presales Executive or Sales User role and an enabled account."
            ).format(", ".join(frappe.bold(get_fullname(e)) for e in refused))
        )
    for employee in employees:
        save_target(employee, start, criteria)
    return {"month": start.strftime("%Y-%m"), "assigned": len(employees)}


@frappe.whitelist()
def get_my_targets(month: str | None = None) -> dict:
    """A Presales Executive or Sales User: their own targets for the month, and the months
    they have targets in."""
    user = frappe.session.user
    if not has_own_targets(user):
        frappe.throw(
            _("Sales targets is for Presales Executives and Sales Users."),
            SalesTargetsForbiddenError,
        )
    start = month_start(month or nowdate())
    months = frappe.qb.get_query(
        TARGET,
        fields=["month"],
        filters={"employee": user},
        order_by="month desc",
        limit=24,
    ).run(pluck=True)
    return {
        "month": start.strftime("%Y-%m"),
        "currency": currency(),
        "months": [m.strftime("%Y-%m") for m in months],
        "target": targets_for(start, [user]).get(user),
    }


def targets_for(start, users: list[str]) -> dict[str, dict]:
    """The month's targets of these people, by person."""
    if not users:
        return {}
    names = frappe.qb.get_query(
        TARGET,
        fields=["name"],
        filters={"month": start, "employee": ["in", users]},
    ).run(pluck=True)
    result = {}
    for name in names:
        # read past the doctype's permissions: the callers decided who may see whose
        target = frappe.get_doc(TARGET, name)
        result[target.employee] = {
            "criteria": criteria_of(target),
            "assigned_by": target.assigned_by,
            "assigned_by_name": get_fullname(target.assigned_by),
            "modified": target.modified,
        }
    return result


def save_target(employee: str, start, criteria: list[dict]):
    name = f"{employee}::{start.strftime('%Y-%m')}"
    if frappe.db.exists(TARGET, name):
        target = frappe.get_doc(TARGET, name)
        target.set("criteria", [])
    else:
        target = frappe.new_doc(TARGET)
        target.employee = employee
        target.month = start
    for row in criteria:
        kind = row.get("value_type")
        value = row.get("target")
        target.append(
            "criteria",
            {
                "criterion": row.get("criterion"),
                "value_type": kind,
                "target_text": value if kind == "Text" else None,
                "target_value": None if kind == "Text" else value,
            },
        )
    target.save()


def currency() -> str:
    """The reporting currency of the CRM dashboards, else the site's, else INR."""
    return (
        frappe.db.get_single_value("HD CRM Settings", "dashboard_currency")
        or frappe.db.get_default("currency")
        or "INR"
    )
