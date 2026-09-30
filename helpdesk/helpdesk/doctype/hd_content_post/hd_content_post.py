# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import (
    enqueue_create_notification,
)
from frappe.desk.form import assign_to
from frappe.model.document import Document
from frappe.utils import (
    add_to_date,
    escape_html,
    format_datetime,
    get_datetime,
    get_url,
    getdate,
    now_datetime,
)

# Posts in these statuses are ready to go; anything else close to its date needs attention
READY_STATUSES = ("Approved", "Scheduled", "Published")
# Posts in these statuses are done with, so they never need a reminder or a missed alert
CLOSED_STATUSES = ("Published", "Cancelled")
REMINDER_WINDOW_HOURS = 48
# role field -> (task type, priority); the designer's type depends on the format
ROLE_TASKS = {
    "writer": ("Content Finalization", "High"),
    "designer": ("Graphic Design", "Medium"),
    "marketer": ("Publishing", "Urgent"),
}
VIDEO_FORMATS = ("Reel", "Video")
DONE_TASK_STATUSES = ("Completed", "Cancelled")


class HDContentPost(Document):
    def on_update(self):
        self.sync_role_tasks()

    def validate(self):
        self.set_customer_from_campaign()
        self.validate_campaign_customer()
        self.validate_publish_on()
        self.validate_published()
        self.set_published_on()
        self.reset_missed_alert()
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

    # --- one ERPNext Task per assigned role ---

    def sync_role_tasks(self):
        """Keep each role's open task in step with who is assigned, the date and the status."""
        if not self.role_tasks_enabled():
            return
        watched = ("publish_on", "status", "title", *ROLE_TASKS)
        hours = self.flags.get("task_hours") or {}
        if not hours and not any(self.has_value_changed(f) for f in watched):
            return

        settings = frappe.get_cached_doc("HD Content Settings")
        open_tasks = {
            t.content_role: t
            for t in frappe.get_all(
                "Task",
                filters={
                    "content_post": self.name,
                    "status": ("not in", DONE_TASK_STATUSES),
                },
                fields=["name", "content_role"],
            )
        }
        for role in ROLE_TASKS:
            user = self.get(role)
            task = open_tasks.get(role)
            if task and (not user or self.status == "Cancelled"):
                self.cancel_role_task(task.name)
            elif user and not task and self.status not in CLOSED_STATUSES:
                self.create_role_task(
                    role, user, hours.get(role) or settings.get(f"{role}_hours")
                )
            elif user and task:
                self.update_role_task(task.name, role, user, hours.get(role))

    def role_tasks_enabled(self) -> bool:
        # the fields arrive with a migrate; until then assigning just sets the person
        if not frappe.get_meta("HD Content Settings").has_field(
            "create_tasks_on_assign"
        ):
            return False
        if not frappe.db.get_single_value(
            "HD Content Settings", "create_tasks_on_assign"
        ):
            return False
        # ERPNext's Task, extended by helpdesk.tasky.setup
        return bool(
            frappe.db.exists("DocType", "Task")
            and frappe.get_meta("Task").has_field("content_post")
        )

    def role_task_values(self, role: str) -> dict:
        task_type, priority = ROLE_TASKS[role]
        if role == "designer" and self.format in VIDEO_FORMATS:
            task_type = "Video Production"
        due = getdate(self.publish_on) if self.publish_on else None
        start = min(getdate(), due) if due else getdate()
        return {
            "subject": f"{_(task_type)}: {self.title} ({self.channel})",
            "priority": priority,
            "exp_start_date": start,
            "exp_end_date": due,
            "project": self.task_project(due),
            "description": self.brief or "",
        }

    def task_project(self, due):
        """The campaign's project, unless the post falls after the project ends (ERPNext refuses that)."""
        if not self.campaign:
            return None
        project = frappe.db.get_value("HD Content Campaign", self.campaign, "project")
        if not project:
            return None
        project_end = frappe.db.get_value("Project", project, "expected_end_date")
        if due and project_end and getdate(project_end) < due:
            return None
        return project

    def create_role_task(self, role: str, user: str, hours):
        task = frappe.get_doc(
            {
                "doctype": "Task",
                **self.role_task_values(role),
                "status": "Open",
                "expected_time": hours or 0,
                "content_post": self.name,
                "content_role": role,
            }
        ).insert(ignore_permissions=True)
        assign_to.add(
            {
                "doctype": "Task",
                "name": task.name,
                "assign_to": [user],
                "description": task.subject,
                "date": task.exp_end_date,
                "priority": "High" if task.priority in ("High", "Urgent") else "Medium",
            },
            ignore_permissions=True,
        )

    def update_role_task(self, task_name: str, role: str, user: str, hours=None):
        task = frappe.get_doc("Task", task_name)
        task.update(self.role_task_values(role))
        if hours:
            task.expected_time = hours
        task.save(ignore_permissions=True)
        assigned = set(frappe.parse_json(task.get("_assign") or "[]"))
        if user not in assigned:
            for previous in assigned:
                assign_to.remove("Task", task.name, previous, ignore_permissions=True)
            assign_to.add(
                {
                    "doctype": "Task",
                    "name": task.name,
                    "assign_to": [user],
                    "description": task.subject,
                    "date": task.exp_end_date,
                },
                ignore_permissions=True,
            )

    @staticmethod
    def cancel_role_task(task_name: str):
        task = frappe.get_doc("Task", task_name)
        task.status = "Cancelled"
        task.save(ignore_permissions=True)
        assign_to.close_all_assignments("Task", task.name, ignore_permissions=True)

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
            "channel": post.channel,
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
        "select `hd_customer` from `tabProject` where ifnull(`hd_customer`, '') != '' and "
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
