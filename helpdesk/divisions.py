"""Divisions: the countries TeamBackOffice works in (India, KSA, UAE, ...), each with its
own ERP site, people and records (docs/divisions.md).

- Super Admins (System Managers and Agent Managers, the hub's existing full-access roles)
  see every division.
- Everyone else sees the divisions they are a member of (`HD Division Member`), with one
  role per division.
- A record with a division (a Project, and a Task through its project) is seen only by
  that division's members; a record with none stays as visible as it always was.
- Until the first division is made, nothing changes for anyone.
"""

from urllib.parse import urlparse

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError

DIVISION = "HD Division"
MEMBER = "HD Division Member"
ACTIVE_DEFAULT = "hd_active_division"

GROUP_ADMIN = "Group Admin"
DIVISION_ADMIN = "Division Admin"
DIVISION_MANAGER = "Division Manager"
SALES_MANAGER = "Sales Manager"
SALES_EXECUTIVE = "Sales Executive"
DIVISION_SALES_USER = "Division Sales User"
PROJECT_MANAGER = "Project Manager"
EMPLOYEE = "Employee"
# highest first; the options of HD Division Member.role
ROLES = (
    GROUP_ADMIN,
    DIVISION_ADMIN,
    DIVISION_MANAGER,
    SALES_MANAGER,
    SALES_EXECUTIVE,
    DIVISION_SALES_USER,
    PROJECT_MANAGER,
    EMPLOYEE,
)
# may change the division's profile, members, teams and departments
MANAGE_ROLES = {GROUP_ADMIN, DIVISION_ADMIN}
# the role each is given on the division's ERP site, whose lead rules then apply: a Sales
# Manager sees every lead there, a Sales User the leads they own, were given or created
ERP_SALES_ROLES = {DIVISION_ADMIN: "Sales Manager", DIVISION_SALES_USER: "Sales User"}
# may open the division's overview and reports
OVERVIEW_ROLES = {
    GROUP_ADMIN,
    DIVISION_ADMIN,
    DIVISION_MANAGER,
    SALES_MANAGER,
    PROJECT_MANAGER,
}


def divisions_on() -> bool:
    return bool(frappe.db.count(DIVISION))


def is_super_admin(user: str | None = None) -> bool:
    # imported here: tasky.permissions imports this module
    from helpdesk.tasky.permissions import is_tasky_admin

    return is_tasky_admin(user or frappe.session.user)


def memberships(user: str | None = None) -> dict[str, str]:
    """{division: role} of the user's active divisions, by division name."""
    user = user or frappe.session.user
    division = frappe.qb.DocType(DIVISION)
    member = frappe.qb.DocType(MEMBER)
    rows = (
        frappe.qb.from_(member)
        .join(division)
        .on(division.name == member.parent)
        .select(member.parent, member.role)
        .where(
            (member.user == user)
            & (member.parenttype == DIVISION)
            & (division.status == "Active")
        )
        .orderby(division.division_name)
        .run()
    )
    return dict(rows)


def active_divisions() -> list[dict]:
    return frappe.get_all(
        DIVISION,
        filters={"status": "Active"},
        fields=[
            "name",
            "division_name",
            "country",
            "currency",
            "workspace_url",
            "crm_source",
        ],
        order_by="division_name asc",
    )


def user_divisions(user: str | None = None) -> list[str]:
    """The divisions whose records the user sees: every active one for a Super Admin."""
    if is_super_admin(user):
        return [d.name for d in active_divisions()]
    return list(memberships(user))


def can_see_division(division: str | None, user: str | None = None) -> bool:
    if not division or is_super_admin(user):
        return True
    return division in memberships(user)


def can_manage_division(division: str, user: str | None = None) -> bool:
    if is_super_admin(user):
        return True
    return memberships(user).get(division) in MANAGE_ROLES


def overview_divisions(user: str | None = None) -> list[str]:
    """The divisions whose overview and reports the user may open. A division whose ERP
    site decides access (its source's *Access follows this site's roles*) opens to the
    managers there and to the people who run the division; any other, to its members with
    an overview role."""
    from helpdesk.crm_dashboard.erp_roles import MANAGER, access_levels

    user = user or frappe.session.user
    divisions = active_divisions()
    if is_super_admin(user):
        return [d.name for d in divisions]
    mine = memberships(user)
    levels = access_levels(user, [d.crm_source for d in divisions if d.crm_source])
    allowed = []
    for d in divisions:
        role = mine.get(d.name)
        if d.crm_source in levels:
            if role in MANAGE_ROLES or levels[d.crm_source] == MANAGER:
                allowed.append(d.name)
        elif role in OVERVIEW_ROLES:
            allowed.append(d.name)
    return allowed


def division_condition(column: str, user: str | None = None) -> str | None:
    """SQL for a permission query: `column` is empty or one of the user's divisions.
    None when the user isn't narrowed (a Super Admin, or no divisions yet)."""
    user = user or frappe.session.user
    if is_super_admin(user) or not divisions_on():
        return None
    unassigned = f"ifnull({column}, '') = ''"
    mine = memberships(user)
    if not mine:
        return f"({unassigned})"
    allowed = ", ".join(frappe.db.escape(d) for d in mine)
    return f"({unassigned} or {column} in ({allowed}))"


# ---------- the active division ----------


def request_division() -> str | None:
    """The division whose workspace URL this request came in on, if any."""
    request = getattr(frappe.local, "request", None)
    host = (getattr(request, "host", None) or "").split(":")[0].lower()
    if not host:
        return None
    for division in active_divisions():
        if urlparse(division.workspace_url or "").hostname == host:
            return division.name
    return None


def active_division(user: str | None = None) -> str | None:
    """The division the user is working in: the one whose URL they came in on, else (a Super
    Admin) the one they picked last, else their first. None means every division (a Super
    Admin's default) or that there are no divisions. Only Super Admins switch: everyone
    else works in their own division."""
    user = user or frappe.session.user
    if user == "Guest" or not divisions_on():
        return None
    mine = user_divisions(user)
    by_host = request_division()
    if by_host in mine:
        return by_host
    if not is_super_admin(user):
        return mine[0] if mine else None
    picked = frappe.defaults.get_user_default(ACTIVE_DEFAULT, user)
    return picked if picked in mine else None


def set_active_division(division: str | None, user: str | None = None):
    user = user or frappe.session.user
    if not is_super_admin(user):
        frappe.throw(
            _(
                "Only Super Admins switch divisions; you work in your own. Ask one to move you."
            ),
            frappe.PermissionError,
        )
    if division and division not in user_divisions(user):
        frappe.throw(
            _("There's no active {0} division.").format(division),
            frappe.PermissionError,
        )
    frappe.defaults.set_user_default(ACTIVE_DEFAULT, division or "", user)


# ---------- the division's ERP site ----------


def division_source(division: str | None):
    """The HD CRM Source of the division's ERP site, or None."""
    name = division and frappe.db.get_value(DIVISION, division, "crm_source")
    return frappe.get_doc("HD CRM Source", name) if name else None


def on_crm_connection(user: str | None = None) -> bool:
    """Whether the user works on the CRM connection (Settings → CRM): no active division,
    or their division's site is the one the CRM connection reads."""
    division = active_division(user)
    if not division:
        return True
    source = division_source(division)
    return bool(source and source.use_crm_connection)


class NoDivisionSiteError(CRMError):
    """The person's active division has no ERP site, so it has no leads to show."""


def division_without_site(user: str | None = None) -> str | None:
    """The user's active division when it has no ERP site yet: its leads would be another
    division's, so the Leads page stays closed there."""
    division = active_division(user)
    if division and not frappe.db.get_value(DIVISION, division, "crm_source"):
        return division
    return None


def leads_role(user: str | None = None) -> str | None:
    """The user's role in their active division when it is one of the two sales roles:
    they get the Leads page there and, like a Sales Employee, the sales screens only."""
    division = active_division(user)
    role = division and memberships(user).get(division)
    return role if role in ERP_SALES_ROLES else None


def is_division_sales_user(user: str | None = None) -> bool:
    """A Division Sales User of their active division (not a Super Admin): a salesperson who
    works their own and allocated leads and sees none of the team's figures."""
    user = user or frappe.session.user
    return leads_role(user) == DIVISION_SALES_USER and not is_super_admin(user)


def scoreboard_people(user: str | None = None) -> set[str] | None:
    """Whose numbers the user sees on the Scoreboard: a Division Admin their division's
    members, a Division Sales User only themselves; None for everyone else, who sees the
    whole team as before."""
    user = user or frappe.session.user
    role = leads_role(user)
    if not role or is_super_admin(user):
        return None
    if role == DIVISION_SALES_USER:
        return {user}
    return set(
        frappe.get_all(
            MEMBER,
            filters={"parent": active_division(user), "parenttype": DIVISION},
            pluck="user",
        )
    )


def leads_closed_by_site(user: str | None = None) -> str | None:
    """The source whose site gives the user no sales role, when their active division's
    access follows its site's roles; None when the Leads page is open to them. What they
    may do there is the site's own decision: it acts as them."""
    from helpdesk.crm_dashboard.erp_roles import access_levels

    user = user or frappe.session.user
    division = active_division(user)
    source = division and frappe.db.get_value(DIVISION, division, "crm_source")
    if not source:
        return None
    return source if access_levels(user, [source]).get(source) == "" else None


def crm_client(user: str | None = None) -> CRMClient:
    """A client for the ERP site of the user's active division: leads, customers and
    quotations are made and read there, so another division's never reach them. A
    division without a site gets none: the CRM connection holds another division's leads.
    """
    return division_client(active_division(user))


def division_client(division: str | None) -> CRMClient:
    """A client for `division`'s ERP site; the CRM connection for no division."""
    if not division:
        return CRMClient.from_settings()
    source = division_source(division)
    if not source:
        raise NoDivisionSiteError(no_site_message(division))
    return source.client()


def no_site_message(division: str) -> str:
    return _(
        "The {0} division has no ERP site yet, so it has no leads here. A Super Admin sets it in Settings → Divisions."
    ).format(frappe.db.get_value(DIVISION, division, "division_name") or division)


# ---------- checks used by the records' controllers ----------


def check_division_for(division: str | None, users: list[str]):
    """Everyone in `users` must be a member of `division` (or a Super Admin)."""
    if not division or not divisions_on():
        return
    outsiders = [
        u for u in dict.fromkeys(users) if u and not can_see_division(division, u)
    ]
    if outsiders:
        frappe.throw(
            _("{0} isn't a member of the {1} division. Add them to it first.").format(
                ", ".join(frappe.utils.get_fullname(u) for u in outsiders),
                frappe.db.get_value(DIVISION, division, "division_name") or division,
            )
        )


def check_assignment_division(project: str | None, user: str):
    """A task of a division's project goes only to that division's members."""
    if project:
        check_division_for(frappe.db.get_value("Project", project, "division"), [user])


def log_activity(subject: str, division: str | None = None):
    """An audit entry (Settings → Audit log) for something done to or with a division's
    data that leaves no Version behind: switching division, exporting a report."""
    frappe.get_doc(
        {
            "doctype": "Activity Log",
            "subject": subject[:140],
            "status": "Success",
            # always the doctype, so the audit log finds "All divisions" entries too
            "reference_doctype": DIVISION,
            "reference_name": division,
            "user": frappe.session.user,
            "full_name": frappe.utils.get_fullname(frappe.session.user),
        }
    ).insert(ignore_permissions=True)
    # a report export is a GET download, and Frappe commits a GET only when asked
    frappe.local.flags.commit = True


def division_info(user: str | None = None) -> dict:
    """What the app shell needs: the divisions the user may switch to (with their role in
    each), the active one, and whether they run any division or may see an overview."""
    user = user or frappe.session.user
    super_admin = is_super_admin(user)
    mine = memberships(user)
    return {
        "divisions": [
            {
                "name": d.name,
                "division_name": d.division_name,
                "country": d.country,
                "currency": d.currency,
                "workspace_url": d.workspace_url,
                "role": mine.get(d.name),
            }
            for d in active_divisions()
            if super_admin or d.name in mine
        ],
        "active_division": active_division(user),
        "is_super_admin": super_admin,
        "can_manage_divisions": super_admin
        or any(role in MANAGE_ROLES for role in mine.values()),
        "can_view_division_overview": bool(overview_divisions(user)),
    }
