"""Offboarding: someone TBO removes from Microsoft loses the hub too
(docs/tbo-smart-api.md, "Offboarding").

Microsoft is the only sign-in for TBO staff, so access must end with the Microsoft
account. Two parts:

- Disabling a User revokes their OAuth Bearer Tokens (`revoke_tokens_of_disabled_user`,
  a User doc event). Frappe already refuses a disabled user's bearer tokens and
  sessions; revoking makes that permanent even if the User is enabled again.
- Every hour, when switched on in HD Settings, `run` reads TBO's tenant through
  Microsoft Graph (app-only, the Entra app from HD Meeting Settings, which needs
  User.Read.All) and disables each enabled hub User whose company address belongs to
  an account that is disabled in Microsoft or no longer exists there. Assignments and
  history stay as they are.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime
from frappe.utils.user import get_users_with_role
from requests import RequestException

from helpdesk import teams_meetings
from helpdesk.work_reminders import notify_users

LOG = "HD Offboarding Log"
REQUIRED_ROLE = "User.Read.All"
SELECT = "id,accountEnabled,mail,userPrincipalName,otherMails,proxyAddresses"
# Graph's largest page for /users
PAGE_SIZE = 999
DEFAULT_CAP = 5
PROTECTED_ROLE = "System Manager"
ALWAYS_PROTECTED = {"Administrator", "Guest"}
DISABLED = "Disabled in Microsoft"
MISSING = "Not in Microsoft"
ERROR_TITLE = "Offboarding from Microsoft stopped"
PEOPLE_LINK = "/agents"


class OffboardingStopped(Exception):
    """A safety rule stopped the run before anyone was disabled; the message says why."""


def revoke_tokens_of_disabled_user(doc, method=None):
    """User on_update: a User who was just disabled loses every OAuth token."""
    if doc.has_value_changed("enabled") and not cint(doc.enabled):
        revoke_bearer_tokens(doc.name)


def revoke_bearer_tokens(user: str):
    token = frappe.qb.DocType("OAuth Bearer Token")
    (
        frappe.qb.update(token)
        .set(token.status, "Revoked")
        .where((token.user == user) & (token.status == "Active"))
        .run()
    )


def run():
    """Hourly job. Off unless switched on; any failure means nobody is disabled."""
    settings = frappe.get_single("HD Settings")
    if not settings.offboard_removed_microsoft_users:
        return
    try:
        offboard(settings, dry_run=bool(settings.offboarding_dry_run))
    except OffboardingStopped as e:
        frappe.log_error(title=ERROR_TITLE, message=str(e))


def offboard(settings, dry_run: bool) -> dict:
    """Finds who has left Microsoft and, unless `dry_run`, disables them. Returns
    {status: "dry_run" | "capped" | "done", people: [{user, full_name, reason}], cap}.
    Raises OffboardingStopped when Graph fails or its answer looks wrong."""
    domains = company_domains(settings.offboarding_domains)
    if not domains:
        raise OffboardingStopped(_("Add the company email domains first."))
    directory = directory_status(read_directory(), domains)
    people = leavers(directory, domains)
    cap = cint(settings.offboarding_max_disables) or DEFAULT_CAP
    if dry_run:
        return {"status": "dry_run", "people": people, "cap": cap}
    if len(people) > cap:
        alert_admins(people, cap)
        return {"status": "capped", "people": people, "cap": cap}
    for person in people:
        disable(person)
    notify_managers(people)
    return {"status": "done", "people": people, "cap": cap}


def company_domains(value: str | None) -> set[str]:
    """The domains from the setting: separated by commas, spaces or new lines."""
    text = (value or "").replace(",", " ").lower()
    return {d.strip().lstrip("@") for d in text.split() if d.strip().lstrip("@")}


def email_domain(email: str | None) -> str:
    return (email or "").rpartition("@")[2].strip().lower()


def read_directory() -> list[dict]:
    """Every account in the tenant. Never acts on a failed or partial read."""
    if not teams_meetings.get_settings().connected_app:
        raise OffboardingStopped(
            _("Choose the Microsoft app in HD Meeting Settings first.")
        )
    try:
        return teams_meetings.graph_list(
            f"/users?$select={SELECT}&$top={PAGE_SIZE}", REQUIRED_ROLE
        )
    except (teams_meetings.GraphError, RequestException) as e:
        raise OffboardingStopped(
            _("Couldn't read the people in Microsoft: {0}").format(str(e))
        ) from e


def directory_status(accounts: list[dict], domains: set[str]) -> dict[str, bool]:
    """Each company address in the tenant, mapped to whether an enabled account has it.
    An address on any enabled account counts as enabled; a missing accountEnabled too."""
    if not accounts:
        raise OffboardingStopped(_("Microsoft returned nobody, so nobody was changed."))
    status = {}
    for account in accounts:
        enabled = account.get("accountEnabled") is not False
        for address in account_addresses(account):
            if email_domain(address) in domains:
                status[address] = status.get(address, False) or enabled
    if not status:
        raise OffboardingStopped(
            _(
                "Microsoft has nobody at {0}, so nobody was changed. Check the domains."
            ).format(", ".join(sorted(domains)))
        )
    return status


def account_addresses(account: dict) -> set[str]:
    addresses = [account.get("mail"), account.get("userPrincipalName")]
    addresses += account.get("otherMails") or []
    # aliases, e.g. "SMTP:anjali@teambackoffice.com"
    addresses += [a.partition(":")[2] for a in account.get("proxyAddresses") or []]
    return {a.strip().lower() for a in addresses if a and a.strip()}


def leavers(directory: dict[str, bool], domains: set[str]) -> list[dict]:
    """Enabled hub Users at a company domain whose address is on no enabled account,
    leaving out Administrator, Guest, System Managers and the automation user."""
    protected = protected_users()
    users = frappe.qb.get_query(
        "User",
        fields=["name", "email", "full_name"],
        filters={"enabled": 1},
        order_by="name asc",
    ).run(as_dict=True)
    people = []
    for user in users:
        email = (user.email or user.name).strip().lower()
        if user.name in protected or email_domain(email) not in domains:
            continue
        enabled = directory.get(email)
        if enabled:
            continue
        people.append(
            {
                "user": user.name,
                "full_name": user.full_name or user.name,
                "reason": MISSING if enabled is None else DISABLED,
            }
        )
    return people


def protected_users() -> set[str]:
    from helpdesk.automation import automation_user

    return (
        ALWAYS_PROTECTED
        | set(get_users_with_role(PROTECTED_ROLE))
        | {automation_user()}
    )


def disable(person: dict):
    """Disables the User (which revokes their tokens) and logs it. Nothing is
    unassigned, so their tickets and tasks keep their history."""
    user = frappe.get_doc("User", person["user"])
    user.enabled = 0
    user.save(ignore_permissions=True)
    person["log"] = (
        frappe.get_doc(
            {
                "doctype": LOG,
                "user": user.name,
                "reason": person["reason"],
                "disabled_on": now_datetime(),
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def people_list(people: list[dict]) -> str:
    return ", ".join(f"{p['full_name']} ({_(p['reason'])})" for p in people)


def notify_managers(people: list[dict]):
    if not people:
        return
    notify_users(
        get_users_with_role("Agent Manager"),
        LOG,
        people[0]["log"],
        _("Disabled after leaving Microsoft: {0}").format(people_list(people)),
        link=PEOPLE_LINK,
    )


def alert_admins(people: list[dict], cap: int):
    """The run stopped because more people would go than the cap allows. Sent once for
    the same people (notify_users skips a message it already sent)."""
    notify_users(
        get_users_with_role(PROTECTED_ROLE),
        "HD Settings",
        "HD Settings",
        _(
            "Offboarding stopped: {0} people would be disabled, more than the limit of {1}. Nobody was changed. Check Microsoft, then raise the limit or run it by hand: {2}"
        ).format(len(people), cap, people_list(people)),
        link=PEOPLE_LINK,
    )
