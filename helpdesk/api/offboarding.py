"""Settings → General → Mobile app: Preview and Run now for offboarding from
Microsoft (helpdesk.offboarding, docs/tbo-smart-api.md "Offboarding")."""

import frappe
from frappe import _

from helpdesk import offboarding, teams_meetings


@frappe.whitelist(methods=["POST"])
def preview_offboarding() -> dict:
    """Who a run would disable now, changing nothing; works with the switch off."""
    settings = system_manager_settings()
    return run_safely(settings, dry_run=True)


@frappe.whitelist(methods=["POST"])
def run_offboarding() -> dict:
    """Runs the hourly job now, with the saved settings (dry run and limit included)."""
    settings = system_manager_settings()
    if not settings.offboard_removed_microsoft_users:
        frappe.throw(_("Turn on Disable people removed from Microsoft and save first."))
    return run_safely(settings, dry_run=bool(settings.offboarding_dry_run))


def system_manager_settings():
    # only_for is skipped in tests, so check the role directly
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            _("Only System Managers can run offboarding."), frappe.PermissionError
        )
    return frappe.get_single("HD Settings")


def run_safely(settings, dry_run: bool) -> dict:
    # a run right after granting User.Read.All must not reuse the old sign-in
    teams_meetings.forget_token()
    try:
        return offboarding.offboard(settings, dry_run=dry_run)
    except offboarding.OffboardingStopped as e:
        frappe.throw(str(e), title=_("Offboarding stopped"))
