# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import (
    enqueue_create_notification,
)
from frappe.model.document import Document
from frappe.utils import (
    add_to_date,
    escape_html,
    format_datetime,
    get_datetime,
    get_url,
    now_datetime,
)

# Posts in these statuses are ready to go; anything else close to its date needs attention
READY_STATUSES = ("Approved", "Scheduled", "Published")
# Posts in these statuses are done with, so they never need a reminder or a missed alert
CLOSED_STATUSES = ("Published", "Cancelled")
REMINDER_WINDOW_HOURS = 48


class HDContentPost(Document):
    def validate(self):
        self.sync_platforms()
        self.set_customer_from_campaign()
        self.validate_campaign_customer()
        self.validate_publish_on()
        self.validate_published()
        self.set_published_on()
        self.reset_missed_alert()
        self.warn_if_no_client_connection()

    def sync_platforms(self):
        """Keep `platforms` (all of them) and `channel` (the main one) in step."""
        platforms = self.platform_list()
        if self.has_value_changed("channel") and not self.has_value_changed(
            "platforms"
        ):
            # an edit that only touched channel (old screens, the Desk form) moves the main platform
            platforms = [self.channel] + [p for p in platforms if p != self.channel]
        valid = self.meta.get_field("channel").options.split("\n")
        platforms = [p for p in platforms if p in valid] or [self.channel]
        self.channel = platforms[0]
        self.platforms = ", ".join(platforms)

    def platform_list(self) -> list[str]:
        raw = [p.strip() for p in (self.platforms or "").split(",")]
        return list(dict.fromkeys(p for p in raw if p)) or (
            [self.channel] if self.channel else []
        )

    @property
    def platforms_label(self) -> str:
        return ", ".join(self.platform_list())

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
        if self.status not in ("Idea", "Cancelled") and not self.publish_on:
            frappe.throw(_("Set a Publish On date before moving the post past Idea"))

    def validate_published(self):
        if self.status == "Published" and not self.published_url:
            frappe.throw(_("Add the Published URL to mark this post as Published"))

    def set_published_on(self):
        if self.status == "Published":
            self.published_on = self.published_on or now_datetime()
        else:
            self.published_on = None

    def reset_missed_alert(self):
        # a new publish time is a new deadline, so it gets its own alert
        if self.has_value_changed("publish_on"):
            self.missed_alert_sent = 0

    def warn_if_no_client_connection(self):
        if self.status != "Client Review" or not self.has_value_changed("status"):
            return
        from helpdesk.content_sync import get_client_connection

        if get_client_connection(self.customer):
            return
        if frappe.db.get_single_value("HD Content Settings", "enable_client_portal"):
            message = _(
                "{0} has no connected ERP. They can review this post in the client portal."
            )
        else:
            message = _(
                "{0} has no connected ERP, so share this post with them for approval yourself."
            )
        frappe.msgprint(message.format(self.customer), indicator="orange", alert=True)

    # --- board actions (the caller has checked write permission) ---

    def postpone(self, publish_on, reason: str):
        """Move the post to a new time; the reason is kept on the post's timeline."""
        if not (reason or "").strip():
            frappe.throw(_("Give a reason for postponing"))
        if self.status in CLOSED_STATUSES:
            frappe.throw(_("A {0} post can't be postponed").format(_(self.status)))
        previous = self.publish_on
        if not publish_on or (
            previous and get_datetime(publish_on) == get_datetime(previous)
        ):
            frappe.throw(_("Pick a different date or time"))
        self.publish_on = get_datetime(publish_on)
        self.times_postponed = (self.times_postponed or 0) + 1
        self.save()
        self.add_comment(
            "Info",
            _("Postponed from {0} to {1}: {2}").format(
                format_datetime(previous) if previous else _("no date"),
                format_datetime(self.publish_on),
                escape_html(reason.strip()),
            ),
        )

    def cancel(self, reason: str):
        if self.status == "Published":
            frappe.throw(_("A published post can't be cancelled"))
        self.status = "Cancelled"
        self.save()
        note = f": {escape_html(reason.strip())}" if (reason or "").strip() else ""
        self.add_comment("Info", _("Cancelled{0}").format(note))

    # --- client decisions from the content portal (the caller has checked the client owns this post) ---

    def approve_from_portal(self, email: str):
        self.ensure_awaiting_client()
        self.status = "Approved"
        self.client_decided_on = now_datetime()
        self.save(ignore_permissions=True)
        self.add_comment(
            "Info", _("Client approved in the content portal ({0})").format(email)
        )

    def request_changes_from_portal(self, email: str, notes: str):
        self.ensure_awaiting_client()
        self.status = "Changes Requested"
        self.client_feedback = notes
        self.client_decided_on = now_datetime()
        self.save(ignore_permissions=True)
        self.add_comment(
            "Info",
            _("Client requested changes in the content portal ({0}): {1}").format(
                email, escape_html(notes)
            ),
        )

    def comment_from_portal(self, email: str, text: str):
        self.add_comment(
            "Comment",
            escape_html(text),
            comment_email=email,
            comment_by=_("{0} (client)").format(email),
        )

    def ensure_awaiting_client(self):
        if self.status != "Client Review":
            frappe.throw(
                _("{0} is no longer waiting for your review").format(self.title)
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
            "status": ("not in", READY_STATUSES + CLOSED_STATUSES),
        },
        fields=[
            "name",
            "title",
            "status",
            "publish_on",
            "writer",
            "designer",
            "marketer",
            "owner",
        ],
    )
    for post in posts:
        users = {
            u
            for u in (post.writer, post.designer, post.marketer, post.owner)
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


def send_missed_post_alerts():
    """Hourly: email once about each post whose publish time passed without it being published or cancelled."""
    settings = frappe.get_single("HD Content Settings")
    if not settings.enable_missed_post_alerts:
        return

    Post = frappe.qb.DocType("HD Content Post")
    cutoff = add_to_date(now_datetime(), minutes=-(settings.grace_period_minutes or 0))
    posts = (
        frappe.qb.from_(Post)
        .select(
            Post.name,
            Post.title,
            Post.customer,
            Post.channel,
            Post.platforms,
            Post.publish_on,
            Post.writer,
            Post.designer,
            Post.marketer,
        )
        .where(Post.publish_on <= cutoff)
        .where(Post.status.notin(CLOSED_STATUSES))
        .where(Post.missed_alert_sent == 0)
        .run(as_dict=True)
    )

    always = settings.get_alert_recipients()
    sent = 0
    for post in posts:
        recipients = always | (
            _user_emails((post.writer, post.designer, post.marketer))
            if settings.notify_post_team
            else set()
        )
        if not recipients:
            # left unflagged so it is picked up once someone is assigned or configured
            continue
        try:
            _send_missed_post_alert(settings, post, recipients)
        except Exception:  # noqa: BLE001 - one bad post must not stop the others
            frappe.log_error(
                title=f"Missed post alert failed for {post.name}",
                message=frappe.get_traceback(),
            )
            continue
        frappe.db.set_value(
            "HD Content Post", post.name, "missed_alert_sent", 1, update_modified=False
        )
        sent += 1

    frappe.db.set_single_value(
        "HD Content Settings",
        {"last_alert_run_on": now_datetime(), "last_alerts_sent": sent},
    )


def _send_missed_post_alert(settings, post, recipients: set[str]):
    hours_late = (now_datetime() - post.publish_on).total_seconds() / 3600
    subject, message = settings.render(
        "missed_post",
        {
            "title": post.title,
            "customer": post.customer,
            "channel": post.platforms or post.channel,
            "due_datetime": format_datetime(post.publish_on),
            "hours_late": round(hours_late, 1),
            "post_link": get_url(f"/helpdesk/content?post={post.name}"),
        },
    )
    frappe.sendmail(
        recipients=sorted(recipients),
        subject=subject,
        message=message,
        reference_doctype="HD Content Post",
        reference_name=post.name,
    )


def _user_emails(users) -> set[str]:
    users = [u for u in users if u and u != "Administrator"]
    if not users:
        return set()
    return set(
        frappe.get_all(
            "User", filters={"name": ("in", users), "enabled": 1}, pluck="email"
        )
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
        f"({table}.`writer` = {u} or {table}.`designer` = {u} or {table}.`marketer` = {u} "
        f"or {table}.`owner` = {u} "
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
        doc.marketer,
        doc.owner,
    ) or doc.customer in member_customers(user):
        return None
    return False
