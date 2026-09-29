# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, formatdate, get_datetime, getdate, now, nowdate

WAITING_ON_TASK = "Waiting on Task"
ON_HOLD = "On Hold"
PENDING_REVIEW = "Pending Review"
DONE = ("Completed", "Cancelled")
# a task can't enter these while the task it depends on is still open
NEEDS_DEPENDENCY_DONE = ("Working", PENDING_REVIEW, "Completed")


class Task(Document):
    def validate(self):
        self.validate_dependency()
        self.track_hold()
        self.route_completion_to_review()
        self.track_slip()

    def on_update(self):
        self.hand_back_ticket_when_completed()
        self.record_hold_change()
        self.record_slip()
        self.request_review()
        self.unblock_dependents()

    def status_changed(self) -> bool:
        before = self.get_doc_before_save()
        return not before or before.status != self.status

    def validate_dependency(self):
        """Same project, no loops, and the task it waits on must be done before this one moves on."""
        if not self.depends_on_task:
            return
        if self.depends_on_task == self.name:
            frappe.throw(_("A task can't depend on itself."))
        dependency = frappe.db.get_value(
            "Task",
            self.depends_on_task,
            ["project", "status", "subject"],
            as_dict=True,
        )
        if not dependency:
            frappe.throw(_("Task {0} not found.").format(self.depends_on_task))
        if dependency.project != self.project:
            frappe.throw(_("A task can only depend on a task in the same project."))
        self.check_dependency_loop()
        if (
            self.status in NEEDS_DEPENDENCY_DONE
            and self.status_changed()
            and dependency.status not in DONE
        ):
            frappe.throw(
                _("Finish {0} ({1}) first: this task depends on it.").format(
                    self.depends_on_task, dependency.subject
                )
            )

    def check_dependency_loop(self):
        seen = {self.name}
        current = self.depends_on_task
        while current:
            if current in seen:
                frappe.throw(_("These tasks would depend on each other in a loop."))
            seen.add(current)
            current = frappe.db.get_value("Task", current, "depends_on_task")

    def route_completion_to_review(self):
        """On projects that want it, a team member's "done" goes to the lead first."""
        from helpdesk.tasky.permissions import can_manage_project

        if not self.status_changed() or self.flags.hold_ended:
            return
        if self.status not in ("Completed", PENDING_REVIEW):
            return
        if not self.project or not frappe.db.get_value(
            "Project", self.project, "review_before_done"
        ):
            return
        if self.status == "Completed" and can_manage_project(self.project):
            return
        self.status = PENDING_REVIEW
        self.flags.review_requested = True

    def track_slip(self):
        """Count due dates moved later; days added by a hold resume aren't a slip."""
        before = self.get_doc_before_save()
        if not before or not before.exp_end_date or not self.exp_end_date:
            return
        if self.flags.hold_ended:
            return
        if getdate(self.exp_end_date) <= getdate(before.exp_end_date):
            return
        self.slip_count = (self.slip_count or 0) + 1
        self.flags.slipped = {"old_due": before.exp_end_date}

    def record_slip(self):
        from helpdesk.work_reminders import notify_users

        slipped = self.flags.slipped
        if not slipped:
            return
        text = _("Due date moved from {0} to {1}.").format(
            formatdate(slipped["old_due"]), formatdate(self.exp_end_date)
        )
        if self.flags.slip_reason:
            text += " " + _("Reason: {0}").format(self.flags.slip_reason)
        self.add_comment("Info", frappe.utils.escape_html(text))

        notify_users(
            [u for u in self.assignees() if u != frappe.session.user],
            "Task",
            self.name,
            _("Due date moved to {0}: {1}").format(
                formatdate(self.exp_end_date), self.subject
            ),
        )
        if self.is_key or self.is_milestone:
            label = _("Milestone") if self.is_milestone else _("Key task")
            notify_users(
                [
                    u
                    for u in self.leads_or_managers(both=True)
                    if u != frappe.session.user
                ],
                "Task",
                self.name,
                _("{0} rescheduled to {1} (moved {2} times): {3}").format(
                    label, formatdate(self.exp_end_date), self.slip_count, self.subject
                ),
            )

    def request_review(self):
        from helpdesk.work_reminders import notify_users

        if not self.flags.review_requested:
            return
        self.add_comment("Info", _("Sent for review."))
        notify_users(
            [u for u in self.leads_or_managers() if u != frappe.session.user],
            "Task",
            self.name,
            _("Ready for review ({0}): {1}").format(
                formatdate(nowdate()), self.subject
            ),
        )

    def unblock_dependents(self):
        """Tell whoever is waiting on this task that they can go ahead."""
        from helpdesk.work_reminders import notify_users

        if self.status != "Completed" or not self.status_changed():
            return
        waiting = frappe.get_all(
            "Task",
            filters={
                "depends_on_task": self.name,
                "status": ("not in", list(DONE)),
            },
            fields=["name", "subject", "_assign"],
        )
        for task in waiting:
            notify_users(
                frappe.parse_json(task._assign or "[]"),
                "Task",
                task.name,
                _("Unblocked, {0} is done: {1}").format(self.subject, task.subject),
            )

    def assignees(self) -> list[str]:
        return frappe.parse_json(self.get("_assign") or "[]")

    def leads_or_managers(self, both: bool = False) -> list[str]:
        """The project lead, or its managers when there's no lead (or both, for escalations)."""
        from helpdesk.work_reminders import get_project_managers

        if not self.project:
            return []
        lead = frappe.db.get_value("Project", self.project, "project_lead")
        managers = get_project_managers(self.project) if both or not lead else []
        return [u for u in [lead, *managers] if u]

    def track_hold(self):
        if self.is_going_on_hold():
            self.start_hold()
        elif self.is_resuming():
            self.end_hold()

    def record_hold_change(self):
        if self.flags.hold_started:
            self.announce_hold()
        if self.flags.hold_ended:
            self.log_resume()

    def hand_back_ticket_when_completed(self):
        if self.status == "Completed" and self.has_value_changed("status"):
            self.notify_ticket_task_completed()

    def is_going_on_hold(self) -> bool:
        before = self.get_doc_before_save()
        return self.status == ON_HOLD and (not before or before.status != ON_HOLD)

    def is_resuming(self) -> bool:
        before = self.get_doc_before_save()
        return bool(before) and before.status == ON_HOLD and self.status != ON_HOLD

    def start_hold(self):
        """Record why and since when; a running timer stops so the hold isn't counted as work."""
        if not self.hold_reason:
            frappe.throw(_("Choose why the task is on hold."))
        before = self.get_doc_before_save()
        self.hold_since = nowdate()
        self.hold_previous_status = before.status if before else "Open"
        if self.get("custom_timer_start"):
            hours = (
                get_datetime(now()) - get_datetime(self.custom_timer_start)
            ).total_seconds() / 3600
            self.custom_actual_hours = (self.custom_actual_hours or 0) + round(hours, 2)
            self.custom_timer_elapsed = (self.custom_timer_elapsed or 0) + round(
                hours, 2
            )
            self.custom_timer_start = None
        self.flags.hold_started = True

    def end_hold(self):
        """Add the days on hold to the due date (unless told not to) and clear the hold."""
        days = max((getdate(nowdate()) - getdate(self.hold_since or nowdate())).days, 0)
        old_due = self.exp_end_date
        if days and self.exp_end_date and self.flags.extend_due_date is not False:
            self.exp_end_date = add_days(self.exp_end_date, days)
        self.hold_days_total = (self.hold_days_total or 0) + days
        if self.status == "Working" and not self.get("custom_timer_start"):
            self.custom_timer_start = now()
        self.flags.hold_ended = {
            "days": days,
            "reason": self.hold_reason,
            "old_due": old_due,
        }
        self.hold_reason = None
        self.hold_note = None
        self.hold_since = None
        self.hold_previous_status = None

    def announce_hold(self):
        """Tell the project lead (or its managers) right away, and keep it in the task's history."""
        from helpdesk.work_reminders import notify_users

        text = _("On hold: {0}").format(self.hold_reason)
        if self.hold_note:
            text += f" - {self.hold_note}"
        self.add_comment("Info", frappe.utils.escape_html(text))

        if not self.project:
            return
        notify_users(
            [u for u in self.leads_or_managers() if u != frappe.session.user],
            "Task",
            self.name,
            _("On hold since {0} ({1}): {2}").format(
                formatdate(self.hold_since), self.hold_reason, self.subject
            ),
        )

    def log_resume(self):
        ended = self.flags.hold_ended
        text = _("Resumed after {0} day(s) on hold ({1}).").format(
            ended["days"], ended["reason"] or ""
        )
        if ended["old_due"] and getdate(ended["old_due"]) != getdate(self.exp_end_date):
            text += " " + _("Due date moved from {0} to {1}.").format(
                formatdate(ended["old_due"]), formatdate(self.exp_end_date)
            )
        self.add_comment("Info", frappe.utils.escape_html(text))

    def notify_ticket_task_completed(self):
        """Hand the linked support ticket back to the agent once the work is done."""
        if not self.hd_ticket or not frappe.db.exists("HD Ticket", self.hd_ticket):
            return
        ticket = frappe.get_doc("HD Ticket", self.hd_ticket)
        if ticket.status == WAITING_ON_TASK:
            ticket.status = "Open"
            ticket.save(ignore_permissions=True)
        done_by = (
            frappe.db.get_value("User", frappe.session.user, "full_name")
            or frappe.session.user
        )
        comment = frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": ticket.name,
                "content": _(
                    "Task {0} ({1}) was completed by {2}. Reply to the customer."
                ).format(
                    frappe.bold(self.name),
                    frappe.utils.escape_html(self.subject or ""),
                    done_by,
                ),
                "commented_by": frappe.session.user,
            }
        )
        comment.insert(ignore_permissions=True)
