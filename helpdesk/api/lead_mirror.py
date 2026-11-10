"""Settings → CRM: the local copy of the ERP's leads, switched on and off, its health, and a
rebuild (docs/lead-mirror.md)."""

import json

import frappe
from frappe import _

from helpdesk.api.crm import require_admin
from helpdesk.helpdesk.doctype.hd_lead_mirror.hd_lead_mirror import HDLeadMirror
from helpdesk.lead_mirror import MIRROR, STATE, enqueue_backfill, is_running, set_state


@frappe.whitelist()
def get_health() -> dict:
    """{enabled, copying, leads_copied, erp_total, last_synced_on, lag_seconds, last_error,
    last_compared_on, compare_result}: what the Settings → CRM health line shows."""
    require_admin()
    state = frappe.get_single(STATE)
    return {
        "enabled": bool(state.enabled),
        # a status left "Copying" by a run that died is not copying
        "copying": state.backfill_status == "Copying" and is_running(),
        "leads_copied": frappe.db.count(MIRROR),
        "erp_total": state.erp_total,
        "last_synced_on": state.last_synced_on,
        "lag_seconds": state.lag_seconds,
        "last_error": state.last_error,
        "last_compared_on": state.last_compared_on,
        "compare_result": state.compare_result,
        "people_in_scopes": len(json.loads(state.scopes or "{}")),
    }


@frappe.whitelist(methods=["POST"])
def set_enabled(enabled: bool) -> dict:
    """Turn the copy on (it starts filling in the background) or off (it stops syncing and
    keeps what it has)."""
    require_admin()
    enabled = frappe.parse_json(enabled) if isinstance(enabled, str) else enabled
    if enabled and not frappe.db.get_single_value("HD CRM Settings", "enabled"):
        frappe.throw(_("Turn the CRM connection on first."))
    set_state(enabled=1 if enabled else 0)
    if enabled:
        # a copy left off for a while is walked again, which only copies what changed
        enqueue_backfill()
    return get_health()


@frappe.whitelist(methods=["POST"])
def rebuild() -> dict:
    """Throw the copy away and fill it again from the ERP. The ERP is never touched."""
    require_admin()
    if not frappe.db.get_single_value(STATE, "enabled"):
        frappe.throw(_("Turn the local copy on first."))
    if is_running():
        frappe.throw(
            _(
                "The copy is being filled in or checked right now. Try again in a few minutes."
            )
        )
    HDLeadMirror.clear()
    set_state(since="", backfill_status="Idle", leads_mirrored=0, last_error="")
    frappe.db.commit()  # nosemgrep
    enqueue_backfill()
    return get_health()
