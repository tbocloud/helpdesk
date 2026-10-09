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
    flt,
    format_datetime,
    formatdate,
    get_datetime,
    get_url,
    getdate,
    now_datetime,
)

from helpdesk.content_team import (
    can_edit_content,
    head_approvers,
    is_dm_head,
    is_erp_only,
)
from helpdesk.utils import add_assignment, remove_assignment
from helpdesk.work_reminders import notify_users

# Posts in these statuses are ready to go; anything else close to its date needs attention
READY_STATUSES = ("Approved", "Scheduled", "Published")
CLIENT_REVIEW = "Client Review"
# the client said yes; the Digital Marketing Head approves it before it can go out
HEAD_REVIEW = "Head Review"
# Posts in these statuses are done with, so they never need a reminder or a missed alert
CLOSED_STATUSES = ("Published", "Cancelled")
REMINDER_WINDOW_HOURS = 48

PER_PERSON = "One task per person"
ONE_TASK = "One task for the post"
NO_TASKS = "No tasks"
# who does which part, in order; the marketer's part is due on the publish date
TASK_ROLES = {
    "writer": "Writer",
    "designer": "Designer",
    "video_editor": "Video Editor",
    "marketer": "Marketer",
}
SHARED_ROLE = "All"
# the design stage's parts: the post leaves Design once all of them are done
DESIGN_ROLES = ("Designer", "Video Editor")
CONTENT_PROJECT_TYPE = "Content Calendar"
DONE_TASK_STATUSES = ("Completed", "Cancelled")
# publishing ends the post's open work; cancelling the post cancels it
CLOSE_TASKS_AS = {"Published": "Completed", "Cancelled": "Cancelled"}
# a finished task moves an early post forward (never back)
STAGES = ("Idea", "Drafting", "Design", "Internal Review")
NEXT_STATUS_AFTER = {
    "Writer": "Design",
    "Designer": "Internal Review",
    "Video Editor": "Internal Review",
    SHARED_ROLE: "Internal Review",
}
# who hears about a post moving into each status
NEXT_PERSON = {
    "Drafting": ("writer",),
    "Design": ("designer", "video_editor"),
    "Changes Requested": ("writer", "designer", "video_editor"),
    "Approved": ("marketer",),
    "Scheduled": ("marketer",),
}


class HDContentPost(Document):
    def validate(self):
        self.guard_editing()
        self.guard_head_review()
        self.clean_team()
        self.sync_platforms()
        self.validate_publish_on()
        self.validate_published()
        self.set_published_on()
        self.reset_missed_alert()
        self.warn_if_no_client_connection()
        self.set_task_mode()
        self.end_design_when_its_last_part_is_dropped()
        self.start_client_review()

    def on_update(self):
        self.sync_tasks()
        self.notify_next_person()

    # --- the team: one main person per role, plus anyone in extra_team ---

    def people(self, role: str) -> list[str]:
        """Everyone on a role, the main person first."""
        return team_of(self)[role]

    def everyone(self) -> list[str]:
        """Everyone on the post, in role order, each once."""
        return list(dict.fromkeys(u for users in team_of(self).values() for u in users))

    def set_people(self, role: str, users: list[str]):
        """Put exactly these people on a role; the first becomes its main person."""
        users = list(dict.fromkeys(u for u in users if u))
        self.set(role, users[0] if users else None)
        others = [
            {"role": r.role, "user": r.user}
            for r in self.get("extra_team") or []
            if r.role != role
        ]
        self.set("extra_team", others + [{"role": role, "user": u} for u in users[1:]])

    def replace_on_part(self, content_role: str, leaving: list[str], newcomer: str):
        """Put `newcomer` in place of `leaving` on the roles behind one task: its role,
        or every role for the post's shared task (a hand-over of that task)."""
        for field, label in TASK_ROLES.items():
            if content_role not in (label, SHARED_ROLE):
                continue
            people = self.people(field)
            if set(leaving) & set(people):
                self.set_people(
                    field, [newcomer if u in leaving else u for u in people]
                )

    def clean_team(self):
        """No one twice on a role, and a role with anyone on it has a main person."""
        for role in TASK_ROLES:
            people = self.people(role)
            extras = [r.user for r in self.get("extra_team") or [] if r.role == role]
            # rows are only rewritten when something is off, not on every save
            # the post dialog sends "" for an empty role
            main = self.get(role) or None
            if main != (people[0] if people else None) or extras != people[1:]:
                self.set_people(role, people)

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
            t.content_role: t.name for t in tasks if t.status not in DONE_TASK_STATUSES
        }
        # a part that was finished or cancelled isn't recreated; reopen its task instead
        handled = {t.content_role for t in tasks if t.status in DONE_TASK_STATUSES}
        closing = CLOSE_TASKS_AS.get(self.status)
        wanted = {} if closing else self.wanted_tasks()

        for role, name in open_tasks.items():
            task = frappe.get_doc("Task", name)
            if role in wanted:
                if self.plan_task(task, wanted[role]):
                    task.save(ignore_permissions=True)
                self.reassign_task(task, wanted[role]["users"])
            else:
                self.close_task(task, closing or "Cancelled")
                task.save(ignore_permissions=True)
                assign_to.close_all_assignments("Task", name, ignore_permissions=True)
        for role, plan in wanted.items():
            if role not in open_tasks and role not in handled:
                self.create_task(role, plan)

    def content_tasks(self) -> list:
        return frappe.get_all(
            "Task",
            filters={"content_post": self.name},
            fields=["name", "content_role", "status", "exp_end_date", "_assign"],
        )

    def wanted_tasks(self) -> dict:
        """{role: {"users": [...], "due": date, "hours": float}} for the tasks this post should have."""
        publish = getdate(self.publish_on) if self.publish_on else None
        settings = frappe.get_cached_doc("HD Content Settings")

        def due(days_before):
            return add_days(publish, -(days_before or 0)) if publish else None

        days = {
            "writer": settings.writer_days_before,
            "designer": settings.designer_days_before,
            "video_editor": settings.video_editor_days_before,
            "marketer": 0,
        }
        if self.task_mode == PER_PERSON:
            # one task per role; several people on a role share it
            return {
                label: {
                    "users": self.people(field),
                    "due": due(days[field]),
                    "hours": self.role_hours(field),
                    "cleared": self.hours_cleared([field]),
                }
                for field, label in TASK_ROLES.items()
                if self.people(field)
            }
        if self.task_mode == ONE_TASK:
            users = self.everyone()
            if users:
                return {
                    SHARED_ROLE: {
                        "users": users,
                        "due": due(days["designer"]),
                        # the shared task covers every role's part
                        "hours": sum(self.role_hours(f) for f in TASK_ROLES),
                        "cleared": self.hours_cleared(list(TASK_ROLES)),
                    }
                }
        return {}

    def hours_cleared(self, roles: list[str]) -> bool:
        """These roles had hours before this save and have none now."""
        before = self.get_doc_before_save()
        if not before or any(self.role_hours(r) for r in roles):
            return False
        return any(flt(before.get(f"{r}_hours")) for r in roles)

    def role_hours(self, role: str) -> float:
        """The hours estimated for a role's part of the post (0 when not given)."""
        return flt(self.get(f"{role}_hours"))

    def task_subject(self, role: str) -> str:
        what = _("Content") if role == SHARED_ROLE else _(role)
        text = f"{what}: {self.title} ({self.platforms_label})"
        if self.customer:
            text += f" · {self.customer}"
        return text[:140]

    def content_project(self) -> str | None:
        """The customer's open Content Calendar project."""
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
                # left empty, the task's hours are estimated by AI instead
                "custom_estimated_hours": plan["hours"] or None,
            }
        ).insert(ignore_permissions=True)
        for user in plan["users"]:
            self.give_task(task, user)

    def plan_task(self, task, plan: dict) -> bool:
        """Set the task's due date, subject and hours from the post; True if anything changed."""
        changed = False
        if plan["due"] and getdate(task.exp_end_date or "1900-01-01") != getdate(
            plan["due"]
        ):
            task.exp_end_date = plan["due"]
            changed = True
        subject = self.task_subject(task.content_role)
        if task.subject != subject:
            task.subject = subject
            changed = True
        # no hours on the post keeps whatever the task has (e.g. an AI estimate),
        # unless the post's hours were just cleared
        if plan["hours"] and flt(task.get("custom_estimated_hours")) != plan["hours"]:
            task.custom_estimated_hours = plan["hours"]
            changed = True
        elif plan.get("cleared") and flt(task.get("custom_estimated_hours")):
            task.custom_estimated_hours = 0
            changed = True
        return changed

    def reassign_task(self, task, users: list):
        current = set(task.assignees())
        for user in current - set(users):
            remove_assignment("Task", task.name, user, ignore_permissions=True)
        for user in set(users) - current:
            self.give_task(task, user)

    def give_task(self, task, user: str):
        if self.flags.quiet_tasks:
            # a monthly plan hands out many tasks at once and its package sends one
            # summary, so the ToDo is created without Frappe's notice per task
            frappe.get_doc(
                {
                    "doctype": "ToDo",
                    "allocated_to": user,
                    "reference_type": "Task",
                    "reference_name": task.name,
                    "description": task.subject,
                    "date": task.exp_end_date,
                    "assigned_by": frappe.session.user,
                }
            ).insert(ignore_permissions=True)
            return
        # the post's rules decided who does it, so the caller's Task permission is skipped
        add_assignment(
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
    def close_task(task, status: str):
        task.status = status
        # the post closed it, so it skips the project's review round
        task.flags.from_content_post = True

    def advance_after_task(self, role: str):
        """A finished part moves an early post to the next stage (writer done: design)."""
        next_status = NEXT_STATUS_AFTER.get(role)
        if not next_status or self.status not in STAGES:
            return
        if role in DESIGN_ROLES and not self.design_done(self.content_tasks()):
            # design and video are one stage: it ends when all its parts are done
            return
        if STAGES.index(self.status) >= STAGES.index(next_status):
            return
        self.status = next_status
        self.save(ignore_permissions=True)

    def end_design_when_its_last_part_is_dropped(self):
        """Taking the person off the last open design part ends Design, as finishing it would.

        sync_tasks cancels that part's task quietly, so the task can't move the post itself.
        """
        if self.is_new() or self.status != "Design" or self.task_mode != PER_PERSON:
            return
        if self.flags.skip_task_sync:
            return
        tasks = self.content_tasks()
        wanted = self.wanted_tasks()
        dropping = {
            t.content_role
            for t in tasks
            if t.content_role in DESIGN_ROLES
            and t.content_role not in wanted
            and t.status not in DONE_TASK_STATUSES
        }
        if dropping and self.design_done(tasks, dropping):
            self.status = "Internal Review"

    @staticmethod
    def design_done(tasks: list, dropping: set | None = None) -> bool:
        """No design part left open, and at least one was finished.

        When every design part was cancelled nobody did the design, so the post
        stays in Design for a lead to reassign or move on by hand.
        """
        design = [t for t in tasks if t.content_role in DESIGN_ROLES]
        still_open = any(
            t.status not in DONE_TASK_STATUSES
            and t.content_role not in (dropping or ())
            for t in design
        )
        return not still_open and any(t.status == "Completed" for t in design)

    def notify_next_person(self):
        """Whoever's turn it is now hears about it, in the bell and in Teams or email."""
        # a new post's people hear through their new task instead
        if self.flags.in_insert or not self.has_value_changed("status"):
            return
        users = [
            u for field in NEXT_PERSON.get(self.status, ()) for u in self.people(field)
        ]
        if self.status == "Internal Review":
            users.append(self.owner)
        message = _("{0} ({1}) is now {2}: your turn.")
        if self.status == HEAD_REVIEW:
            users.extend(head_approvers())
            message = _("{0} ({1}) was approved by the client and needs your approval.")
        users = [u for u in dict.fromkeys(users) if u and u != frappe.session.user]
        if not users:
            return
        notify_users(
            users,
            "HD Content Post",
            self.name,
            message.format(
                self.title, self.customer or self.platforms_label, _(self.status)
            ),
            link=self.board_path(),
        )

    def start_client_review(self):
        """Entering Client Review starts the clock for the client reminder and team alert,
        and a new round for the head (their last decision was on an older version)."""
        if self.status != CLIENT_REVIEW or not self.has_value_changed("status"):
            return
        self.client_review_since = now_datetime()
        self.client_reminded_on = None
        self.client_escalated_on = None
        self.head_decided_by = None
        self.head_decided_on = None
        self.head_feedback = None

    # --- the Digital Marketing Head's approval, after the client's ---

    def guard_editing(self):
        """Only DM Coordinators, managers and System Managers add or change entries.

        Everyone else can attach files (that never saves the post). Changes the app
        makes on someone's behalf pass `ignore_permissions`: the client's portal and ERP
        decisions, the head's approval, and a finished task moving the post on.
        """
        if (
            self.flags.ignore_permissions
            or frappe.flags.in_install
            or frappe.flags.in_migrate
        ):
            return
        if not can_edit_content():
            frappe.throw(
                _(
                    "Only a DM Coordinator can add or change content entries. You can attach files to them."
                ),
                frappe.PermissionError,
            )

    def guard_head_review(self):
        """Once a post has been to the client, it goes out only after the client and then
        the Digital Marketing Head approve it.

        Setting Approved while the post is in Client Review records the client's yes and
        lands in Head Review (the portal and the client's ERP land there too). Any other
        way into Approved, Scheduled or Published for such a post is refused, so it can't
        skip either approval. Only a head moves a post on from Head Review; cancelling
        stays open to everyone. Posts that never went to the client are unchanged.
        """
        before = self.get_doc_before_save()
        previous = before.status if before else None
        if self.status == previous:
            return
        if previous == HEAD_REVIEW:
            self.record_head_decision()
            return
        if self.status == HEAD_REVIEW:
            if previous != CLIENT_REVIEW:
                frappe.throw(
                    _(
                        "A post goes to the Digital Marketing Head only once the client approves it."
                    )
                )
            return
        if self.status not in READY_STATUSES or previous in READY_STATUSES:
            return
        if previous != CLIENT_REVIEW and not self.client_review_since:
            return
        if previous == CLIENT_REVIEW and self.status == "Approved":
            self.status = HEAD_REVIEW
            return
        frappe.throw(
            _(
                "{0} went to the client, so the client and then the Digital Marketing Head approve it before it can be {1}. Send it to Client Review."
            ).format(self.title, _(self.status))
        )

    def record_head_decision(self):
        """Leaving Head Review: only a head decides (or anyone cancels), and it's stamped."""
        if self.status == "Cancelled":
            return
        if not is_dm_head():
            frappe.throw(
                _(
                    "Only the Digital Marketing Head can approve this post or send it back."
                )
            )
        if self.status == "Changes Requested" and not (
            self.head_feedback and self.has_value_changed("head_feedback")
        ):
            frappe.throw(_("Say what needs to change when sending the post back."))
        self.head_decided_by = frappe.session.user
        self.head_decided_on = now_datetime()

    def approve_as_head(self):
        """The head's yes: the post is Approved and the marketer hears it's their turn."""
        self.ensure_in_head_review()
        self.status = "Approved"
        self.save(ignore_permissions=True)
        self.add_comment("Info", _("Approved by the Digital Marketing Head."))

    def send_back_as_head(self, reason: str):
        """The head's no: back to Changes Requested with why, for the team to fix."""
        reason = (reason or "").strip()
        if not reason:
            frappe.throw(_("Say what needs to change when sending the post back."))
        self.ensure_in_head_review()
        self.status = "Changes Requested"
        self.head_feedback = reason
        self.save(ignore_permissions=True)
        self.add_comment(
            "Info",
            _("Sent back by the Digital Marketing Head: {0}").format(
                escape_html(reason)
            ),
        )

    def ensure_in_head_review(self):
        if self.status != HEAD_REVIEW:
            frappe.throw(
                _("{0} isn't waiting for the Digital Marketing Head").format(self.title)
            )
        if not is_dm_head():
            frappe.throw(
                _(
                    "Only the Digital Marketing Head can approve this post or send it back."
                )
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
        valid = set(
            frappe.qb.get_query("HD Content Platform", fields=["name"]).run(pluck=True)
        )
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

    def validate_publish_on(self):
        # a post without a date has no slot on the calendar, so nobody would see it
        if self.status != "Cancelled" and not self.publish_on:
            frappe.throw(_("Set the posting date and time"))

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
        self.status = HEAD_REVIEW
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
            "owner",
        ],
    )
    teams = teams_of([p.name for p in posts])
    heads = head_approvers()
    for post in posts:
        users = [*teams[post.name], post.owner]
        # waiting on the head's approval, so they hear it too
        if post.status == HEAD_REVIEW:
            users.extend(heads)
        # same path as other reminders: the bell plus Teams or email, once per day and stage;
        # notify_users drops empty slots, Administrator and Guest, and duplicates
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
        )
        .where(Post.publish_on <= cutoff)
        .where(Post.status.notin(CLOSED_STATUSES))
        .where(Post.missed_alert_sent == 0)
        .run(as_dict=True)
    )

    always = settings.get_alert_recipients()
    teams = teams_of([p.name for p in posts])
    sent = 0
    for post in posts:
        recipients = always | (
            _user_emails(teams[post.name]) if settings.notify_post_team else set()
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
            teams[post.name],
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


def team_of(doc) -> dict[str, list[str]]:
    """Each role's people, the main person first, without repeats."""
    team = {}
    for role in TASK_ROLES:
        users = [doc.get(role)] + [
            r.user for r in doc.get("extra_team") or [] if r.role == role
        ]
        team[role] = list(dict.fromkeys(u for u in users if u))
    return team


def teams_of(posts: list[str]) -> dict[str, list[str]]:
    """Everyone on each of these posts, in role order, for reminders and alerts."""
    return {
        name: list(dict.fromkeys(u for users in team.values() for u in users))
        for name, team in role_teams_of(posts).items()
    }


def role_teams_of(posts: list[str]) -> dict[str, dict[str, list[str]]]:
    """Each post's people by role, the main person first, in two queries for any number of posts."""
    if not posts:
        return {}
    main = frappe.get_all(
        "HD Content Post",
        filters={"name": ("in", posts)},
        fields=["name", *TASK_ROLES],
    )
    extra = frappe.get_all(
        "HD Content Post Member",
        filters={"parenttype": "HD Content Post", "parent": ("in", posts)},
        fields=["parent", "role", "user"],
        order_by="idx asc",
    )
    out = {p.name: {role: [p.get(role)] for role in TASK_ROLES} for p in main}
    for row in extra:
        if row.parent in out and row.role in TASK_ROLES:
            out[row.parent][row.role].append(row.user)
    return {
        name: {
            role: list(dict.fromkeys(u for u in users if u))
            for role, users in team.items()
        }
        for name, team in out.items()
    }


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
    """Sees every post: project managers, the DM Coordinators and System Managers, who
    edit them all, and the Digital Marketing Head, who approves them all."""
    from helpdesk.tasky.permissions import is_project_manager

    return is_project_manager(user) or can_edit_content(user) or is_dm_head(user)


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
    # the content calendar is the Digital team's; ERP Employees don't see it
    if is_erp_only(user):
        return "1 = 0"
    u = frappe.db.escape(user)
    table = "`tabHD Content Post`"
    return (
        f"({table}.`writer` = {u} or {table}.`designer` = {u} or {table}.`marketer` = {u} "
        f"or {table}.`video_editor` = {u} or {table}.`owner` = {u} "
        f"or {table}.`name` in (select `parent` from `tabHD Content Post Member` "
        f"where `parenttype` = 'HD Content Post' and `user` = {u}) "
        f"or {table}.`customer` in ({_member_customers_sql(user)}))"
    )


def has_permission(
    doc, ptype: str | None = None, user: str | None = None
) -> bool | None:
    user = user or frappe.session.user
    if ptype == "create" or _is_content_lead(user):
        return None
    if is_erp_only(user):
        return False
    on_team = any(user in people for people in team_of(doc).values())
    if on_team or user == doc.owner or doc.customer in member_customers(user):
        return None
    return False
