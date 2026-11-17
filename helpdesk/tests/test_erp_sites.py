from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, getdate

from helpdesk.api import erp_sites as settings_api
from helpdesk.crm_dashboard import sync
from helpdesk.crm_dashboard.erp_roles import access_levels
from helpdesk.helpdesk.doctype.hd_crm_source.hd_crm_source import HDCRMSource
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRMSite,
    fill_crm_site,
    hold_commits,
    make_crm_source,
    make_division,
    make_sales_employee,
)

LEAD = "HD CRM Report Lead"
SOURCE = "Test Source"
ANN = "ann.crmdash@example.com"
BOB = "bob.crmdash@example.com"
VIEWER = "viewer.crmdash@example.com"
TABLES = (
    "HD Division Member",
    "HD Division",
    LEAD,
    "HD CRM Status Map",
    "HD CRM Source Role",
    "HD CRM Source User",
    "HD CRM Source",
)


class ERPSiteCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        for table in TABLES:
            frappe.db.delete(table)
        frappe.db.set_single_value("HD CRM Settings", "dashboard_currency", "INR")
        self.sites = {SOURCE: FakeCRMSite()}
        self.site = self.sites[SOURCE]
        client = patch.object(HDCRMSource, "client", lambda doc: self.sites[doc.name])
        client.start()
        self.addCleanup(client.stop)
        # nothing here may reach a real queue; tests run the jobs themselves
        enqueue = patch.object(frappe, "enqueue")
        self.enqueue = enqueue.start()
        self.addCleanup(enqueue.stop)
        # a failed sync rolls back its work; the test's one transaction must survive that
        rollback = patch.object(frappe.db, "rollback")
        rollback.start()
        self.addCleanup(rollback.stop)
        self.today = getdate()

    def sync(self, source: str = SOURCE, full: bool = False):
        sync.run_job(source, full=full)

    def lead(self, name: str, source: str = SOURCE):
        return frappe.get_doc(LEAD, f"{source}::{name}")


class TestERPSiteSync(ERPSiteCase):
    def test_sync_copies_the_mapped_fields_and_counts_each_status_once(self):
        make_crm_source(company_label="Head Office")
        fill_crm_site(self.site, self.today)
        self.sync()

        won = self.lead("L2")
        self.assertEqual(
            (won.company, won.branch, won.lead_owner, won.status, won.category),
            ("Acme", "North", ANN, "Won", "Won"),
        )
        self.assertEqual((won.won_value, won.expected_revenue), (500, 600))
        self.assertEqual(won.closing_days, 10)
        self.assertEqual(
            won.employee, ANN, "the owner is the employee when none is mapped"
        )
        # no company on the lead: the source's own
        self.assertEqual(self.lead("L5").company, "Head Office")
        self.assertEqual(
            self.lead("L5").category, "", "an unmapped status counts nowhere"
        )
        self.assertEqual(
            frappe.db.get_value("HD CRM Source", SOURCE, "leads_synced"), 5
        )
        self.assertEqual(
            frappe.db.get_value("HD CRM Source", SOURCE, "last_sync_status"), "OK"
        )

    def test_a_sync_reads_only_changes_and_a_full_one_drops_deleted_leads(self):
        make_crm_source()
        fill_crm_site(self.site, self.today)
        self.sync()
        cursor = frappe.db.get_value("HD CRM Source", SOURCE, "sync_cursor")

        self.site.put("L1", status="Won", won=900)
        self.site.remove("L3")
        self.sync()
        since = str(add_to_date(get_datetime(cursor), seconds=-60))
        self.assertEqual(self.site.pages[-1]["filters"], [["modified", ">=", since]])
        self.assertEqual(self.lead("L1").category, "Won")
        self.assertTrue(
            frappe.db.exists(LEAD, f"{SOURCE}::L3"), "only a full sync drops"
        )

        self.sync(full=True)
        self.assertFalse(frappe.db.exists(LEAD, f"{SOURCE}::L3"))
        self.assertEqual(frappe.db.count(LEAD), 4)

    def test_a_new_status_mapping_recounts_without_reading_the_source(self):
        source = make_crm_source()
        fill_crm_site(self.site, self.today)
        self.sync()
        pages = len(self.site.pages)

        source.append("status_map", {"status": "Demo Demanded", "category": "Open"})
        source.save()
        sync.recompute_source(SOURCE)

        self.assertEqual(self.lead("L5").category, "Open")
        self.assertEqual(len(self.site.pages), pages, "the source wasn't read")

    def test_a_failed_sync_is_recorded_and_logged_once_per_outage(self):
        make_crm_source()
        self.site.down = True
        before = frappe.db.count("Error Log")

        self.sync()
        self.sync()

        source = frappe.get_doc("HD CRM Source", SOURCE)
        self.assertEqual(source.last_sync_status, "Failed")
        self.assertIn("down", source.last_error)
        self.assertEqual(frappe.db.count("Error Log"), before + 1)

        self.site.down = False
        self.sync()
        self.assertEqual(
            frappe.db.get_value("HD CRM Source", SOURCE, "last_sync_status"), "OK"
        )

    def test_a_lead_doctype_the_site_lacks_fails_the_sync_and_keeps_the_copy(self):
        make_crm_source()
        fill_crm_site(self.site, self.today)
        self.sync()
        frappe.db.set_value("HD CRM Source", SOURCE, "lead_doctype", "CRM Lead")

        self.sync(full=True)

        source = frappe.get_doc("HD CRM Source", SOURCE)
        self.assertEqual(source.last_sync_status, "Failed")
        self.assertIn("CRM Lead", source.last_error)
        self.assertEqual(frappe.db.count(LEAD), 5, "an unread site drops nothing")

    def test_a_full_read_asked_for_during_a_sync_is_queued_on_its_own(self):
        make_crm_source()
        sync.enqueue_sync(SOURCE)
        sync.enqueue_sync(SOURCE, full=True)
        ids = [c.kwargs["job_id"] for c in self.enqueue.call_args_list]
        self.assertEqual(len(set(ids)), 2, "neither swallows the other")

    def test_a_sync_recounts_only_the_leads_it_read(self):
        make_crm_source()
        fill_crm_site(self.site, self.today)
        self.sync()
        # a sync re-reads the minute before its cursor; move the cursor well past L3
        self.site.clock += timedelta(minutes=5)
        self.site.put("L1", status="Contacted")
        self.sync()
        # a mark on a lead the next sync won't read stays: it isn't counted again
        frappe.db.set_value(LEAD, f"{SOURCE}::L3", "lead_source", "untouched")
        self.site.clock += timedelta(minutes=5)
        self.site.put("L1", status="Won", won=900)

        self.sync()

        self.assertEqual(self.lead("L1").category, "Won")
        self.assertEqual(self.lead("L3").lead_source, "untouched")


class TestERPSiteSettings(ERPSiteCase):
    def test_a_source_refuses_mappings_that_make_no_sense(self):
        with self.assertRaisesRegex(frappe.ValidationError, "both"):
            make_crm_source(branch_field="company")
        with self.assertRaisesRegex(frappe.ValidationError, "lead status"):
            make_crm_source(status_field="")
        with self.assertRaisesRegex(frappe.ValidationError, "isn't a field name"):
            make_crm_source(team_field="Team Name")
        with self.assertRaisesRegex(frappe.ValidationError, "mapped twice"):
            make_crm_source(status_map=[{"status": "New", "category": "Open"}] * 2)
        # one amount field for both, and the owner as the employee, are fine
        make_crm_source(expected_revenue_field="won", employee_field="lead_owner")

    def test_a_site_is_read_by_one_source_only(self):
        make_crm_source()
        with self.assertRaisesRegex(frappe.ValidationError, "counted twice"):
            make_crm_source("Other", site_url="https://test_source.example/")

    def test_saving_checks_the_mapping_against_the_sites_fields(self):
        source = make_crm_source()
        with self.assertRaisesRegex(frappe.ValidationError, "has no field nope"):
            settings_api.save_source({"team_field": "nope"}, SOURCE)
        with self.assertRaisesRegex(frappe.ValidationError, "Currency field"):
            settings_api.save_source({"team_field": "annual_revenue"}, SOURCE)

        self.site.down = True
        saved = settings_api.save_source({"team_field": "team"}, SOURCE)
        self.assertIn("couldn't be checked", saved["warning"])
        self.assertEqual(source.reload().team_field, "team")

    def test_the_api_secret_never_leaves_the_server(self):
        make_crm_source()
        source = settings_api.get_source(SOURCE)
        self.assertEqual(source["api_secret"]["set"], True)
        self.assertNotIn("secret", frappe.as_json(source["api_secret"]))
        self.assertNotIn("api_secret", settings_api.SOURCE_FIELDS)

    def test_the_list_names_the_divisions_each_site_serves(self):
        make_crm_source()
        make_crm_source("Spare", site_url="https://spare.example")
        make_division("IND", "India", crm_source=SOURCE)

        sources = {s["name"]: s for s in settings_api.get_sources()["sources"]}

        self.assertEqual(sources[SOURCE]["divisions"], ["India"])
        self.assertEqual(sources["Spare"]["divisions"], [])

    def test_a_site_a_division_uses_cant_be_deleted(self):
        make_crm_source()
        fill_crm_site(self.site, self.today)
        self.sync()
        division = make_division("IND", "India", crm_source=SOURCE)
        with self.assertRaises(frappe.LinkExistsError):
            settings_api.delete_source(SOURCE)

        division.crm_source = ""
        division.save()
        settings_api.delete_source(SOURCE)
        self.assertFalse(frappe.db.count(LEAD), "its copied leads go with it")

    def test_history_says_who_changed_what(self):
        make_crm_source()
        # Frappe keeps no versions in tests unless told to
        with patch.dict(frappe.flags, {"in_test": False}):
            settings_api.save_source({"sync_every": "Daily"}, SOURCE)
        history = settings_api.get_history("HD CRM Source", SOURCE)
        self.assertIn("Daily", history["changes"][0]["lines"][0])
        self.assertEqual(history["changes"][0]["by"], "Administrator")

    def test_only_super_admins_change_the_sites(self):
        make_crm_source()
        make_sales_employee(VIEWER, "Vee Viewer")
        frappe.set_user(VIEWER)
        for call in (
            settings_api.get_sources,
            lambda: settings_api.get_source(SOURCE),
            lambda: settings_api.set_currency("USD"),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()


class TestERPSiteRoles(ERPSiteCase):
    """Access that follows the site's roles (docs/divisions.md, "ERP sites"). Ann is a
    Sales Manager there, Bob a Sales User, the viewer has no sales role."""

    def setUp(self):
        super().setUp()
        for email, name in ((ANN, "Ann Seller"), (BOB, "Bob Seller"), (VIEWER, "Vee")):
            make_sales_employee(email, name)
        self.site.add_user(ANN, "Sales Manager", "Employee")
        self.site.add_user(BOB, "Sales User")
        self.site.add_user(VIEWER, "Accounts User")
        make_crm_source(company_label="Head Office", use_erp_roles=1)
        fill_crm_site(self.site, self.today)
        self.sync()

    def access(self, user: str) -> str | None:
        return access_levels(user, [SOURCE]).get(SOURCE)

    def test_the_sync_reads_the_sites_users_and_their_access(self):
        self.assertEqual(
            {u: self.access(u) for u in (ANN, BOB, VIEWER)},
            {ANN: "Manager", BOB: "Executive", VIEWER: ""},
        )
        self.assertEqual(self.access("Administrator"), "Manager", "hub admins")
        source = frappe.get_doc("HD CRM Source", SOURCE)
        self.assertEqual(
            [(r.erp_role, r.access) for r in source.role_map],
            [
                ("Sales Manager", "Manager"),
                ("Sales Master Manager", "Manager"),
                ("Sales User", "Executive"),
            ],
            "starts with ERPNext's sales roles",
        )
        self.assertTrue(source.users_read_on)

        del self.site.users[VIEWER]
        self.sync()
        self.assertFalse(frappe.db.exists("HD CRM Source User", f"{SOURCE}::{VIEWER}"))

    def test_a_new_role_mapping_applies_at_once_without_reading_the_site(self):
        pages = len(self.site.pages)
        source = frappe.get_doc("HD CRM Source", SOURCE)
        source.append("role_map", {"erp_role": "Accounts User", "access": "Manager"})
        source.save()
        self.assertEqual(self.access(VIEWER), "Manager")
        self.assertEqual(len(self.site.pages), pages)

    def test_a_user_disabled_on_the_site_loses_access(self):
        self.site.add_user(ANN, "Sales Manager", enabled=False)
        self.sync()
        self.assertEqual(self.access(ANN), "")

    def test_switched_off_the_hubs_own_rules_apply_again(self):
        source = frappe.get_doc("HD CRM Source", SOURCE)
        source.use_erp_roles = 0
        source.save()
        self.assertIsNone(self.access(VIEWER))

    def test_a_site_that_wont_list_its_users_keeps_the_last_copy(self):
        with patch.object(
            self.site,
            "users_with_roles",
            side_effect=CRMError("The CRM site answered 403: no access", 403),
        ):
            self.sync()
        source = frappe.get_doc("HD CRM Source", SOURCE)
        self.assertEqual(source.last_sync_status, "OK", "the leads still synced")
        self.assertIn("403", source.users_error)
        self.assertEqual(self.access(ANN), "Manager")

    def test_settings_list_the_users_and_save_the_role_mapping(self):
        users = settings_api.get_source(SOURCE)["users"]
        self.assertEqual([u["email"] for u in users], [ANN, BOB, VIEWER])
        self.assertTrue(all(u["in_hub"] for u in users))
        self.assertEqual(users[0]["roles"], ["Employee", "Sales Manager"])

        settings_api.save_source(
            {"role_map": [{"erp_role": "Sales User", "access": "Manager"}]}, name=SOURCE
        )
        self.assertEqual(self.access(BOB), "Manager")
        self.assertEqual(self.access(ANN), "", "Sales Manager is no longer mapped")
        with self.assertRaisesRegex(frappe.ValidationError, "mapped twice"):
            settings_api.save_source(
                {
                    "role_map": [
                        {"erp_role": "Sales User", "access": "Manager"},
                        {"erp_role": "Sales User", "access": "Executive"},
                    ]
                },
                name=SOURCE,
            )
