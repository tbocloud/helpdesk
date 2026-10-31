"""Sales commission (docs/leads.md, "Commission"): thin proxies to TBO Smart's
`tbo_smart.api.hub_commission`. The ERP site holds the plans, project set-ups and statements,
works the money out from its receipts and decides who sees whose commission and who approves it;
the hub only shows and asks. Nothing here is cached: a statement changes when it is approved."""

import frappe
from frappe import _

from helpdesk.api.leads import parse_data
from helpdesk.integrations.crm.leads import (
    LeadsUnavailableError,
    call_if_deployed,
    require_leads,
)

COMMISSION = "tbo_smart.api.hub_commission"
OLDER_ERP = "The ERP site can't work out commission yet. It needs the latest TBO Smart."
MANAGERS_ONLY = "Only a Sales Manager, System Manager or TBO Management on the ERP site can do this."


def ask(method: str, post: bool = False, **params):
    """The ERP site's answer as the signed-in person; an older TBO Smart says so in words."""
    require_leads()
    result = call_if_deployed(
        method,
        post=post,
        api=COMMISSION,
        permission_message=_(MANAGERS_ONLY),
        **params,
    )
    if result is None:
        frappe.throw(_(OLDER_ERP), LeadsUnavailableError)
    return result


def read(method: str, **params) -> dict:
    """A read that stays quietly unavailable on an older ERP site: `{available: False}`."""
    require_leads()
    result = call_if_deployed(
        method, api=COMMISSION, permission_message=_(MANAGERS_ONLY), **params
    )
    if result is None:
        return {"available": False}
    return {**result, "available": True}


@frappe.whitelist()
def get_commission(
    month: str, user: str | None = None, department: str | None = None
) -> dict:
    """The month's commission, per person and project, as the signed-in person may see it
    (a salesperson their own, a department head their department's, a manager everyone's, with
    the money that could not be attributed). `available` is false on an older ERP site."""
    return read(
        "get_commission",
        month=month,
        user=(user or "").strip() or None,
        department=(department or "").strip() or None,
    )


@frappe.whitelist(methods=["POST"])
def generate_statements(month: str) -> list:
    """Managers: creates or refreshes the month's Draft statements. Approved and Paid ones are
    left as they are (`skipped`)."""
    return ask("generate_statements", post=True, month=month)


@frappe.whitelist(methods=["POST"])
def approve_statement(name: str) -> dict:
    """A manager approves a Draft statement. Nobody but a System Manager approves their own."""
    return ask("approve_statement", post=True, name=name)


@frappe.whitelist(methods=["POST"])
def mark_paid(name: str) -> dict:
    """A manager marks an Approved statement paid."""
    return ask("mark_paid", post=True, name=name)


@frappe.whitelist()
def get_commission_plans() -> dict:
    """Managers: the commission plans, the departments and lead types they can name."""
    return read("get_commission_plans")


@frappe.whitelist(methods=["POST"])
def save_commission_plan(values: dict | str, name: str | None = None) -> dict:
    """Managers: adds a plan, or edits `name`: its rule conditions (department, lead type,
    project type, user), basis, target, above-target rate and slabs."""
    return ask(
        "save_commission_plan",
        post=True,
        values=frappe.as_json(parse_data(values)),
        name=name or None,
    )


@frappe.whitelist()
def get_project_commission(project: str) -> dict:
    """Managers: who earns commission on the project, by which plan or slabs, with what has
    been collected on it and credited so far."""
    return read("get_project_commission", project=project)


@frappe.whitelist(methods=["POST"])
def save_project_commission(values: dict | str) -> dict:
    """Managers: sets who earns on a project (shares adding up to 100) and its plan or own
    slabs."""
    return ask(
        "save_project_commission",
        post=True,
        values=frappe.as_json(parse_data(values)),
    )
