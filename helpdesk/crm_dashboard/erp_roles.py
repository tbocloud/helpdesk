"""Access that follows an ERP site's own roles (docs/divisions.md, "ERP sites").

When a source has *Access follows this site's roles* on, the site decides who reaches its
division's CRM parts:

- each sync reads the site's desk users and their roles into `HD CRM Source User`;
- the source's role mapping turns those roles into an access level: Manager (every lead of the
  source; opens its division's overview) or Executive (their own leads). A user with no mapped
  role, or disabled there, has none and the division's Leads page stays closed to them;
- a hub user is matched to a site user by email. Hub admins (System Managers and Agent
  Managers) see everything, whatever the site says.

A source with it off keeps the hub's own rules (division roles).
"""

import frappe
from frappe.utils import now_datetime

from helpdesk.api.crm import ADMIN_ROLES
from helpdesk.helpdesk.doctype.hd_crm_source_user.hd_crm_source_user import (
    DOCTYPE as SOURCE_USER,
)
from helpdesk.helpdesk.doctype.hd_crm_source_user.hd_crm_source_user import (
    HDCRMSourceUser,
)
from helpdesk.integrations.crm.client import CRMError

SOURCE = "HD CRM Source"
MANAGER = "Manager"
EXECUTIVE = "Executive"
# what a source starts with when its access is switched on: ERPNext's own sales roles
DEFAULT_ROLE_MAP = (
    ("Sales Manager", MANAGER),
    ("Sales Master Manager", MANAGER),
    ("Sales User", EXECUTIVE),
)


def is_hub_admin(user: str) -> bool:
    return user == "Administrator" or bool(ADMIN_ROLES & set(frappe.get_roles(user)))


def access_from(roles: list[str], role_map: dict[str, str]) -> str:
    """The highest access any of `roles` maps to, or "" for none."""
    levels = {role_map.get(role) for role in roles}
    if MANAGER in levels:
        return MANAGER
    return EXECUTIVE if EXECUTIVE in levels else ""


def governed(sources: list[str] | None = None) -> list[str]:
    """The enabled sources whose access follows their site's roles (of `sources`, if given)."""
    filters = {"enabled": 1, "use_erp_roles": 1}
    if sources is not None:
        if not sources:
            return []
        filters["name"] = ["in", sources]
    return frappe.qb.get_query(SOURCE, fields=["name"], filters=filters).run(pluck=True)


def access_levels(user: str, sources: list[str] | None = None) -> dict[str, str]:
    """{source: Manager, Executive or ""} for the governed ones of `sources`. A source left
    out keeps the hub's own rules."""
    names = governed(sources)
    if not names:
        return {}
    if is_hub_admin(user):
        return dict.fromkeys(names, MANAGER)
    found = dict(
        frappe.qb.get_query(
            SOURCE_USER,
            fields=["source", "access"],
            filters={"source": ["in", names], "email": user, "enabled": 1},
        ).run()
    )
    return {name: found.get(name) or "" for name in names}


# ---------- reading the site's users ----------


def read_users(source, client) -> None:
    """Copy the site's desk users and their roles. A failure is kept on the source and never
    raised: the leads were read, and the last good copy of the users stays."""
    try:
        users = client.users_with_roles()
        store_users(source, users)
    except Exception as e:
        frappe.db.rollback()
        message = getattr(e, "user_message", "") if isinstance(e, CRMError) else ""
        source.db_set(
            "users_error",
            (message or str(e) or e.__class__.__name__)[:500],
            update_modified=False,
        )
        return
    source.db_set(
        {"users_read_on": now_datetime(), "users_error": ""}, update_modified=False
    )


def store_users(source, users: list[dict]) -> None:
    """Add, change or drop the source's users to match `users` (the site's list)."""
    role_map = source.role_map_dict()
    existing = set(
        frappe.qb.get_query(
            SOURCE_USER, fields=["name"], filters={"source": source.name}
        ).run(pluck=True)
    )
    kept = []
    for user in users:
        name = HDCRMSourceUser.key(source.name, user["email"])
        values = {
            "full_name": user.get("full_name") or "",
            "enabled": int(user.get("enabled") or 0),
            "erp_roles": "\n".join(user.get("roles") or []),
            "access": (
                access_from(user.get("roles") or [], role_map)
                if user.get("enabled")
                else ""
            ),
        }
        if name in existing:
            frappe.db.set_value(SOURCE_USER, name, values, update_modified=False)
        else:
            frappe.get_doc(
                {
                    "doctype": SOURCE_USER,
                    "source": source.name,
                    "email": user["email"],
                    **values,
                }
            ).insert(ignore_permissions=True)
        kept.append(name)
    gone = existing - set(kept)
    if gone:
        frappe.db.delete(SOURCE_USER, {"name": ["in", sorted(gone)]})


def recompute_access(source) -> None:
    """Work out every copied user's access again from their stored roles, after the role
    mapping changed. The site isn't read."""
    role_map = source.role_map_dict()
    for row in frappe.qb.get_query(
        SOURCE_USER,
        fields=["name", "erp_roles", "enabled", "access"],
        filters={"source": source.name},
    ).run(as_dict=True):
        access = (
            access_from((row.erp_roles or "").splitlines(), role_map)
            if row.enabled
            else ""
        )
        if access != (row.access or ""):
            frappe.db.set_value(
                SOURCE_USER, row.name, "access", access, update_modified=False
            )
