import frappe

from helpdesk.github_sync import receive_webhook


@frappe.whitelist(  # GitHub can't log in; every delivery must carry our HMAC signature before anything is read - nosemgrep
    allow_guest=True, methods=["POST"]
)
def webhook() -> dict:
    """GitHub webhook for pull requests, reviews and workflow runs (see helpdesk.github_sync).

    The signature covers the exact bytes GitHub sent, so it is checked against
    the raw body rather than Frappe's parsed form data.
    """
    return receive_webhook(frappe.request.get_data(), frappe.request.headers)
