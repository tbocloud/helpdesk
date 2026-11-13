"""Settings → CRM dashboards: the reporting currency, the data sources (connection, field and
status mapping, sync), the organisation, and the dashboards themselves, for System Managers
and Agent Managers (docs/crm-dashboard.md).

A source's API secret never leaves the server: the page gets whether one is set and a masked
hint, and sends a secret only to replace or remove it."""

import frappe
from frappe import _
from frappe.query_builder.functions import Count

from helpdesk.api.chat_settings import mask
from helpdesk.crm_dashboard.registry import (
    ORG_LEVELS,
    STANDARD_FIELDS,
    UNIT_PARENTS,
    describe,
    mapped_fields,
)
from helpdesk.crm_dashboard.report import is_admin
from helpdesk.crm_dashboard.sync import enqueue_sync, is_syncing
from helpdesk.helpdesk.doctype.hd_crm_dashboard.hd_crm_dashboard import HDCRMDashboard
from helpdesk.helpdesk.doctype.hd_crm_org_unit.hd_crm_org_unit import LEVEL_OF
from helpdesk.integrations.crm.client import CRMError

SETTINGS = "HD CRM Settings"
SOURCE = "HD CRM Source"
UNIT = "HD CRM Org Unit"
DASHBOARD = "HD CRM Dashboard"
LEAD = "HD CRM Report Lead"
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
)
UNIT_FIELDS = (
    "label",
    "is_active",
    "company",
    "branch",
    "department",
    "team",
    "user",
    "leader",
)
DASHBOARD_FIELDS = (
    "dashboard_name",
    "description",
    "is_active",
    "is_default",
    "scope",
    "default_period",
    "value_format",
)
DASHBOARD_TABLES = {
    "roles": ("role",),
    "units": ("unit",),
    "filters": ("filter", "default_value"),
    "kpis": ("metric", "enabled", "label", "period", "basis", "aggregation"),
    "charts": (
        "title",
        "enabled",
        "chart_type",
        "dimension",
        "metric",
        "compare_metric",
        "basis",
        "aggregation",
        "period",
        "sort",
        "max_items",
        "width",
    ),
}
HISTORY_DOCTYPES = (SETTINGS, SOURCE, UNIT, DASHBOARD)
HISTORY_LIMIT = 20


def require_admin():
    # frappe.only_for is skipped in tests, so the roles are checked here
    if not is_admin():
        frappe.throw(
            _("Only System Managers and Agent Managers can change the CRM dashboards."),
            frappe.PermissionError,
        )


# ---------- the page ----------


@frappe.whitelist()
def get_settings() -> dict:
    """The reporting currency, what a dashboard can show (the registry), and every source
    and dashboard in summary."""
    require_admin()
    crm = frappe.get_cached_doc(SETTINGS)
    return {
        "currency": crm.dashboard_currency,
        "crm_connection": {"enabled": bool(crm.enabled), "site_url": crm.site_url},
        "registry": describe(),
        "sources": [
            {**source, "running": is_syncing(source.name)}
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
        "dashboards": frappe.qb.get_query(
            DASHBOARD,
            fields=[
                "name",
                "dashboard_name",
                "is_active",
                "is_default",
                "scope",
                "template",
            ],
            order_by="is_default desc, dashboard_name asc",
        ).run(as_dict=True),
        "unit_count": frappe.db.count(UNIT),
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
        "running": is_syncing(doc.name),
        "modified": doc.modified,
        "modified_by": doc.modified_by,
    }


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
    """Deletes the source with its copied leads and its units; the source's own site is
    never touched."""
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


# ---------- the organisation ----------


@frappe.whitelist()
def get_units(source: str | None = None, unit_type: str | None = None) -> list[dict]:
    """The units, each with how many copied leads it has."""
    require_admin()
    filters = {}
    if source:
        filters["source"] = source
    if unit_type:
        filters["unit_type"] = unit_type
    units = frappe.qb.get_query(
        UNIT,
        filters=filters,
        fields=[
            "name",
            "source",
            "unit_type",
            "unit_name",
            "label",
            "is_active",
            "origin",
            *ORG_LEVELS[:-1],
            "user",
            "leader",
        ],
        order_by="unit_type asc, label asc",
    ).run(as_dict=True)
    counts = lead_counts(source)
    for unit in units:
        unit["leads"] = counts.get(
            (unit.source, LEVEL_OF[unit.unit_type], unit.unit_name), 0
        )
    return units


def lead_counts(source: str | None) -> dict[tuple, int]:
    L = frappe.qb.DocType(LEAD)
    counts = {}
    for level in ORG_LEVELS:
        column = getattr(L, level)
        query = (
            frappe.qb.from_(L)
            .select(L.source, column, Count("*"))
            .groupby(L.source, column)
        )
        if source:
            query = query.where(L.source == source)
        for src, value, leads in query.run():
            counts[(src, level, value)] = leads
    return counts


@frappe.whitelist(methods=["POST"])
def save_unit(values: dict, name: str | None = None) -> dict:
    """Add a unit (a team, a branch the leads don't carry yet...) or change where one sits.
    Its type, source and name on the leads are fixed once saved."""
    require_admin()
    if name:
        doc = frappe.get_doc(UNIT, name)
    else:
        doc = frappe.new_doc(UNIT)
        doc.update({k: values.get(k) for k in ("source", "unit_type", "unit_name")})
    allowed = set(UNIT_FIELDS) - {
        level
        for level in ORG_LEVELS[:-1]
        if level not in UNIT_PARENTS.get(doc.unit_type, ())
    }
    doc.update({k: v for k, v in values.items() if k in allowed})
    doc.save()
    return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def set_unit_active(name: str, active: bool) -> dict:
    """An inactive unit's leads are left out of every dashboard; switching it on counts them
    again."""
    require_admin()
    doc = frappe.get_doc(UNIT, name)
    doc.is_active = 1 if active else 0
    doc.save()
    return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def delete_unit(name: str) -> dict:
    require_admin()
    frappe.delete_doc(UNIT, name)
    return {"deleted": name}


# ---------- dashboards ----------


@frappe.whitelist()
def get_dashboard_config(name: str) -> dict:
    require_admin()
    doc = frappe.get_doc(DASHBOARD, name)
    labels = {
        u.name: u
        for u in frappe.qb.get_query(
            UNIT,
            fields=["name", "unit_type", "label", "source"],
            filters={"name": ["in", [r.unit for r in doc.units] or [""]]},
        ).run(as_dict=True)
    }
    config = {
        f: doc.get(f)
        for f in ("name", "template", "modified", "modified_by", *DASHBOARD_FIELDS)
    }
    for table, fields in DASHBOARD_TABLES.items():
        config[table] = [{f: row.get(f) for f in fields} for row in doc.get(table)]
    config["units"] = [
        {
            "unit": r.unit,
            **(
                {k: labels[r.unit][k] for k in ("unit_type", "label", "source")}
                if r.unit in labels
                else {}
            ),
        }
        for r in doc.units
    ]
    return config


@frappe.whitelist(methods=["POST"])
def save_dashboard(values: dict, name: str) -> dict:
    require_admin()
    doc = frappe.get_doc(DASHBOARD, name)
    doc.update({k: v for k, v in values.items() if k in DASHBOARD_FIELDS})
    for table, fields in DASHBOARD_TABLES.items():
        if table in values:
            doc.set(
                table, [{f: row.get(f) for f in fields} for row in values[table] or []]
            )
    doc.save()
    return get_dashboard_config(doc.name)


@frappe.whitelist(methods=["POST"])
def create_dashboard(template: str, dashboard_name: str) -> dict:
    """A new dashboard from one of the templates; it starts inactive, so nobody but admins
    sees it until it's switched on."""
    require_admin()
    doc = HDCRMDashboard.from_template(template, dashboard_name.strip())
    doc.is_active = 0
    doc.insert()
    return get_dashboard_config(doc.name)


@frappe.whitelist(methods=["POST"])
def duplicate_dashboard(name: str, dashboard_name: str) -> dict:
    require_admin()
    doc = frappe.get_doc(DASHBOARD, name).duplicate(dashboard_name.strip())
    doc.insert()
    return get_dashboard_config(doc.name)


@frappe.whitelist(methods=["POST"])
def set_dashboard_active(name: str, active: bool) -> dict:
    require_admin()
    doc = frappe.get_doc(DASHBOARD, name)
    doc.is_active = 1 if active else 0
    doc.save()
    return {"name": doc.name, "is_active": doc.is_active}


@frappe.whitelist(methods=["POST"])
def delete_dashboard(name: str) -> dict:
    require_admin()
    frappe.delete_doc(DASHBOARD, name)
    return {"deleted": name}


# ---------- change history ----------


@frappe.whitelist()
def get_history(doctype: str, name: str) -> dict:
    """{created_by, created_on, changes: [{at, by, lines}]}: who changed a source, unit,
    dashboard or the reporting currency, and what, newest first. Secrets show as masked."""
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
