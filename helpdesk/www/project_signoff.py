import frappe
from frappe.sessions import get_csrf_token

from helpdesk.api.config import get_config
from helpdesk.api.signoff_portal import page_data
from helpdesk.www.content_portal import to_script_json

no_cache = 1


def get_context(context):
    context.no_cache = 1
    config = get_config()
    # same icon and name as the helpdesk app
    context.favicon = config.favicon
    context.brand_name = config.brand_name or "TBO"
    token = frappe.form_dict.get("token") or ""
    context.page_data = to_script_json(
        {
            # a signed-in desk user opening the page still needs CSRF on POSTs
            "csrf_token": get_csrf_token() if frappe.session.user != "Guest" else "",
            "token": token,
            **page_data(token),
        }
    )
    return context
