"""Settings → Divisions → ERP sites: each division's ERP site (connection, field and status
mapping, roles, sync) and the reporting currency, for Super Admins (System Managers and Agent
Managers; docs/divisions.md, "ERP sites").

A source's API secret never leaves the server: the page gets whether one is set and a masked
hint, and sends a secret only to replace or remove it."""

import frappe
from frappe import _
from frappe.query_builder.functions import Count

from helpdesk.api.chat_settings import mask
from helpdesk.crm_dashboard.registry import STANDARD_FIELDS, describe, mapped_fields
from helpdesk.crm_dashboard.sync import enqueue_sync, is_syncing
from helpdesk.divisions import is_super_admin
from helpdesk.integrations.crm.client import CRMError

SETTINGS = "HD CRM Settings"
SOURCE = "HD CRM Source"
LEAD = "HD CRM Report Lead"
SOURCE_USER = "HD CRM Source User"
SOURCE_FIELDS = (
    "enabled",
    "company_label",
    "use_crm_connection",
    "site_url",
    "api_key",
    "lead_doctype",
    "currency",
    "exchange_rate",
    "sync_every",
    "use_erp_roles",
    *mapped_fields(),
)
# a change to these is checked against the source's own lead fields on save
CHECKED_FIELDS = (
    "use_crm_connection",
    "site_url",
    "api_key",
    "lead_doctype",
    *mapped_fields(),
)
SOURCE_HEALTH = (
    "last_sync_status",
    "last_synced_on",
    "last_full_sync_on",
    "leads_synced",
    "last_error",
    "users_read_on",
    "users_error",
)
HISTORY_DOCTYPES = (SETTINGS, SOURCE)
HISTORY_LIMIT = 20


def require_admin():
    # frappe.only_for is skipped in tests, so the roles are checked here
    if not is_super_admin():
        frappe.throw(
            _(
                "Only Super Admins (System Managers and Agent Managers) can change ERP sites."
            ),
            frappe.PermissionError,
        )


# ---------- the page ----------


@frappe.whitelist()
def get_sources() -> dict:
    """The reporting currency, the CRM connection, what a source maps (the registry), and
    every source in summary with the divisions it serves."""
    require_admin()
    crm = frappe.get_cached_doc(SETTINGS)
    divisions = {}
    for division, source in frappe.qb.get_query(
        "HD Division",
        fields=["division_name", "crm_source"],
        filters={"crm_source": ["is", "set"]},
    ).run():
        divisions.setdefault(source, []).append(division)
    return {
        "currency": crm.dashboard_currency,
        "crm_connection": {"enabled": bool(crm.enabled), "site_url": crm.site_url},
        "registry": describe(),
        "sources": [
            {
                **source,
                "running": is_syncing(source.name),
                "divisions": divisions.get(source.name, []),
            }
            for source in frappe.qb.get_query(
                SOURCE,
                fields=[
                    "name",
                    "enabled",
                    "use_crm_connection",
                    "site_url",
                    *SOURCE_HEALTH,
                ],
                order_by="source_name asc",
            ).run(as_dict=True)
        ],
    }


@frappe.whitelist(methods=["POST"])
def set_currency(currency: str) -> dict:
    require_admin()
    if not frappe.db.exists("Currency", currency):
        frappe.throw(_("There's no currency {0}.").format(currency))
    crm = frappe.get_doc(SETTINGS)
    crm.dashboard_currency = currency
    crm.save(ignore_permissions=True)
    return {"currency": currency}


# ---------- data sources ----------


@frappe.whitelist()
def get_source(name: str) -> dict:
    """A source's settings without its secret, its sync health, and the statuses its copied
    leads carry with how many leads each (to map them)."""
    require_admin()
    doc = frappe.get_doc(SOURCE, name)
    secret = doc.get_password("api_secret", raise_exception=False)
    L = frappe.qb.DocType(LEAD)
    statuses = (
        frappe.qb.from_(L)
        .select(L.status, L.company, L.category, Count("*").as_("leads"))
        .where(L.source == name)
        .groupby(L.status, L.company, L.category)
        .orderby(Count("*"), order=frappe.qb.desc)
        .run(as_dict=True)
    )
    return {
        "name": doc.name,
        "source_name": doc.source_name,
        **{f: doc.get(f) for f in SOURCE_FIELDS},
        **{f: doc.get(f) for f in SOURCE_HEALTH},
        "api_secret": {"set": bool(secret), "masked": mask(secret) if secret else ""},
        "status_map": [
            {"status": r.status, "category": r.category, "company": r.company or ""}
            for r in doc.status_map
        ],
        "statuses": statuses,
        "role_map": [
            {"erp_role": r.erp_role, "access": r.access} for r in doc.role_map
        ],
        "users": source_users(doc.name),
        "running": is_syncing(doc.name),
        "modified": doc.modified,
        "modified_by": doc.modified_by,
    }


def source_users(source: str) -> list[dict]:
    """The site's users as the last sync read them, with whether each has a hub account
    (matched by email): managers first, then executives, then the rest."""
    rows = frappe.qb.get_query(
        SOURCE_USER,
        fields=["email", "full_name", "enabled", "access", "erp_roles"],
        filters={"source": source},
        order_by="full_name asc",
    ).run(as_dict=True)
    hub = set(
        frappe.qb.get_query(
            "User",
            fields=["name"],
            filters={"name": ["in", [r.email for r in rows] or [""]], "enabled": 1},
        ).run(pluck=True)
    )
    rank = {"Manager": 0, "Executive": 1}
    return sorted(
        (
            {
                "email": r.email,
                "full_name": r.full_name or r.email,
                "enabled": r.enabled,
                "access": r.access or "",
                "roles": (r.erp_roles or "").splitlines(),
                "in_hub": r.email in hub,
            }
            for r in rows
        ),
        key=lambda u: (rank.get(u["access"], 2), not u["enabled"]),
    )


@frappe.whitelist(methods=["POST"])
def save_source(values: dict, name: str | None = None) -> dict:
    """Make or change a source. The name is fixed once saved. When the connection or the
    mapping changes, the mapped fields are checked against the source's own lead fields;
    a field it doesn't have refuses the save, and an unreachable site saves with a warning."""
    require_admin()
    doc = frappe.get_doc(SOURCE, name) if name else frappe.new_doc(SOURCE)
    if not name:
        doc.source_name = (values.get("source_name") or "").strip()
    before = {f: doc.get(f) for f in CHECKED_FIELDS}
    doc.update({k: v for k, v in values.items() if k in SOURCE_FIELDS})
    if values.get("api_secret") is not None:
        doc.api_secret = str(values["api_secret"]).strip()
    if "role_map" in values:
        doc.set(
            "role_map",
            [
                {k: row.get(k) for k in ("erp_role", "access")}
                for row in values["role_map"] or []
            ],
        )
    if "status_map" in values:
        doc.set(
            "status_map",
            [
                {k: row.get(k) for k in ("status", "category", "company")}
                for row in values["status_map"] or []
            ],
        )
    check = doc.is_new() or any(
        (before[f] or "") != (doc.get(f) or "") for f in CHECKED_FIELDS
    )
    doc.save()
    warning = check_fields(doc) if check else None
    return {"source": get_source(doc.name), "warning": warning}


def check_fields(doc) -> str | None:
    """Refuses the save when a mapped field doesn't fit the source's lead fields. Returns a
    warning when they couldn't be read."""
    try:
        fields = doc.client().doctype_fields(doc.lead_doctype)
    except CRMError as e:
        return _("Saved, but the mapped fields couldn't be checked: {0}").format(str(e))
    if not fields:
        frappe.throw(
            _("{0} has no document type {1}, or its API user may not read it.").format(
                doc.name, doc.lead_doctype
            )
        )
    problems = doc.check_remote_fields([*STANDARD_FIELDS, *fields])
    if problems:
        frappe.throw(
            "<br>".join(problems),
            title=_("The mapping doesn't fit {0}").format(doc.lead_doctype),
        )
    return None


@frappe.whitelist(methods=["POST"])
def delete_source(name: str) -> dict:
    """Deletes the source with its copied leads and users; the source's own site is never
    touched. A division still on it refuses (its link)."""
    require_admin()
    frappe.delete_doc(SOURCE, name)
    return {"deleted": name}


@frappe.whitelist(methods=["POST"])
def test_source(name: str) -> dict:
    """{ok, message, details}: who the key is on the source, how many leads it may read, and
    whether the mapped fields fit."""
    require_admin()
    doc = frappe.get_doc(SOURCE, name)
    try:
        client = doc.client()
        user = client.logged_user()
        fields = client.doctype_fields(doc.lead_doctype)
        leads = client.call("frappe.client.get_count", doctype=doc.lead_doctype)
    except CRMError as e:
        return {"ok": False, "message": str(e)}
    problems = (
        doc.check_remote_fields([*STANDARD_FIELDS, *fields])
        if fields
        else [_("There's no document type {0} there.").format(doc.lead_doctype)]
    )
    return {
        "ok": not problems,
        "message": _("Connected as {0}.").format(user or _("the API user"))
        if not problems
        else _("Connected as {0}, but the mapping needs fixing.").format(user),
        "details": [
            {"label": _("Leads it can read"), "value": str(leads or 0)},
            *({"label": _("Mapping"), "value": p} for p in problems),
        ],
    }


@frappe.whitelist()
def get_remote_fields(name: str) -> dict:
    """{ok, fields: [{fieldname, label, fieldtype, options}], message}: the source's lead
    fields, custom ones included, for the mapping pickers."""
    require_admin()
    doc = frappe.get_doc(SOURCE, name)
    try:
        fields = doc.client().doctype_fields(doc.lead_doctype)
    except CRMError as e:
        return {"ok": False, "fields": [], "message": str(e)}
    return {"ok": True, "fields": [*STANDARD_FIELDS, *fields], "message": ""}


@frappe.whitelist(methods=["POST"])
def sync_source_now(name: str, full: bool = False) -> dict:
    """Queue a sync now: changed leads only, or every lead with `full` (which also drops
    the leads deleted on the source)."""
    require_admin()
    doc = frappe.get_doc(SOURCE, name)
    if not doc.enabled:
        frappe.throw(_("Switch {0} on first.").format(name))
    enqueue_sync(name, full=bool(full))
    return {"queued": True}


# ---------- change history ----------


@frappe.whitelist()
def get_history(doctype: str, name: str) -> dict:
    """{created_by, created_on, changes: [{at, by, lines}]}: who changed a source or the
    reporting currency, and what, newest first. Secrets show as masked."""
    require_admin()
    if doctype not in HISTORY_DOCTYPES:
        frappe.throw(_("There's no history for {0} here.").format(doctype))
    meta = frappe.get_meta(doctype)
    owner, creation = frappe.db.get_value(doctype, name, ["owner", "creation"])
    versions = frappe.qb.get_query(
        "Version",
        fields=["owner", "creation", "data"],
        filters={"ref_doctype": doctype, "docname": name},
        order_by="creation desc",
        limit=HISTORY_LIMIT,
    ).run(as_dict=True)
    return {
        "created_by": user_name(owner),
        "created_on": creation,
        "changes": [
            {
                "at": v.creation,
                "by": user_name(v.owner),
                "lines": change_lines(meta, v.data),
            }
            for v in versions
        ],
    }


def change_lines(meta, data: str) -> list[str]:
    data = frappe.parse_json(data or "{}") or {}
    lines = []

    def label(field: str, of=None) -> str:
        df = (of or meta).get_field(field)
        return _(df.label) if df and df.label else field

    def shown(field: str, value, of=None):
        df = (of or meta).get_field(field)
        if df and df.fieldtype == "Password":
            return "••••"
        return value if value not in (None, "") else _("empty")

    for field, old, new in data.get("changed") or []:
        lines.append(f"{label(field)}: {shown(field, old)} → {shown(field, new)}")
    for table, _row in data.get("added") or []:
        lines.append(_("Added a row to {0}").format(label(table)))
    for table, _row in data.get("removed") or []:
        lines.append(_("Removed a row from {0}").format(label(table)))
    for table, idx, _rowname, changes in data.get("row_changed") or []:
        child = (
            frappe.get_meta(meta.get_field(table).options)
            if meta.get_field(table)
            else meta
        )
        for field, old, new in changes:
            lines.append(
                _("{0} row {1}").format(label(table), idx)
                + f": {label(field, child)}: {shown(field, old, child)} → {shown(field, new, child)}"
            )
    return lines


def user_name(user: str) -> str:
    return frappe.db.get_value("User", user, "full_name") or user
