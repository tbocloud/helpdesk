import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.ticket import MAX_SLA_TICKETS, get_sla_time_left
from helpdesk.test_utils import (
    create_agent,
    create_user,
    make_sla_calendar,
    make_team,
    make_ticket,
    run_as_user,
)

HOUR = 3600

# October 2026: Mon 5 ... Fri 9, Sat 10 (the 2nd Saturday), Sun 11, Mon 12; Sat 17 is the 3rd
TBO_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
HOLIDAY = "2026-10-08"
SECOND_SATURDAY = "2026-10-10"


class TestSlaTimeLeft(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.sla = make_sla_calendar(
            "Time Left SLA", TBO_WEEK, holidays=[HOLIDAY, SECOND_SATURDAY]
        )
        self.ticket = str(make_ticket(subject="Printer offline").name)

    def set_clock(self, **values):
        frappe.db.set_value(
            "HD Ticket",
            self.ticket,
            {
                "sla": self.sla.name,
                "status_category": "Open",
                "first_responded_on": None,
                "resolution_date": None,
                **values,
            },
        )

    def left_at(self, now) -> dict:
        with self.freeze_time(now):
            return get_sla_time_left([self.ticket])[self.ticket]

    def resolution_left(self, now, deadline) -> int | None:
        self.set_clock(response_by=None, resolution_by=deadline)
        return self.left_at(now)["resolution"]

    def test_inside_working_hours(self):
        self.assertEqual(
            self.resolution_left("2026-10-07 11:00", "2026-10-07 15:30"), 4.5 * HOUR
        )

    def test_before_opening_counts_from_opening(self):
        # 08:17 with a 10:30 deadline is 30 working minutes, not 2h 13m
        self.assertEqual(
            self.resolution_left("2026-10-07 08:17", "2026-10-07 10:30"), 30 * 60
        )

    def test_overnight_skips_closed_hours(self):
        # 17:00 → 18:00, then 10:00 → 11:00 the next day
        self.assertEqual(
            self.resolution_left("2026-10-06 17:00", "2026-10-07 11:00"), 2 * HOUR
        )

    def test_weekend_skips_the_second_saturday_and_sunday(self):
        # Friday 1h, Saturday off, Sunday not a workday, Monday 2h
        self.assertEqual(
            self.resolution_left("2026-10-09 17:00", "2026-10-12 12:00"), 3 * HOUR
        )

    def test_a_working_saturday_counts(self):
        # Friday 1h, the 3rd Saturday 8h, Monday 2h
        self.assertEqual(
            self.resolution_left("2026-10-16 17:00", "2026-10-19 12:00"), 11 * HOUR
        )

    def test_holiday_is_skipped(self):
        # Wednesday 1h, Thursday is a holiday, Friday 1h
        self.assertEqual(
            self.resolution_left("2026-10-07 17:00", "2026-10-09 11:00"), 2 * HOUR
        )

    def test_passed_deadline_is_zero(self):
        self.assertEqual(
            self.resolution_left("2026-10-07 12:00", "2026-10-07 11:00"), 0
        )

    def test_paused_ticket_has_no_running_clock(self):
        self.set_clock(
            status_category="Paused",
            response_by="2026-10-07 12:00",
            resolution_by="2026-10-07 16:00",
        )
        self.assertEqual(
            self.left_at("2026-10-07 11:00"), {"response": None, "resolution": None}
        )

    def test_met_deadlines_have_no_running_clock(self):
        self.set_clock(
            response_by="2026-10-07 12:00",
            first_responded_on="2026-10-07 10:30",
            resolution_by="2026-10-07 16:00",
        )
        self.assertEqual(
            self.left_at("2026-10-07 11:00"), {"response": None, "resolution": 5 * HOUR}
        )

        self.set_clock(
            response_by=None,
            resolution_by="2026-10-07 16:00",
            resolution_date="2026-10-07 10:45",
        )
        self.assertIsNone(self.left_at("2026-10-07 11:00")["resolution"])

    def test_ticket_without_sla_has_no_clock(self):
        self.set_clock(sla=None, response_by="2026-10-07 12:00")
        self.assertEqual(
            self.left_at("2026-10-07 11:00"), {"response": None, "resolution": None}
        )

    def test_too_many_tickets_are_refused(self):
        with self.assertRaises(frappe.ValidationError):
            get_sla_time_left([str(n) for n in range(MAX_SLA_TICKETS + 1)])


class TestSlaTimeLeftPermissions(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.ticket = str(make_ticket(subject="Invoice totals are wrong").name)

    def test_non_agent_is_refused(self):
        outsider = create_user("sla-left-outsider@example.com").name
        with self.assertRaises(frappe.PermissionError):
            run_as_user(outsider, lambda: get_sla_time_left([self.ticket]))

    def test_tickets_the_agent_cannot_read_are_left_out(self):
        agent = create_agent("sla-left-other-team@example.com").name
        team = make_team(
            "SLA Left Restricted Team",
            members=[create_agent("sla-left-team@example.com").name],
        )
        frappe.db.set_value("HD Ticket", self.ticket, "agent_group", team.name)
        frappe.db.set_single_value(
            "HD Settings",
            {
                "restrict_tickets_by_agent_group": 1,
                "do_not_restrict_tickets_without_an_agent_group": 0,
            },
        )

        self.assertEqual(
            run_as_user(agent, lambda: get_sla_time_left([self.ticket])), {}
        )
