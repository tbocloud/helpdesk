"""Leads read from the hub's local copy while the ERP can't be used (docs/lead-mirror.md,
phase 2a).

The ERP is still asked first, every time. Only when it can't answer (down, being updated,
unreachable) do the Leads list and a lead's page read `HD Lead Mirror` instead, read only, and
say so with the time of the copy. A person sees in the copy exactly the leads the ERP would show
them: their scope (`HD Lead Sync State.scopes`, refreshed by every sync) decides.
"""

import json

import frappe
from frappe.query_builder.functions import Count
from frappe.utils import cint

from helpdesk.helpdesk.doctype.hd_lead_mirror.hd_lead_mirror import DOCTYPE as MIRROR
from helpdesk.lead_mirror import STATE, mirror_on

ASSIGNEE = "HD Lead Mirror Assignee"
SEARCH_COLUMNS = ("name", "lead_name", "company_name", "mobile_no", "email_id")
# list filter -> the copy's column; each takes one value or a list (any of them)
FILTER_COLUMNS = {
    "stage": "tbo_stage",
    "owner": "lead_owner",
    "department": "department",
    "source": "source",
    "temperature": "temperature",
    "industry": "industry",
    "state": "state",
    "district": "district",
    "org_size": "org_size",
    "product": "product",
    "last_call_result": "last_call_result",
}
# what the person may do is the ERP's to say: the copy is for reading
READ_ONLY = {
    "can_write": False,
    "can_call": False,
    "can_remove_numbers": False,
    "can_merge": False,
}


def ready() -> bool:
    """The copy is on and its first full copy has finished (`since` is set only then; an
    empty Datetime such as `last_synced_on` reads back as now, so it can't tell)."""
    return bool(mirror_on() and frappe.db.get_single_value(STATE, "since"))


def scope_of(user: str) -> dict | None:
    """{all, team, departments} of `user` as the ERP gave it; None for someone it doesn't
    know (they see nothing in the copy)."""
    scopes = json.loads(frappe.db.get_single_value(STATE, "scopes") or "{}")
    return scopes.get(user)


def visible(Copy, scope: dict):
    """The criterion for the leads `scope` may see; None when it sees every lead."""
    if scope.get("all"):
        return None
    team = scope.get("team") or []
    Assignee = frappe.qb.DocType(ASSIGNEE)
    assigned = (
        frappe.qb.from_(Assignee)
        .select(Assignee.parent)
        .where((Assignee.parenttype == MIRROR) & Assignee.user.isin(team or [""]))
    )
    criterion = Copy.lead_owner.isin(team or [""]) | Copy.name.isin(assigned)
    departments = scope.get("departments") or []
    if departments:
        criterion = criterion | Copy.department.isin(departments)
    return criterion


def values_of(value) -> list[str]:
    """One value, a list or a JSON list, as a list without blanks."""
    if isinstance(value, str) and value.strip().startswith("["):
        value = json.loads(value)
    values = value if isinstance(value, (list, tuple)) else [value]
    return [str(v) for v in values if v not in (None, "")]


def list_copy(
    user: str,
    search: str | None = None,
    mine: bool = False,
    start: int = 0,
    page_length: int = 20,
    **filters,
) -> dict | None:
    """A page of the leads `user` may see, from the copy, the last changed first:
    {rows, total, from_copy, copied_at}. `filters` are FILTER_COLUMNS' keys. None when the
    ERP never told the hub who this person is."""
    scope = scope_of(user)
    if scope is None:
        return None
    Copy = frappe.qb.DocType(MIRROR)
    criterion = visible(Copy, scope)
    conditions = [] if criterion is None else [criterion]
    if mine:
        conditions.append(Copy.lead_owner == user)
    for key, column in FILTER_COLUMNS.items():
        wanted = values_of(filters.get(key))
        if wanted:
            conditions.append(Copy[column].isin(wanted))
    text = (search or "").strip()
    if text:
        like = Copy[SEARCH_COLUMNS[0]].like(f"%{text}%")
        for column in SEARCH_COLUMNS[1:]:
            like = like | Copy[column].like(f"%{text}%")
        conditions.append(like)

    def query(*columns):
        q = frappe.qb.from_(Copy).select(*columns)
        for condition in conditions:
            q = q.where(condition)
        return q

    total = query(Count(Copy.name)).run()[0][0]
    rows = (
        query(Copy.list_row)
        .orderby(Copy.erp_modified, order=frappe.qb.desc)
        .orderby(Copy.name)
        .limit(cint(page_length))
        .offset(cint(start))
        .run(pluck=True)
    )
    return {
        "rows": [json.loads(row or "{}") for row in rows],
        "total": total,
        "from_copy": True,
        "copied_at": str(frappe.db.get_single_value(STATE, "last_synced_on")),
    }


def lead_copy(user: str, name: str) -> dict | None:
    """The lead's page as the ERP last gave it (`get_lead`), read only, with `from_copy` and
    `copied_at`. None when there is no copy of it or `user` may not see it."""
    scope = scope_of(user)
    if scope is None:
        return None
    Copy = frappe.qb.DocType(MIRROR)
    query = (
        frappe.qb.from_(Copy)
        .select(Copy.payload, Copy.synced_at)
        .where(Copy.name == name)
    )
    criterion = visible(Copy, scope)
    if criterion is not None:
        query = query.where(criterion)
    found = query.run(as_dict=True)
    if not found:
        return None
    detail = json.loads(found[0].payload or "{}")
    if not detail.get("lead"):
        return None
    detail["lead"].update(READ_ONLY)
    detail.update(
        allowed_stages=[], from_copy=True, copied_at=str(found[0].synced_at)
    )
    return detail
