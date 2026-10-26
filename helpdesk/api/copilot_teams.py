"""The TBO Copilot bot's messaging endpoint for Microsoft Teams (Phase 6, helpdesk.copilot.teams).

Guest access by design: Bot Framework calls it with its own signed token, which is checked
before anything is read, together with our tenant.
"""

import json
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import escape_html
from werkzeug.wrappers import Response

from helpdesk.copilot import teams


@frappe.whitelist(allow_guest=True, methods=["POST"])
def messages():
    if not teams.enabled():
        return Response("The Teams bot is not set up.", status=404)
    activity = frappe.request.get_json(silent=True) or {}
    header = frappe.get_request_header("Authorization")
    try:
        teams.check_token(header, activity.get("serviceUrl"))
    except frappe.PermissionError as e:
        frappe.clear_last_message()
        teams.note_refusal(str(e), activity, header)
        return Response(str(e), status=401)
    try:
        answer = teams.handle_activity(activity)
    except frappe.PermissionError as e:
        frappe.clear_last_message()
        teams.note_refusal(str(e), activity, header)
        return Response(str(e), status=403)
    except Exception:
        # written down and kept: a failing call from Teams would otherwise leave no trace
        frappe.db.rollback()
        frappe.log_error(title="Copilot Teams bot could not handle a call")
        frappe.db.commit()  # only the Error Log is written here - nosemgrep
        return Response("The Teams bot could not handle this.", status=500)
    if answer is None:
        return Response(status=200)
    return Response(json.dumps(answer), status=200, content_type="application/json")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def link(code: str = ""):
    """The page a one-time link from the Teams bot opens: whose Teams account, and a button to link it.

    Signed out, the person signs in first and comes back here. Nothing changes until they
    press Link (a POST with their session's CSRF token), so a link someone else opens, or a
    page that loads it, joins nothing.
    """
    if frappe.session.user == "Guest":
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = "/login?redirect-to=" + quote(
            f"/api/method/helpdesk.api.copilot_teams.link?code={code}", safe=""
        )
        return
    record = teams.link_target(code)
    user = frappe.session.user
    if not record:
        return _page(
            _("Link not valid"),
            _(
                "This link is no longer valid. Write to TBO Copilot in Teams for a new one."
            ),
            ok=False,
        )
    if reason := teams.why_not_link(record, user):
        return _page(_("Cannot link"), reason, ok=False)
    form = (
        '<form method="POST" action="/api/method/helpdesk.api.copilot_teams.confirm_link">'
        f'<input type="hidden" name="code" value="{escape_html(code)}">'
        f'<input type="hidden" name="csrf_token" value="{escape_html(frappe.sessions.get_csrf_token())}">'
        f'<button class="btn btn-primary" type="submit">{escape_html(_("Link"))}</button></form>'
    )
    return _page(
        _("Link your Teams account"),
        "<p>{0}</p><p>{1}</p>{2}".format(
            escape_html(
                _(
                    "This joins the Teams account that wrote to TBO Copilot to your TBO Support account, {0}. Then the bot acts as you: it can approve fixes in your name."
                ).format(user)
            ),
            escape_html(
                _(
                    "Only do this for your own Teams account, from a link the bot sent you."
                )
            ),
            form,
        ),
        ok=True,
        escaped=True,
    )


@frappe.whitelist(methods=["POST"])
def confirm_link(code: str = ""):
    """The Link button: joins the Teams account to the signed-in agent, once."""
    try:
        teams.link(code, frappe.session.user)
    except (frappe.PermissionError, frappe.ValidationError) as e:
        frappe.clear_last_message()
        return _page(_("Cannot link"), str(e), ok=False)
    return _page(
        _("Teams account linked"),
        _("Done. Go back to Teams and write help to TBO Copilot."),
        ok=True,
    )


def _page(title: str, message: str, ok: bool, escaped: bool = False):
    frappe.respond_as_web_page(
        title,
        message if escaped else escape_html(message),
        http_status_code=200 if ok else 400,
        indicator_color="green" if ok else "red",
    )


@frappe.whitelist(methods=["GET"])
def app_package():
    """The "TBO Copilot" Teams app (manifest and icons) for the Microsoft 365 admin, with this site's bot."""
    frappe.only_for("System Manager")
    if not teams.app_id():
        frappe.throw("Set the bot app ID in HDS Copilot Settings first.")
    frappe.local.response.filename = "tbo-copilot-teams-app.zip"
    frappe.local.response.filecontent = teams.app_package()
    frappe.local.response.type = "download"
