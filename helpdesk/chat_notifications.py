"""Deliver agent notifications to Slack or Microsoft Teams instead of email.

Configured in HD Chat Settings. Reminders and mentions (HD Notification) go to
the person directly; escalations are also posted once to a team channel.

- Slack: a Slack app bot token; people are matched by email
  (users.lookupByEmail), so the app needs chat:write, users:read and
  users:read.email.
- Microsoft Teams: Teams Workflows webhooks (no Azure app). The direct-message
  workflow receives `recipient` (the person's email) plus an Adaptive Card and
  posts it to them as the Flow bot; the channel workflow is Teams' standard
  "Post to a channel when a webhook request is received" template.
"""

import hashlib

import frappe
import requests
from frappe import _

SLACK = "Slack"
TEAMS = "Microsoft Teams"
SLACK_API = "https://slack.com/api/"
TIMEOUT = 10
SLACK_USER_CACHE_SECONDS = 24 * 60 * 60


class ChatError(Exception):
    pass


def get_settings():
    return frappe.get_cached_doc("HD Chat Settings")


def is_enabled() -> bool:
    return bool(frappe.db.get_single_value("HD Chat Settings", "enabled"))


def helpdesk_url(path: str | None) -> str:
    return frappe.utils.get_url("/helpdesk" + (path or "/my-work"))


# --- Slack ---


def slack_call(method: str, payload: dict) -> dict:
    token = get_settings().get_password("slack_bot_token", raise_exception=False)
    if not token:
        raise ChatError("no_token")
    response = requests.post(
        SLACK_API + method,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    if response.status_code == 429:
        raise ChatError("ratelimited")
    data = response.json()
    if not data.get("ok"):
        raise ChatError(data.get("error") or "unknown_error")
    return data


def slack_user_id(email: str) -> str | None:
    """The Slack member with this email, or None if they aren't in the workspace."""
    key = f"helpdesk:slack_user:{email}"
    cached = frappe.cache.get_value(key)
    if cached is not None:
        return cached or None
    try:
        user_id = slack_call("users.lookupByEmail", {"email": email})["user"]["id"]
    except ChatError as e:
        if str(e) != "users_not_found":
            raise
        user_id = ""
    frappe.cache.set_value(key, user_id, expires_in_sec=SLACK_USER_CACHE_SECONDS)
    return user_id or None


def slack_escape(text: str) -> str:
    """Slack treats &, < and > as control characters in message text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_post(channel: str, text: str, url: str | None):
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": slack_escape(text)}}
    ]
    if url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": _("Open in TBO Support"),
                        },
                        "url": url,
                    }
                ],
            }
        )
    slack_call(
        "chat.postMessage",
        {"channel": channel, "text": text, "blocks": blocks, "unfurl_links": False},
    )


# --- Microsoft Teams ---


def teams_message(text: str, url: str | None) -> dict:
    """A Teams message with one Adaptive Card, the shape Workflows webhooks accept."""
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        # Teams only breaks lines on blank lines
        "body": [
            {"type": "TextBlock", "text": text.replace("\n", "\n\n"), "wrap": True}
        ],
    }
    if url:
        card["actions"] = [
            {"type": "Action.OpenUrl", "title": _("Open in TBO Support"), "url": url}
        ]
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }


def teams_post(webhook_field: str, payload: dict):
    url = get_settings().get_password(webhook_field, raise_exception=False)
    if not url:
        raise ChatError("no_webhook")
    response = requests.post(url, json=payload, timeout=TIMEOUT)
    if response.status_code >= 300:
        raise ChatError(f"http_{response.status_code}")


# --- delivery ---


def send_direct(email: str, text: str, url: str | None = None) -> bool:
    """Message one person; False when chat can't reach them, so they get an email.

    That is someone missing from Slack, or Teams without the direct-message
    workflow (only the escalation channel is set up).
    """
    settings = get_settings()
    if settings.platform == SLACK:
        user_id = slack_user_id(email)
        if not user_id:
            return False
        slack_post(user_id, text, url)
        return True
    if not settings.get_password("teams_direct_webhook", raise_exception=False):
        return False
    teams_post("teams_direct_webhook", {"recipient": email, **teams_message(text, url)})
    return True


def post_to_channel(text: str, url: str | None = None) -> bool:
    """False when no escalation channel is set up."""
    settings = get_settings()
    if settings.platform == SLACK:
        if not settings.slack_escalation_channel:
            return False
        slack_post(settings.slack_escalation_channel, text, url)
        return True
    if not settings.get_password("teams_channel_webhook", raise_exception=False):
        return False
    teams_post("teams_channel_webhook", teams_message(text, url))
    return True


def deliver_notification(notification: str):
    """Background job: send an HD Notification to chat, or email it if chat can't."""
    doc = frappe.get_doc("HD Notification", notification)
    try:
        if send_direct(doc.user_to, doc.chat_text(), helpdesk_url(doc.chat_path())):
            return
    except (ChatError, requests.RequestException):
        frappe.log_error(title="Chat notification not sent")
    if get_settings().email_when_unreachable:
        doc.send_email()


def post_escalation(text: str, path: str | None = None):
    """Queue a channel post, once per message text (recorded in HD Chat Escalation)."""
    if not is_enabled():
        return
    digest = hashlib.sha1(text.encode()).hexdigest()
    if frappe.db.exists("HD Chat Escalation", digest):
        return
    frappe.get_doc(
        {
            "doctype": "HD Chat Escalation",
            "message_hash": digest,
            "message": text,
            "link": path,
        }
    ).insert(ignore_permissions=True)
    frappe.enqueue(
        "helpdesk.chat_notifications.deliver_escalation",
        text=text,
        path=path,
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )


def deliver_escalation(text: str, path: str | None = None):
    try:
        post_to_channel(text, helpdesk_url(path))
    except (ChatError, requests.RequestException):
        frappe.log_error(title="Chat escalation not posted")


@frappe.whitelist()
def send_test_message() -> dict:
    """System Managers check the setup: a message to themselves and to the channel."""
    # only_for is skipped in tests, so check the role directly
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Managers can send a test."), frappe.PermissionError)
    text = _("Test message from TBO Support. Chat notifications are working.")
    try:
        direct = send_direct(frappe.session.user, text, helpdesk_url(None))
        channel = post_to_channel(text, helpdesk_url(None))
    except (ChatError, requests.RequestException) as e:
        hint = teams_http_hint(str(e))
        frappe.throw(
            _("The chat platform refused the message: {0}").format(str(e))
            + (f" {hint}" if hint else "")
        )
    if not direct and not channel:
        frappe.throw(
            _("Nothing was sent: add a Direct Message or Escalation Channel URL first.")
        )
    if not direct:
        frappe.msgprint(_direct_not_sent_message())
    return {"direct": direct, "channel": channel}


def teams_http_hint(error: str) -> str:
    """What a Teams Workflows refusal usually means, for the person setting it up."""
    return {
        "http_401": _(
            "The workflow refused the caller: its URL has no &sig= part, or the trigger's 'Who can trigger the flow' isn't Anyone."
        ),
        "http_403": _(
            "The workflow refused the caller: check that the trigger's 'Who can trigger the flow' is Anyone."
        ),
        "http_404": _(
            "No workflow at that URL: the flow was deleted, or the URL was copied before the flow was saved."
        ),
        "http_405": _(
            "That URL isn't a workflow's HTTP URL (for example a link to a Teams message). Copy the HTTP URL from the flow's trigger."
        ),
    }.get(error, "")


def _direct_not_sent_message() -> str:
    if get_settings().platform == SLACK:
        return _(
            "{0} wasn't found in Slack. Use the same email in Slack and here."
        ).format(frappe.session.user)
    return _(
        "Only the escalation channel was tested. Without a Direct Message Workflow URL, people get their reminders by email."
    )
