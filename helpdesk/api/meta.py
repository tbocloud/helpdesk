"""Publishing to Meta from the content calendar (docs/meta-publishing.md).

Settings are for System Managers. Connecting and publishing follow `can_handle_credentials`
(a project's managers and lead, the Digital Marketing Head, System Managers; never a
Sales Employee). No function here returns a token."""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cstr, strip_html

from helpdesk.helpdesk.doctype.hd_meta_settings.hd_meta_settings import HDMetaSettings
from helpdesk.integrations.meta import connect, publisher, signing
from helpdesk.integrations.meta.graph import MetaError, graph_version
from helpdesk.tasky.permissions import can_handle_credentials

SETTINGS = connect.SETTINGS
PLAIN_FIELDS = ("enabled", "app_id", "graph_api_version")
ADMIN_ROLE = "System Manager"
PROJECT_PAGE = "/helpdesk/projects/{0}/meta"


def check_admin():
    if frappe.session.user != "Administrator" and ADMIN_ROLE not in frappe.get_roles():
        frappe.throw(
            _("Only System Managers can change the Meta settings."),
            frappe.PermissionError,
        )


def require_project_access(project: str):
    if not project or not frappe.db.exists("Project", project):
        frappe.throw(_("Project not found: {0}").format(project))
    if not can_handle_credentials(project):
        frappe.throw(
            _("You can't connect Meta for this project."), frappe.PermissionError
        )


def settings_payload(doc) -> dict:
    return {
        "settings": {f: doc.get(f) for f in PLAIN_FIELDS},
        "secrets": {
            "app_secret": {
                "set": bool(doc.get_password("app_secret", raise_exception=False)),
                "masked": "…",
            }
        },
        "redirect_url": HDMetaSettings.oauth_redirect_url(),
        "graph_api_version": doc.graph_api_version or graph_version(),
    }


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    """Plain fields as sent; the App Secret only when its key is sent (a value replaces
    it, an empty string removes it)."""
    check_admin()
    values = frappe.parse_json(values) or {}
    doc = frappe.get_doc(SETTINGS)
    doc.update({k: v for k, v in values.items() if k in PLAIN_FIELDS})
    if values.get("app_secret") is not None:
        doc.app_secret = cstr(values["app_secret"]).strip()
    doc.save(ignore_permissions=True)
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist(methods=["POST"])
def test_app() -> dict:
    """Ask Meta whether the saved App ID and secret work."""
    check_admin()
    return connect.check_app()


def connection_summary(project: str) -> dict | None:
    name = frappe.db.exists(connect.CONNECTION, project)
    if not name:
        return None
    doc = frappe.get_doc(connect.CONNECTION, name)
    return {
        "status": doc.status,
        "last_error": doc.last_error,
        "facebook_page_name": doc.facebook_page_name,
        "instagram_username": doc.instagram_username,
        "connected_by": doc.connected_by,
        "connected_on": cstr(doc.connected_on) if doc.connected_on else None,
    }


@frappe.whitelist()
def get_connection(project: str) -> dict:
    """The project's Meta connection (no tokens) and whether Meta is switched on."""
    require_project_access(project)
    return {
        "enabled": bool(frappe.db.get_single_value(SETTINGS, "enabled")),
        "connection": connection_summary(project),
    }


@frappe.whitelist(methods=["POST"])
def start_connect(project: str) -> dict:
    """Facebook's login dialog for this project."""
    require_project_access(project)
    return {"url": connect.login_url(project, frappe.session.user)}


@frappe.whitelist(methods=["GET"])
def oauth_callback(
    code: str | None = None, state: str | None = None, error: str | None = None
):
    """Where Facebook sends the person back. Needs the same signed-in person who started
    it (the state names them); then the browser returns to the project's Meta page."""
    project = None
    try:
        _user, project = signing.read_state(state or "")
        if error or not code:
            frappe.throw(_("Facebook sign-in was cancelled. Nothing was connected."))
        require_project_access(project)
        connect.finish_login(code, state, frappe.session.user)
        outcome = "signed_in=1"
    except (MetaError, frappe.ValidationError, frappe.PermissionError) as e:
        message = e.user_message if isinstance(e, MetaError) else strip_message(e)
        outcome = "error=" + quote(message)
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = (
        f"{PROJECT_PAGE.format(project)}?{outcome}" if project else "/helpdesk"
    )


def strip_message(error: Exception) -> str:
    return strip_html(str(error))[:300]


@frappe.whitelist()
def list_pages(project: str) -> list[dict]:
    """The Pages the connecting person can post to, with their Instagram account."""
    require_project_access(project)
    try:
        return connect.list_pages(project)
    except MetaError as e:
        frappe.throw(e.user_message)


@frappe.whitelist(methods=["POST"])
def select_page(project: str, page_id: str) -> dict | None:
    require_project_access(project)
    try:
        connect.select_page(project, page_id)
    except MetaError as e:
        frappe.throw(e.user_message)
    return connection_summary(project)


@frappe.whitelist(methods=["POST"])
def disconnect(project: str):
    """Forget the Page: the tokens are deleted with the connection."""
    require_project_access(project)
    if frappe.db.exists(connect.CONNECTION, project):
        frappe.delete_doc(connect.CONNECTION, project, ignore_permissions=True)
    return None


@frappe.whitelist()
def get_publish_state(post: str) -> dict:
    return publisher.publish_state(post)


@frappe.whitelist(methods=["POST"])
def publish(
    post: str,
    targets: list | str,
    publish_at: str | None = None,
    story: bool | int | str = False,
    link: str | None = None,
) -> dict:
    """Publish an approved post now, or at `publish_at`, to Facebook and/or Instagram."""
    targets = frappe.parse_json(targets) if isinstance(targets, str) else targets
    publisher.queue(
        post,
        targets,
        publisher.STORY if frappe.utils.sbool(story) else None,
        publish_at,
        link,
    )
    return publisher.publish_state(post)


@frappe.whitelist(methods=["POST"])
def unschedule(post: str, target: str | None = None) -> dict:
    """Take queued targets off the schedule."""
    publisher.cancel_queued(post, target)
    return publisher.publish_state(post)


@frappe.whitelist(  # Meta's servers fetch it; the signed, expiring token is checked - nosemgrep
    allow_guest=True, methods=["GET"]
)
def media(token: str):
    """One post attachment for Meta to fetch: public only through a link the hub signed
    for that file, good for an hour."""
    file_name = signing.read_media_token(token)
    file_doc = frappe.get_doc("File", file_name)
    if file_doc.attached_to_doctype != publisher.POST:
        frappe.throw(_("This link isn't valid."), frappe.ValidationError)
    frappe.local.response.filename = file_doc.file_name
    frappe.local.response.filecontent = file_doc.get_content()
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"
