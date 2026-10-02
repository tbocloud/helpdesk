# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_to_date,
    escape_html,
    format_datetime,
    get_datetime,
    now_datetime,
    validate_email_address,
)

from helpdesk import teams_meetings
from helpdesk.work_reminders import notify_users

REFERENCE_DOCTYPES = ("HD Ticket", "Task")
SCHEDULED = "Scheduled"
CANCELLED = "Cancelled"
MAX_ATTENDEES = 50
SYNC_DAYS_AHEAD = 60
# Outlook's attendee replies, as shown in the hub; the organizer has no reply
OUTLOOK_REPLIES = {
    "accepted": "Accepted",
    "tentativelyAccepted": "Tentative",
    "declined": "Declined",
    "notResponded": "No reply",
    "none": "No reply",
}


class HDMeeting(Document):
    def validate(self):
        self.validate_reference()
        self.validate_times()
        self.clean_attendees()
        self.set_customer()

    def validate_reference(self):
        if self.reference_doctype not in REFERENCE_DOCTYPES:
            frappe.throw(_("Meetings can be scheduled from tickets and tasks only."))

    def validate_times(self):
        if get_datetime(self.ends_on) <= get_datetime(self.starts_on):
            frappe.throw(_("The meeting must end after it starts."))

    def clean_attendees(self):
        """Lowercase, valid and unique emails; staff are marked for reminders."""
        seen = set()
        rows = []
        for row in self.attendees:
            email = (row.email or "").strip().lower()
            if not email or email in seen:
                continue
            if not validate_email_address(email):
                frappe.throw(_("{0} is not a valid email address.").format(row.email))
            seen.add(email)
            row.email = email
            row.is_internal = int(self.is_staff(email))
            rows.append(row)
        if not rows:
            frappe.throw(_("Add at least one attendee."))
        if len(rows) > MAX_ATTENDEES:
            frappe.throw(
                _("A meeting can have at most {0} attendees.").format(MAX_ATTENDEES)
            )
        self.attendees = rows

    def set_customer(self):
        if self.reference_doctype == "HD Ticket":
            self.customer = frappe.db.get_value(
                "HD Ticket", self.reference_name, "customer"
            )
        elif self.reference_doctype == "Task":
            project = frappe.db.get_value("Task", self.reference_name, "project")
            customer = project and frappe.db.get_value("Project", project, "customer")
            self.customer = (
                customer
                if customer and frappe.db.exists("HD Customer", customer)
                else None
            )

    # --- Teams ---

    def schedule_in_teams(self):
        """Creates the Outlook event with its Teams link; the caller saves."""
        created = teams_meetings.create_event(self)
        self.external_id = created["external_id"]
        self.join_url = created["join_url"]

    def cancel_in_teams(self, reason: str = ""):
        """Cancels the Outlook event (attendees are told) and marks this meeting; the caller saves."""
        if self.status == CANCELLED:
            return
        if self.external_id:
            teams_meetings.cancel_event(self, reason)
        self.status = CANCELLED
        self.cancel_reason = reason

    def sync_from_outlook(self) -> tuple[list[str], bool]:
        """Takes Outlook's version of the meeting (people move and cancel meetings there).

        Returns what changed, for a note on the ticket or task, and whether
        anything changed at all (replies included). The caller saves.
        """
        try:
            event = teams_meetings.get_event(self)
        except teams_meetings.GraphError as e:
            if e.status != 404:
                raise
            self.status = CANCELLED
            self.cancel_reason = _("Deleted in Outlook")
            return [_("deleted in Outlook")], True
        if event.get("isCancelled"):
            self.status = CANCELLED
            self.cancel_reason = _("Cancelled in Outlook")
            return [_("cancelled in Outlook")], True

        changes = []
        subject = (event.get("subject") or "").strip()
        if subject and subject != self.subject:
            self.subject = subject
            changes.append(_("renamed to {0}").format(subject))
        start = teams_meetings.system_time(event.get("start"))
        end = teams_meetings.system_time(event.get("end"))
        # Outlook keeps whole seconds; what is stored here may carry microseconds
        old_start = get_datetime(self.starts_on).replace(microsecond=0)
        old_end = get_datetime(self.ends_on).replace(microsecond=0)
        if start and end and (start != old_start or end != old_end):
            self.starts_on, self.ends_on = start, end
            if start != old_start:
                # a reminder already sent was for the old time
                self.reminder_sent = int(start <= now_datetime())
                changes.append(_("moved to {0}").format(self.when_label()))
            else:
                changes.append(
                    _("now ends at {0}").format(format_datetime(end, "HH:mm"))
                )
        replies_changed = self.take_replies(event.get("attendees") or [])
        return changes, bool(changes) or replies_changed

    def take_replies(self, attendees: list[dict]) -> bool:
        """Each attendee's Accepted/Tentative/Declined; people added in Outlook join the list."""
        replies = {}
        for attendee in attendees:
            email = ((attendee.get("emailAddress") or {}).get("address") or "").lower()
            response = (attendee.get("status") or {}).get("response") or "none"
            if email and response != "organizer":
                replies[email] = OUTLOOK_REPLIES.get(response, "No reply")
        changed = False
        for row in self.attendees:
            reply = replies.pop(row.email, None)
            # no reply yet and Outlook's "none" are the same thing
            if reply and reply != (row.response or "No reply"):
                row.response = reply
                changed = True
        for email, reply in replies.items():
            if len(self.attendees) >= MAX_ATTENDEES:
                break
            self.append("attendees", {"email": email, "response": reply})
            changed = True
        return changed

    def invitation_body(self) -> str:
        """What attendees read in the invitation: the agenda and which ticket or task it is about."""
        parts = []
        if self.agenda:
            parts.append(escape_html(self.agenda).replace("\n", "<br>"))
        parts.append(escape_html(self.reference_label()))
        return "".join(f"<p>{part}</p>" for part in parts)

    def reference_label(self) -> str:
        if self.reference_doctype == "HD Ticket":
            subject = frappe.db.get_value("HD Ticket", self.reference_name, "subject")
            return _("TBO Support ticket #{0}: {1}").format(
                self.reference_name, subject
            )
        subject = frappe.db.get_value("Task", self.reference_name, "subject")
        return _("TBO Support task {0}: {1}").format(self.reference_name, subject)

    # --- notes and reminders ---

    def note_on_reference(self, text: str):
        """An internal note on the ticket or task, so the team sees the meeting there."""
        if self.reference_doctype == "HD Ticket":
            frappe.get_doc(
                {
                    "doctype": "HD Ticket Comment",
                    "reference_ticket": self.reference_name,
                    "commented_by": frappe.session.user,
                    "content": f"<p>{escape_html(text)}</p>",
                }
            ).insert(ignore_permissions=True)
        else:
            frappe.get_doc("Task", self.reference_name).add_comment("Comment", text)

    def when_label(self) -> str:
        return format_datetime(self.starts_on, "d MMM, HH:mm")

    def staff_users(self) -> list[str]:
        emails = [a.email for a in self.attendees if a.is_internal]
        if self.scheduled_by:
            emails.append(self.scheduled_by)
        return sorted(
            set(frappe.get_all("User", filters={"email": ("in", emails)}, pluck="name"))
        )

    def send_reminder(self):
        """Reminds the TBO staff in the meeting; the caller saves."""
        notify_users(
            self.staff_users(),
            self.reference_doctype,
            self.reference_name,
            _("Teams meeting at {0}: {1}. Join: {2}").format(
                format_datetime(self.starts_on, "HH:mm"), self.subject, self.join_url
            ),
        )
        self.reminder_sent = 1

    @staticmethod
    def is_staff(email: str) -> bool:
        user = frappe.db.get_value("User", {"email": email}, "name")
        return bool(
            user and frappe.db.exists("HD Agent", {"user": user, "is_active": 1})
        )


def send_reminders():
    """Every 5 minutes: remind staff of Teams meetings starting soon."""
    if not teams_meetings.is_enabled():
        return
    minutes = frappe.db.get_single_value("HD Meeting Settings", "reminder_minutes")
    if not minutes:
        return
    now = now_datetime()
    due = frappe.get_all(
        "HD Meeting",
        filters={
            "status": SCHEDULED,
            "reminder_sent": 0,
            "join_url": ("is", "set"),
            "starts_on": ("between", [now, add_to_date(now, minutes=minutes)]),
        },
        pluck="name",
    )
    for name in due:
        meeting = frappe.get_doc("HD Meeting", name)
        meeting.send_reminder()
        meeting.save(ignore_permissions=True)


def sync_with_outlook():
    """Every 15 minutes: upcoming meetings take the changes made in Outlook."""
    if not teams_meetings.is_enabled():
        return
    now = now_datetime()
    names = frappe.get_all(
        "HD Meeting",
        filters={
            "status": SCHEDULED,
            "external_id": ("is", "set"),
            "ends_on": (">=", add_to_date(now, days=-1)),
            "starts_on": ("<=", add_to_date(now, days=SYNC_DAYS_AHEAD)),
        },
        pluck="name",
    )
    for name in names:
        meeting = frappe.get_doc("HD Meeting", name)
        try:
            changes, changed = meeting.sync_from_outlook()
        except (teams_meetings.GraphError, requests.RequestException):
            # the same problem (a revoked permission, an outage) would fail every meeting
            frappe.log_error(title="Teams meeting sync failed")
            return
        if not changed:
            continue
        meeting.save(ignore_permissions=True)
        if changes:
            meeting.note_on_reference(
                _("Teams meeting {0} changed in Outlook: {1}").format(
                    meeting.subject, ", ".join(changes)
                )
            )
