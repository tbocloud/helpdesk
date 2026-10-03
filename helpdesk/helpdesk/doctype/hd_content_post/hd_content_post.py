# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    add_to_date,
    escape_html,
    format_datetime,
    formatdate,
    get_datetime,
    get_url,
    getdate,
    now_datetime,
)

from helpdesk.work_reminders import notify_users

# Posts in these statuses are ready to go; anything else close to its date needs attention
READY_STATUSES = ("Approved", "Scheduled", "Published")
# Posts in these statuses are done with, so they never need a reminder or a missed alert
CLOSED_STATUSES = ("Published", "Cancelled")
REMINDER_WINDOW_HOURS = 48

PER_PERSON = "One task per person"
ONE_TASK = "One task for the post"
NO_TASKS = "No tasks"
# who does which part, in order; the marketer's part is due on the publish date
TASK_ROLES = {"writer": "Writer", "designer": "Designer", "marketer": "Marketer"}
SHARED_ROLE = "All"
CONTENT_PROJECT_TYPE = "Content Calendar"
DONE_TASK_STATUSES = ("Completed", "Cancelled")
# a finished task moves an early post forward (never back)
STAGES = ("Idea", "Drafting", "Design", "Internal Review")
NEXT_STATUS_AFTER = {
    "Writer": "Design",
    "Designer": "Internal Review",
    SHARED_ROLE: "Internal Review",
}
# who hears about a post moving into each status
NEXT_PERSON = {
    "Drafting": ("writer",),
    "Design": ("designer",),
    "Changes Requested": ("writer", "designer"),
    "Approved": ("marketer",),
    "Scheduled": ("marketer",),
}


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
        self.set_task_mode()

    def on_update(self):
        self.sync_tasks()
        self.notify_next_person()

    # --- tasks: each person's part of the post (or one shared task) ---

    def set_task_mode(self):
        if not self.task_mode:
            self.task_mode = (
                frappe.db.get_single_value("HD Content Settings", "default_task_mode")
                or PER_PERSON
            )

    def sync_tasks(self):
        """Keep the post's tasks in step with who does it, the date and the status."""
        if self.flags.skip_task_sync:
            return
        tasks = self.content_tasks()
        open_tasks = {
            t.content_role: t for t in tasks if t.status not in DONE_TASK_STATUSES
        }
        if self.status == "Published":
            for task in open_tasks.values():
                self.close_task(task.name, "Completed")
            return
        if self.status == "Cancelled":
            for task in open_tasks.values():
                self.close_task(task.name, "Cancelled")
            return
        finished = {t.content_role for t in tasks if t.status == "Completed"}
        wanted = self.wanted_tasks()
        for role, plan in wanted.items():
            if role in open_tasks:
                self.update_task(open_tasks[role], plan)
            elif role not in finished:
                self.create_task(role, plan)
        for role, task in open_tasks.items():
            if role not in wanted:
                self.close_task(task.name, "Cancelled")

    def content_tasks(self) -> list:
        return frappe.get_all(
            "Task",
            filters={"content_post": self.name},
            fields=["name", "content_role", "status", "exp_end_date", "_assign"],
        )

    def wanted_tasks(self) -> dict:
        """{role: {"users": [...], "due": date}} for the tasks this post should have."""
        publish = getdate(self.publish_on) if self.publish_on else None
        settings = frappe.get_cached_doc("HD Content Settings")

        def due(days_before):
            return add_days(publish, -(days_before or 0)) if publish else None

        days = {
            "writer": settings.writer_days_before,
            "designer": settings.designer_days_before,
            "marketer": 0,
        }
        if self.task_mode == PER_PERSON:
            return {
                label: {"users": [self.get(field)], "due": due(days[field])}
                for field, label in TASK_ROLES.items()
                if self.get(field)
            }
        if self.task_mode == ONE_TASK:
            users = list(
                dict.fromkeys(u for u in (self.get(f) for f in TASK_ROLES) if u)
            )
            if users:
                return {SHARED_ROLE: {"users": users, "due": due(days["designer"])}}
        return {}

    def task_subject(self, role: str) -> str:
        what = _("Content") if role == SHARED_ROLE else _(role)
        text = f"{what}: {self.title} ({self.platforms_label})"
        if self.customer:
            text += f" · {self.customer}"
        return text[:140]

    def content_project(self) -> str | None:
        """The campaign's project, or the customer's open Content Calendar project."""
        if self.campaign:
            project = frappe.db.get_value(
                "HD Content Campaign", self.campaign, "project"
            )
            if project:
                return project
        if not self.customer:
            return None
        return frappe.db.get_value(
            "Project",
            {
                "customer": self.customer,
                "project_type": CONTENT_PROJECT_TYPE,
                "status": "Open",
            },
            "name",
            order_by="modified desc",
        )

    def create_task(self, role: str, plan: dict):
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": self.task_subject(role),
                "project": self.content_project(),
                "status": "Open",
                "priority": "Medium",
                "exp_end_date": plan["due"],
                "description": escape_html(self.brief or ""),
                "content_post": self.name,
                "content_role": role,
            }
        ).insert(ignore_permissions=True)
        for user in plan["users"]:
            self.give_task(task, user)

    def update_task(self, task, plan: dict):
        doc = frappe.get_doc("Task", task.name)
        changed = False
        if plan["due"] and getdate(doc.exp_end_date or "1900-01-01") != getdate(
            plan["due"]
        ):
            doc.exp_end_date = plan["due"]
            changed = True
        if doc.subject != self.task_subject(task.content_role):
            doc.subject = self.task_subject(task.content_role)
            changed = True
        if changed:
            doc.save(ignore_permissions=True)
        current = set(doc.assignees())
        for user in current - set(plan["users"]):
            assign_to._remove("Task", doc.name, user, ignore_permissions=True)
        for user in set(plan["users"]) - current:
            self.give_task(doc, user)

    def give_task(self, task, user: str):
        # the post's rules decided who does it; _add skips the caller's Task permission
        assign_to._add(
            {"doctype": "Task", "name": task.name, "assign_to": [user]},
            ignore_permissions=True,
        )
        notify_users(
            [user],
            "Task",
            task.name,
            _("New content task: {0}{1}").format(
                task.subject,
                _(", due {0}").format(formatdate(task.exp_end_date))
                if task.exp_end_date
                else "",
            ),
            link=self.board_path(),
        )

    @staticmethod
    def close_task(task_name: str, status: str):
        doc = frappe.get_doc("Task", task_name)
        doc.status = status
        doc.flags.from_content_post = True
        doc.save(ignore_permissions=True)
        assign_to.close_all_assignments("Task", task_name, ignore_permissions=True)

    def advance_after_task(self, role: str):
        """A finished part moves an early post to the next stage (writer done: design)."""
        next_status = NEXT_STATUS_AFTER.get(role)
        if not next_status or self.status not in STAGES:
            return
        if STAGES.index(self.status) >= STAGES.index(next_status):
            return
        self.status = next_status
        self.save(ignore_permissions=True)

    def notify_next_person(self):
        """Whoever's turn it is now hears about it, in the bell and in Teams or email."""
        # a new post's people hear through their new task instead
        if self.flags.in_insert or not self.has_value_changed("status"):
            return
        users = [self.get(field) for field in NEXT_PERSON.get(self.status, ())]
        if self.status == "Internal Review":
            users.append(self.owner)
        users = [u for u in dict.fromkeys(users) if u and u != frappe.session.user]
        if not users:
            return
        notify_users(
            users,
            "HD Content Post",
            self.name,
            _("{0} ({1}) is now {2}: your turn.").format(
                self.title, self.customer or self.platforms_label, _(self.status)
            ),
            link=self.board_path(),
        )

    def board_path(self) -> str:
        return f"/content?post={self.name}"

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
        users = [post.writer, post.designer, post.marketer, post.owner]
        # same path as other reminders: the bell plus Teams or email, once per day and stage
        notify_users(
            users,
            "HD Content Post",
            post.name,
            _("{0} publishes {1} and is still in {2}").format(
                post.title,
                format_datetime(post.publish_on, "d MMM, h:mm a"),
                _(post.status),
            ),
            link=f"/content?post={post.name}",
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
        notify_users(
            [post.writer, post.designer, post.marketer],
            "HD Content Post",
            post.name,
            _(
                "Missed: {0} was due {1} and isn't published. Publish or postpone it."
            ).format(post.title, format_datetime(post.publish_on, "d MMM, h:mm a")),
            link=f"/content?post={post.name}",
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
