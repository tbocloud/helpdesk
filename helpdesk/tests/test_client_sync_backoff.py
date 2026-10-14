"""A customer site that keeps failing is backed off and announced once (docs/client-site-sync.md)."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from helpdesk import tasks, ticket_puller
from helpdesk.test_utils import (
    create_customer,
    get_outage_logs,
    hold_commits,
    make_support_connection,
    make_ticket,
    run_client_pull,
)

START = get_datetime("2026-10-14 10:00:00")
NOTIFY = "helpdesk.work_reminders.notify_users"


class TestClientSyncBackoff(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer("Backoff Traders LLC")
        self.conn = make_support_connection(
            "Backoff Traders LLC", site_url="https://backoff.example.com"
        ).name
        notify = patch(NOTIFY)
        self.notify = notify.start()
        self.addCleanup(notify.stop)

    def state(self):
        return frappe.db.get_value(
            "HDS Support Connection",
            self.conn,
            [
                "connection_status",
                "consecutive_failures",
                "next_attempt_at",
                "unreachable_since",
                "last_error",
            ],
            as_dict=True,
        )

    def is_due(self) -> bool:
        return self.conn in ticket_puller.due_connections(
            ticket_puller.PULLABLE_STATUSES
        )

    def fail_at(self, at):
        with self.freeze_time(at):
            run_client_pull(self.conn, error="503 Service Unavailable")

    def test_the_first_failures_retry_every_minute(self):
        self.fail_at(START)
        self.fail_at(START)

        state = self.state()
        self.assertEqual(
            (state.connection_status, state.consecutive_failures), ("Error", 2)
        )
        self.assertIsNone(state.next_attempt_at)
        self.assertIn("503", state.last_error)
        self.assertEqual(get_outage_logs(self.conn), [])
        self.notify.assert_not_called()

    def test_from_the_third_failure_it_backs_off_1_5_15_then_60_minutes(self):
        at = START
        waits = []
        for _attempt in range(7):
            self.fail_at(at)
            state = self.state()
            if state.next_attempt_at:
                waits.append(get_datetime(state.next_attempt_at) - at)
                at = get_datetime(state.next_attempt_at)

        self.assertEqual(waits, [timedelta(minutes=m) for m in (1, 5, 15, 60, 60)])
        self.assertEqual(self.state().connection_status, "Unreachable")

    def test_an_unreachable_site_waits_for_its_next_attempt(self):
        for _attempt in range(3):
            self.fail_at(START)

        with self.freeze_time(START + timedelta(seconds=30)):
            self.assertFalse(self.is_due())
        with self.freeze_time(START + timedelta(minutes=1)):
            self.assertTrue(self.is_due())

    def test_an_outage_is_logged_and_announced_once_and_so_is_the_recovery(self):
        at = START
        for _attempt in range(6):
            self.fail_at(at)
            at += timedelta(hours=1)

        self.assertEqual(len(get_outage_logs(self.conn)), 1)
        self.assertEqual(self.notify.call_count, 1)
        self.assertIn("unreachable", self.notify.call_args.args[3])
        self.assertTrue(self.notify.call_args.kwargs["escalate"])

        with self.freeze_time(at):
            run_client_pull(self.conn)
            run_client_pull(self.conn)

        state = self.state()
        self.assertEqual(
            (state.connection_status, state.consecutive_failures), ("Connected", 0)
        )
        self.assertIsNone(state.next_attempt_at)
        self.assertIsNone(state.unreachable_since)
        self.assertEqual(self.notify.call_count, 2)
        self.assertIn("reachable again", self.notify.call_args.args[3])
        self.assertEqual(len(get_outage_logs(self.conn)), 1)

    def test_a_success_resets_the_count_before_an_outage(self):
        self.fail_at(START)
        self.fail_at(START)
        with self.freeze_time(START):
            run_client_pull(self.conn)
        self.fail_at(START)

        self.assertEqual(self.state().consecutive_failures, 1)
        self.notify.assert_not_called()

    def test_the_daily_health_check_feeds_the_same_backoff(self):
        for _attempt in range(3):
            self.fail_at(START)

        with self.freeze_time(START + timedelta(seconds=30)), patch.object(
            tasks, "MCPClient"
        ) as client:
            tasks.health_check_connections()
        # still waiting: not called before its next attempt
        self.assertNotIn(self.conn, [c.args[0] for c in client.call_args_list])

        with self.freeze_time(START + timedelta(minutes=1)), patch.object(
            tasks, "MCPClient"
        ) as client:
            client.return_value.health_check.return_value = True
            tasks.health_check_connections()

        self.assertEqual(self.state().connection_status, "Connected")
        self.assertIn("reachable again", self.notify.call_args.args[3])

    def test_the_five_minute_jobs_skip_an_unreachable_site(self):
        make_ticket(subject="Invoice totals wrong").db_set(
            {
                "custom_client_ticket": "SUP-BACKOFF-1",
                "custom_qcs_connection": self.conn,
            }
        )
        for _attempt in range(3):
            self.fail_at(START)

        self.assertIn(self.conn, ticket_puller.unreachable_connections())
        with patch.object(ticket_puller, "MCPClient") as client:
            ticket_puller.sync_conversations()
            ticket_puller.push_ticket_statuses()
        self.assertNotIn(self.conn, [c.args[0] for c in client.call_args_list])

    def test_a_five_minute_job_that_cant_connect_counts_a_failure_not_an_error_log(
        self,
    ):
        make_ticket(subject="Stock report empty").db_set(
            {
                "custom_client_ticket": "SUP-BACKOFF-2",
                "custom_qcs_connection": self.conn,
            }
        )
        with patch.object(
            ticket_puller, "MCPClient", side_effect=RuntimeError("502 Bad Gateway")
        ):
            ticket_puller.push_ticket_statuses()

        self.assertEqual(self.state().consecutive_failures, 1)
        self.assertFalse(
            frappe.db.exists(
                "Error Log", {"method": f"Status push failed for {self.conn}"}
            )
        )
