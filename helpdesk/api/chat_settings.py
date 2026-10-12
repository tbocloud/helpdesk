"""Settings → Chat & Teams: HD Chat Settings for System Managers and Agent Managers.

The bot token and the workflow URLs are secrets (a Teams workflow URL carries its
&sig= key), so once saved they never go back to the browser: the page gets a
masked value and whether each is set, and sends a secret only to replace or
remove it. docs/settings-ui.md describes the page.
"""

from urllib.parse import urlparse

import frappe
import requests
from frappe import _

from helpdesk import chat_notifications
from helpdesk.error_alerts import CHAT_ERROR_TITLES
from helpdesk.tasky.permissions import is_tasky_admin

SETTINGS = "HD Chat Settings"
PLAIN_FIELDS = (
    "enabled",
    "platform",
    "email_when_unreachable",
    "slack_escalation_channel",
    "post_error_alerts",
    "ignored_error_titles",
)
SECRET_FIELDS = ("slack_bot_token", "teams_direct_webhook", "teams_channel_webhook")
TARGETS = ("direct", "channel")


def check_admin():
    # only_for is skipped in tests, so check the roles directly
    if not is_tasky_admin():
        frappe.throw(
            _("Only System Managers and Agent Managers can change chat settings."),
            frappe.PermissionError,
        )


def mask(value: str) -> str:
    """Enough to recognise a secret, not to use it: a URL's host, a token's prefix."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname}/…"
    prefix, dash, _rest = value.partition("-")
    return f"{prefix}-…" if dash and len(prefix) <= 4 else "…"


def settings_payload(doc) -> dict:
    secrets = {}
    for field in SECRET_FIELDS:
        value = doc.get_password(field, raise_exception=False)
        secrets[field] = {"set": bool(value), "masked": mask(value) if value else ""}
    return {
        "settings": {f: doc.get(f) for f in PLAIN_FIELDS},
        "secrets": secrets,
        "last_problem": last_problem(),
    }


def last_problem() -> dict | None:
    """The latest logged chat delivery failure: its title and time, not the
    traceback, which can hold the workflow URL."""
    ErrorLog = frappe.qb.DocType("Error Log")
    rows = (
        frappe.qb.from_(ErrorLog)
        .select(ErrorLog.method, ErrorLog.creation)
        .where(ErrorLog.method.isin(CHAT_ERROR_TITLES))
        .orderby(ErrorLog.creation, order=frappe.qb.desc)
        .limit(1)
        .run(as_dict=True)
    )
    if not rows:
        return None
    return {"title": rows[0].method, "at": rows[0].creation}


@frappe.whitelist()
def get_settings() -> dict:
    check_admin()
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
    """Plain fields as sent. A secret only when its key is sent: a value replaces
    it, an empty string removes it; HDChatSettings.validate checks the URLs."""
    check_admin()
    values = frappe.parse_json(values) or {}
    doc = frappe.get_doc(SETTINGS)
    doc.update({k: v for k, v in values.items() if k in PLAIN_FIELDS})
    for field in SECRET_FIELDS:
        if values.get(field) is not None:
            doc.set(field, str(values[field]).strip())
    doc.save(ignore_permissions=True)
    return settings_payload(frappe.get_doc(SETTINGS))


@frappe.whitelist(methods=["POST"])
def send_test(target: str) -> dict:
    """A test to the caller ("direct") or to the escalation channel, with the saved
    settings: whether it was sent, and what to do when it wasn't."""
    check_admin()
    if target not in TARGETS:
        frappe.throw(_("Choose what to test: direct or channel."))
    text = chat_notifications.setup_check_text()
    url = chat_notifications.helpdesk_url(None)
    try:
        if target == "direct":
            sent = chat_notifications.send_direct(frappe.session.user, text, url)
        else:
            sent = chat_notifications.post_to_channel(text, url)
    except (chat_notifications.ChatError, requests.RequestException) as e:
        return {"ok": False, "message": chat_notifications.describe_error(e)}
    if sent:
        return {"ok": True, "message": sent_message(target)}
    return {"ok": False, "message": not_sent_message(target)}


def sent_message(target: str) -> str:
    if target == "direct":
        return _("Sent to you ({0}). Check your chat.").format(frappe.session.user)
    return _("Posted to the escalation channel.")


def not_sent_message(target: str) -> str:
    slack = chat_notifications.get_settings().platform == chat_notifications.SLACK
    if target == "channel":
        if slack:
            return _("No escalation channel ID yet: add it, save, then test again.")
        return _(
            "No Escalation Channel Workflow URL yet: add it, save, then test again."
        )
    if slack:
        return chat_notifications.direct_not_sent_message()
    return _("No Direct Message Workflow URL yet: add it, save, then test again.")
