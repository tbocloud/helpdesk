import frappe

from helpdesk.chatwoot_bridge import receive_webhook
from helpdesk.helpdesk.doctype.hd_chatwoot_settings.hd_chatwoot_settings import (
    ACCOUNT,
    BOT,
)


@frappe.whitelist(  # Chatwoot can't log in; every delivery must carry our HMAC signature (or the bot URL's secret token) before anything is read - nosemgrep
    allow_guest=True, methods=["POST"]
)
def bot_webhook() -> dict:
    """The TBO AI Agent Bot's outgoing URL: events of conversations in the bot's inboxes.

    The signature covers the exact bytes Chatwoot sent, so it is checked against
    the raw body rather than Frappe's parsed form data.
    """
    return receive_webhook(
        BOT,
        frappe.request.get_data(),
        frappe.request.headers,
        frappe.request.args.get("token"),
    )


@frappe.whitelist(  # Chatwoot can't log in; every delivery must carry our HMAC signature before anything is read - nosemgrep
    allow_guest=True, methods=["POST"]
)
def account_webhook() -> dict:
    """The account webhook: conversations created, updated or changing status, and new messages."""
    return receive_webhook(ACCOUNT, frappe.request.get_data(), frappe.request.headers)
