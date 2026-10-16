"""Sales leads, live from ERPNext on the CRM site (docs/leads.md).

The hub keeps no copy: every read and write goes to TBO Smart's hub leads API there
(`tbo_smart.api.hub_leads.<method>`) over the CRM connection in HD CRM Settings, with
`acting_user` set to the person signed in here. The CRM site attributes writes to them
and shows them only the leads they may see.
"""

from urllib.parse import urlparse

import frappe
from frappe import _

from helpdesk.integrations.crm.client import CRMClient, CRMError

API = "tbo_smart.api.hub_leads"
MANAGER_ROLES = {"System Manager", "Agent Manager"}
# what Frappe answers when a whitelisted method isn't there (an older TBO Smart)
NOT_DEPLOYED_HINTS = (
    "failed to get method",
    "is not whitelisted",
    "no module named",
    "has no attribute",
)


class LeadsError(frappe.ValidationError):
    """A lead request that couldn't be done, with a message for the person."""


class LeadsUnavailableError(LeadsError):
    """The CRM site can't be used for leads right now (setup, reach or version)."""


def leads_on() -> bool:
    return bool(
        frappe.db.get_single_value("HD CRM Settings", "enabled")
        and frappe.db.get_single_value("HD CRM Settings", "enable_leads")
    )


def leads_teams() -> list[str]:
    raw = frappe.db.get_single_value("HD CRM Settings", "leads_teams") or ""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def can_use_leads(user: str | None = None) -> bool:
    """Leads are on, and `user` is a System Manager or Agent Manager, or an active agent
    in one of the Leads teams (any active agent when no team is picked)."""
    from helpdesk.utils import is_agent

    user = user or frappe.session.user
    if user == "Guest" or not leads_on():
        return False
    if user == "Administrator" or MANAGER_ROLES & set(frappe.get_roles(user)):
        return True
    if not is_agent(user) or not frappe.db.get_value("HD Agent", user, "is_active"):
        return False
    teams = leads_teams()
    if not teams:
        return True
    team, member = frappe.qb.DocType("HD Team"), frappe.qb.DocType("HD Team Member")
    return bool(
        frappe.qb.from_(member)
        .join(team)
        .on(team.name == member.parent)
        .select(member.name)
        .where(member.user == user)
        .where(team.name.isin(teams))
        .where(team.disabled == 0)
        .limit(1)
        .run()
    )


def require_leads():
    if not can_use_leads():
        frappe.throw(
            _(
                "Leads aren't turned on for you. Ask an admin to add your team in Settings → CRM."
            ),
            frappe.PermissionError,
        )


def call(method: str, post: bool = False, **params):
    """`tbo_smart.api.hub_leads.<method>` on the CRM site as the signed-in person; any
    failure becomes a LeadsError the person can act on."""
    try:
        client = CRMClient.from_settings()
    except CRMError:
        raise LeadsUnavailableError(
            _("Leads aren't connected yet. Ask an admin to set up Settings → CRM.")
        ) from None
    try:
        return client.call(
            f"{API}.{method}", post=post, acting_user=frappe.session.user, **params
        )
    except CRMError as e:
        raise friendly_error(e, client.base) from None


def friendly_error(error: CRMError, site_url: str) -> LeadsError:
    site = urlparse(site_url).netloc or site_url
    detail = error.detail or ""
    if error.status is None:
        return LeadsUnavailableError(
            _("Couldn't reach the ERP site ({0}). Try again in a minute.").format(site)
        )
    if error.status == 401:
        return LeadsUnavailableError(
            _(
                "The ERP site refused the hub's API key. Ask an admin to check Settings → CRM."
            )
        )
    if error.status in (403, 404, 417) and not_deployed(detail):
        return LeadsUnavailableError(
            _("Leads need the latest TBO Smart on the ERP site ({0}).").format(site)
        )
    if error.status == 403:
        return LeadsError(
            _(
                "You don't have a sales account on the ERP site yet. Ask an admin to give {0} the Sales User role on {1}."
            ).format(frappe.session.user, site)
        )
    if error.status == 404:
        return LeadsError(
            _("That lead isn't on the ERP site any more, or you can't see it.")
        )
    if error.status < 500 and detail:
        # the ERP site's own reason, e.g. a missing field or a stage it doesn't allow
        return LeadsError(detail)
    return LeadsUnavailableError(
        _(
            "The ERP site ran into a problem ({0}). Try again; if it keeps happening, tell an admin."
        ).format(error.status)
    )


def not_deployed(detail: str) -> bool:
    text = detail.casefold()
    return any(hint.casefold() in text for hint in NOT_DEPLOYED_HINTS)
