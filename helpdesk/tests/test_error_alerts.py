from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk import error_alerts
from helpdesk.api import chat_settings
from helpdesk.test_utils import (
    TEST_TEAMS_CHANNEL_URL,
    enable_chat_notifications,
    hold_commits,
    make_error_log,
    make_tasky_user,
)

CHANNEL = TEST_TEAMS_CHANNEL_URL


class TestErrorAlerts(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        self.addCleanup(
            frappe.clear_document_cache, "HD Chat Settings", "HD Chat Settings"
        )
        self.now = now_datetime()
        enable_chat_notifications(
            teams_channel_webhook=CHANNEL,
            post_error_alerts=1,
            ignored_error_titles="",
            errors_checked_until=add_to_date(self.now, minutes=-10),
        )
        # only this test's errors count
        frappe.db.delete("Error Log")

    def run_digest(self):
        with patch("helpdesk.error_alerts.post_to_channel") as post:
            error_alerts.post_error_digest()
        return post

    def test_new_errors_are_posted_once_grouped_by_title(self):
        for _i in range(3):
            make_error_log("Ticket pull failed")
        make_error_log("Triage failed")

        post = self.run_digest()

        post.assert_called_once()
        text, url = post.call_args.args
        self.assertIn("4 new error(s)", text)
        self.assertLess(
            text.index("3 × Ticket pull failed"), text.index("1 × Triage failed")
        )
        self.assertTrue(url.endswith("/app/error-log"))

        # the checkpoint moved on: the same errors aren't posted again
        self.assertFalse(self.run_digest().called)

    def test_errors_before_the_checkpoint_are_not_posted(self):
        make_error_log("Old failure", at=add_to_date(self.now, hours=-2))
        self.assertFalse(self.run_digest().called)

    def test_ignored_and_chat_errors_are_left_out(self):
        enable_chat_notifications(
            teams_channel_webhook=CHANNEL,
            post_error_alerts=1,
            ignored_error_titles="Noisy Import\n",
            errors_checked_until=add_to_date(self.now, minutes=-15),
        )
        make_error_log("noisy import of contacts")
        make_error_log("Chat escalation not posted")
        self.assertFalse(self.run_digest().called)

        make_error_log("Invoice sync failed")
        text = self.run_digest().call_args.args[0]
        self.assertIn("1 × Invoice sync failed", text)
        self.assertNotIn("Chat escalation", text)

    def test_long_lists_are_cut_short(self):
        for i in range(error_alerts.MAX_TITLES + 2):
            make_error_log(f"Failure {chr(ord('A') + i)}")
        text = self.run_digest().call_args.args[0]
        self.assertIn("…and 2 more kind(s).", text)

    def test_nothing_is_posted_when_alerts_or_chat_are_off(self):
        make_error_log("Ticket pull failed")
        frappe.db.set_single_value("HD Chat Settings", "post_error_alerts", 0)
        self.assertFalse(self.run_digest().called)

        frappe.db.set_single_value("HD Chat Settings", "post_error_alerts", 1)
        frappe.db.set_single_value("HD Chat Settings", "enabled", 0)
        self.assertFalse(self.run_digest().called)

    def test_titles_that_differ_only_by_a_number_are_one_line(self):
        for ticket in (101, 102, 103):
            make_error_log(f"Status push failed for {ticket}")
        make_error_log("Triage failed")

        text = self.run_digest().call_args.args[0]
        self.assertIn("3 × Status push failed for", text)
        self.assertIn("(and 2 similar)", text)
        self.assertIn("1 × Triage failed", text)
        self.assertNotIn("1 × Status push", text)


class TestMarkOldSyncErrorsSeen(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.db.delete("Error Log")
        two_days_ago = add_to_date(now_datetime(), days=-2)
        self.old_sync = make_error_log(
            "Ticket pull failed for TBO-CONN-2026-00002", at=two_days_ago
        ).name
        self.old_outage = make_error_log(
            "Customer site unreachable: Metta", at=two_days_ago
        ).name
        self.new_sync = make_error_log(
            "Ticket pull failed for TBO-CONN-2026-00001"
        ).name
        self.old_other = make_error_log("Triage failed", at=two_days_ago).name

    def seen(self, name) -> int:
        return frappe.db.get_value("Error Log", name, "seen")

    def test_a_system_manager_marks_only_old_sync_errors(self):
        result = chat_settings.mark_old_sync_errors_seen()

        self.assertEqual(result["ok"], True)
        self.assertIn("2", result["message"])
        self.assertEqual((self.seen(self.old_sync), self.seen(self.old_outage)), (1, 1))
        self.assertEqual((self.seen(self.new_sync), self.seen(self.old_other)), (0, 0))

    def test_others_cant(self):
        user = make_tasky_user(
            "manager.errors@error-alerts.example", "Divya Rao", roles=("Agent Manager",)
        )
        frappe.set_user(user)
        with self.assertRaises(frappe.PermissionError):
            chat_settings.mark_old_sync_errors_seen()
        frappe.set_user("Administrator")
        self.assertEqual(self.seen(self.old_sync), 0)
