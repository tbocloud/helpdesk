"""The TBO Copilot bot's messaging endpoint for Microsoft Teams (Phase 6, helpdesk.copilot.teams).

Guest access by design: Bot Framework calls it with its own signed token, which is checked
before anything is read, together with our tenant.
"""

import json

import frappe
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
    if answer is None:
        return Response(status=200)
    return Response(json.dumps(answer), status=200, content_type="application/json")


@frappe.whitelist(methods=["GET"])
def app_package():
    """The "TBO Copilot" Teams app (manifest and icons) for the Microsoft 365 admin, with this site's bot."""
    frappe.only_for("System Manager")
    if not teams.app_id():
        frappe.throw("Set the bot app ID in HDS Copilot Settings first.")
    frappe.local.response.filename = "tbo-copilot-teams-app.zip"
    frappe.local.response.filecontent = teams.app_package()
    frappe.local.response.type = "download"
