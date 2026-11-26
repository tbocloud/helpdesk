"""Division Management (Settings → Divisions), the division switcher and the audit log
(docs/divisions.md)."""

import frappe
import pytz
from frappe import _
from frappe.query_builder.functions import Count

from helpdesk.api.erp_sites import change_lines, user_name
from helpdesk.divisions import (
    DIVISION,
    GROUP_ADMIN,
    MEMBER,
    ROLES,
    can_manage_division,
    is_super_admin,
    log_activity,
    memberships,
    set_active_division,
)

# what only a Super Admin changes: identity, domain, money, status and the ERP site
CENTRAL_FIELDS = (
    "division_name",
    "division_code",
    "status",
    "country",
    "workspace_url",
    "currency",
    "division_admin",
    "crm_source",
    "weekly_lead_report",
)
# what the division's own admins change too
LOCAL_FIELDS = ("time_zone", "language")
UNIT_DOCTYPES = {"teams": "HD Team", "departments": "HD Department"}
AUDIT_LIMIT = 100


def require_super_admin():
    # frappe.only_for is skipped in tests, so the roles are checked here
    if not is_super_admin():
        frappe.throw(
            _("Only Super Admins (System Managers and Agent Managers) can do this."),
            frappe.PermissionError,
        )


def require_manager(division: str):
    if not can_manage_division(division):
        frappe.throw(
            _("Only the division's admins can change it."), frappe.PermissionError
        )


# ---------- the settings page ----------


@frappe.whitelist()
def get_divisions() -> dict:
    """Every division a Super Admin sees, or the ones a division's admin runs, with how many
    people, teams, departments and projects each has."""
    super_admin = is_super_admin()
    managed = [d for d in memberships() if can_manage_division(d)]
    if not (super_admin or managed):
        frappe.throw(_("You don't run any division."), frappe.PermissionError)
    filters = None if super_admin else {"name": ("in", managed)}
    rows = frappe.qb.get_query(
        DIVISION,
        fields=[
            "name",
            "division_name",
            "status",
            "country",
            "currency",
            "workspace_url",
            "crm_source",
            "creation",
        ],
        filters=filters,
        order_by="division_name asc",
    ).run(as_dict=True)
    members = counts(MEMBER, "parent", {"parenttype": DIVISION})
    teams = counts("HD Team", "division")
    departments = counts("HD Department", "division")
    projects = counts("Project", "division")
    for row in rows:
        row.members = members.get(row.name, 0)
        row.teams = teams.get(row.name, 0)
        row.departments = departments.get(row.name, 0)
        row.projects = projects.get(row.name, 0)
    return {
        "divisions": rows,
        "can_create": super_admin,
        "central_url": frappe.utils.get_url(),
        "unassigned_projects": (
            frappe.db.count("Project", {"division": ("is", "not set")})
            if super_admin
            else 0
        ),
    }


def counts(doctype: str, field: str, filters: dict | None = None) -> dict[str, int]:
    table = frappe.qb.DocType(doctype)
    query = (
        frappe.qb.from_(table)
        .select(table[field], Count("*"))
        .where(table[field].isnotnull())
        .groupby(table[field])
    )
    for key, value in (filters or {}).items():
        query = query.where(table[key] == value)
    return dict(query.run())


@frappe.whitelist()
def get_division(name: str) -> dict:
    """A division's profile, members, teams and departments, and what the viewer may change."""
    require_manager(name)
    doc = frappe.get_doc(DIVISION, name)
    return {
        "division": {
            field: doc.get(field) for field in ("name", *CENTRAL_FIELDS, *LOCAL_FIELDS)
        },
        "members": [
            {"user": m.user, "full_name": user_name(m.user), "role": m.role}
            for m in doc.members
        ],
        "teams": frappe.get_all(
            "HD Team", filters={"division": name}, pluck="name", order_by="name asc"
        ),
        "departments": frappe.get_all(
            "HD Department",
            filters={"division": name},
            pluck="name",
            order_by="name asc",
        ),
        "roles": roles_for(name),
        "can_edit_central": is_super_admin(),
    }


@frappe.whitelist()
def get_options() -> dict:
    """The pick lists of the division form that aren't doctypes."""
    return {"time_zones": pytz.common_timezones, "roles": list(ROLES)}


def roles_for(division: str) -> list[str]:
    """The roles the viewer may give in `division`: a division's own admins can't make Group
    Admins, who run several divisions."""
    if is_super_admin():
        return list(ROLES)
    return [r for r in ROLES if r != GROUP_ADMIN]


@frappe.whitelist(methods=["POST"])
def save_division(values: dict | str, name: str | None = None) -> dict:
    """Create a division (Super Admins) or change its profile."""
    values = frappe.parse_json(values)
    if name:
        require_manager(name)
        doc = frappe.get_doc(DIVISION, name)
    else:
        require_super_admin()
        doc = frappe.new_doc(DIVISION)
    fields = (*CENTRAL_FIELDS, *LOCAL_FIELDS) if is_super_admin() else LOCAL_FIELDS
    site_before, admin_before = doc.crm_source, doc.division_admin
    for field in fields:
        if field in values and not (name and field == "division_code"):
            doc.set(field, values[field] or None)
    doc.save(ignore_permissions=True)
    if doc.crm_source != site_before:
        problems = doc.apply_erp_roles()
    elif doc.division_admin != admin_before:
        problems = doc.apply_erp_roles([doc.division_admin])
    else:
        problems = []
    return {"name": doc.name, "erp_problems": problems}


@frappe.whitelist(methods=["POST"])
def delete_division(name: str):
    require_super_admin()
    # Frappe refuses while a project, team or department is still in it
    frappe.delete_doc(DIVISION, name, ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def set_members(division: str, members: list | str) -> dict:
    """Replace the division's members: [{user, role}]. Every Division Admin and Division
    Sales User gets their role on the division's ERP site; what couldn't be done comes
    back as `erp_problems`."""
    require_manager(division)
    members = frappe.parse_json(members) or []
    doc = frappe.get_doc(DIVISION, division)
    allowed = set(roles_for(division))
    before = {m.user: m.role for m in doc.members}
    after = {m["user"]: m["role"] for m in members}
    for user in set(before) | set(after):
        changed = before.get(user) != after.get(user)
        touches_group_admin = GROUP_ADMIN in (before.get(user), after.get(user))
        if changed and touches_group_admin and GROUP_ADMIN not in allowed:
            frappe.throw(
                _("Only Super Admins give or take away the Group Admin role."),
                frappe.PermissionError,
            )
    for role in after.values():
        if role not in ROLES:
            frappe.throw(_("{0} isn't a division role.").format(role))
    doc.set("members", [{"user": u, "role": r} for u, r in after.items()])
    doc.save(ignore_permissions=True)
    # everyone, not only who changed: someone added to the ERP site later gets their role
    # on the next save; a role already right there is left alone
    return {"members": len(doc.members), "erp_problems": doc.apply_erp_roles()}


# ---------- a division's agents (docs/divisions.md, "Agents of a division") ----------


@frappe.whitelist()
def get_division_agents(division: str) -> dict:
    """The division's people as agents (name, image, whether the agent is active, their
    role in the division) and the invites to it not yet accepted, for its admins."""
    require_manager(division)
    doc = frappe.get_doc(DIVISION, division)
    users = [m.user for m in doc.members]
    info = {
        u.name: u
        for u in frappe.get_all(
            "User",
            filters={"name": ("in", users or [""])},
            fields=["name", "full_name", "user_image", "enabled"],
        )
    }
    active = dict(
        frappe.get_all(
            "HD Agent",
            filters={"name": ("in", users or [""])},
            fields=["name", "is_active"],
            as_list=True,
        )
    )
    return {
        "agents": [
            {
                "user": m.user,
                "full_name": (info.get(m.user) or {}).get("full_name") or m.user,
                "user_image": (info.get(m.user) or {}).get("user_image"),
                "is_active": bool(
                    active.get(m.user) and (info.get(m.user) or {}).get("enabled")
                ),
                "role": m.role,
            }
            for m in doc.members
        ],
        "invites": frappe.get_all(
            "User Invitation",
            filters={
                "division": division,
                "status": "Pending",
                "app_name": "helpdesk",
            },
            fields=["name", "email", "division_role"],
            order_by="creation desc",
        ),
        "roles": roles_for(division),
    }


@frappe.whitelist(methods=["POST"])
def invite_to_division(division: str, emails: str, role: str) -> dict:
    """Bring people into the division with `role`. Someone who is already an agent here
    joins it now (and gets their role on its ERP site); anyone else is invited as an Agent
    and joins it when they accept. {added, invited, already_invited, already_member,
    disabled, erp_problems}."""
    require_manager(division)
    if role not in roles_for(division):
        frappe.throw(_("{0} isn't a role you can give here.").format(role))
    frappe.utils.validate_email_address(emails, throw=True)
    emails = [e.lower() for e in frappe.utils.split_emails(emails)]
    if not emails:
        frappe.throw(_("Add at least one email."))
    doc = frappe.get_doc(DIVISION, division)
    result = {
        k: []
        for k in (
            "added",
            "invited",
            "already_invited",
            "already_member",
            "disabled",
        )
    }
    for email in dict.fromkeys(emails):
        user = frappe.db.get_value("User", {"name": email}, ["name", "enabled"])
        if user and not user[1]:
            result["disabled"].append(email)
        elif user and frappe.db.get_value("HD Agent", email, "is_active"):
            key = "added" if doc.add_member(email, role) else "already_member"
            result[key].append(email)
        elif frappe.db.exists(
            "User Invitation",
            {"email": email, "status": "Pending", "app_name": "helpdesk"},
        ):
            result["already_invited"].append(email)
        else:
            invite_agent(email, division, role)
            result["invited"].append(email)
    if result["added"]:
        doc.save(ignore_permissions=True)
    result["erp_problems"] = (
        doc.apply_erp_roles(result["added"]) if result["added"] else []
    )
    if result["added"] or result["invited"]:
        log_activity(
            _("Brought {0} into {1} as {2}").format(
                ", ".join(result["added"] + result["invited"]), division, role
            ),
            division,
        )
    return result


def invite_agent(email: str, division: str, role: str):
    """An Agent's invite that puts them in `division` with `role` once accepted."""
    invitation = frappe.get_doc(
        doctype="User Invitation",
        email=email,
        roles=[{"role": "Agent"}],
        app_name="helpdesk",
        redirect_to_path="/helpdesk",
        division=division,
        division_role=role,
    )
    invitation.flags.division_invite = True
    invitation.insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def cancel_division_invite(division: str, name: str):
    require_manager(division)
    invitation = frappe.get_doc("User Invitation", name)
    if invitation.division != division or invitation.status != "Pending":
        frappe.throw(_("This isn't a pending invite to {0}.").format(division))
    # a division admin holds no rights on invitations; checked above instead
    invitation.flags.ignore_permissions = True
    invitation.cancel_invite()


@frappe.whitelist(methods=["POST"])
def set_units(division: str, teams: list | str, departments: list | str) -> dict:
    """Put exactly these teams and departments in the division. A team or department of
    another division moves only for a Super Admin."""
    require_manager(division)
    picked = {
        "teams": set(frappe.parse_json(teams) or []),
        "departments": set(frappe.parse_json(departments) or []),
    }
    for key, doctype in UNIT_DOCTYPES.items():
        current = set(
            frappe.get_all(doctype, filters={"division": division}, pluck="name")
        )
        for name in picked[key] - current:
            elsewhere = frappe.db.get_value(doctype, name, "division")
            if elsewhere and not is_super_admin():
                frappe.throw(
                    _(
                        "{0} is in the {1} division. Ask a Super Admin to move it."
                    ).format(name, elsewhere),
                    frappe.PermissionError,
                )
            frappe.db.set_value(doctype, name, "division", division)
        for name in current - picked[key]:
            frappe.db.set_value(doctype, name, "division", None)
    log_activity(
        _("Changed the teams and departments of {0}").format(division), division
    )
    return {key: len(value) for key, value in picked.items()}


@frappe.whitelist(methods=["POST"])
def assign_unassigned_projects(division: str) -> dict:
    """Put every project without a division into `division`. A project whose lead or
    members aren't the division's people is left as it is and counted."""
    require_super_admin()
    moved, skipped = 0, []
    for name in frappe.get_all(
        "Project", filters={"division": ("is", "not set")}, pluck="name"
    ):
        project = frappe.get_doc("Project", name)
        project.division = division
        try:
            project.save(ignore_permissions=True)
            moved += 1
        except frappe.ValidationError:
            frappe.clear_last_message()
            skipped.append(name)
    return {"moved": moved, "skipped": skipped}


# ---------- the switcher ----------


@frappe.whitelist(methods=["POST"])
def switch_division(division: str | None = None):
    set_active_division(division or None)
    log_activity(
        _("Switched to {0}").format(division or _("All divisions")), division or None
    )


# ---------- the audit log ----------


@frappe.whitelist()
def get_audit_log(division: str | None = None) -> list[dict]:
    """Who changed which division (profile, members, ERP site), who switched division and
    who exported a report, newest first; for every division, also who moved a project
    between divisions."""
    if division:
        require_manager(division)
    else:
        require_super_admin()
    version_filters = {"ref_doctype": DIVISION}
    activity_filters = {"reference_doctype": DIVISION}
    if division:
        version_filters["docname"] = division
        activity_filters["reference_name"] = division
    meta = frappe.get_meta(DIVISION)
    entries = [
        {
            "at": v.creation,
            "by": user_name(v.owner),
            "division": v.docname,
            "lines": change_lines(meta, v.data),
        }
        for v in frappe.qb.get_query(
            "Version",
            fields=["owner", "creation", "data", "docname"],
            filters=version_filters,
            order_by="creation desc",
            limit=AUDIT_LIMIT,
        ).run(as_dict=True)
    ]
    if not division:
        entries += project_moves()
    entries += [
        {
            "at": a.creation,
            "by": a.full_name or user_name(a.user),
            "division": a.reference_name,
            "lines": [a.subject],
        }
        for a in frappe.qb.get_query(
            "Activity Log",
            fields=["user", "full_name", "creation", "subject", "reference_name"],
            filters=activity_filters,
            order_by="creation desc",
            limit=AUDIT_LIMIT,
        ).run(as_dict=True)
    ]
    entries.sort(key=lambda e: e["at"], reverse=True)
    return entries[:AUDIT_LIMIT]


def project_moves() -> list[dict]:
    """Projects put into, or moved between, divisions (from the projects' Versions)."""
    meta = frappe.get_meta("Project")
    label = _(meta.get_field("division").label)
    moves = []
    for v in frappe.qb.get_query(
        "Version",
        fields=["owner", "creation", "data", "docname"],
        filters={"ref_doctype": "Project", "data": ("like", '%"division"%')},
        order_by="creation desc",
        limit=AUDIT_LIMIT,
    ).run(as_dict=True):
        lines = [
            line for line in change_lines(meta, v.data) if line.startswith(f"{label}:")
        ]
        if lines:
            moves.append(
                {
                    "at": v.creation,
                    "by": user_name(v.owner),
                    "division": None,
                    "lines": [_("Project {0}").format(v.docname), *lines],
                }
            )
    return moves
