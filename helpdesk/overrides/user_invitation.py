import frappe
from frappe import _
from frappe.core.doctype.user_invitation.user_invitation import UserInvitation

# what a division admin's invite may give: an agent, whose place is their division role
DIVISION_INVITE_ROLES = {"Agent"}


class HelpdeskUserInvitation(UserInvitation):
    def _get_email_title(self):
        # Use the org's brand name (set during onboarding) in the invitation
        # subject — "You've been invited to join <brand> on Helpdesk" — falling
        # back to the framework app title when it isn't set. The override class
        # is registered site-wide, so invitations from other apps (ERPNext,
        # etc.) must keep their own app title.
        if self.app_name != "helpdesk":
            return super()._get_email_title()
        brand = frappe.db.get_single_value("HD Settings", "brand_name")
        if not brand:
            return super()._get_email_title()
        return _("{0} on {1}").format(brand, super()._get_email_title())

    def _validate_roles(self):
        # a division admin holds no inviting role of their own: their invite was checked
        # by helpdesk.api.divisions.invite_to_division and may only make an agent
        if self.flags.division_invite and self.division:
            if {r.role for r in self.roles} != DIVISION_INVITE_ROLES:
                frappe.throw(_("A division's invite makes an agent only."))
            return
        super()._validate_roles()
