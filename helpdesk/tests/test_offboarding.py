# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import offboarding
from helpdesk.teams_meetings import GRAPH
from helpdesk.test_utils import (
    bearer_token_works,
    call_as_user,
    enable_offboarding,
    graph_response,
    hold_commits,
    issue_sso_token,
    make_oauth_client,
    make_tasky_user,
    microsoft_account,
    mock_microsoft_directory,
)

STAYS = ("stays@offboarding.example", "Anjali Pillai")
LEFT = ("left@offboarding.example", "Rahul Menon")
DISABLED = ("disabled@offboarding.example", "Divya Nair")
ADMIN = ("it.admin@offboarding.example", "Arun Kumar")
OUTSIDER = ("partner@elsewhere.example", "Meera Das")
MANAGER = ("manager@elsewhere.example", "Joseph Thomas")
PREVIEW = "helpdesk.api.offboarding.preview_offboarding"
RUN_NOW = "helpdesk.api.offboarding.run_offboarding"


class TestOffboarding(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Meeting Settings", "HD Meeting Settings"
        )
        for person in (STAYS, LEFT, DISABLED, OUTSIDER):
            make_tasky_user(*person)
        make_tasky_user(*ADMIN, roles=("System Manager",))
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        enable_offboarding()

    def directory(self, *pages, status: int = 200):
        return mock_microsoft_directory(self, *pages, status=status)

    def tenant(self) -> list:
        """STAYS enabled, DISABLED switched off, LEFT and ADMIN gone."""
        return [
            microsoft_account(STAYS[0]),
            microsoft_account(DISABLED[0], enabled=False),
        ]

    def enabled(self, person) -> bool:
        return bool(frappe.db.get_value("User", person[0], "enabled"))

    def notifications(self, user: str) -> int:
        return frappe.db.count("HD Notification", {"user_to": user})

    def assertNobodyChanged(self):
        for person in (STAYS, LEFT, DISABLED, ADMIN, OUTSIDER):
            self.assertTrue(self.enabled(person), person)
        self.assertEqual(frappe.db.count(offboarding.LOG), 0)

    # --- who goes ---

    def test_disables_only_people_who_left_microsoft(self):
        self.directory(self.tenant())

        offboarding.run()

        self.assertFalse(self.enabled(LEFT))
        self.assertFalse(self.enabled(DISABLED))
        # the System Manager is gone from Microsoft too, but never touched
        for person in (STAYS, ADMIN, OUTSIDER, MANAGER):
            self.assertTrue(self.enabled(person), person)
        self.assertTrue(frappe.db.get_value("User", "Administrator", "enabled"))
        reasons = dict(
            frappe.get_all(offboarding.LOG, fields=["user", "reason"], as_list=True)
        )
        self.assertEqual(
            reasons,
            {LEFT[0]: offboarding.MISSING, DISABLED[0]: offboarding.DISABLED},
        )

    def test_an_alias_on_an_enabled_account_keeps_the_user(self):
        alias = microsoft_account(
            "rahul.menon@offboarding.example",
            proxyAddresses=["SMTP:rahul.menon@offboarding.example", f"smtp:{LEFT[0]}"],
        )
        self.directory([*self.tenant(), alias])

        offboarding.run()

        self.assertTrue(self.enabled(LEFT))
        self.assertFalse(self.enabled(DISABLED))

    def test_reads_every_page_of_the_directory(self):
        graph = self.directory(
            [microsoft_account(STAYS[0])],
            [microsoft_account(LEFT[0]), microsoft_account(DISABLED[0])],
        )

        offboarding.run()

        self.assertEqual(graph.call_count, 2)
        self.assertIn("$skiptoken=page1", graph.call_args_list[1].args[1])
        for person in (STAYS, LEFT, DISABLED):
            self.assertTrue(self.enabled(person), person)

    def test_offboarded_users_tokens_stop_working(self):
        client = make_oauth_client()
        access_token = issue_sso_token(LEFT[0], client)["access_token"]
        self.assertTrue(bearer_token_works(access_token))
        self.directory(self.tenant())

        offboarding.run()

        self.assertEqual(
            frappe.db.get_value("OAuth Bearer Token", access_token, "status"),
            "Revoked",
        )
        self.assertFalse(bearer_token_works(access_token))

    def test_log_is_written_and_managers_are_told_once(self):
        self.directory(self.tenant())

        offboarding.run()
        offboarding.run()

        self.assertEqual(frappe.db.count(offboarding.LOG), 2)
        self.assertEqual(self.notifications(MANAGER[0]), 1)
        message = frappe.db.get_value(
            "HD Notification", {"user_to": MANAGER[0]}, "message"
        )
        self.assertIn(LEFT[1], message)
        self.assertIn(DISABLED[1], message)

    # --- safety ---

    def test_switched_off_does_nothing(self):
        enable_offboarding(offboard_removed_microsoft_users=0)
        graph = self.directory(self.tenant())

        offboarding.run()

        graph.assert_not_called()
        self.assertNobodyChanged()

    def test_graph_error_changes_nothing(self):
        self.directory(status=403)

        offboarding.run()

        self.assertNobodyChanged()
        self.assertTrue(
            frappe.db.exists("Error Log", {"method": offboarding.ERROR_TITLE})
        )

    def test_failure_on_a_later_page_changes_nothing(self):
        graph = self.directory()
        graph.side_effect = [
            graph_response(
                {"value": self.tenant(), "@odata.nextLink": f"{GRAPH}/users?page=2"}
            ),
            graph_response({"error": {"code": "ServiceUnavailable"}}, 503),
        ]

        offboarding.run()

        self.assertNobodyChanged()

    def test_empty_directory_changes_nothing(self):
        self.directory([])

        offboarding.run()

        self.assertNobodyChanged()

    def test_directory_without_the_domains_changes_nothing(self):
        self.directory([microsoft_account("someone@elsewhere.example")])

        offboarding.run()

        self.assertNobodyChanged()

    def test_the_limit_stops_the_run_and_alerts_once(self):
        enable_offboarding(offboarding_max_disables=1)
        self.directory(self.tenant())

        offboarding.run()
        offboarding.run()

        self.assertNobodyChanged()
        self.assertEqual(self.notifications(ADMIN[0]), 1)
        self.assertEqual(self.notifications(MANAGER[0]), 0)

    def test_dry_run_changes_nothing(self):
        enable_offboarding(offboarding_dry_run=1)
        self.directory(self.tenant())

        offboarding.run()

        self.assertNobodyChanged()
        self.assertEqual(self.notifications(MANAGER[0]), 0)

    # --- Settings: Preview and Run now ---

    def test_preview_lists_who_would_go_and_changes_nothing(self):
        enable_offboarding(offboard_removed_microsoft_users=0)
        self.directory(self.tenant())

        answer = call_as_user("Administrator", PREVIEW)

        self.assertEqual(answer["status"], "dry_run")
        self.assertEqual(
            {p["user"]: p["reason"] for p in answer["people"]},
            {LEFT[0]: offboarding.MISSING, DISABLED[0]: offboarding.DISABLED},
        )
        self.assertNobodyChanged()

    def test_run_now_disables(self):
        self.directory(self.tenant())

        answer = call_as_user("Administrator", RUN_NOW)

        self.assertEqual(answer["status"], "done")
        self.assertFalse(self.enabled(LEFT))

    def test_run_now_reports_a_graph_error(self):
        self.directory(status=403)

        with self.assertRaises(frappe.ValidationError):
            call_as_user("Administrator", RUN_NOW)
        self.assertNobodyChanged()

    def test_only_system_managers_can_preview_or_run(self):
        for method in (PREVIEW, RUN_NOW):
            with self.assertRaises(frappe.PermissionError):
                call_as_user(MANAGER[0], method)

    def test_settings_need_domains_and_a_limit(self):
        settings = frappe.get_doc("HD Settings")
        settings.offboarding_domains = " OffBoarding.example, @Second.example "
        settings.save()
        self.assertEqual(
            settings.offboarding_domains, "offboarding.example\nsecond.example"
        )

        for field, value in (
            ("offboarding_domains", ""),
            ("offboarding_domains", "anjali@offboarding.example"),
            ("offboarding_max_disables", 0),
        ):
            settings.reload()
            settings.set(field, value)
            with self.assertRaises(frappe.ValidationError):
                settings.save()
