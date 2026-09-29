# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, formatdate, get_datetime, getdate, now, nowdate

WAITING_ON_TASK = "Waiting on Task"
ON_HOLD = "On Hold"


class Task(Document):
    def validate(self):
        self.track_hold()

    def on_update(self):
        self.hand_back_ticket_when_completed()
        self.record_hold_change()

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
        from helpdesk.work_reminders import get_project_managers, notify_users

        text = _("On hold: {0}").format(self.hold_reason)
        if self.hold_note:
            text += f" - {self.hold_note}"
        self.add_comment("Info", frappe.utils.escape_html(text))

        if not self.project:
            return
        lead = frappe.db.get_value("Project", self.project, "project_lead")
        recipients = [lead] if lead else get_project_managers(self.project)
        notify_users(
            [u for u in recipients if u != frappe.session.user],
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
