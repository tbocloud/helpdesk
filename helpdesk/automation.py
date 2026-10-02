"""Who the hub's own work is credited to.

AI triage and investigation notes, session-replay notes, reminders, KB drafts
and changes picked up from Outlook or GitHub are made by the hub, not by a
person. They are credited to the user set in HDS Hub Settings ("TBO AI",
e.g. ai@teambackoffice.com), or to Administrator when none is set.

An agent's own actions stay theirs: a reply drafted by the AI and sent by an
agent is the agent's reply, tagged AI-drafted (see HDTicket.reply_via_agent).
"""

import frappe
from frappe import _

# a background job or webhook runs as one of these, never as a person
SYSTEM_USERS = ("Administrator", "Guest")
DEFAULT_NAME = "TBO AI"
AUTOMATION_ROLES = ("Agent", "Project Manager")


def automation_user() -> str:
    user = frappe.db.get_single_value("HDS Hub Settings", "automation_user")
    if user and frappe.db.get_value("User", user, "enabled"):
        return user
    return "Administrator"


def acting_user() -> str:
    """The person doing this, or the automation user when no person is (jobs, webhooks)."""
    user = frappe.session.user
    return automation_user() if user in SYSTEM_USERS else user


@frappe.whitelist(methods=["POST"])
def create_automation_user(email: str, full_name: str = DEFAULT_NAME) -> str:
    """HDS Hub Settings button: makes the TBO AI user and credits the hub's own work to it."""
    # only_for is skipped in tests, so check the role directly
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            _("Only System Managers can create the automation user."),
            frappe.PermissionError,
        )
    email = (email or "").strip().lower()
    if not frappe.utils.validate_email_address(email):
        frappe.throw(_("{0} is not a valid email address.").format(email))
    first, _sep, last = (full_name or DEFAULT_NAME).strip().partition(" ")
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first,
                "last_name": last,
                "user_type": "System User",
                # nobody logs in as it; it acts through its API key
                "send_welcome_email": 0,
            }
        )
        user.insert(ignore_permissions=True)
    missing = [r for r in AUTOMATION_ROLES if r not in frappe.get_roles(user.name)]
    if missing:
        user.add_roles(*missing)
    frappe.db.set_single_value("HDS Hub Settings", "automation_user", user.name)
    return user.name
