# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import (
    enqueue_create_notification,
)
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime

# Posts in these statuses are ready to go; anything else close to its date needs attention
READY_STATUSES = ("Approved", "Scheduled", "Published")
REMINDER_WINDOW_HOURS = 48


class HDContentPost(Document):
    def validate(self):
        self.set_customer_from_campaign()
        self.validate_campaign_customer()
        self.validate_publish_on()
        self.validate_published()
        self.set_published_on()
        self.warn_if_no_client_connection()

    def set_customer_from_campaign(self):
        if self.campaign and not self.customer:
            self.customer = frappe.db.get_value(
                "HD Content Campaign", self.campaign, "customer"
            )

    def validate_campaign_customer(self):
        if not self.campaign:
            return
        campaign_customer = frappe.db.get_value(
            "HD Content Campaign", self.campaign, "customer"
        )
        if campaign_customer and campaign_customer != self.customer:
            frappe.throw(
                _("Campaign {0} belongs to {1}, not {2}").format(
                    self.campaign, campaign_customer, self.customer
                )
            )

    def validate_publish_on(self):
        if self.status != "Idea" and not self.publish_on:
            frappe.throw(_("Set a Publish On date before moving the post past Idea"))

    def validate_published(self):
        if self.status == "Published" and not self.published_url:
            frappe.throw(_("Add the Published URL to mark this post as Published"))

    def set_published_on(self):
        if self.status == "Published":
            self.published_on = self.published_on or now_datetime()
        else:
            self.published_on = None

    def warn_if_no_client_connection(self):
        if self.status != "Client Review" or not self.has_value_changed("status"):
            return
        from helpdesk.content_sync import get_client_connection

        if not get_client_connection(self.customer):
            frappe.msgprint(
                _(
                    "{0} has no connected ERP, so share this post with them for approval yourself."
                ).format(self.customer),
                indicator="orange",
                alert=True,
            )


def send_due_reminders():
    """Daily: nudge the team about posts publishing soon that aren't approved yet."""
    now = now_datetime()
    posts = frappe.get_all(
        "HD Content Post",
        filters={
            "publish_on": (
                "between",
                [now, add_to_date(now, hours=REMINDER_WINDOW_HOURS)],
            ),
            "status": ("not in", READY_STATUSES),
        },
        fields=["name", "title", "status", "publish_on", "writer", "designer", "owner"],
    )
    for post in posts:
        users = {
            u
            for u in (post.writer, post.designer, post.owner)
            if u and u != "Administrator"
        }
        if not users:
            continue
        enqueue_create_notification(
            list(users),
            {
                "type": "Alert",
                "document_type": "HD Content Post",
                "document_name": post.name,
                "subject": _("{0} publishes {1} and is still in {2}").format(
                    frappe.bold(post.title),
                    frappe.utils.pretty_date(post.publish_on),
                    post.status,
                ),
                "from_user": "Administrator",
            },
        )


# --- permissions: leads see everything; the rest of the team sees their own work
# and every post for the clients whose projects they are on ---


def _is_content_lead(user: str) -> bool:
    from helpdesk.tasky.permissions import is_project_manager

    return is_project_manager(user)


def _member_customers_sql(user: str) -> str:
    u = frappe.db.escape(user)
    return (
        "select `customer` from `tabProject` where ifnull(`customer`, '') != '' and "
        f"(`owner` = {u} or `name` in (select `parent` from `tabProject User` "
        f"where `parenttype` = 'Project' and `user` = {u}))"
    )


def member_customers(user: str) -> set[str]:
    return set(frappe.db.sql_list(_member_customers_sql(user)))


def permission_query(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if _is_content_lead(user):
        return None
    u = frappe.db.escape(user)
    table = "`tabHD Content Post`"
    return (
        f"({table}.`writer` = {u} or {table}.`designer` = {u} or {table}.`owner` = {u} "
        f"or {table}.`customer` in ({_member_customers_sql(user)}))"
    )


def has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    user = user or frappe.session.user
    if ptype == "create" or _is_content_lead(user):
        return None
    if user in (
        doc.writer,
        doc.designer,
        doc.owner,
    ) or doc.customer in member_customers(user):
        return None
    return False
