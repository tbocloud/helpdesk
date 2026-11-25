import frappe
from frappe.sessions import get_csrf_token

from helpdesk.api.config import get_config
from helpdesk.api.content_portal import (
    get_portal_posts,
    get_session,
    portal_enabled,
    session_accounts,
)

no_cache = 1


def get_context(context):
    context.no_cache = 1
    # same icon as the helpdesk app (HD Settings, then Website Settings, then ours)
    context.favicon = get_config().favicon
    context.portal_data = to_script_json(build_portal_data())
    return context


def build_portal_data() -> dict:
    data = {
        # a signed-in desk user opening the portal still needs CSRF on POSTs
        "csrf_token": get_csrf_token() if frappe.session.user != "Guest" else "",
        "enabled": portal_enabled(),
    }
    if not data["enabled"]:
        return data

    session = get_session()
    if not session:
        return {**data, "signed_in": False}

    # the page calls every account a customer: a whole customer, or a branch it approves for
    accounts = session_accounts(session)
    if not accounts:
        return {**data, "signed_in": False}
    requested = frappe.form_dict.get("customer")
    account = requested if requested in accounts else accounts[0]
    return {
        **data,
        "signed_in": True,
        "email": session["email"],
        "customers": accounts,
        "customer": account,
        "posts": get_portal_posts(account, session),
    }


def to_script_json(value) -> str:
    # safe inside <script>: no "</script>" or "<!--" can end the block early
    return frappe.as_json(value, indent=None).replace("<", "\\u003c")
