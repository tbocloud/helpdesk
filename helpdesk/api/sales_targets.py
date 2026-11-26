"""Monthly sales targets (docs/sales-targets.md): a Sales Head sets them on Sales targets, and
each Presales Executive or Sales User reads their own on Sales targets."""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, get_fullname, getdate, nowdate

from helpdesk.api.leads import READ_TTL, cached_read
from helpdesk.divisions import DIVISION, active_division, is_division_sales_user
from helpdesk.integrations.crm.leads import LeadsError, call
from helpdesk.sales_targets import (
    MEASURES,
    VALUE_TYPES,
    SalesTargetsForbiddenError,
    asked_heads,
    criteria_of,
    default_criteria,
    has_own_targets,
    measured,
    month_start,
    remind_sales_heads,
    require_assigner,
    target_givers,
    target_people,
    targets_division,
)

TARGET = "HD Sales Target"
MAX_PEOPLE = 200


@frappe.whitelist()
def get_team(month: str) -> dict:
    """Sales Heads and Division Admins: who they may give targets to, and what each has
    for the month."""
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
        "defaults": default_criteria(),
        # which measures fit each value type; the page holds their words and formulas
        "measures": {
            kind: [m for m, of in MEASURES.items() if of == kind]
            for kind in VALUE_TYPES
        },
        "people": people,
    }


@frappe.whitelist(methods=["POST"])
def assign_targets(month: str, employees, criteria) -> dict:
    """Sales Heads and Division Admins: gives every one of `employees` these criteria for
    the month, replacing what they had for it. All or none: one invalid row saves nobody's."""
    require_assigner()
    start = month_start(month)
    employees = list(dict.fromkeys(frappe.parse_json(employees) or []))
    criteria = frappe.parse_json(criteria) or []
    if not employees:
        frappe.throw(_("Pick at least one person."))
    if len(employees) > MAX_PEOPLE:
        frappe.throw(_("Assign to {0} people or fewer at a time.").format(MAX_PEOPLE))
    # everyone is checked before anyone is saved
    allowed = {p["user"] for p in target_people()}
    refused = [e for e in employees if e not in allowed]
    if refused:
        frappe.throw(
            _(
                "{0} can't be given targets by you: they need the Presales Executive or Sales User role, an enabled account and, for a Division Admin, to be in your division."
            ).format(", ".join(frappe.bold(get_fullname(e)) for e in refused))
        )
    for employee in employees:
        save_target(employee, start, criteria)
    return {"month": start.strftime("%Y-%m"), "assigned": len(employees)}


@frappe.whitelist()
def get_my_targets(month: str | None = None) -> dict:
    """A Presales Executive or Sales User: their own targets for the month, the months they
    have targets in, and, with none yet, whether they already asked a Sales Head for them."""
    user = require_own_targets()
    start = month_start(month or nowdate())
    months = frappe.qb.get_query(
        TARGET,
        fields=["month"],
        filters={"employee": user},
        order_by="month desc",
        limit=24,
    ).run(pluck=True)
    target = targets_for(start, [user]).get(user)
    return {
        "month": start.strftime("%Y-%m"),
        "currency": currency(),
        "months": [m.strftime("%Y-%m") for m in months],
        "target": target,
        "asked": not target and bool(asked_heads(user, start)),
    }


@frappe.whitelist(methods=["POST"])
def ask_for_targets(month: str) -> dict:
    """A person with no targets for the month reminds whoever sets them (`target_givers`)."""
    user = require_own_targets()
    start = month_start(month)
    if targets_for(start, [user]).get(user):
        frappe.throw(
            _("You already have targets for {0}.").format(start.strftime("%B %Y"))
        )
    if not target_givers(user):
        frappe.throw(_("There's no one to ask for targets yet. Ask your manager."))
    return {"told": remind_sales_heads(user, start)}


def require_own_targets() -> str:
    """The signed-in user, when they are given targets; else refused."""
    user = frappe.session.user
    if not has_own_targets(user):
        frappe.throw(
            _("Sales targets is for Presales Executives and Sales Users."),
            SalesTargetsForbiddenError,
        )
    return user


@frappe.whitelist()
def get_progress(month: str, employee: str | None = None, fresh: int | str = 0) -> dict:
    """How far a person is with the month's targets, counted from their leads on the ERP
    site. Their own, or, for a Sales Head or Division Admin, one of their people's."""
    start = month_start(month)
    employee = progress_person(employee)
    target = targets_for(start, [employee]).get(employee)
    if not target:
        return {"state": "no_targets"}
    return progress_for(employee, start, target["criteria"], fresh)


@frappe.whitelist()
def get_team_progress(month: str, fresh: int | str = 0) -> dict:
    """Sales Heads and Division Admins: each of their people's progress for the month, for
    those with targets."""
    require_assigner()
    start = month_start(month)
    people = [p["user"] for p in target_people()]
    return {
        user: progress_for(user, start, target["criteria"], fresh)
        for user, target in targets_for(start, people).items()
    }


@frappe.whitelist(methods=["POST"])
def mark_kpi_done(
    month: str, criterion: str, done: int | str = 1, note: str = ""
) -> dict:
    """A person ticks off one of their KPIs (a Text target) for the month, or takes it back."""
    user = frappe.session.user
    if not has_own_targets(user):
        frappe.throw(
            _("Sales targets is for Presales Executives and Sales Users."),
            SalesTargetsForbiddenError,
        )
    target = target_doc(user, month_start(month))
    target.mark_kpi(criterion, bool(cint(done)), note)
    # the person has no write permission on targets; what they may change was checked above
    target.save(ignore_permissions=True)
    return targets_for(target.month, [user])[user]


@frappe.whitelist(methods=["POST"])
def confirm_kpi(
    month: str, employee: str, criterion: str, confirmed: int | str = 1
) -> dict:
    """Sales Heads and Division Admins: confirm a KPI one of their people marked done, or
    reopen a confirmed one."""
    require_target_person(employee)
    target = target_doc(employee, month_start(month))
    target.confirm_kpi(criterion, bool(cint(confirmed)), frappe.session.user)
    # a Division Admin holds no write permission on targets; require_target_person checked
    target.save(ignore_permissions=True)
    return targets_for(target.month, [employee])[employee]


def progress_person(employee: str | None) -> str:
    """Whose progress the signed-in person may read: their own, or one of their people's
    as a Sales Head or Division Admin."""
    user = frappe.session.user
    if not employee or employee == user:
        if not has_own_targets(user):
            frappe.throw(
                _("Sales targets is for Presales Executives and Sales Users."),
                SalesTargetsForbiddenError,
            )
        return user
    require_target_person(employee)
    return employee


def require_target_person(employee: str):
    """Refused unless the signed-in person gives `employee` their targets."""
    require_assigner()
    if employee not in {p["user"] for p in target_people()}:
        frappe.throw(
            _("{0} isn't one of the people you set targets for.").format(
                frappe.bold(get_fullname(employee))
            ),
            SalesTargetsForbiddenError,
        )


def progress_for(employee: str, start, criteria: list[dict], fresh=0) -> dict:
    """The month so far (the 1st to today, or the whole month once it is over) counted
    from the person's own leads: one result per counted criterion, by name. A month not
    begun counts nothing; an ERP site that refuses the person says why, instead of failing
    the page."""
    today = getdate(nowdate())
    end = add_days(add_months(start, 1), -1)
    if start > today:
        return {"state": "not_started"}
    to_date = min(end, today)
    when = {"from_date": str(start), "to_date": str(to_date)}
    measures = {c["measure"] for c in criteria if c.get("measure")}
    result = {"state": "counted", **when, "month_over": to_date == end, "criteria": {}}
    if not measures:
        return result
    try:
        totals = read_figures("get_overview", employee, when, fresh).get("totals") or {}
        money = (
            read_figures("get_proposal_money", employee, when, fresh).get("totals")
            or {}
            if "collected" in measures
            else {}
        )
    except LeadsError as e:
        # the reason goes on the card, not in a toast as well
        frappe.clear_last_message()
        return {"state": "unavailable", "reason": str(e)}
    for criterion in criteria:
        if criterion.get("measure"):
            result["criteria"][criterion["criterion"]] = measured(
                criterion["measure"], totals, money
            )
    return result


def read_figures(method: str, employee: str, when: dict, fresh) -> dict:
    """One of the ERP site's overview reads for one person's own leads, read as that
    person so their own scope applies, and cached a minute like the Leads Overview."""
    params = {"period": "custom", **when, "owner": employee}
    return cached_read(
        f"targets:{method}",
        params,
        READ_TTL,
        fresh,
        lambda: call(method, acting_user=employee, **params) or {},
    )


def target_doc(employee: str, start):
    name = f"{employee}::{start.strftime('%Y-%m')}"
    if not frappe.db.exists(TARGET, name):
        frappe.throw(
            _("There are no targets for {0} yet.").format(start.strftime("%B %Y")),
            frappe.DoesNotExistError,
        )
    return frappe.get_doc(TARGET, name)


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
    before = {}
    if frappe.db.exists(TARGET, name):
        target = frappe.get_doc(TARGET, name)
        before = {row.criterion.casefold(): row for row in target.criteria}
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
                "measure": row.get("measure") or "",
                "info_only": cint(row.get("info_only")) if kind == "Text" else 0,
                "target_text": value if kind == "Text" else None,
                "target_value": None if kind == "Text" else value,
            },
        )
    target.keep_kpi_state(before)
    # a Division Admin holds no write permission on targets; assign_targets checked who
    target.save(ignore_permissions=True)


def currency() -> str:
    """A division's own currency for a Division Admin's or Division Sales User's targets
    (their division's ERP site is the one counted), else the CRM dashboards' reporting
    currency, else the site's, else INR."""
    division = targets_division() or (
        active_division() if is_division_sales_user() else None
    )
    return (
        (division and frappe.db.get_value(DIVISION, division, "currency"))
        or frappe.db.get_single_value("HD CRM Settings", "dashboard_currency")
        or frappe.db.get_default("currency")
        or "INR"
    )
