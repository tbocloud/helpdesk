"""Settings → Departments: the departments projects belong to, in the order the
Projects page lists them."""

import frappe
from frappe import _
from frappe.query_builder.functions import Count

from helpdesk.content_team import content_team_members
from helpdesk.tasky.permissions import (
    DEPARTMENT_HEAD_TABLE,
    DEPARTMENT_HEADS,
    HIDDEN_DEPARTMENTS,
    hidden_departments,
    is_tasky_admin,
)

DEPARTMENT = "HD Department"


@frappe.whitelist()
def get_departments(include_inactive: bool = False) -> list[dict]:
    """Departments in display order, each with how many projects it has and its
    heads: the people set in Settings → Departments, and the roles that head it."""
    frappe.has_permission(DEPARTMENT, "read", throw=True)
    department = frappe.qb.DocType(DEPARTMENT)
    query = (
        frappe.qb.from_(department)
        .select(
            department.name,
            department.department_name,
            department.sort_order,
            department.is_active,
            department.description,
        )
        .orderby(department.sort_order)
        .orderby(department.department_name)
    )
    if not frappe.utils.sbool(include_inactive):
        query = query.where(department.is_active == 1)
    # each team keeps out of the other's department (tasky.permissions.hidden_departments)
    hidden = hidden_departments()
    if hidden:
        query = query.where(department.name.notin(hidden))
    rows = query.run(as_dict=True)
    counts = _project_counts()
    heads = _configured_heads([row.name for row in rows])
    for row in rows:
        row.is_active = bool(row.is_active)
        row.project_count = counts.get(row.name, 0)
        row.heads = heads.get(row.name, [])
        row.head_roles = [r for r, d in DEPARTMENT_HEADS.items() if d == row.name]
    return rows


def _configured_heads(departments: list[str]) -> dict[str, list[dict]]:
    """Each department's Heads setting, as {user, full_name}, in the order set.
    Disabled accounts are left out, as in tasky.permissions.department_heads, so
    saving the row again drops them."""
    if not departments:
        return {}
    head = frappe.qb.DocType(DEPARTMENT_HEAD_TABLE)
    user = frappe.qb.DocType("User")
    out: dict[str, list[dict]] = {}
    for row in (
        frappe.qb.from_(head)
        .join(user)
        .on(user.name == head.user)
        .select(head.parent, head.user, user.full_name)
        .where(
            (head.parenttype == DEPARTMENT)
            & (head.parentfield == "heads")
            & head.parent.isin(departments)
            & (user.enabled == 1)
        )
        .orderby(head.idx)
        .run(as_dict=True)
    ):
        out.setdefault(row.parent, []).append(
            {"user": row.user, "full_name": row.full_name or row.user}
        )
    return out


def _project_counts() -> dict:
    project = frappe.qb.DocType("Project")
    return dict(
        frappe.qb.from_(project)
        .select(project.custom_department, Count(project.name))
        .where(project.custom_department.isnotnull())
        .groupby(project.custom_department)
        .run()
    )


@frappe.whitelist(methods=["POST"])
def add_department(department_name: str, description: str | None = None) -> dict:
    """Adds a department at the end of the list."""
    frappe.has_permission(DEPARTMENT, "create", throw=True)
    name = _clean_name(department_name)
    _check_name_free(name)
    doc = frappe.get_doc(
        {
            "doctype": DEPARTMENT,
            "department_name": name,
            "description": (description or "").strip() or None,
        }
    ).insert()
    return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def rename_department(department: str, new_name: str) -> dict:
    """Renames a department; its projects move with it."""
    doc = _get_department(department, "write")
    name = _clean_name(new_name)
    if name == doc.name:
        return {"name": doc.name}
    # MariaDB compares names case-insensitively, so "erp" -> "ERP" is the same record
    if name.lower() != doc.name.lower():
        _check_name_free(name)
    new = frappe.rename_doc(DEPARTMENT, doc.name, name)
    return {"name": new}


@frappe.whitelist(methods=["POST"])
def move_department(department: str, direction: str) -> list[str]:
    """Moves a department one place up or down; returns the new order."""
    doc = _get_department(department, "write")
    if direction not in ("up", "down"):
        frappe.throw(_("Move a department up or down."))
    # lock every row first, so two moves at once can't renumber from the same stale order
    Department = frappe.qb.DocType(DEPARTMENT)
    order = (
        frappe.qb.from_(Department)
        .select(Department.name)
        .orderby(Department.sort_order)
        .orderby(Department.department_name)
        .for_update()
        .run(pluck=True)
    )
    index = order.index(doc.name)
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(order):
        order[index], order[target] = order[target], order[index]
    # renumber everything so ties and gaps from older edits can't stall a move
    for position, name in enumerate(order, start=1):
        frappe.db.set_value(DEPARTMENT, name, "sort_order", position)
    return order


@frappe.whitelist(methods=["POST"])
def set_department_active(department: str, is_active: bool) -> dict:
    """Inactive departments can't be picked for projects; their projects keep them."""
    doc = _get_department(department, "write")
    doc.is_active = 1 if frappe.utils.sbool(is_active) else 0
    doc.save()
    return {"name": doc.name, "is_active": bool(doc.is_active)}


@frappe.whitelist(methods=["POST"])
def set_department_heads(department: str, heads: list[str] | str | None = None) -> dict:
    """Who heads a department; they're told when its Scoreboard champion is chosen
    (tasky.permissions.department_heads). System Managers and Agent Managers."""
    doc = _get_department(department, "write")
    heads = frappe.parse_json(heads) if isinstance(heads, str) else heads or []
    users = list(dict.fromkeys(u for u in heads if u))
    user = frappe.qb.DocType("User")
    active = (
        set(
            frappe.qb.from_(user)
            .select(user.name)
            .where(user.name.isin(users) & (user.enabled == 1))
            .run(pluck=True)
        )
        if users
        else set()
    )
    disabled = [u for u in users if u not in active]
    if disabled:
        frappe.throw(
            _("{0} can't head a department: no active account.").format(
                ", ".join(disabled)
            )
        )
    doc.set("heads", [{"user": u} for u in users])
    doc.save()
    return {"name": doc.name, "heads": users}


@frappe.whitelist(methods=["POST"])
def delete_department(department: str) -> dict:
    """Deletes a department no project uses."""
    doc = _get_department(department, "delete")
    try:
        frappe.delete_doc(DEPARTMENT, doc.name)
    except frappe.LinkExistsError:
        # replace Frappe's "Cannot delete or cancel because ..." with what to do about it
        frappe.clear_last_message()
        count = frappe.db.count("Project", {"custom_department": doc.name})
        frappe.throw(
            _(
                "{0} is still used by {1} project(s). Move them to another department "
                "first, or deactivate {0} instead."
            ).format(doc.name, count),
            frappe.LinkExistsError,
            title=_("Department in use"),
        )
    return {"name": doc.name}


def _get_department(department: str, ptype: str):
    if not frappe.db.exists(DEPARTMENT, department):
        frappe.throw(
            _("Department not found: {0}").format(department), frappe.DoesNotExistError
        )
    doc = frappe.get_doc(DEPARTMENT, department)
    doc.check_permission(ptype)
    return doc


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        frappe.throw(_("Give the department a name."))
    if len(name) > 140:
        frappe.throw(_("Keep the department name under 140 characters."))
    return name


def _check_name_free(name: str):
    if frappe.db.exists(DEPARTMENT, name):
        frappe.throw(_("There is already a department called {0}.").format(name))


# --- department walls: which agents are kept out of the other team's department ---


@frappe.whitelist()
def get_department_walls(users: list[str] | str) -> dict[str, list[str]]:
    """Each agent's wall roles (DM Employee, ERP Employee), for Settings → Agents."""
    _check_can_set_walls()
    users = frappe.parse_json(users) if isinstance(users, str) else users or []
    if not users:
        return {}
    has_role = frappe.qb.DocType("Has Role")
    walls = {user: [] for user in users}
    for user, role in (
        frappe.qb.from_(has_role)
        .select(has_role.parent, has_role.role)
        .where(
            (has_role.parenttype == "User")
            & has_role.parent.isin(users)
            & has_role.role.isin(list(HIDDEN_DEPARTMENTS))
        )
        .orderby(has_role.role)
        .run()
    ):
        walls[user].append(role)
    return walls


@frappe.whitelist()
def get_content_team(users: list[str] | str) -> list[str]:
    """Which agents are in the content team and see the content calendar, for the badge
    in Settings → Agents. The Digital team wall (DM Employee) adds someone to it."""
    _check_can_set_walls()
    users = frappe.parse_json(users) if isinstance(users, str) else users or []
    return content_team_members(users)


@frappe.whitelist(methods=["POST"])
def set_department_wall(user: str, role: str | None = None) -> list[str]:
    """Give an agent one wall role, or none (empty role); their other roles stay."""
    from helpdesk.content_team import ensure_role

    _check_can_set_walls()
    role = role or None
    if role and role not in HIDDEN_DEPARTMENTS:
        frappe.throw(_("Pick DM Employee, ERP Employee or no wall."))
    if not frappe.db.exists("HD Agent", user):
        frappe.throw(_("{0} is not an agent.").format(user), frappe.DoesNotExistError)
    ensure_role()
    doc = frappe.get_doc("User", user)
    doc.set(
        "roles",
        [r for r in doc.roles if r.role not in HIDDEN_DEPARTMENTS or r.role == role],
    )
    if role and role not in {r.role for r in doc.roles}:
        doc.append("roles", {"role": role})
    # Agent Managers may not have write access on User; the check above decides
    doc.save(ignore_permissions=True)
    return [role] if role else []


def _check_can_set_walls():
    if not is_tasky_admin():
        frappe.throw(
            _("Only System Managers and Agent Managers can set department walls."),
            frappe.PermissionError,
        )
