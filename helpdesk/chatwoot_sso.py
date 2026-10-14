"""TBO Chat (Chatwoot) sign-in through TBO Support (docs/chatwoot-sso.md).

Chatwoot Community has no Microsoft login, but its Platform API can make a one-time
sign-in link for any user. TBO Support signs staff in with Microsoft, so it brokers:

- Open TBO Chat (`helpdesk.api.chatwoot_sso.login`): an active agent signed in here
  is found in the Chatwoot account by email, added when missing (if allowed), and sent
  to Chatwoot's one-time link. The link is a credential: it is never logged or stored.
- Offboarding: a User who is disabled (by hand or by helpdesk.offboarding when the
  Microsoft account goes) or an HD Agent who is deactivated is removed from the
  Chatwoot account, which ends their access there, and the removal is logged in
  HD Offboarding Log.

The bridge user's token (HD Chatwoot Settings) finds people in the account; the
Platform App's token adds and removes them and makes the sign-in links.
"""

import secrets

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from helpdesk.chatwoot_bridge import SETTINGS, ChatwootClient
from helpdesk.offboarding import LOG

LOGIN_PATH = "/api/method/helpdesk.api.chatwoot_sso.login"
# a failed Chatwoot sign-in returns to /app/login, which Caddy sends back here: the
# limit also ends that loop
RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 60
AGENT = "agent"
ADMINISTRATOR = "administrator"
MANAGER_ROLES = ("System Manager", "Agent Manager")
USER_DISABLED = "User disabled"
AGENT_DEACTIVATED = "Agent deactivated"
AGENT_REMOVED = "Agent removed"
REMOVED = "Removed from TBO Chat"
REMOVAL_FAILED = "TBO Chat: couldn't remove someone"


class SignInRefused(Exception):
    """Why this person can't open TBO Chat now, shown to them as a page."""

    def __init__(self, title: str, message: str, status: int = 403):
        super().__init__(message)
        self.title = title
        self.message = message
        self.status = status


def sign_in_url(user: str) -> str:
    """Chatwoot's one-time sign-in link for `user`, adding them to the account first
    when they are missing and that is allowed. Raises SignInRefused."""
    settings = frappe.get_single(SETTINGS)
    if not settings.sso_enabled:
        raise SignInRefused(
            _("TBO Chat sign-in is off"),
            _("Ask an administrator to turn on sign-in through TBO Support."),
            404,
        )
    if not is_active_agent(user):
        raise SignInRefused(
            _("TBO Chat is for agents"),
            _("Only active agents can open TBO Chat. Ask your manager if you need it."),
        )
    check_rate(user)

    client = ChatwootClient(settings)
    email = user_email(user)
    agents = account_agents(client)
    member = find_agent(agents, email)
    if not member and not settings.sso_create_users:
        raise SignInRefused(
            _("You're not in TBO Chat yet"),
            _("Ask a TBO Chat administrator to add {0}.").format(email),
        )
    # also gives the Platform App the right to sign in an existing user
    chat_user = client.platform_request(
        "POST",
        "/users",
        {
            "name": frappe.utils.get_fullname(user),
            "email": email,
            "password": unusable_password(),
        },
    )
    if not chat_user or not chat_user.get("id"):
        raise unavailable()
    if not member:
        added = client.platform_request(
            "POST",
            f"/accounts/{cint(settings.account_id)}/account_users",
            {"user_id": chat_user["id"], "role": new_member_role(user, settings)},
        )
        if added is None:
            raise unavailable()
    return one_time_link(client, chat_user["id"])


def is_active_agent(user: str) -> bool:
    return bool(frappe.db.exists("HD Agent", {"user": user, "is_active": 1}))


def check_rate(user: str):
    key = frappe.cache.make_key(f"chatwoot-sso:{user}")
    count = frappe.cache.incrby(key, 1)
    # also when an earlier expire was lost, so nobody is locked out for good
    if count == 1 or frappe.cache.ttl(key) == -1:
        frappe.cache.expire(key, RATE_WINDOW_SECONDS)
    if count > RATE_LIMIT:
        raise SignInRefused(
            _("Too many tries"),
            _(
                "TBO Chat was opened too often in a short time. Wait a minute, then try again."
            ),
            429,
        )


def user_email(user: str) -> str:
    return (frappe.db.get_value("User", user, "email") or user).strip().lower()


def account_agents(client: ChatwootClient) -> list[dict]:
    agents = client.request("GET", "/agents")
    if not isinstance(agents, list):
        raise unavailable()
    return agents


def find_agent(agents: list[dict], email: str) -> dict | None:
    return next(
        (a for a in agents if (a.get("email") or "").strip().lower() == email), None
    )


def unusable_password() -> str:
    """Chatwoot requires a password; nobody ever learns this one. It has every kind
    of character Chatwoot asks for."""
    return secrets.token_urlsafe(32) + "aA1!"


def new_member_role(user: str, settings) -> str:
    if settings.sso_managers_as_admins and set(MANAGER_ROLES) & set(
        frappe.get_roles(user)
    ):
        return ADMINISTRATOR
    return settings.sso_default_role or AGENT


def one_time_link(client: ChatwootClient, chat_user_id: int) -> str:
    """The link Chatwoot made, only when it leads to our Chatwoot's sign-in page."""
    answer = client.platform_request("GET", f"/users/{cint(chat_user_id)}/login")
    url = (answer or {}).get("url") or ""
    if not url.startswith(f"{client.root}/app/login?"):
        raise unavailable()
    return url


def unavailable() -> SignInRefused:
    return SignInRefused(
        _("Couldn't open TBO Chat"),
        _("TBO Chat didn't answer as expected. Try again in a minute."),
        502,
    )


# --- offboarding ---


def on_user_update(doc, method=None):
    """User on_update: someone just disabled leaves TBO Chat too."""
    if doc.has_value_changed("enabled") and not cint(doc.enabled):
        queue_removal(doc.name, USER_DISABLED)


def on_agent_update(doc, method=None):
    """HD Agent on_update: an agent just deactivated leaves TBO Chat too."""
    if doc.has_value_changed("is_active") and not cint(doc.is_active):
        queue_removal(doc.user, AGENT_DEACTIVATED)


def on_agent_trash(doc, method=None):
    """HD Agent on_trash: a deleted agent leaves TBO Chat too."""
    queue_removal(doc.user, AGENT_REMOVED)


def queue_removal(user: str, reason: str):
    if not can_manage_chat(frappe.get_single(SETTINGS)):
        return
    frappe.enqueue(
        "helpdesk.chatwoot_sso.remove_from_chat",
        queue="short",
        user=user,
        reason=reason,
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )


def can_manage_chat(settings) -> bool:
    """Removal works whenever both tokens are saved, even with sign-in switched off."""
    return bool(
        settings.base_url
        and settings.get_password("platform_api_token", raise_exception=False)
        and settings.get_password("api_access_token", raise_exception=False)
    )


def remove_from_chat(user: str, reason: str):
    """Background job: takes `user` out of the Chatwoot account and logs it. Someone
    who isn't in the account is left alone; a failure is logged for the error alerts."""
    settings = frappe.get_single(SETTINGS)
    client = ChatwootClient(settings)
    agents = client.request("GET", "/agents")
    if not isinstance(agents, list):
        frappe.log_error(
            title=REMOVAL_FAILED, message=f"{user}: couldn't read the account's agents"
        )
        return
    member = find_agent(agents, user_email(user))
    if not member:
        return
    removed = client.platform_request(
        "DELETE",
        f"/accounts/{cint(settings.account_id)}/account_users",
        {"user_id": member["id"]},
    )
    if removed is None:
        frappe.log_error(
            title=REMOVAL_FAILED, message=f"{user}: Chatwoot refused the removal"
        )
        return
    frappe.get_doc(
        {
            "doctype": LOG,
            "user": user,
            "reason": reason,
            "action": REMOVED,
            "disabled_on": now_datetime(),
        }
    ).insert(ignore_permissions=True)
