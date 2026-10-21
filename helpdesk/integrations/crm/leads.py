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
    who is a Sales Employee or in one of the Leads teams (any active agent when no team
    is picked)."""
    from helpdesk.content_team import SALES_EMPLOYEE_ROLE
    from helpdesk.utils import is_agent

    user = user or frappe.session.user
    if user == "Guest" or not leads_on():
        return False
    if user == "Administrator" or MANAGER_ROLES & set(frappe.get_roles(user)):
        return True
    if not is_agent(user) or not frappe.db.get_value("HD Agent", user, "is_active"):
        return False
    teams = leads_teams()
    # a salesperson's screens are the sales ones, whatever team they are in
    if not teams or SALES_EMPLOYEE_ROLE in frappe.get_roles(user):
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


def call(
    method: str,
    post: bool = False,
    api: str = API,
    acting_user: str | None = None,
    **params,
):
    """`<api>.<method>` on the CRM site (TBO Smart's hub leads API by default, or its hub
    proposals API) as the signed-in person (or `acting_user`, for a call the hub makes on
    someone's behalf); any failure becomes a LeadsError the person can act on."""
    try:
        client = CRMClient.from_settings()
    except CRMError:
        fail(
            LeadsUnavailableError(
                _("Leads aren't connected yet. Ask an admin to set up Settings → CRM.")
            )
        )
    try:
        return client.call(
            f"{api}.{method}",
            post=post,
            acting_user=acting_user or frappe.session.user,
            **params,
        )
    except CRMError as e:
        fail(friendly_error(e, client, acting_user))


def download(method: str, api: str = API, **params) -> tuple[bytes, str]:
    """A file from `<api>.<method>` on the CRM site as the signed-in person: (bytes,
    content type); failures as `call`'s."""
    try:
        client = CRMClient.from_settings()
    except CRMError:
        fail(
            LeadsUnavailableError(
                _("Leads aren't connected yet. Ask an admin to set up Settings → CRM.")
            )
        )
    try:
        return client.download(
            f"{api}.{method}", acting_user=frappe.session.user, **params
        )
    except CRMError as e:
        fail(friendly_error(e, client))


def fail(error: LeadsError):
    # through frappe.throw, so the message reaches the page; a bare raise shows people only
    # "Internal Server Error"
    frappe.throw(str(error), exc=type(error))


def friendly_error(
    error: CRMError, client, acting_user: str | None = None
) -> LeadsError:
    """A message the person can act on; it names the user the ERP site checked (`acting_user`
    for a call made on someone's behalf)."""
    user = acting_user or frappe.session.user
    site_url = client.base
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
    if error.status == 403 and "an integration user, not a person" in detail.casefold():
        # the person signed in here holds the ERP site's integration role themselves
        return LeadsError(
            _(
                "Your user {0} on {1} has the Hub Integration role, which is only for the hub's API user. Ask an admin to remove it from your user there (keep Sales User or Sales Manager)."
            ).format(user, site)
        )
    if error.status == 403 and "integration user" in detail.casefold():
        return LeadsUnavailableError(
            _(
                "The hub's API user{0} on {1} isn't the site's integration user: it needs the role in TBO Smart Settings → Hub integration role there (blank: Hub Integration). Ask an admin to add the role that field names to that user."
            ).format(api_user(client), site)
        )
    if error.status == 403:
        return LeadsError(
            _(
                "You don't have a sales account on the ERP site yet. Ask an admin to give {0} the Sales User role on {1}."
            ).format(user, site)
        )
    if error.status == 404:
        return LeadsError(
            _("That lead isn't on the ERP site any more, or you can't see it.")
        )
    if error.status < 500 and error.user_message:
        # the ERP site's own reason, e.g. a missing field or a stage it doesn't allow;
        # never its exception text
        return LeadsError(error.user_message)
    return LeadsUnavailableError(
        _(
            "The ERP site ran into a problem ({0}). Try again; if it keeps happening, tell an admin."
        ).format(error.status)
    )


def not_deployed(detail: str) -> bool:
    text = detail.casefold()
    return any(hint.casefold() in text for hint in NOT_DEPLOYED_HINTS)


def api_user(client) -> str:
    """The user the hub's API key belongs to, as " (email)": which user an admin has to
    give the integration role to. Empty when the site can't say."""
    try:
        email = client.logged_user()
    except CRMError:
        return ""
    return f" ({email})" if email else ""
