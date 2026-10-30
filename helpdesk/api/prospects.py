"""Find prospects (docs/leads.md, "Find prospects"): businesses found by industry and district
land in a lead department's unassigned pool. Thin proxies to TBO Smart's hub leads API
(`estimate_prospect_run`, `start_prospect_run`, `get_prospect_runs`, `get_prospect_run`); the ERP
site decides who may, prices the run, keeps the monthly cap and does the searching."""

import frappe
from frappe import _

from helpdesk.api.leads import clear_cached_reads, parse_data
from helpdesk.integrations.crm.leads import (
    LeadsUnavailableError,
    call_if_deployed,
    require_leads,
)

OLDER_ERP = "The ERP site can't find prospects yet. It needs the latest TBO Smart."
NOT_ALLOWED = "Only managers and department heads can find prospects."


def ask(method: str, post: bool = False, **params):
    """The ERP site's answer; an older TBO Smart says so in words."""
    require_leads()
    result = call_if_deployed(
        method, post=post, permission_message=_(NOT_ALLOWED), **params
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    return result


@frappe.whitelist(methods=["POST"])
def estimate_prospect_run(values: dict | str) -> dict:
    """Prices a search before anything is searched or bought. `values`: `industry`, `state`,
    `districts` (a list), `provider`, `max_results`, `department`; `name` estimates a draft
    again. Returns the run, Estimated, with its `estimated_cost` (USD), `expected_count` and
    `estimate_note`."""
    return ask("estimate_prospect_run", post=True, values=parse_data(values))


@frappe.whitelist(methods=["POST"])
def start_prospect_run(name: str) -> dict:
    """Starts an estimated run in the background on the ERP site. It refuses a paid run that
    would pass the monthly spend cap."""
    run = ask("start_prospect_run", post=True, name=name)
    clear_cached_reads()
    return run


@frappe.whitelist()
def get_prospect_runs() -> dict:
    """The newest runs the person may see. Never cached: a running run's counts grow.
    `available` is false while the ERP site is older than this."""
    require_leads()
    runs = call_if_deployed("get_prospect_runs", permission_message=_(NOT_ALLOWED))
    if runs is None:
        return {"available": False, "runs": []}
    return {"available": True, "runs": runs}


@frappe.whitelist()
def get_prospect_run(name: str) -> dict:
    """One run with its log and the leads it created (each with its Why call line)."""
    return ask("get_prospect_run", name=name)
