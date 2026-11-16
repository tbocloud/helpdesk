import frappe
from frappe.sessions import get_csrf_token

from helpdesk.api.config import get_config
from helpdesk.api.signoff_portal import page_data
from helpdesk.www.content_portal import to_script_json

no_cache = 1


def get_context(context):
    context.no_cache = 1
    config = get_config()
    # same icon and name as the helpdesk app; a private file can't be loaded by a customer
    # who isn't signed in (a broken image), so the name stands in for it
    context.favicon = public_file(config.favicon)
    context.brand_name = config.brand_name or "TBO"
    context.brand_logo = public_file(config.brand_logo)
    token = frappe.form_dict.get("token") or ""
    data = page_data(token)
    # a training sign-off's page, or a UAT's (signoff_portal.words)
    context.page_title = data["words"]["title"]
    context.page_data = to_script_json(
        {
            # a signed-in desk user opening the page still needs CSRF on POSTs
            "csrf_token": get_csrf_token() if frappe.session.user != "Guest" else "",
            "token": token,
            **data,
        }
    )
    return context


def public_file(url: str | None) -> str | None:
    """The file's URL when anyone may load it, else None."""
    return None if (url or "").startswith("/private/") else url
