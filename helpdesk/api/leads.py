"""The Leads page: sales leads read and written live in ERPNext on the CRM site, as the
signed-in person (docs/leads.md). Thin proxies to `tbo_smart.api.hub_leads`; the CRM
site decides what each person may see and do, and the API key never leaves the hub."""

import frappe
from frappe import _
from frappe.utils import cint

from helpdesk.integrations.crm.leads import call, require_leads

VIEWS = ("all", "mine", "call_today", "follow_up")
PERIODS = ("week", "month", "quarter", "custom")
MAX_PAGE = 100


@frappe.whitelist()
def get_options() -> dict:
    """Stages, sources, segments, owners, territories and industries for the pickers."""
    require_leads()
    return call("get_options") or {}


@frappe.whitelist()
def list_leads(
    search: str | None = None,
    stage: str | None = None,
    owner: str | None = None,
    segment: str | None = None,
    view: str = "all",
    start: int | str = 0,
    page_length: int | str = 20,
    source: str | None = None,
    temperature: str | None = None,
    metric: str | None = None,
    period: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """A page of leads. `metric` with its period keeps the leads one number of the
    Overview counts (the ERP site picks them)."""
    require_leads()
    if view not in VIEWS:
        frappe.throw(_("Pick All, Mine, Call today or Follow-up."))
    if period and period not in PERIODS:
        frappe.throw(_("Pick a week, a month, a quarter or your own dates."))
    result = call(
        "list_leads",
        search=(search or "").strip() or None,
        stage=stage or None,
        owner=owner or None,
        segment=segment or None,
        source=source or None,
        temperature=temperature or None,
        metric=metric or None,
        period=(period or None) if metric else None,
        from_date=(from_date or None) if metric else None,
        to_date=(to_date or None) if metric else None,
        view=view,
        # cint: a malformed number is 0, never a server error
        start=max(cint(start), 0),
        page_length=min(max(cint(page_length) or 20, 1), MAX_PAGE),
    )
    return result or {"rows": [], "total": 0}


@frappe.whitelist()
def get_overview(
    period: str = "month",
    from_date: str | None = None,
    to_date: str | None = None,
    owner: str | None = None,
) -> dict:
    """The Overview: the pipeline, the funnel and the period's figures for the
    leads the signed-in person may see (theirs, their team's or everyone's)."""
    require_leads()
    if period not in PERIODS:
        frappe.throw(_("Pick a week, a month, a quarter or your own dates."))
    if period == "custom" and not (from_date and to_date):
        frappe.throw(_("Pick both dates for your own period."))
    return (
        call(
            "get_overview",
            period=period,
            from_date=from_date if period == "custom" else None,
            to_date=to_date if period == "custom" else None,
            owner=owner or None,
        )
        or {}
    )


@frappe.whitelist()
def get_lead(name: str) -> dict:
    """The lead, its timeline, its quotations and the stages it may move to."""
    require_leads()
    return call("get_lead", name=name) or {}


@frappe.whitelist(methods=["POST"])
def create_lead(data: dict | str) -> dict:
    require_leads()
    return call("create_lead", post=True, data=parse_data(data)) or {}


@frappe.whitelist(methods=["POST"])
def update_lead(name: str, data: dict | str) -> dict:
    require_leads()
    return call("update_lead", post=True, name=name, data=parse_data(data)) or {}


@frappe.whitelist(methods=["POST"])
def set_stage(name: str, stage: str, note: str | None = None) -> dict:
    require_leads()
    return (
        call(
            "set_stage",
            post=True,
            name=name,
            stage=stage,
            note=(note or "").strip() or None,
        )
        or {}
    )


@frappe.whitelist(methods=["POST"])
def add_note(name: str, note: str) -> dict:
    require_leads()
    note = (note or "").strip()
    if not note:
        frappe.throw(_("Write the note first."))
    return call("add_note", post=True, name=name, note=note) or {}


def parse_data(data: dict | str) -> dict:
    data = frappe.parse_json(data) if isinstance(data, str) else data
    if not isinstance(data, dict):
        frappe.throw(_("The lead's details must be a set of fields."))
    return data
