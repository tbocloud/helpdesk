# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class HDContentCampaign(Document):
    def validate(self):
        self.validate_dates()

    def validate_dates(self):
        if (
            self.start_date
            and self.end_date
            and getdate(self.end_date) < getdate(self.start_date)
        ):
            frappe.throw(_("End Date cannot be before Start Date"))


def permission_query(user: str | None = None) -> str | None:
    from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
        _is_content_lead,
        _member_customers_sql,
    )

    user = user or frappe.session.user
    if _is_content_lead(user):
        return None
    table = "`tabHD Content Campaign`"
    return (
        f"({table}.`owner` = {frappe.db.escape(user)} "
        f"or {table}.`customer` in ({_member_customers_sql(user)}))"
    )


def has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
        _is_content_lead,
        member_customers,
    )

    user = user or frappe.session.user
    if ptype == "create" or _is_content_lead(user):
        return None
    if doc.owner == user or doc.customer in member_customers(user):
        return None
    return False
