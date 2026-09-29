"""Keep the Frappe desk (/app) for System Managers; everyone else works in /helpdesk."""

import frappe

DESK_ROLES = ("System Manager",)
HELPDESK_HOME = "/helpdesk"


def can_access_desk(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return user == "Administrator" or bool(
        set(DESK_ROLES) & set(frappe.get_roles(user))
    )


def is_desk_path(path: str) -> bool:
    return path == "/app" or path.startswith("/app/")


def redirect_desk_to_helpdesk(context):
    """update_website_context hook, which runs while /app is being rendered.

    A redirect raised from before_request is not handled by Frappe (it becomes a
    500), but one raised during page rendering is. 302 rather than frappe.redirect's
    301 so browsers don't cache it for the next person on the same machine.
    """
    request = getattr(frappe.local, "request", None)
    if not request or not is_desk_path(request.path):
        return
    # guests are sent to /login by the desk page itself
    if frappe.session.user == "Guest" or can_access_desk():
        return
    frappe.flags.redirect_location = HELPDESK_HOME
    raise frappe.Redirect(302)
