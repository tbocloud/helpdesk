"""Open TBO Chat, and Settings → TBO Chat (docs/chatwoot-sso.md).

`login` is the one way into TBO Chat: Caddy sends Chatwoot's sign-in page here.
The settings page is for System Managers, who alone may change HD Chatwoot
Settings. Saved tokens never go back to the browser: the page gets whether each is
set, and sends one only to replace or remove it (as Settings → GitHub does).
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.sessions import get_csrf_token
from frappe.utils import escape_html, get_url

from helpdesk import chatwoot_sso
from helpdesk.chatwoot_bridge import SETTINGS

PLAIN_FIELDS = (
    "sso_enabled",
    "base_url",
    "account_id",
    "sso_create_users",
    "sso_default_role",
    "sso_managers_as_admins",
)
SECRET_FIELDS = ("api_access_token", "platform_api_token")
# Chatwoot tokens have no prefix worth showing, so nothing of the token is shown
MASK = "••••••••"


@frappe.whitelist(  # a guest is sent to the Microsoft sign-in and back here; nothing is read or changed for them - nosemgrep
    allow_guest=True, methods=["GET"]
)
def login() -> None:
    """Sends the person to TBO Chat, signed in, or shows why not."""
    user = frappe.session.user
    if user == "Guest":
        redirect(f"/login?redirect-to={quote(chatwoot_sso.LOGIN_PATH, safe='')}")
        return
    if chatwoot_sso.should_pause(
        user, frappe.form_dict, frappe.get_request_header("Referer")
    ):
        show_signed_out()
        return
    try:
        url = chatwoot_sso.sign_in_url(user)
    except chatwoot_sso.SignInRefused as e:
        frappe.respond_as_web_page(
            e.title,
            escape_html(e.message),
            http_status_code=e.status,
            indicator_color="red" if e.status >= 500 else "orange",
            primary_action="/helpdesk",
            primary_label=_("Back to TBO Support"),
        )
        return
    chatwoot_sso.note_opened(user)
    redirect(url)


@frappe.whitelist(methods=["POST"])
def sign_out() -> None:
    """The signed-out page's "Sign out of TBO Support too": the hub's own logout, then
    its sign-in page."""
    frappe.local.login_manager.logout()
    redirect("/login")


def show_signed_out():
    """Asks before signing back in, so a sign-out of TBO Chat sticks (docs/chatwoot-sso.md)."""
    again = f"{chatwoot_sso.LOGIN_PATH}?{chatwoot_sso.CONTINUE}=1"
    message = escape_html(
        _(
            "You're still signed in to TBO Support. Open TBO Chat again, or sign out here too."
        )
    )
    frappe.respond_as_web_page(
        _("You're signed out of TBO Chat"),
        f"""<p>{message}</p>
<div><a href="{again}" class="btn btn-primary btn-sm btn-block">{escape_html(_("Open TBO Chat again"))}</a></div>
<form method="post" action="/api/method/helpdesk.api.chatwoot_sso.sign_out" style="margin-top: 8px">
<input type="hidden" name="csrf_token" value="{escape_html(get_csrf_token())}">
<button type="submit" class="btn btn-default btn-sm btn-block">{escape_html(_("Sign out of TBO Support too"))}</button>
</form>""",
        indicator_color="blue",
        primary_action=None,
    )


def redirect(location: str):
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = location


def check_admin():
    # only_for is skipped in tests, so check the roles directly
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            _("Only System Managers can change TBO Chat settings."),
            frappe.PermissionError,
        )


def settings_payload(doc) -> dict:
    secrets = {}
    for field in SECRET_FIELDS:
        is_set = bool(doc.get_password(field, raise_exception=False))
        secrets[field] = {"set": is_set, "masked": MASK if is_set else ""}
    return {
        "settings": {f: doc.get(f) for f in PLAIN_FIELDS},
        "secrets": secrets,
        "login_url": get_url(chatwoot_sso.LOGIN_PATH),
    }


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return settings_payload(frappe.get_single(SETTINGS))


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    """Plain fields as sent. A token only when its key is sent: a value replaces it,
    an empty string removes it; HDChatwootSettings.validate checks the rest."""
    check_admin()
    values = frappe.parse_json(values) or {}
    doc = frappe.get_single(SETTINGS)
    doc.update({k: v for k, v in values.items() if k in PLAIN_FIELDS})
    for field in SECRET_FIELDS:
        if values.get(field) is not None:
            doc.set(field, str(values[field]).strip())
    doc.save(ignore_permissions=True)
    return settings_payload(frappe.get_single(SETTINGS))
