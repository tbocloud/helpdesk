"""The Leads page: sales leads read and written live in ERPNext on the CRM site, as the
signed-in person (docs/leads.md). Thin proxies to `tbo_smart.api.hub_leads`; the CRM
site decides what each person may see and do, and the API key never leaves the hub."""

import frappe
from frappe import _
from frappe.utils import cint

from helpdesk.integrations.crm.leads import call, require_leads

VIEWS = ("all", "mine", "call_today", "follow_up")
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
) -> dict:
    require_leads()
    if view not in VIEWS:
        frappe.throw(_("Pick All, Mine, Call today or Follow-up."))
    result = call(
        "list_leads",
        search=(search or "").strip() or None,
        stage=stage or None,
        owner=owner or None,
        segment=segment or None,
        view=view,
        # cint: a malformed number is 0, never a server error
        start=max(cint(start), 0),
        page_length=min(max(cint(page_length) or 20, 1), MAX_PAGE),
    )
    return result or {"rows": [], "total": 0}


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
