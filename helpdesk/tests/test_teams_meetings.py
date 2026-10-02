import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk import teams_meetings
from helpdesk.api import meetings
from helpdesk.helpdesk.doctype.hd_meeting.hd_meeting import send_reminders
from helpdesk.test_utils import (
    create_customer,
    enable_teams_meetings,
    get_reminder_messages,
    graph_response,
    make_assignment,
    make_tasky_user,
    make_ticket,
)

AGENT = ("agent.meet@teams-meetings.example", "Nisha Paul")
OTHER_AGENT = ("other.meet@teams-meetings.example", "Rahul Dev")
CUSTOMER = "Meeting Traders LLC"
CUSTOMER_EMAIL = "accounts@meeting-traders.example"
JOIN_URL = "https://teams.microsoft.com/l/meetup-join/test"
TOKEN = {"access_token": "graph-token", "expires_in": 3600}
EVENT = {"id": "AAMk-event-1", "onlineMeeting": {"joinUrl": JOIN_URL}}


class MeetingCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        self.addCleanup(
            frappe.clear_document_cache, "HD Meeting Settings", "HD Meeting Settings"
        )
        create_customer(CUSTOMER)
        make_tasky_user(*AGENT)
        make_tasky_user(*OTHER_AGENT)
        enable_teams_meetings()
        ticket = make_ticket(
            subject="GST report totals wrong",
            customer=CUSTOMER,
            raised_by=CUSTOMER_EMAIL,
        )
        self.ticket = str(ticket.name)
        make_assignment("HD Ticket", self.ticket, AGENT[0])
        make_assignment("HD Ticket", self.ticket, OTHER_AGENT[0])
        self.start = f"{add_days(nowdate(), 2)} 15:00:00"

    def graph(self, *responses):
        """Patches the token call and the Graph calls (answered in order)."""
        token = patch(
            "helpdesk.teams_meetings.requests.post",
            return_value=graph_response(TOKEN),
        )
        calls = patch(
            "helpdesk.teams_meetings.requests.request",
            side_effect=list(responses) or [graph_response(EVENT, 201)],
        )
        token.start()
        self.addCleanup(token.stop)
        mocked = calls.start()
        self.addCleanup(calls.stop)
        return mocked

    def schedule(self, user=AGENT, **overrides):
        frappe.set_user(user[0])
        try:
            return meetings.schedule_meeting(
                **{
                    "reference_doctype": "HD Ticket",
                    "reference_name": self.ticket,
                    "subject": "Walk through the GST report",
                    "starts_on": self.start,
                    "duration": 30,
                    "attendees": json.dumps(
                        [{"email": CUSTOMER_EMAIL}, {"email": AGENT[0]}]
                    ),
                    "agenda": "Check the July totals",
                    **overrides,
                }
            )
        finally:
            frappe.set_user("Administrator")


class TestScheduling(MeetingCase):
    def test_creates_a_teams_meeting_in_the_organizers_calendar(self):
        graph = self.graph()

        result = self.schedule()

        method, url = graph.call_args.args[:2]
        payload = graph.call_args.kwargs["json"]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith(f"/users/{AGENT[0].replace('@', '%40')}/events"))
        self.assertTrue(payload["isOnlineMeeting"])
        self.assertEqual(payload["onlineMeetingProvider"], "teamsForBusiness")
        self.assertEqual(
            {a["emailAddress"]["address"] for a in payload["attendees"]},
            {CUSTOMER_EMAIL, AGENT[0]},
        )
        self.assertEqual(payload["start"], teams_meetings.graph_time(self.start))
        self.assertIn(f"#{self.ticket}", payload["body"]["content"])

        meeting = frappe.get_doc("HD Meeting", result["name"])
        self.assertEqual(meeting.join_url, JOIN_URL)
        self.assertEqual(meeting.external_id, "AAMk-event-1")
        self.assertEqual(meeting.organizer, AGENT[0])
        self.assertEqual(meeting.customer, CUSTOMER)
        staff = {a.email: a.is_internal for a in meeting.attendees}
        self.assertEqual(staff, {CUSTOMER_EMAIL: 0, AGENT[0]: 1})
        note = frappe.get_all(
            "HD Ticket Comment",
            filters={
                "reference_ticket": self.ticket,
                "content": ("like", "%Teams meeting%"),
            },
            pluck="content",
        )
        self.assertTrue(any(JOIN_URL in n for n in note))

    def test_a_shared_mailbox_can_organise(self):
        enable_teams_meetings(
            organizer="A shared mailbox",
            shared_mailbox="support@teams-meetings.example",
        )
        graph = self.graph()

        self.schedule()

        self.assertIn(
            "/users/support%40teams-meetings.example/events", graph.call_args.args[1]
        )

    def test_graph_refusal_is_shown_to_the_agent(self):
        self.graph(
            graph_response(
                {
                    "error": {
                        "code": "ErrorAccessDenied",
                        "message": "Access is denied.",
                    }
                },
                403,
            )
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            self.schedule()
        self.assertIn("Access is denied", str(caught.exception))

    def test_bad_input_is_rejected(self):
        self.graph()
        with self.assertRaises(frappe.ValidationError):
            self.schedule(starts_on=str(add_to_date(now_datetime(), hours=-2)))
        with self.assertRaises(frappe.ValidationError):
            self.schedule(attendees=json.dumps([{"email": "not-an-email"}]))
        with self.assertRaises(frappe.ValidationError):
            self.schedule(duration=600)

    def test_nothing_happens_when_meetings_are_off(self):
        enable_teams_meetings(enabled=0)
        graph = self.graph()
        with self.assertRaises(frappe.ValidationError):
            self.schedule()
        self.assertFalse(graph.called)
        frappe.set_user(AGENT[0])
        self.assertFalse(meetings.get_meetings("HD Ticket", self.ticket)["enabled"])

    def test_defaults_invite_the_customer_and_the_team(self):
        frappe.set_user(AGENT[0])
        defaults = meetings.get_meeting_defaults("HD Ticket", self.ticket)

        self.assertEqual(
            defaults["subject"], f"Ticket #{self.ticket}: GST report totals wrong"
        )
        emails = [a["email"] for a in defaults["attendees"]]
        self.assertIn(CUSTOMER_EMAIL, emails)
        self.assertIn(AGENT[0], emails)
        self.assertIn(OTHER_AGENT[0], emails)
        self.assertEqual(defaults["duration"], 30)


class TestCancelAndRemind(MeetingCase):
    def test_organizer_cancels_and_outlook_is_told(self):
        self.graph(graph_response(EVENT, 201), graph_response({}, 202))
        name = self.schedule()["name"]

        frappe.set_user(OTHER_AGENT[0])
        with self.assertRaises(frappe.PermissionError):
            meetings.cancel_meeting(name)

        frappe.set_user(AGENT[0])
        meetings.cancel_meeting(name, reason="Customer is on leave")

        meeting = frappe.get_doc("HD Meeting", name)
        self.assertEqual(meeting.status, "Cancelled")
        self.assertEqual(meeting.cancel_reason, "Customer is on leave")
        listed = meetings.get_meetings("HD Ticket", self.ticket)
        self.assertEqual(listed["upcoming"], [])
        self.assertEqual([m.name for m in listed["earlier"]], [name])

    def test_staff_get_a_reminder_once(self):
        self.graph()
        self.start = str(add_to_date(now_datetime(), minutes=5))
        name = self.schedule()["name"]

        send_reminders()
        send_reminders()

        messages = [
            m
            for m in get_reminder_messages(AGENT[0], self.ticket)
            if m.startswith("Teams meeting at")
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn(JOIN_URL, messages[0])
        self.assertTrue(frappe.db.get_value("HD Meeting", name, "reminder_sent"))


class TestGraphTime(FrappeTestCase):
    def test_converts_system_time_to_utc(self):
        with patch.object(
            teams_meetings, "get_system_timezone", return_value="Asia/Kolkata"
        ):
            self.assertEqual(
                teams_meetings.graph_time("2026-10-05 15:00:00"),
                {"dateTime": "2026-10-05T09:30:00", "timeZone": "UTC"},
            )
