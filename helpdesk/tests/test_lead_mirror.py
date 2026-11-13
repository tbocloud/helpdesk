import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import lead_mirror
from helpdesk.api import lead_mirror as mirror_api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import FakeLeadERP, create_agent, hold_commits

FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
STATE = "HD Lead Sync State"
MIRROR = "HD Lead Mirror"
ANN = "ann@erp.example"
BOB = "bob@erp.example"
PLAIN_AGENT = "mirror.plain@example.com"


class LeadMirrorCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD CRM Settings", "HD CRM Settings"
        )
        frappe.set_user("Administrator")
        frappe.db.set_single_value(
            "HD CRM Settings",
            {"enabled": 1, "site_url": "https://crm.example", "api_key": "test-key"},
        )
        frappe.clear_document_cache("HD CRM Settings", "HD CRM Settings")
        frappe.db.delete(MIRROR)
        frappe.db.set_single_value(
            STATE,
            {
                "enabled": 1,
                "since": "",
                "backfill_status": "Idle",
                "last_error": "",
                "scopes": "",
            },
        )
        self.erp = FakeLeadERP()
        patcher = patch(FROM_SETTINGS, return_value=self.erp)
        patcher.start()
        self.addCleanup(patcher.stop)
        # a failed run rolls back its open batch; the test's one transaction must survive that
        rollback = patch.object(frappe.db, "rollback")
        rollback.start()
        self.addCleanup(rollback.stop)
        # nothing here may reach a real queue
        enqueue = patch.object(lead_mirror.frappe, "enqueue")
        self.enqueue = enqueue.start()
        self.addCleanup(enqueue.stop)

    def fill(self, *names: str):
        for name in names:
            self.erp.put(name, lead_name=f"Lead {name}")

    def backfilled(self, *names: str):
        self.fill(*names)
        lead_mirror.backfill_lead_mirror()

    def copy(self, name: str):
        return frappe.get_doc(MIRROR, name)

    def names(self) -> list[str]:
        return sorted(frappe.get_all(MIRROR, pluck="name"))

    def state(self, field: str):
        return frappe.db.get_single_value(STATE, field)

    def bulk_names(self) -> list[list[str]]:
        return [params["names"] for params in self.erp.get_calls("get_leads_bulk")]


class TestLeadMirrorBackfill(LeadMirrorCase):
    def test_a_backfill_copies_every_lead_and_hands_over_to_the_feed(self):
        self.erp.put(
            "L-1",
            lead_name="Ravi",
            tbo_stage="Contacted",
            tbo_department="Growth",
            assignees=[BOB],
            score=7,
        )
        self.fill("L-2", "L-3")
        lead_mirror.backfill_lead_mirror()
        self.assertEqual(self.names(), ["L-1", "L-2", "L-3"])
        copy = self.copy("L-1")
        self.assertEqual(
            (copy.lead_name, copy.tbo_stage, copy.department, copy.score),
            ("Ravi", "Contacted", "Growth", 7),
        )
        self.assertEqual(copy.lead_owner, ANN)
        self.assertEqual([row.user for row in copy.assignees], [BOB])
        self.assertEqual(json.loads(copy.payload)["lead"]["name"], "L-1")
        self.assertEqual(copy.status, "Open")
        self.assertEqual(self.state("since"), str(self.erp.clock))
        self.assertEqual(self.state("backfill_status"), "Idle")
        self.assertEqual(self.state("leads_mirrored"), 3)
        self.assertEqual(self.state("erp_total"), 3)
        self.assertFalse(self.state("last_error"))
        self.assertTrue(self.state("last_synced_on"))
        self.assertEqual(json.loads(self.state("scopes")), self.erp.scopes)

    def test_a_backfill_pages_through_the_index_and_the_bulk_read(self):
        self.fill("L-1", "L-2", "L-3", "L-4", "L-5")
        with (
            patch.object(lead_mirror, "INDEX_PAGE", 2),
            patch.object(lead_mirror, "BULK", 2),
        ):
            lead_mirror.backfill_lead_mirror()
        self.assertEqual(len(self.erp.get_calls("get_lead_index")), 3)
        self.assertEqual(self.names(), ["L-1", "L-2", "L-3", "L-4", "L-5"])
        self.assertTrue(all(len(names) <= 2 for names in self.bulk_names()))

    def test_running_it_again_copies_only_what_differs(self):
        self.backfilled("L-1", "L-2")
        first = len(self.erp.get_calls("get_leads_bulk"))
        lead_mirror.backfill_lead_mirror()
        self.assertEqual(len(self.erp.get_calls("get_leads_bulk")), first)
        self.erp.put("L-2", lead_name="Renamed")
        lead_mirror.backfill_lead_mirror()
        self.assertEqual(self.bulk_names()[first:], [["L-2"]])
        self.assertEqual(self.copy("L-2").lead_name, "Renamed")

    def test_a_backfill_waits_for_nobody_forever(self):
        self.fill("L-1")
        with lead_mirror.single_flight() as held:
            self.assertTrue(held)
            with patch.object(lead_mirror, "BACKFILL_WAIT", 0):
                lead_mirror.backfill_lead_mirror()
        self.assertEqual(self.names(), [])

    def test_a_failed_backfill_is_shown_and_leaves_the_copy_starting_again(self):
        self.fill("L-1")
        self.erp.bulk_error = CRMError("The CRM site answered 500", 500)
        with patch("helpdesk.lead_mirror.frappe.log_error"):
            lead_mirror.backfill_lead_mirror()
        self.assertTrue(self.state("last_error"))
        self.assertEqual(self.state("backfill_status"), "Idle")
        self.assertFalse(self.state("since"))
        self.erp.bulk_error = None
        lead_mirror.backfill_lead_mirror()
        self.assertEqual(self.names(), ["L-1"])
        self.assertFalse(self.state("last_error"))


class TestLeadMirrorSync(LeadMirrorCase):
    def test_nothing_runs_while_the_copy_is_off(self):
        frappe.db.set_single_value(STATE, "enabled", 0)
        self.fill("L-1")
        lead_mirror.sync_lead_changes()
        lead_mirror.backfill_lead_mirror()
        lead_mirror.check_drift()
        self.assertEqual(self.erp.calls, [])
        self.assertEqual(self.names(), [])

    def test_the_first_sync_starts_the_backfill_instead(self):
        self.fill("L-1")
        lead_mirror.sync_lead_changes()
        self.enqueue.assert_called_once()
        self.assertEqual(self.enqueue.call_args.args[0], lead_mirror.BACKFILL_JOB)
        self.assertEqual(self.names(), [])

    def test_a_sync_whose_backfill_died_starts_it_again(self):
        self.backfilled("L-1")
        frappe.db.set_single_value(STATE, "backfill_status", "Copying")
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.state("backfill_status"), "Idle")
        self.enqueue.assert_called_once()

    def test_changes_are_copied_in_the_order_they_happened(self):
        self.backfilled("L-1", "L-2", "L-3")
        self.erp.put("L-3", lead_name="Third")
        self.erp.put("L-1", lead_name="First")
        self.erp.put("L-3", lead_name="Third again")
        lead_mirror.sync_lead_changes()
        # each lead once, by its latest change: L-1 before L-3 (L-2, a minute back, is read again)
        fetched = self.bulk_names()[-1]
        self.assertEqual(fetched, ["L-2", "L-1", "L-3"])
        self.assertEqual(self.copy("L-3").lead_name, "Third again")
        self.assertEqual(self.copy("L-1").lead_name, "First")
        self.assertEqual(self.copy("L-2").lead_name, "Lead L-2")
        self.assertEqual(self.state("since"), str(self.erp.clock))
        self.assertFalse(self.state("last_error"))

    def test_a_change_that_leaves_modified_alone_still_refreshes_the_copy(self):
        self.backfilled("L-1")
        self.erp.leads["L-1"]["tbo_stage"] = "Won"
        self.erp.note("L-1")
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.copy("L-1").tbo_stage, "Won")

    def test_syncing_twice_leaves_the_same_copies(self):
        self.backfilled("L-1", "L-2")
        self.erp.put("L-2", lead_name="Changed", assignees=[BOB])
        lead_mirror.sync_lead_changes()
        before = {n: self.copy(n).as_dict() for n in self.names()}
        since = self.state("since")
        lead_mirror.sync_lead_changes()
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.names(), ["L-1", "L-2"])
        self.assertEqual(self.state("since"), since)
        for name, doc in before.items():
            now = self.copy(name)
            self.assertEqual(
                (now.lead_name, now.erp_modified, [a.user for a in now.assignees]),
                (doc.lead_name, doc.erp_modified, [a.user for a in doc.assignees]),
            )
        self.assertEqual([a.user for a in self.copy("L-2").assignees], [BOB])

    def test_a_change_a_minute_back_is_read_again(self):
        self.backfilled("L-1")
        self.erp.put("L-1", lead_name="First")
        lead_mirror.sync_lead_changes()
        calls = len(self.erp.get_calls("get_lead_changes"))
        lead_mirror.sync_lead_changes()
        asked = self.erp.get_calls("get_lead_changes")[calls]["since"]
        self.assertLess(asked, self.state("since"))

    def test_deleted_and_merged_leads_lose_their_copy(self):
        self.backfilled("L-1", "L-2", "L-3")
        self.erp.drop("L-1")
        self.erp.drop("L-2")
        self.erp.put("L-3", lead_name="Kept")
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.names(), ["L-3"])
        self.assertEqual(self.state("leads_mirrored"), 1)

    def test_the_feed_is_read_a_page_at_a_time(self):
        self.backfilled("L-1", "L-2", "L-3")
        for name in ("L-1", "L-2", "L-3"):
            self.erp.put(name, lead_name=f"New {name}")
        with patch.object(lead_mirror, "CHANGES_PAGE", 2):
            lead_mirror.sync_lead_changes()
        self.assertEqual(self.bulk_names()[-2:], [["L-1", "L-2"], ["L-3"]])
        self.assertEqual(self.copy("L-3").lead_name, "New L-3")
        self.assertEqual(self.state("since"), str(self.erp.clock))

    def test_the_feed_does_not_move_on_when_a_batch_fails(self):
        self.backfilled("L-1", "L-2")
        since = self.state("since")
        self.erp.put("L-1", lead_name="Changed")
        self.erp.bulk_error = CRMError("The CRM site answered 502", 502)
        with patch("helpdesk.lead_mirror.frappe.log_error"):
            lead_mirror.sync_lead_changes()
        self.assertEqual(self.state("since"), since)
        self.assertTrue(self.state("last_error"))
        self.assertEqual(self.copy("L-1").lead_name, "Lead L-1")
        self.erp.bulk_error = None
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.copy("L-1").lead_name, "Changed")
        self.assertFalse(self.state("last_error"))

    def test_a_lead_the_erp_cannot_read_keeps_its_old_copy_and_is_named(self):
        self.backfilled("L-1", "L-2")
        self.erp.put("L-1", lead_name="Changed")
        self.erp.put("L-2", lead_name="Also changed")
        self.erp.unreadable["L-1"] = "no permission"
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.copy("L-1").lead_name, "Lead L-1")
        self.assertEqual(self.copy("L-2").lead_name, "Also changed")
        self.assertIn("L-1: no permission", self.state("last_error"))

    def test_the_scopes_follow_the_erp_every_run(self):
        self.backfilled("L-1")
        self.erp.scopes = {
            BOB: {"all": False, "team": [BOB, ANN], "departments": ["Growth"]}
        }
        lead_mirror.sync_lead_changes()
        self.assertEqual(json.loads(self.state("scopes")), self.erp.scopes)

    def test_only_one_run_at_a_time(self):
        self.backfilled("L-1")
        self.erp.put("L-1", lead_name="Changed")
        calls = len(self.erp.calls)
        with lead_mirror.single_flight() as held:
            self.assertTrue(held)
            with lead_mirror.single_flight() as second:
                self.assertFalse(second)
            lead_mirror.sync_lead_changes()
            lead_mirror.check_drift()
        self.assertEqual(len(self.erp.calls), calls)
        with lead_mirror.single_flight() as free:
            self.assertTrue(free)

    def test_the_lag_is_how_old_the_newest_change_was(self):
        self.backfilled("L-1")
        self.erp.put("L-1", lead_name="Changed")
        self.erp.clock = self.erp.clock.replace(second=self.erp.clock.second + 5)
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.state("lag_seconds"), 5)
        lead_mirror.sync_lead_changes()
        self.assertEqual(self.state("lag_seconds"), 0)

    def test_a_site_without_the_feed_is_told_plainly(self):
        self.backfilled("L-1")
        error = CRMError("answered 404", 404, "failed to get method hub_lead_mirror")
        self.erp.bulk_error = error
        self.erp.put("L-1", lead_name="Changed")
        with patch("helpdesk.lead_mirror.frappe.log_error"):
            lead_mirror.sync_lead_changes()
        self.assertIn("latest TBO Smart", self.state("last_error"))


class TestLeadMirrorDrift(LeadMirrorCase):
    def test_the_nightly_check_fixes_what_the_feed_missed(self):
        self.backfilled("L-1", "L-2", "L-3")
        since = self.state("since")
        # an outage: none of these reached the change feed
        self.erp.leads["L-1"]["lead_name"] = "Quietly changed"
        self.erp.leads["L-1"]["modified"] = "2031-03-04 05:59:59"
        self.erp.drop("L-2", log=False)
        self.erp.leads["L-4"] = {
            **self.erp.leads["L-3"],
            "lead_name": "Quietly added",
            "modified": "2031-03-04 05:59:58",
        }
        lead_mirror.check_drift()
        self.assertEqual(self.names(), ["L-1", "L-3", "L-4"])
        self.assertEqual(self.copy("L-1").lead_name, "Quietly changed")
        self.assertEqual(self.copy("L-4").lead_name, "Quietly added")
        self.assertEqual(self.state("since"), since)
        self.assertEqual(self.state("erp_total"), 3)
        self.assertEqual(
            self.state("compare_result"),
            "3 leads on the ERP: 2 copied again, 1 copies dropped.",
        )
        self.assertTrue(self.state("last_compared_on"))

    def test_a_clean_copy_is_left_alone(self):
        self.backfilled("L-1", "L-2")
        bulk = len(self.erp.get_calls("get_leads_bulk"))
        lead_mirror.check_drift()
        self.assertEqual(len(self.erp.get_calls("get_leads_bulk")), bulk)
        self.assertEqual(
            self.state("compare_result"),
            "2 leads on the ERP: 0 copied again, 0 copies dropped.",
        )

    def test_no_check_before_the_first_copy(self):
        self.fill("L-1")
        lead_mirror.check_drift()
        self.assertEqual(self.erp.calls, [])


class TestLeadMirrorSettings(LeadMirrorCase):
    def test_only_admins_see_the_health_and_change_it(self):
        create_agent(PLAIN_AGENT)
        frappe.set_user(PLAIN_AGENT)
        for call in (
            mirror_api.get_health,
            lambda: mirror_api.set_enabled(True),
            mirror_api.rebuild,
        ):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_turning_it_on_starts_the_backfill_in_the_background(self):
        frappe.db.set_single_value(STATE, "enabled", 0)
        health = mirror_api.set_enabled(True)
        self.assertTrue(health["enabled"])
        self.enqueue.assert_called_once()
        mirror_api.set_enabled(False)
        self.assertFalse(mirror_api.get_health()["enabled"])
        self.assertEqual(self.enqueue.call_count, 1)

    def test_it_needs_the_crm_connection(self):
        frappe.db.set_single_value(STATE, "enabled", 0)
        frappe.db.set_single_value("HD CRM Settings", "enabled", 0)
        frappe.clear_document_cache("HD CRM Settings", "HD CRM Settings")
        with self.assertRaises(frappe.ValidationError):
            mirror_api.set_enabled(True)

    def test_the_health_line_says_how_the_copy_stands(self):
        self.backfilled("L-1", "L-2")
        health = mirror_api.get_health()
        self.assertEqual(health["leads_copied"], 2)
        self.assertEqual(health["erp_total"], 2)
        self.assertFalse(health["copying"])
        self.assertFalse(health["last_error"])
        self.assertTrue(health["last_synced_on"])
        self.assertEqual(health["lag_seconds"], 0)

    def test_a_copy_that_died_does_not_show_as_copying(self):
        frappe.db.set_single_value(STATE, "backfill_status", "Copying")
        self.assertFalse(mirror_api.get_health()["copying"])
        with lead_mirror.single_flight():
            self.assertTrue(mirror_api.get_health()["copying"])

    def test_rebuild_clears_the_copy_and_fills_it_again(self):
        self.backfilled("L-1")
        mirror_api.rebuild()
        self.assertEqual(self.names(), [])
        self.assertFalse(self.state("since"))
        self.enqueue.assert_called_once()
        lead_mirror.backfill_lead_mirror()
        self.assertEqual(self.names(), ["L-1"])

    def test_rebuild_waits_for_a_run_in_progress_and_needs_the_copy_on(self):
        self.backfilled("L-1")
        with lead_mirror.single_flight(), self.assertRaises(frappe.ValidationError):
            mirror_api.rebuild()
        self.assertEqual(self.names(), ["L-1"])
        frappe.db.set_single_value(STATE, "enabled", 0)
        with self.assertRaises(frappe.ValidationError):
            mirror_api.rebuild()

    def test_nobody_edits_the_copy_by_hand(self):
        for doctype in (MIRROR, STATE):
            roles = {p.role for p in frappe.get_meta(doctype).permissions}
            self.assertEqual(roles, {"System Manager", "Agent Manager"})
            for permission in frappe.get_meta(doctype).permissions:
                self.assertFalse(
                    permission.write or permission.create or permission.delete
                )
