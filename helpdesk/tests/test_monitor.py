# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Monitor intake (Phase 18): alerts become one ticket each, follow-ups one task each, and a
quiet watcher is reported."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from helpdesk import intake, monitor
from helpdesk.api import monitor as api
from helpdesk.automation import create_automation_user
from helpdesk.consts import ALERT_TICKET_TYPE, MONITOR_RESOLVED_STATUS
from helpdesk.test_utils import (
    create_agent,
    create_customer,
    hold_commits,
    make_project,
)

KEY = "site-down:hydrotechsa.tbo365.cloud"


def clear_cache_keys():
    for key in (
        monitor.HEARTBEAT_KEY,
        monitor.LAST_SEEN_KEY,
        monitor.QUIET_TOLD_KEY,
    ):
        frappe.cache.delete_value(key.format(source="watcher"))
    frappe.cache.delete(
        frappe.cache.make_key(monitor.QUIET_ONCE_KEY.format(source="watcher"))
    )


class MonitorCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        intake.ensure_intake_defaults()
        # TBO AI is an agent on the real hub too (automation.create_automation_user)
        self.ai = create_automation_user("monitor.ai@example.com", "Monitor AI")
        self.customer = create_customer("Team Back Office International LLP").name
        self.project = make_project("Team Back Office Internal").name
        frappe.db.set_single_value(
            "HDS Hub Settings",
            {
                "automation_user": self.ai,
                "internal_customer": self.customer,
                "internal_project": self.project,
                "monitor_quiet_minutes": 3,
            },
        )
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        self.announced, self.told = [], []
        for target, side_effect in (
            (
                "helpdesk.intake.announce",
                lambda ticket, text: self.announced.append(text),
            ),
            (
                "helpdesk.copilot.pilot._tell_managers",
                lambda subject, *a, **k: self.told.append(subject),
            ),
        ):
            patcher = patch(target, side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        clear_cache_keys()
        self.addCleanup(clear_cache_keys)
        self.addCleanup(frappe.set_user, "Administrator")

    def comments(self, ticket) -> int:
        return frappe.db.count("HD Ticket Comment", {"reference_ticket": ticket})


class TestAlerts(MonitorCase):
    def test_an_alert_opens_one_ticket_for_the_internal_customer(self):
        first = monitor.alert(
            KEY,
            "open",
            title="Site down: hydrotechsa.tbo365.cloud",
            text="No answer for 3 minutes; the server answers.",
            severity="critical",
            evidence={"checks": [502, 502, 502]},
            runbook="restart_bench",
        )
        self.assertEqual(first["action"], "opened")
        ticket = frappe.get_doc("HD Ticket", first["ticket"])
        self.assertEqual(ticket.customer, self.customer)
        self.assertEqual(ticket.ticket_type, ALERT_TICKET_TYPE)
        self.assertEqual(ticket.alert_key, KEY)
        self.assertEqual(ticket.raised_by, self.ai)
        self.assertEqual(ticket.priority, "Urgent")
        self.assertIn("restart_bench", ticket.description)
        self.assertIn("502", ticket.description)
        again = monitor.alert(KEY.upper(), "firing", text="still down")
        self.assertEqual((again["action"], again["ticket"]), ("updated", ticket.name))
        self.assertEqual(self.comments(ticket.name), 1)
        self.assertEqual(frappe.db.count("HD Ticket", {"alert_key": KEY}), 1)

    def test_resolved_closes_the_ticket_and_a_second_resolve_does_nothing(self):
        ticket = monitor.alert(KEY, "open", title="Site down")["ticket"]
        done = monitor.alert(KEY, "resolved", text="healthy for 15 minutes")
        self.assertEqual((done["action"], done["ticket"]), ("resolved", ticket))
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket, "status"), MONITOR_RESOLVED_STATUS
        )
        self.assertTrue(any("resolved" in text.lower() for text in self.announced))
        self.assertEqual(monitor.alert(KEY, "ok")["action"], "noop")
        reopened = monitor.alert(KEY, "open", title="Site down again")
        self.assertEqual(reopened["action"], "opened")
        self.assertNotEqual(reopened["ticket"], ticket)

    def test_an_unknown_state_or_an_empty_key_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            monitor.alert(KEY, "maybe")
        with self.assertRaises(frappe.ValidationError):
            monitor.alert("   ", "open")

    def test_without_an_internal_customer_nothing_opens(self):
        frappe.db.set_single_value("HDS Hub Settings", "internal_customer", None)
        frappe.clear_document_cache("HDS Hub Settings", "HDS Hub Settings")
        with self.assertRaises(frappe.ValidationError):
            monitor.alert(KEY, "open", title="Site down")


class TestFollowups(MonitorCase):
    def test_a_follow_up_is_one_task_per_key_while_open(self):
        first = monitor.followup(
            "cert:tbocloud.in",
            "Certificate for tbocloud.in expires in 13 days",
            "renew it",
        )
        self.assertEqual(first["action"], "created")
        task = frappe.get_doc("Task", first["task"])
        self.assertEqual(
            (task.project, task.status, task.custom_monitor_key),
            (self.project, "Open", "cert:tbocloud.in"),
        )
        again = monitor.followup(
            "CERT:tbocloud.in", "Certificate for tbocloud.in expires in 12 days"
        )
        self.assertEqual((again["action"], again["task"]), ("exists", task.name))
        task.db_set("status", "Completed")
        third = monitor.followup(
            "cert:tbocloud.in",
            "Certificate for tbocloud.in expires in 6 days",
            priority="High",
        )
        self.assertEqual(third["action"], "created")
        self.assertEqual(frappe.db.get_value("Task", third["task"], "priority"), "High")


class TestHeartbeats(MonitorCase):
    def test_a_quiet_watcher_is_reported_once_an_hour_and_once_when_back(self):
        monitor.heartbeat("watcher")
        now = now_datetime()
        monitor.watch_heartbeats(now)
        self.assertEqual(self.told, [])
        # the heartbeat key has lapsed; the last-seen record is 10 minutes old
        frappe.cache.delete_value(monitor.HEARTBEAT_KEY.format(source="watcher"))
        frappe.cache.set_value(
            monitor.LAST_SEEN_KEY.format(source="watcher"),
            str(now - timedelta(minutes=10)),
        )
        monitor.watch_heartbeats(now)
        self.assertEqual(len(self.told), 1)
        self.assertIn("quiet", self.told[0])
        monitor.watch_heartbeats(now + timedelta(minutes=5))
        self.assertEqual(len(self.told), 1)  # once an hour, not every five minutes
        monitor.heartbeat("watcher")
        monitor.watch_heartbeats(now + timedelta(minutes=12))
        self.assertEqual(len(self.told), 2)
        self.assertIn("back", self.told[1])

    def test_a_watcher_never_heard_from_is_not_missed(self):
        monitor.watch_heartbeats(now_datetime())
        self.assertEqual(self.told, [])

    def test_within_the_quiet_time_nothing_is_said(self):
        now = now_datetime()
        frappe.cache.set_value(
            monitor.LAST_SEEN_KEY.format(source="watcher"),
            str(now - timedelta(minutes=1)),
        )
        monitor.watch_heartbeats(now)
        self.assertEqual(self.told, [])

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            monitor.heartbeat("toaster")


class TestApi(MonitorCase):
    def test_only_the_monitor_role_may_call_and_the_self_check_answers(self):
        agent = create_agent("monitor.agent@example.com").name
        frappe.set_user(agent)
        with self.assertRaises(frappe.PermissionError):
            api.alert(KEY, "open", title="Site down")
        with self.assertRaises(frappe.PermissionError):
            api.heartbeat()
        check = api.self_check()  # an agent may look
        for key in (
            "scheduler_enabled",
            "queues",
            "failed_jobs",
            "email_queue_stuck",
            "error_log_10m",
        ):
            self.assertIn(key, check)
        watcher = monitor.ensure_user()
        frappe.set_user(watcher)
        self.assertEqual(api.heartbeat()["ok"], True)
        opened = api.alert(KEY, "open", title="Site down", evidence='{"checks": [502]}')
        self.assertEqual(opened["action"], "opened")
        self.assertIn(
            "502", frappe.db.get_value("HD Ticket", opened["ticket"], "description")
        )
        self.assertEqual(
            api.followup("disk:workload", "Disk above 75% on the workload")["action"],
            "created",
        )
