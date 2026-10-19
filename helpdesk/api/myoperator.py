"""Settings → Telephony → MyOperator: lead calls through MyOperator, set up on the ERP
site (TBO Smart's docs/telephony-myoperator.md). Thin proxies to its telephony API as the
signed-in person; the ERP site lets only its System Managers read or change them, and no
secret ever comes back (a new webhook secret once, right after it is made)."""

import frappe
from frappe import _

from helpdesk.integrations.crm.leads import MANAGER_ROLES, call, require_leads

TELEPHONY = "tbo_smart.api.telephony"


def require_editor() -> None:
    """Hub admins and managers who use leads; the ERP site checks its own role too."""
    require_leads()
    if frappe.session.user != "Administrator" and not (
        MANAGER_ROLES & set(frappe.get_roles())
    ):
        frappe.throw(
            _("Only an admin can change the telephony settings."),
            frappe.PermissionError,
        )


def telephony(method: str, post: bool = False, **params):
    return call(method, post=post, api=TELEPHONY, **params)


@frappe.whitelist()
def get_settings() -> dict:
    """The settings, the people mapping, which secrets are saved, the webhook to paste
    into MyOperator and the ERP site's sales users."""
    require_editor()
    return telephony("get_settings") or {}


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    require_editor()
    values = frappe.parse_json(values) if isinstance(values, str) else values
    if not isinstance(values, dict):
        frappe.throw(_("Send the values as a set of fields."))
    return telephony("save_settings", post=True, values=values) or {}


@frappe.whitelist(methods=["POST"])
def test_connection() -> dict:
    """Checks the saved keys without placing a call; lists MyOperator's users."""
    require_editor()
    return telephony("test_connection", post=True) or {}


@frappe.whitelist(methods=["POST"])
def regenerate_webhook_secret() -> dict:
    """{secret, header, url}: shown once; MyOperator needs it before calls land again."""
    require_editor()
    return telephony("regenerate_webhook_secret", post=True) or {}
