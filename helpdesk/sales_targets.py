"""Monthly sales targets (docs/sales-targets.md).

A Sales Head gives Presales Executives and Sales Users their targets for a month: a list of
criteria (Target Amount, Quality Target, ...) each with a value, plus any criteria the head adds.
One `HD Sales Target` per person per month holds them; the person sees theirs on Sales targets.
"""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cint, flt, get_fullname, getdate

from helpdesk.content_team import PRESALES_EXECUTIVE_ROLE, SALES_HEAD_ROLE
from helpdesk.divisions import (
    DIVISION,
    DIVISION_ADMIN,
    DIVISION_SALES_USER,
    MEMBER,
    active_division,
    leads_role,
    memberships,
)
from helpdesk.work_reminders import new_notification

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
# a Text target (a KPI) is ticked off by the person and confirmed by a Sales Head, unless it is
# information only (where to focus: an industry, a place), which nobody ticks off or counts
KPI_DONE = "Done"
KPI_CONFIRMED = "Confirmed"
# what a new set of targets starts with: (name, value type, measure, information only); the
# head can drop any and add their own
DEFAULT_CRITERIA = (
    ("Target Amount", "Amount", "won_value", False),
    ("Quality Target", "Percent", "meeting_rate", False),
    ("Client Meeting", "Number", "meetings", False),
    ("Sales KPI", "Text", "", False),
    ("Proposal Count", "Number", "proposals", False),
    ("Industry", "Text", "", True),
    ("Location", "Text", "", True),
)
MAX_CRITERIA = 30
# the built-in accounts hold every role but are no salespeople
NOT_PEOPLE = ("Administrator", "Guest")


class SalesTargetsForbiddenError(frappe.PermissionError):
    pass


def can_assign_targets(user: str | None = None) -> bool:
    """A Sales Head or an admin: sets everyone's targets and runs the Sales team."""
    return bool(set(ASSIGNER_ROLES) & set(frappe.get_roles(user)))


def targets_division(user: str | None = None) -> str | None:
    """The division whose people a Division Admin sets targets for: their active one. None
    for a Sales Head or an admin, who set everyone's, and for anyone else."""
    user = user or frappe.session.user
    if can_assign_targets(user) or leads_role(user) != DIVISION_ADMIN:
        return None
    return active_division(user)


def can_give_targets(user: str | None = None) -> bool:
    """Opens Assign sales targets and Team targets: a Sales Head or an admin for everyone,
    a Division Admin for their division's people."""
    return can_assign_targets(user) or bool(targets_division(user))


def has_own_targets(user: str | None = None) -> bool:
    """An enabled Presales Executive, Sales User or Division Sales User: is given targets
    and sees them."""
    user = user or frappe.session.user
    return (
        user not in NOT_PEOPLE
        and (
            bool(set(TARGET_ROLES) & set(frappe.get_roles(user)))
            or DIVISION_SALES_USER in memberships(user).values()
        )
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
    if not can_give_targets():
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


def sales_heads() -> list[str]:
    """Enabled Sales Heads: who sets targets, and who hears a person asking for theirs."""
    has_role = frappe.qb.DocType("Has Role")
    user = frappe.qb.DocType("User")
    return (
        frappe.qb.from_(has_role)
        .join(user)
        .on(user.name == has_role.parent)
        .select(user.name)
        .distinct()
        .where(
            (has_role.parenttype == "User")
            & (has_role.role == SALES_HEAD_ROLE)
            & (user.enabled == 1)
            & user.name.notin(NOT_PEOPLE)
        )
        .run(pluck=True)
    )


def target_givers(user: str) -> list[str]:
    """Who sets `user`'s targets: a Division Sales User's Division Admins, else the Sales
    Heads."""
    divisions = [
        d for d, role in memberships(user).items() if role == DIVISION_SALES_USER
    ]
    if not divisions:
        return sales_heads()
    return frappe.get_all(
        MEMBER,
        filters={
            "parent": ["in", divisions],
            "parenttype": DIVISION,
            "role": DIVISION_ADMIN,
        },
        pluck="user",
        distinct=True,
    )


def ask_key(user: str, start) -> str:
    """The notice a person's ask for a month's targets is kept under, once per head."""
    return f"sales-targets-ask:{user}:{start:%Y-%m}"


def asked_heads(user: str, start) -> set[str]:
    """The Sales Heads already told that `user` waits for the month's targets."""
    return set(
        frappe.qb.get_query(
            "HD Notification",
            fields=["user_to"],
            filters={"dedupe_key": ask_key(user, start)},
        ).run(pluck=True)
    )


def remind_sales_heads(user: str, start) -> int:
    """Tell each of `user`'s target givers (`target_givers`) not told yet that they have no
    targets for the month, with a link to the Assign page on them. Asking again tells no one
    twice. Returns how many were told."""
    told = asked_heads(user, start)
    message = _("{0} asks for their sales targets for {1}.").format(
        get_fullname(user), start.strftime("%B %Y")
    )
    link = "/helpdesk/sales-targets?" + urlencode(
        {"month": f"{start:%Y-%m}", "employee": user}
    )
    heads = [head for head in target_givers(user) if head not in told and head != user]
    for head in heads:
        new_notification(
            head,
            "User",
            user,
            message,
            link,
            user_from=user,
            dedupe_key=ask_key(user, start),
        )
    return len(heads)


def target_people() -> list[dict]:
    """Who the signed-in person may give targets to, by name: for a Sales Head every enabled
    user with a target role; for a Division Admin those of their division's members, and its
    Division Sales Users (shown as Sales Users: that is their role on its ERP site)."""
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
    division = targets_division()
    if division:
        rows = division_target_rows(division, rows)
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
        if row.role not in person["roles"]:
            person["roles"].append(row.role)
    for person in people.values():
        # the same order everywhere: Presales Executive before Sales User
        person["roles"].sort(key=TARGET_ROLES.index)
    return sorted(people.values(), key=lambda p: p["full_name"].lower())


def division_target_rows(division: str, rows: list[dict]) -> list[dict]:
    """`rows` (user, role) narrowed to the division's members, plus a Sales User row for each
    of its enabled Division Sales Users."""
    members = frappe.get_all(
        MEMBER,
        filters={"parent": division, "parenttype": DIVISION},
        fields=["user", "role"],
    )
    in_division = {m.user for m in members}
    rows = [r for r in rows if r.name in in_division]
    sales_users = [m.user for m in members if m.role == DIVISION_SALES_USER]
    if sales_users:
        rows += [
            frappe._dict(
                name=u.name,
                full_name=u.full_name,
                user_image=u.user_image,
                role=SALES_USER_ROLE,
            )
            for u in frappe.get_all(
                "User",
                filters={"name": ["in", sales_users], "enabled": 1},
                fields=["name", "full_name", "user_image"],
            )
            if u.name not in NOT_PEOPLE
        ]
    return rows


def default_criteria() -> list[dict]:
    """The criteria new targets start with, as the pages read them (without a target): the
    Assign page fills them in, and a person's page shows each one not assigned as 0."""
    return [
        {
            "criterion": name,
            "value_type": kind,
            "measure": measure,
            "info_only": cint(info_only),
        }
        for name, kind, measure, info_only in DEFAULT_CRITERIA
    ]


def criteria_of(target) -> list[dict]:
    """A target's criteria as the pages read them: one `target` that is a number or text,
    what it counts from, whether it is information only, and a KPI's state."""
    return [
        {
            "criterion": row.criterion,
            "value_type": row.value_type,
            "target": row.target_text if row.value_type == "Text" else row.target_value,
            "measure": row.measure or "",
            "info_only": cint(row.info_only),
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
        meetings, contacted = (
            cint(totals.get("meetings")),
            cint(totals.get("contacted")),
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
