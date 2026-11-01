"""Connecting a client's Facebook Page and Instagram account to their project
(docs/meta-publishing.md): Facebook Login, the long-lived token, the Page choice.

Tokens stay on the server: they go into Password fields (encrypted) and no function here
returns one."""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.password import remove_encrypted_password

from helpdesk.helpdesk.doctype.hd_meta_connection.hd_meta_connection import (
    CONNECTED,
    PENDING,
)
from helpdesk.helpdesk.doctype.hd_meta_settings.hd_meta_settings import HDMetaSettings
from helpdesk.integrations.meta import signing
from helpdesk.integrations.meta.graph import (
    DIALOG_HOST,
    GraphClient,
    MetaError,
    graph_version,
)

SETTINGS = "HD Meta Settings"
CONNECTION = "HD Meta Connection"
# Phase 2 (paid ads) adds ads_management and ads_read here and asks again; nothing else changes
SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_content_publish",
    "business_management",
)
# a Page role that may post (Admin and Editor have one of these)
POSTING_TASKS = {"CREATE_CONTENT", "MANAGE"}


def app() -> tuple[str, str]:
    """(app id, app secret) once Meta is turned on in the settings."""
    settings = frappe.get_cached_doc(SETTINGS)
    secret = settings.get_password("app_secret", raise_exception=False)
    if not (settings.enabled and settings.app_id and secret):
        frappe.throw(
            _(
                "Meta isn't set up yet. A System Manager adds the app in Settings → Meta."
            )
        )
    return settings.app_id, secret


def login_url(project: str, user: str) -> str:
    """Facebook's login dialog for this project, with a state only `user` can complete."""
    app_id, _secret = app()
    return f"{DIALOG_HOST}/{graph_version()}/dialog/oauth?" + urlencode(
        {
            "client_id": app_id,
            "redirect_uri": HDMetaSettings.oauth_redirect_url(),
            "state": signing.make_state(user, project),
            "scope": ",".join(SCOPES),
            "response_type": "code",
        }
    )


def finish_login(code: str, state: str, session_user: str) -> str:
    """Trade Facebook's code for a long-lived token and keep it until the Page is picked.
    Returns the project. The state must be fresh, signed, and made for this very person."""
    user, project = signing.read_state(state)
    if user != session_user:
        frappe.throw(
            _("This sign-in was started by someone else."), frappe.PermissionError
        )
    app_id, secret = app()
    graph = GraphClient()
    short = graph.get(
        "oauth/access_token",
        client_id=app_id,
        client_secret=secret,
        redirect_uri=HDMetaSettings.oauth_redirect_url(),
        code=code,
    )
    long = graph.get(
        "oauth/access_token",
        grant_type="fb_exchange_token",
        client_id=app_id,
        client_secret=secret,
        fb_exchange_token=short["access_token"],
    )
    token = long["access_token"]
    permissions = GraphClient(token, secret).get("me/permissions").get("data", [])
    granted = [p["permission"] for p in permissions if p.get("status") == "granted"]
    missing = [s for s in SCOPES if s not in granted]
    if missing:
        frappe.throw(
            _(
                "Meta didn't get these permissions: {0}. Connect again and allow all of them."
            ).format(", ".join(missing))
        )
    connection = get_or_new(project)
    connection.update(
        {
            "status": PENDING,
            "last_error": None,
            "user_access_token": token,
            "granted_scopes": ", ".join(granted),
            "connected_by": user,
        }
    )
    connection.save(ignore_permissions=True)
    return project


def get_or_new(project: str):
    if frappe.db.exists(CONNECTION, project):
        return frappe.get_doc(CONNECTION, project)
    return frappe.get_doc({"doctype": CONNECTION, "project": project})


def user_pages(connection) -> list[dict]:
    """The Pages the signed-in person can post to, with their linked Instagram account.
    Page tokens are in the answer, so it never leaves the server."""
    token = connection.user_token()
    if not token:
        frappe.throw(_("Sign in with Facebook first."))
    _app_id, secret = app()
    data = GraphClient(token, secret).get(
        "me/accounts",
        fields="id,name,access_token,tasks,instagram_business_account{id,username}",
        limit=100,
    )
    return [
        page
        for page in data.get("data", [])
        if not page.get("tasks") or POSTING_TASKS & set(page["tasks"])
    ]


def list_pages(project: str) -> list[dict]:
    """The choices shown to the person: id, name and Instagram username, nothing secret."""
    pages = user_pages(frappe.get_doc(CONNECTION, project))
    return [
        {
            "id": page["id"],
            "name": page["name"],
            "instagram_username": (page.get("instagram_business_account") or {}).get(
                "username"
            ),
        }
        for page in pages
    ]


def select_page(project: str, page_id: str):
    """Keep this Page's token (and its Instagram account) on the connection; the
    sign-in token is deleted, since the Page token does not expire and nothing else needs it."""
    connection = frappe.get_doc(CONNECTION, project)
    page = next((p for p in user_pages(connection) if p["id"] == page_id), None)
    if not page:
        frappe.throw(_("That Page isn't one you can post to. Pick another."))
    instagram = page.get("instagram_business_account") or {}
    connection.update(
        {
            "status": CONNECTED,
            "last_error": None,
            "facebook_page_id": page["id"],
            "facebook_page_name": page["name"],
            "page_access_token": page["access_token"],
            "instagram_user_id": instagram.get("id"),
            "instagram_username": instagram.get("username"),
            "connected_by": frappe.session.user,
            "connected_on": now_datetime(),
        }
    )
    connection.save(ignore_permissions=True)
    remove_encrypted_password(CONNECTION, project, "user_access_token")
    return connection


def check_app() -> dict:
    """Ask Meta whether the saved App ID and secret work (the Settings page's test)."""
    app_id, secret = app()
    try:
        GraphClient().get(
            "oauth/access_token",
            client_id=app_id,
            client_secret=secret,
            grant_type="client_credentials",
        )
    except MetaError as e:
        return {"ok": False, "message": e.user_message}
    return {"ok": True, "message": _("Meta accepted the App ID and secret.")}
