# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""Work that repeats on a schedule: "Monthly backup check" on the 1st, "GST filing
reminder" on the 15th, "Weekly status report" every Friday.

The daily job (create_recurring_tasks) creates the task for each occurrence once its
day comes (the due date minus the lead time), assigns it and links it back here.
Dates that went past while the schedule was new, paused or changed are skipped, not
created late. See docs/recurring-tasks.md.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    cint,
    cstr,
    escape_html,
    flt,
    formatdate,
    getdate,
    nowdate,
)

from helpdesk.recurrence import (
    AFTER,
    MONTHS_PER_STEP,
    ON_DATE,
    describe,
    occurrences,
    time_label,
    upcoming,
    validate_rule,
    weekday_names,
    weekday_numbers,
    working_day_checker,
)

RECURRING_TASK = "HD Recurring Task"
CLOSED_PROJECT = ("Completed", "Cancelled")
# a change to any of these starts the schedule over from today
SCHEDULE_FIELDS = (
    "frequency",
    "interval",
    "weekdays",
    "month_day",
    "last_day_of_month",
    "start_date",
    "ends",
    "end_date",
    "max_occurrences",
    "lead_days",
    "skip_non_working_days",
)
# the working-day calendar is read this far ahead (upcoming() looks ten years out)
CALENDAR_DAYS_AHEAD = 4100


class HDRecurringTask(Document):
    def validate(self):
        self.clean_task_fields()
        self.validate_project_open()
        self.validate_assignee()
        self.clean_schedule()
        self.clear_reason_on_resume()
        self.skip_past_occurrences()
        self.set_next_due()

    def on_trash(self):
        self.unlink_generated_tasks()

    # --- validation ---

    def clean_task_fields(self):
        self.subject = (self.subject or "").strip()
        if not self.subject:
            frappe.throw(_("Give the task a name."))
        if self.category and self.category not in self.task_options("custom_category"):
            frappe.throw(_("Category {0} isn't a task category.").format(self.category))
        self.priority = self.priority or "Medium"
        if flt(self.estimated_hours) < 0:
            frappe.throw(_("Estimated hours can't be negative."))

    @staticmethod
    def task_options(fieldname: str) -> list[str]:
        options = frappe.get_meta("Task").get_options(fieldname) or ""
        return [o for o in options.split("\n") if o]

    def validate_project_open(self):
        if not (self.is_new() or self.resumed()):
            return
        status = frappe.db.get_value("Project", self.project, "status")
        if status in CLOSED_PROJECT:
            frappe.throw(
                _("Project {0} is {1}, so nothing can repeat in it.").format(
                    self.project_name or self.project, _(status)
                )
            )

    def validate_assignee(self):
        from helpdesk.tasky.api import _is_assignable
        from helpdesk.tasky.permissions import get_project_team

        if not self.assignee or not self.has_value_changed("assignee"):
            return
        if not _is_assignable(self.assignee):
            frappe.throw(_("{0} is not an active agent.").format(self.assignee))
        if self.assignee not in get_project_team(self.project):
            frappe.throw(
                _(
                    "{0} isn't on this project's team. Add them to the project first."
                ).format(self.assignee)
            )

    def clean_schedule(self):
        """Keeps only the fields the frequency uses, so the rule reads one way."""
        self.interval = cint(self.interval) or 1
        self.lead_days = cint(self.lead_days)
        start = getdate(self.start_date) if self.start_date else None
        if self.frequency == "Weekly":
            numbers = weekday_numbers(self.weekdays) or (
                [start.weekday()] if start else []
            )
            self.weekdays = weekday_names(numbers)
        else:
            self.weekdays = None
        if self.frequency in MONTHS_PER_STEP:
            self.last_day_of_month = cint(self.last_day_of_month)
            if self.last_day_of_month:
                self.month_day = None
            elif not self.month_day and start:
                self.month_day = start.day
        else:
            self.month_day = None
            self.last_day_of_month = 0
        if self.ends != ON_DATE:
            self.end_date = None
        if self.ends != AFTER:
            self.max_occurrences = None
        validate_rule(self)

    def clear_reason_on_resume(self):
        if self.resumed():
            self.inactive_reason = None

    # --- the schedule ---

    def resumed(self) -> bool:
        return (
            not self.is_new()
            and cint(self.is_active)
            and self.has_value_changed("is_active")
        )

    def schedule_changed(self) -> bool:
        before = None if self.is_new() else self.get_doc_before_save()
        if not before:
            return True
        return any(
            self.schedule_value(self, field) != self.schedule_value(before, field)
            for field in SCHEDULE_FIELDS
        )

    @staticmethod
    def schedule_value(doc, field: str):
        """Compares like with like: the dialog sends "2026-10-01" where the database
        has a date, so has_value_changed would see every save as a change."""
        value = doc.get(field)
        if field in ("start_date", "end_date"):
            return getdate(value) if value else None
        if field in ("frequency", "weekdays", "ends"):
            return cstr(value)
        return cint(value)

    def is_working(self):
        today = getdate(nowdate())
        return working_day_checker(
            min(getdate(self.start_date), today),
            add_days(today, CALENDAR_DAYS_AHEAD),
        )

    def skip_past_occurrences(self, force: bool = False):
        """A new, changed or resumed schedule starts from today: dates already due
        before today are marked handled instead of becoming overdue tasks."""
        if not (force or self.schedule_changed() or self.resumed()):
            return
        today = getdate(nowdate())
        past = [
            occurrence.on
            for occurrence in occurrences(self, self.is_working(), today)
            if occurrence.due < today
        ]
        if past and (
            not self.last_occurrence or past[-1] > getdate(self.last_occurrence)
        ):
            self.last_occurrence = past[-1]

    def next_occurrences(self, count: int) -> list:
        after = getdate(self.last_occurrence) if self.last_occurrence else None
        return upcoming(self, self.is_working(), after, count)

    def set_next_due(self):
        upcoming_ = self.next_occurrences(1)
        self.next_due_date = upcoming_[0].due if upcoming_ else None
        self.next_create_on = upcoming_[0].create_on if upcoming_ else None
        if upcoming_:
            self.restart_if_extended()
            return
        if self.schedule_changed() or self.resumed():
            frappe.throw(
                _(
                    "This schedule has no dates left. Change the start date or when it ends."
                )
            )
        if cint(self.is_active):
            self.is_active = 0
            self.inactive_reason = _(
                "Finished: every task in the schedule was created."
            )

    def restart_if_extended(self):
        """A finished schedule whose end was moved later runs again; a paused one
        stays paused until someone resumes it."""
        before = None if self.is_new() else self.get_doc_before_save()
        if (
            before
            and not cint(self.is_active)
            and not before.next_due_date
            and self.schedule_changed()
            and frappe.db.get_value("Project", self.project, "status")
            not in CLOSED_PROJECT
        ):
            self.is_active = 1
            self.inactive_reason = None

    def preview(self, count: int = 5) -> list:
        """The next due dates as they would be created if this rule were saved now."""
        self.clean_schedule()
        self.skip_past_occurrences(force=True)
        return self.next_occurrences(count)

    # --- the daily job ---

    def create_due_tasks(self, today=None) -> str | None:
        """Creates the task whose day has come and saves the schedule; returns the task.

        After missed runs only the latest occurrence is created, with a note naming
        the dates that were skipped.
        """
        today = getdate(today or nowdate())
        if not cint(self.is_active):
            return None
        if self.stop_for_closed_project():
            self.save(ignore_permissions=True)
            return None
        pending = self.pending_occurrences(today)
        task = self.create_task(pending[-1], pending[:-1]) if pending else None
        self.save(ignore_permissions=True)
        return task

    def stop_for_closed_project(self) -> bool:
        status = frappe.db.get_value("Project", self.project, "status")
        if status not in CLOSED_PROJECT:
            return False
        self.is_active = 0
        self.inactive_reason = _("Stopped: project {0} is {1}.").format(
            self.project_name or self.project, _(status)
        )
        self.notify_stopped()
        return True

    def pending_occurrences(self, today) -> list:
        """Occurrences whose creation day has come and that aren't handled yet, oldest first."""
        after = getdate(self.last_occurrence) if self.last_occurrence else None
        return [
            occurrence
            for occurrence in occurrences(
                self, self.is_working(), add_days(today, cint(self.lead_days))
            )
            if occurrence.create_on <= today
            and (after is None or occurrence.on > after)
        ]

    def create_task(self, occurrence, missed: list) -> str | None:
        from helpdesk.tasky.api import _assign_user

        self.last_occurrence = occurrence.on
        if frappe.db.exists(
            "Task",
            {
                "custom_recurring_task": self.name,
                "custom_recurrence_date": occurrence.on,
            },
        ):
            return None
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": self.subject,
                "description": self.description or "",
                "project": self.project,
                "custom_category": self.category or "",
                "priority": self.priority or "Medium",
                "custom_estimated_hours": flt(self.estimated_hours),
                "is_key": cint(self.is_key),
                "status": "Open",
                "exp_end_date": occurrence.due,
                "custom_recurring_task": self.name,
                "custom_recurrence_date": occurrence.on,
            }
        ).insert(ignore_permissions=True)
        assignee = self.current_assignee()
        if assignee:
            _assign_user(
                task,
                assignee,
                ignore_permissions=True,
                assigned_by=self.owner,
                note=self.assignment_note(occurrence),
            )
        else:
            self.notify_unassigned(task)
        if missed:
            self.note_missed(task, missed)
        self.last_task = task.name
        self.occurrences_created = cint(self.occurrences_created) + 1
        return task.name

    def current_assignee(self) -> str | None:
        """The assignee, while they are still an active agent on the project's team."""
        from helpdesk.tasky.api import _is_assignable
        from helpdesk.tasky.permissions import get_project_team

        if (
            self.assignee
            and _is_assignable(self.assignee)
            and self.assignee in get_project_team(self.project)
        ):
            return self.assignee
        return None

    def assignment_note(self, occurrence) -> str:
        due = formatdate(occurrence.due, "d MMM yyyy")
        if self.due_time:
            due = f"{due}, {time_label(self.due_time)}"
        return _("{0} (repeats: {1}), due {2}").format(
            escape_html(self.subject), escape_html(describe(self)), due
        )

    def note_missed(self, task, missed: list):
        dates = ", ".join(formatdate(o.due, "d MMM yyyy") for o in missed)
        task.add_comment(
            "Info",
            _(
                "The daily run missed earlier dates of this schedule ({0}); only this latest task was created."
            ).format(dates),
        )

    def people_to_tell(self) -> list[str]:
        from helpdesk.work_reminders import get_project_managers

        lead = frappe.db.get_value("Project", self.project, "project_lead")
        return [self.owner, lead, *get_project_managers(self.project)]

    def notify_unassigned(self, task):
        from helpdesk.work_reminders import notify_users

        notify_users(
            self.people_to_tell(),
            "Task",
            task.name,
            _(
                "Recurring task {0} was created without an assignee: pick someone for it."
            ).format(self.subject),
        )

    def notify_stopped(self):
        from helpdesk.work_reminders import notify_users

        notify_users(
            self.people_to_tell(),
            RECURRING_TASK,
            self.name,
            _("Recurring task {0} stopped: {1}").format(
                self.subject, self.inactive_reason
            ),
            link=f"/projects/{self.project}/recurring",
        )

    # --- deleting ---

    def unlink_generated_tasks(self):
        """The tasks it created stay; they just stop pointing at a schedule that's gone."""
        task = frappe.qb.DocType("Task")
        (
            frappe.qb.update(task)
            .set(task.custom_recurring_task, None)
            .where(task.custom_recurring_task == self.name)
        ).run()


def create_recurring_tasks():
    """Daily: create the tasks whose day has come, one schedule at a time."""
    today = getdate(nowdate())
    for name in frappe.get_all(RECURRING_TASK, filters={"is_active": 1}, pluck="name"):
        try:
            frappe.get_doc(RECURRING_TASK, name).create_due_tasks(today)
            frappe.db.commit()  # nosemgrep - one schedule's task must not undo another's
        except Exception:  # noqa: BLE001 - one bad schedule must not stop the others
            frappe.db.rollback()
            frappe.log_error(
                title=f"Recurring task failed for {name}",
                message=frappe.get_traceback(),
            )
