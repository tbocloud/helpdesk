"""Internal meetings scheduled from the Meetings calendar (no ticket or task)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.api import calendar, meetings
from helpdesk.test_utils import (
    get_reminder_messages,
    make_meeting,
    make_tasky_user,
    make_ticket,
)

ORGANISER = ("organiser.team@team-meetings.example", "Anu Joseph")
COLLEAGUE = ("colleague.team@team-meetings.example", "Biju Mathew")
OTHER = ("other.team@team-meetings.example", "Cini Varghese")
MEETING_TYPE = "Weekly review"


class TeamMeetingCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        mail = patch("frappe.sendmail")
        self.sendmail = mail.start()
        self.addCleanup(mail.stop)
        for person in (ORGANISER, COLLEAGUE, OTHER):
            make_tasky_user(*person)
            frappe.db.set_value("HD Agent", person[0], "is_active", 1)
        if not frappe.db.exists("HD Meeting Type", MEETING_TYPE):
            frappe.get_doc(
                {
                    "doctype": "HD Meeting Type",
                    "meeting_type": MEETING_TYPE,
                    "default_duration": 45,
                }
            ).insert(ignore_permissions=True)
        self.day = add_days(nowdate(), 2)

    def at(self, hhmm: str) -> str:
        return f"{self.day} {hhmm}:00"

    def schedule(self, start="10:00", end="10:30", people=(COLLEAGUE,), **values):
        frappe.set_user(ORGANISER[0])
        try:
            return meetings.schedule_team_meeting(
                **{
                    "subject": "Sales review",
                    "starts_on": self.at(start),
                    "ends_on": self.at(end),
                    "attendees": json.dumps([p[0] for p in people]),
                    "meeting_type": MEETING_TYPE,
                    **values,
                }
            )
        finally:
            frappe.set_user("Administrator")

    def people(self, start="10:00", end="10:30") -> dict:
        frappe.set_user(ORGANISER[0])
        try:
            rows = meetings.get_meeting_people(self.at(start), self.at(end))
        finally:
            frappe.set_user("Administrator")
        return {row["user"]: row for row in rows}


class TestScheduling(TeamMeetingCase):
    def test_an_internal_meeting_needs_no_ticket_and_no_teams(self):
        name = self.schedule()["name"]

        meeting = frappe.get_doc("HD Meeting", name)
        self.assertFalse(meeting.reference_doctype)
        self.assertFalse(meeting.reference_name)
        self.assertFalse(meeting.join_url)
        self.assertFalse(meeting.provider)
        self.assertEqual(meeting.meeting_type, MEETING_TYPE)
        self.assertEqual(meeting.scheduled_by, ORGANISER[0])
        self.assertEqual(meeting.organizer, ORGANISER[0])
        self.assertEqual([a.email for a in meeting.attendees], [COLLEAGUE[0]])

    def test_the_people_invited_are_notified_but_not_the_organiser(self):
        name = self.schedule()["name"]

        self.assertEqual(len(get_reminder_messages(COLLEAGUE[0], name)), 1)
        self.assertIn("Sales review", get_reminder_messages(COLLEAGUE[0], name)[0])
        self.assertEqual(get_reminder_messages(ORGANISER[0], name), [])

    def test_only_active_employees_can_be_invited(self):
        frappe.db.set_value("HD Agent", OTHER[0], "is_active", 0)

        self.assertNotIn(OTHER[0], self.people())
        with self.assertRaises(frappe.ValidationError):
            self.schedule(people=(OTHER,))

    def test_someone_already_in_a_meeting_cannot_be_added(self):
        self.schedule(start="10:00", end="11:00", people=(COLLEAGUE,))

        busy = self.people(start="10:30", end="11:30")[COLLEAGUE[0]]["busy"]
        self.assertEqual(busy["subject"], "Sales review")
        self.assertIsNone(self.people(start="10:30", end="11:30")[OTHER[0]]["busy"])
        with self.assertRaises(frappe.ValidationError):
            self.schedule(start="10:30", end="11:30", people=(OTHER, COLLEAGUE))

    def test_people_need_ten_minutes_after_a_meeting(self):
        self.schedule(start="10:00", end="11:00", people=(COLLEAGUE,))

        for start, end in (("11:00", "11:30"), ("11:09", "11:30")):
            self.assertTrue(self.people(start=start, end=end)[COLLEAGUE[0]]["busy"])
            with self.assertRaises(frappe.ValidationError):
                self.schedule(start=start, end=end, people=(COLLEAGUE,))

        self.assertIsNone(self.people(start="11:10", end="11:30")[COLLEAGUE[0]]["busy"])
        self.schedule(start="11:10", end="11:30", people=(COLLEAGUE,))

    def test_people_need_ten_minutes_before_a_meeting(self):
        self.schedule(start="10:00", end="11:00", people=(COLLEAGUE,))

        self.assertTrue(self.people(start="09:30", end="09:55")[COLLEAGUE[0]]["busy"])
        self.assertIsNone(self.people(start="09:20", end="09:50")[COLLEAGUE[0]]["busy"])
        self.schedule(start="09:20", end="09:50", people=(COLLEAGUE,))

    def test_a_meeting_from_a_ticket_also_makes_people_busy(self):
        ticket = make_ticket(subject="Report totals", raised_by=COLLEAGUE[0])
        make_meeting("HD Ticket", ticket.name, self.at("15:00"), [OTHER[0]])

        self.assertTrue(self.people(start="15:00", end="15:30")[OTHER[0]]["busy"])

    def test_a_cancelled_meeting_frees_its_people(self):
        name = self.schedule(start="10:00", end="11:00")["name"]
        frappe.set_user(ORGANISER[0])
        meetings.cancel_meeting(name, "Moved to Friday")
        frappe.set_user("Administrator")

        self.assertEqual(frappe.db.get_value("HD Meeting", name, "status"), "Cancelled")
        self.assertIsNone(self.people()[COLLEAGUE[0]]["busy"])
        cancelled = [
            m
            for m in get_reminder_messages(COLLEAGUE[0], name)
            if "cancelled" in m
        ]
        self.assertEqual(len(cancelled), 1)
        self.assertIn("Moved to Friday", cancelled[0])

    def test_bad_times_and_types_are_rejected(self):
        for start, end in (("11:00", "10:00"), ("10:00", "10:02")):
            with self.assertRaises(frappe.ValidationError):
                self.schedule(start=start, end=end)
        frappe.db.set_value("HD Meeting Type", MEETING_TYPE, "disabled", 1)
        with self.assertRaises(frappe.ValidationError):
            self.schedule()
        with self.assertRaises(frappe.ValidationError):
            self.schedule(meeting_type="No such type")


class TestMeetingEmails(TeamMeetingCase):
    def test_the_people_invited_get_an_invitation_email(self):
        name = self.schedule(people=(COLLEAGUE, OTHER), agenda="Q3 numbers")["name"]

        self.sendmail.assert_called_once()
        mail = self.sendmail.call_args.kwargs
        self.assertEqual(mail["recipients"], [COLLEAGUE[0], OTHER[0]])
        self.assertIn("Sales review", mail["subject"])
        self.assertIn("Q3 numbers", mail["message"])
        self.assertIn(COLLEAGUE[1], mail["message"])
        self.assertEqual(mail["reference_name"], name)

    def test_the_organiser_alone_gets_no_email(self):
        self.schedule(people=(ORGANISER,))

        self.sendmail.assert_not_called()

    def test_cancelling_emails_the_people_invited_with_the_reason(self):
        name = self.schedule()["name"]
        self.sendmail.reset_mock()
        frappe.set_user(ORGANISER[0])
        meetings.cancel_meeting(name, "Moved to Friday")
        frappe.set_user("Administrator")

        self.sendmail.assert_called_once()
        mail = self.sendmail.call_args.kwargs
        self.assertEqual(mail["recipients"], [COLLEAGUE[0]])
        self.assertIn("cancelled", mail["subject"])
        self.assertIn("Moved to Friday", mail["message"])

    def test_a_meeting_cannot_be_cancelled_without_a_reason(self):
        name = self.schedule()["name"]
        frappe.set_user(ORGANISER[0])
        try:
            for reason in (None, "   "):
                with self.assertRaises(frappe.ValidationError):
                    meetings.cancel_meeting(name, reason)
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(frappe.db.get_value("HD Meeting", name, "status"), "Scheduled")

    def test_the_notification_does_not_send_a_second_email(self):
        name = self.schedule()["name"]

        self.assertEqual(len(get_reminder_messages(COLLEAGUE[0], name)), 1)
        self.sendmail.assert_called_once()

    def test_a_teams_meeting_is_left_to_outlook(self):
        ticket = make_ticket(subject="Report totals", raised_by=COLLEAGUE[0])
        meeting = make_meeting("HD Ticket", ticket.name, self.at("15:00"), [OTHER[0]])

        meeting.email_attendees("Invitation", "Hello")

        self.sendmail.assert_not_called()


class TestMeetingCalendar(TeamMeetingCase):
    def test_the_meetings_calendar_shows_meetings_with_their_people(self):
        name = self.schedule()["name"]
        frappe.set_user(COLLEAGUE[0])
        data = calendar.get_calendar(self.day, self.day, meetings_only=1)
        frappe.set_user("Administrator")

        self.assertEqual(data["tasks"], [])
        [meeting] = [m for m in data["meetings"] if m["name"] == name]
        self.assertEqual(meeting["meeting_type"], MEETING_TYPE)
        self.assertEqual(meeting["attendees"], [COLLEAGUE[1]])
        # only the organiser (or a manager) can cancel it
        self.assertFalse(meeting["can_cancel"])


class TestMeetingType(FrappeTestCase):
    def test_length_must_be_a_real_meeting_length(self):
        doc = frappe.get_doc(
            {
                "doctype": "HD Meeting Type",
                "meeting_type": "Too long",
                "default_duration": 9 * 60,
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
