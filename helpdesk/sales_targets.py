"""Monthly sales targets (docs/sales-targets.md).

A Sales Head gives Presales Executives and Sales Users their targets for a month: a list of
criteria (Target Amount, Quality Target, ...) each with a value, plus any criteria the head adds.
One `HD Sales Target` per person per month holds them; the person sees theirs on Sales targets.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_fullname, getdate

from helpdesk.content_team import PRESALES_EXECUTIVE_ROLE, SALES_HEAD_ROLE

# ERPNext's role, also given on the hub to the CRM's salespeople (helpdesk.integrations.crm.users)
SALES_USER_ROLE = "Sales User"
# who is given targets
TARGET_ROLES = (PRESALES_EXECUTIVE_ROLE, SALES_USER_ROLE)
# who gives them; admins too, as everywhere in the app
ASSIGNER_ROLES = (SALES_HEAD_ROLE, "System Manager")

VALUE_TYPES = ("Amount", "Number", "Percent", "Text")
# what a target can count from the person's leads on the ERP site, and the value type it
# gives; blank is a target nobody counts (docs/sales-targets.md, Progress)
MEASURES = {
    "won_value": "Amount",
    "collected": "Amount",
    "meetings": "Number",
    "proposals": "Number",
    "won": "Number",
    "contacted": "Number",
    "new_leads": "Number",
    "meeting_rate": "Percent",
    "win_rate": "Percent",
}
# the measures read straight off the overview's totals (TBO Smart hub-leads-api.md §2.4)
OVERVIEW_FIGURES = {
    "won_value": "won_value",
    "meetings": "meetings",
    "proposals": "quotations_sent",
    "won": "won",
    "contacted": "contacted",
    "new_leads": "new",
}
# a Text target (a KPI) is ticked off by the person and confirmed by a Sales Head
KPI_DONE = "Done"
KPI_CONFIRMED = "Confirmed"
# what a new set of targets starts with; the head can drop any and add their own
DEFAULT_CRITERIA = (
    ("Target Amount", "Amount", "won_value"),
    ("Quality Target", "Percent", "meeting_rate"),
    ("Client Meeting", "Number", "meetings"),
    ("Sales KPI", "Text", ""),
    ("Proposal Count", "Number", "proposals"),
)
MAX_CRITERIA = 30
# the built-in accounts hold every role but are no salespeople
NOT_PEOPLE = ("Administrator", "Guest")


class SalesTargetsForbiddenError(frappe.PermissionError):
    pass


def can_assign_targets(user: str | None = None) -> bool:
    return bool(set(ASSIGNER_ROLES) & set(frappe.get_roles(user)))


def has_own_targets(user: str | None = None) -> bool:
    """An enabled Presales Executive or Sales User: is given targets and sees them."""
    user = user or frappe.session.user
    return (
        user not in NOT_PEOPLE
        and bool(set(TARGET_ROLES) & set(frappe.get_roles(user)))
        and bool(frappe.db.get_value("User", user, "enabled"))
    )


def hides_todays_calls(user: str | None = None) -> bool:
    """A Presales Executive who is no Sales User doesn't get Today's calls at all: no sidebar
    item, no pill on Leads, and Leads never opens on it. Sales Users keep it, and so does
    someone with both roles. Administrator, who holds every role, is left out."""
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    return (
        user not in NOT_PEOPLE
        and PRESALES_EXECUTIVE_ROLE in roles
        and SALES_USER_ROLE not in roles
    )


def require_assigner():
    if not can_assign_targets():
        frappe.throw(
            _("Only a Sales Head can set sales targets."), SalesTargetsForbiddenError
        )


def month_start(month: str):
    """`2026-12` or any date in it → 2026-12-01."""
    value = str(month or "").strip()
    try:
        return getdate(f"{value}-01" if len(value) == 7 else value).replace(day=1)
    except Exception:
        frappe.throw(_("Pick a month, like 2026-12."))


def target_people() -> list[dict]:
    """Enabled users with a target role, by name: who a Sales Head may give targets to."""
    has_role = frappe.qb.DocType("Has Role")
    user = frappe.qb.DocType("User")
    rows = (
        frappe.qb.from_(has_role)
        .join(user)
        .on(user.name == has_role.parent)
        .select(user.name, user.full_name, user.user_image, has_role.role)
        .where(
            (has_role.parenttype == "User")
            & has_role.role.isin(TARGET_ROLES)
            & (user.enabled == 1)
            & user.name.notin(NOT_PEOPLE)
        )
        .run(as_dict=True)
    )
    people: dict[str, dict] = {}
    for row in rows:
        person = people.setdefault(
            row.name,
            {
                "user": row.name,
                "full_name": row.full_name or row.name,
                "user_image": row.user_image,
                "roles": [],
            },
        )
        person["roles"].append(row.role)
    for person in people.values():
        # the same order everywhere: Presales Executive before Sales User
        person["roles"].sort(key=TARGET_ROLES.index)
    return sorted(people.values(), key=lambda p: p["full_name"].lower())


def criteria_of(target) -> list[dict]:
    """A target's criteria as the pages read them: one `target` that is a number or text,
    what it counts from, and a KPI's state."""
    return [
        {
            "criterion": row.criterion,
            "value_type": row.value_type,
            "target": row.target_text if row.value_type == "Text" else row.target_value,
            "measure": row.measure or "",
            "kpi_status": row.kpi_status or "",
            "kpi_note": row.kpi_note or "",
            "kpi_done_on": row.kpi_done_on,
            "kpi_confirmed_by": row.kpi_confirmed_by,
            "kpi_confirmed_by_name": (
                get_fullname(row.kpi_confirmed_by) if row.kpi_confirmed_by else None
            ),
        }
        for row in target.criteria
    ]


def measured(measure: str, totals: dict, money: dict) -> dict:
    """What a person achieved on one measure, from the ERP site's overview totals (and its
    proposal money for `collected`). A rate carries the two figures it divides, so the page
    can show the sum; its `achieved` is None while there is nothing to divide by."""
    if measure in OVERVIEW_FIGURES:
        return {"achieved": flt(totals.get(OVERVIEW_FIGURES[measure]))}
    if measure == "collected":
        return {"achieved": flt(money.get("advances"))}
    if measure == "meeting_rate":
        meetings, contacted = cint(totals.get("meetings")), cint(
            totals.get("contacted")
        )
        return {
            "achieved": rate(meetings, contacted),
            "parts": {"meetings": meetings, "contacted": contacted},
        }
    if measure == "win_rate":
        won, lost = cint(totals.get("won")), cint(totals.get("lost"))
        return {"achieved": rate(won, won + lost), "parts": {"won": won, "lost": lost}}
    return {"achieved": None}


def rate(part: int, whole: int) -> float | None:
    return round(part * 100 / whole, 1) if whole else None
