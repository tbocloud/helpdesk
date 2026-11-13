from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import (
    add_days,
    add_months,
    add_to_date,
    get_datetime,
    get_first_day,
    getdate,
)

from helpdesk.api import crm_dashboard as viewer_api
from helpdesk.api import crm_dashboard_settings as settings_api
from helpdesk.content_team import SALES_EMPLOYEE_ROLE
from helpdesk.crm_dashboard import sync
from helpdesk.crm_dashboard.registry import templates
from helpdesk.helpdesk.doctype.hd_crm_source.hd_crm_source import HDCRMSource
from helpdesk.test_utils import (
    FakeCRMSite,
    crm_kpi,
    enable_leads,
    fill_crm_site,
    hold_commits,
    make_crm_dashboard,
    make_crm_org_unit,
    make_crm_source,
    make_sales_employee,
)

LEAD = "HD CRM Report Lead"
UNIT = "HD CRM Org Unit"
SOURCE = "Test Source"
ANN = "ann.crmdash@example.com"
BOB = "bob.crmdash@example.com"
VIEWER = "viewer.crmdash@example.com"
TABLES = (
    "HD CRM Dashboard",
    "HD CRM Dashboard Role",
    "HD CRM Dashboard Unit",
    "HD CRM Dashboard Filter",
    "HD CRM Dashboard KPI",
    "HD CRM Dashboard Chart",
    LEAD,
    UNIT,
    "HD CRM Status Map",
    "HD CRM Source",
)


class CRMDashboardCase(FrappeTestCase):
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

    def report(self, dashboard=None, filters=None) -> dict:
        dashboard = dashboard or make_crm_dashboard()
        return viewer_api.get_dashboard(dashboard.name, filters)


class TestCRMDashboardSync(CRMDashboardCase):
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

    def test_units_come_from_erpnext_records_and_from_the_leads(self):
        make_crm_source()
        self.site.org = {
            "Company": [{"name": "Acme"}],
            "Department": [
                {
                    "name": "Sales North",
                    "department_name": "North sales",
                    "company": "Acme",
                }
            ],
            "Employee": [
                {
                    "name": "EMP-1",
                    "employee_name": "Ann Example",
                    "user_id": ANN,
                    "company": "Acme",
                    "department": "Sales North",
                },
                # not on any lead: no unit
                {"name": "EMP-9", "employee_name": "Zed", "user_id": "zed@example.com"},
            ],
        }
        fill_crm_site(self.site, self.today)
        self.sync()

        def unit(unit_type, name):
            return frappe.db.get_value(
                UNIT,
                {"unit_type": unit_type, "unit_name": name},
                ["label", "company", "branch", "department", "origin"],
                as_dict=True,
            )

        self.assertEqual(unit("Department", "Sales North").label, "North sales")
        self.assertEqual(
            unit("Branch", "South").company, "Acme", "seen together on a lead"
        )
        ann = unit("Employee", ANN)
        self.assertEqual(
            (ann.label, ann.department, ann.company),
            ("Ann Example", "Sales North", "Acme"),
        )
        self.assertEqual(ann.origin, "Synced")
        self.assertIsNone(unit("Employee", "zed@example.com"))

        # an admin's edit stays through the next sync
        frappe.db.set_value(
            UNIT, {"unit_type": "Employee", "unit_name": ANN}, "label", "Ann E."
        )
        self.sync(full=True)
        self.assertEqual(unit("Employee", ANN).label, "Ann E.")

    def test_putting_an_employee_in_a_team_moves_their_leads_with_it(self):
        make_crm_source()
        fill_crm_site(self.site, self.today)
        self.sync()
        make_crm_org_unit(SOURCE, "Department", "Inside Sales", company="Acme")
        team = make_crm_org_unit(SOURCE, "Team", "Hunters", department="Inside Sales")
        self.assertEqual(
            team.company, "Acme", "a team sits in its department's company"
        )
        bob = frappe.get_doc(UNIT, {"unit_type": "Employee", "unit_name": BOB})
        bob.team = "Hunters"
        bob.save()
        sync.recompute_source(SOURCE)

        lost = self.lead("L3")
        self.assertEqual((lost.team, lost.department), ("Hunters", "Inside Sales"))
        self.assertEqual(lost.branch, "South", "what the lead carries wins")

    def test_an_inactive_unit_leaves_its_leads_out(self):
        make_crm_source()
        fill_crm_site(self.site, self.today)
        self.sync()
        beta = frappe.get_doc(UNIT, {"unit_type": "Company", "unit_name": "Beta"})
        beta.is_active = 0
        beta.save()
        sync.recompute_source(SOURCE)

        self.assertEqual(crm_kpi(self.report(), "total_leads")["value"], 4)

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


class TestCRMDashboardConfig(CRMDashboardCase):
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

    def test_units_are_unique_and_their_parents_agree(self):
        make_crm_source()
        make_crm_org_unit(SOURCE, "Company", "Acme")
        make_crm_org_unit(SOURCE, "Branch", "North", company="Acme")
        with self.assertRaises(frappe.DuplicateEntryError):
            make_crm_org_unit(SOURCE, "Company", "Acme")
        with self.assertRaisesRegex(
            frappe.ValidationError, "Add it under Organisation"
        ):
            make_crm_org_unit(SOURCE, "Team", "Hunters", branch="Nowhere")
        make_crm_org_unit(SOURCE, "Company", "Beta")
        with self.assertRaisesRegex(frappe.ValidationError, "not Beta"):
            make_crm_org_unit(SOURCE, "Team", "Hunters", branch="North", company="Beta")
        team = make_crm_org_unit(SOURCE, "Team", "Hunters", branch="North")
        self.assertEqual(team.company, "Acme")
        with self.assertRaisesRegex(frappe.ValidationError, "sits under it"):
            frappe.delete_doc(UNIT, frappe.db.get_value(UNIT, {"unit_name": "North"}))

    def test_a_dashboard_refuses_charts_and_cards_that_cant_work(self):
        cases = {
            "group it by Month": {
                "charts": [
                    {
                        "title": "t",
                        "chart_type": "line",
                        "dimension": "company",
                        "metric": "total_leads",
                    }
                ]
            },
            "parts of a whole": {
                "charts": [
                    {
                        "title": "t",
                        "chart_type": "donut",
                        "dimension": "company",
                        "metric": "conversion_rate",
                    }
                ]
            },
            "share an axis": {
                "charts": [
                    {
                        "title": "t",
                        "chart_type": "bar",
                        "dimension": "company",
                        "metric": "total_leads",
                        "compare_metric": "won_value",
                    }
                ]
            },
            "can't be calculated": {"kpis": [{"metric": "won_value", "basis": "lost"}]},
            "can't be shown as": {
                "kpis": [
                    {"metric": "total_leads"},
                    {"metric": "won_value", "aggregation": "median"},
                ]
            },
            "listed twice": {"filters": [{"filter": "company"}, {"filter": "company"}]},
            "at least one": {"kpis": [], "charts": []},
        }
        for message, values in cases.items():
            with self.subTest(message), self.assertRaisesRegex(
                frappe.ValidationError, message
            ):
                make_crm_dashboard(**values)

    def test_every_template_makes_a_valid_dashboard_and_copies_start_inactive(self):
        for key in templates():
            created = settings_api.create_dashboard(key, f"From {key}")
            self.assertEqual(created["is_active"], 0)
            self.assertTrue(created["kpis"])
        executive = frappe.get_value("HD CRM Dashboard", {"template": "executive"})
        settings_api.set_dashboard_active(executive, True)
        copy = settings_api.duplicate_dashboard(executive, "Copy")
        self.assertEqual((copy["is_active"], copy["dashboard_name"]), (0, "Copy"))
        self.assertEqual(
            len(copy["charts"]),
            len(frappe.get_doc("HD CRM Dashboard", executive).charts),
        )

    def test_one_dashboard_is_the_default(self):
        first = make_crm_dashboard("First", is_default=1)
        make_crm_dashboard("Second", is_default=1)
        self.assertEqual(first.reload().is_default, 0)

    def test_history_says_who_changed_what(self):
        dashboard = make_crm_dashboard()
        # Frappe keeps no versions in tests unless told to
        with patch.dict(frappe.flags, {"in_test": False}):
            settings_api.save_dashboard(
                {"default_period": "this_quarter"}, dashboard.name
            )
        history = settings_api.get_history("HD CRM Dashboard", dashboard.name)
        self.assertIn("this_quarter", history["changes"][0]["lines"][0])
        self.assertEqual(history["changes"][0]["by"], "Administrator")

    def test_only_admins_change_the_dashboards(self):
        make_sales_employee(VIEWER, "Vee Viewer")
        frappe.set_user(VIEWER)
        for call in (
            settings_api.get_settings,
            lambda: settings_api.create_dashboard("executive", "Mine"),
            lambda: settings_api.set_currency("USD"),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_a_unit_or_source_a_dashboard_covers_cant_be_deleted(self):
        make_crm_source()
        acme = make_crm_org_unit(SOURCE, "Company", "Acme")
        dashboard = make_crm_dashboard(units=[{"unit": acme.name}])
        with self.assertRaisesRegex(frappe.ValidationError, "Test Dashboard covers"):
            settings_api.delete_unit(acme.name)
        with self.assertRaisesRegex(frappe.ValidationError, "Test Dashboard covers"):
            settings_api.delete_source(SOURCE)
        self.assertTrue(frappe.db.exists(UNIT, acme.name))

        frappe.delete_doc("HD CRM Dashboard", dashboard.name)
        settings_api.delete_source(SOURCE)
        self.assertFalse(frappe.db.exists(UNIT, acme.name))


class TestCRMDashboardReport(CRMDashboardCase):
    def setUp(self):
        super().setUp()
        make_crm_source(company_label="Head Office")
        fill_crm_site(self.site, self.today)
        self.sync()

    def test_every_kpi_counts_each_lead_once(self):
        page = self.report(
            make_crm_dashboard(
                kpis=[
                    {"metric": m}
                    for m in (
                        "total_leads",
                        "open_leads",
                        "won_leads",
                        "lost_leads",
                        "converted_leads",
                        "expected_revenue",
                        "pending_value",
                    )
                ]
                + [
                    {"metric": "conversion_rate", "basis": "all"},
                    {"metric": "conversion_rate", "basis": "closed"},
                    {"metric": "won_value", "aggregation": "sum"},
                    {"metric": "won_value", "aggregation": "average"},
                    {"metric": "average_deal_value"},
                    {"metric": "avg_closing_days", "basis": "sold"},
                    {"metric": "avg_closing_days", "basis": "closed"},
                ]
            )
        )
        values = [(c["metric"], round(c["value"], 2)) for c in page["kpis"]]
        self.assertEqual(
            values,
            [
                ("total_leads", 5),
                ("open_leads", 1),
                ("won_leads", 1),
                ("lost_leads", 1),
                ("converted_leads", 1),
                ("expected_revenue", 1800),
                ("pending_value", 1000),
                # won and converted, never one lead twice
                ("conversion_rate", 40),
                ("conversion_rate", 66.67),
                ("won_value", 800),
                ("won_value", 400),
                ("average_deal_value", 400),
                ("avg_closing_days", 15),
                ("avg_closing_days", 20),
            ],
        )

    def test_a_metric_without_its_field_says_what_to_map(self):
        frappe.db.set_value("HD CRM Source", SOURCE, "won_value_field", "")
        card = crm_kpi(self.report(), "won_value")
        self.assertIsNone(card["value"])
        self.assertIn("won sales value", card["missing"])

    def test_statuses_without_a_category_are_pointed_out(self):
        notice = self.report()["notices"][0]
        self.assertEqual(notice["kind"], "unmapped_statuses")
        self.assertIn("Demo Demanded", notice["text"])

    def test_a_company_table_ranks_and_limits_its_rows(self):
        dashboard = make_crm_dashboard(
            charts=[
                {
                    "title": "Companies",
                    "chart_type": "table",
                    "dimension": "company",
                    "metric": "total_leads",
                    "max_items": 1,
                }
            ]
        )
        chart = self.report(dashboard)["charts"][0]
        self.assertEqual([i["key"] for i in chart["items"]], ["Acme"])
        self.assertEqual(chart["items"][0]["columns"]["won_value"], 500)
        self.assertEqual(chart["total_groups"], 3)

    def test_a_monthly_trend_shows_every_month_up_to_now(self):
        self.site.put(
            "L6",
            lead_owner=ANN,
            status="Won",
            won=50,
            creation=f"{add_months(self.today, -3)} 09:00:00",
        )
        self.sync()
        dashboard = make_crm_dashboard(
            charts=[
                {
                    "title": "Trend",
                    "chart_type": "line",
                    "dimension": "month",
                    "metric": "won_value",
                    "max_items": 12,
                },
                {
                    "title": "Rate",
                    "chart_type": "line",
                    "dimension": "month",
                    "metric": "conversion_rate",
                },
            ]
        )
        trend, rate = self.report(dashboard)["charts"]
        months = [i["key"] for i in trend["items"]]
        self.assertEqual(
            months[0], get_first_day(add_months(self.today, -3)).strftime("%Y-%m")
        )
        self.assertEqual(months[-1], self.today.strftime("%Y-%m"))
        self.assertEqual(len(months), 4)
        self.assertEqual(trend["items"][-1]["value"], 0, "an empty month is no sales")
        self.assertIsNone(rate["items"][-1]["value"], "and no rate to show")

    def test_filters_offer_only_what_the_choice_above_allows(self):
        dashboard = make_crm_dashboard()
        page = self.report(dashboard, {"company": "Acme", "period": "all_time"})
        branch = next(f for f in page["filters"] if f["key"] == "branch")
        self.assertEqual([o["value"] for o in branch["options"]], ["North", "South"])
        company = next(f for f in page["filters"] if f["key"] == "company")
        self.assertEqual(
            [o["value"] for o in company["options"]], ["Acme", "Beta", "Head Office"]
        )
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 3)

    def test_a_filter_the_dashboard_doesnt_offer_is_ignored(self):
        page = self.report(filters={"lead_owner": ANN, "period": "all_time"})
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 5)

    def test_the_period_counts_leads_by_the_day_they_were_created(self):
        page = self.report(filters={"period": "last_30_days"})
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 0)
        page = self.report(
            filters={
                "period": "custom",
                "from_date": str(add_days(self.today, -45)),
                "to_date": str(self.today),
            }
        )
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 5)

    def test_companies_on_other_sites_add_up_in_the_reporting_currency(self):
        self.sites["Gulf"] = FakeCRMSite()
        make_crm_source("Gulf", currency="USD", exchange_rate=80)
        self.sites["Gulf"].put(
            "G1", company="Gulf Co", lead_owner=BOB, status="Won", won=10
        )
        self.sync("Gulf")
        page = self.report()
        self.assertEqual(crm_kpi(page, "won_value", "sum")["value"], 800 + 800)
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 6)

    def test_a_viewer_needs_one_of_the_roles(self):
        enable_leads()
        make_sales_employee(VIEWER, "Vee Viewer")
        dashboard = make_crm_dashboard()
        frappe.set_user(VIEWER)
        self.assertEqual(viewer_api.get_dashboards()["dashboards"], [])
        with self.assertRaises(frappe.PermissionError):
            viewer_api.get_dashboard(dashboard.name)

    def test_a_team_leader_sees_only_their_teams_leads(self):
        enable_leads()
        make_sales_employee(VIEWER, "Vee Viewer")
        make_crm_org_unit(SOURCE, "Team", "Hunters", company="Acme", leader=VIEWER)
        ann = frappe.get_doc(UNIT, {"unit_type": "Employee", "unit_name": ANN})
        ann.team = "Hunters"
        ann.save()
        sync.recompute_source(SOURCE)
        dashboard = make_crm_dashboard(
            scope="team", roles=[{"role": SALES_EMPLOYEE_ROLE}]
        )

        frappe.set_user(VIEWER)
        page = viewer_api.get_dashboard(dashboard.name)
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 2, "Ann's two leads")
        self.assertFalse(page["can_configure"])
        # a filter can't widen the scope
        page = viewer_api.get_dashboard(
            dashboard.name, {"company": "Beta", "period": "all_time"}
        )
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 0)

    def test_a_viewer_the_organisation_doesnt_place_sees_nothing(self):
        enable_leads()
        make_sales_employee(VIEWER, "Vee Viewer")
        dashboard = make_crm_dashboard(
            scope="branch", roles=[{"role": SALES_EMPLOYEE_ROLE}]
        )
        frappe.set_user(VIEWER)
        page = viewer_api.get_dashboard(dashboard.name)
        self.assertTrue(page["not_placed"])
        self.assertEqual(page["kpis"], [])

    def test_own_scope_shows_the_viewers_leads(self):
        enable_leads()
        make_sales_employee(BOB, "Bob Seller")
        dashboard = make_crm_dashboard(
            scope="own", roles=[{"role": SALES_EMPLOYEE_ROLE}]
        )
        frappe.set_user(BOB)
        page = viewer_api.get_dashboard(dashboard.name)
        self.assertEqual(crm_kpi(page, "total_leads")["value"], 2)

    def test_units_of_different_kinds_cover_the_leads_of_any(self):
        beta = frappe.db.get_value(UNIT, {"unit_type": "Company", "unit_name": "Beta"})
        north = frappe.db.get_value(UNIT, {"unit_type": "Branch", "unit_name": "North"})
        page = self.report(make_crm_dashboard(units=[{"unit": beta}, {"unit": north}]))
        self.assertEqual(
            crm_kpi(page, "total_leads")["value"], 3, "North's two and Beta's"
        )

    def test_a_name_two_sites_share_never_opens_the_other_sites_leads(self):
        enable_leads()
        make_sales_employee(VIEWER, "Vee Viewer")
        self.sites["Gulf"] = FakeCRMSite()
        make_crm_source("Gulf")
        self.sites["Gulf"].put(
            "G1", company="Gulf Co", branch="North", lead_owner=BOB, status="New"
        )
        self.sync("Gulf")
        make_crm_org_unit(SOURCE, "Employee", VIEWER, user=VIEWER, branch="North")
        dashboard = make_crm_dashboard(
            scope="branch", roles=[{"role": SALES_EMPLOYEE_ROLE}]
        )
        frappe.set_user(VIEWER)
        page = viewer_api.get_dashboard(dashboard.name)
        self.assertEqual(
            crm_kpi(page, "total_leads")["value"], 2, "this site's North only"
        )

    def test_an_average_card_says_it_is_one(self):
        page = self.report(
            make_crm_dashboard(
                kpis=[
                    {"metric": "won_value", "aggregation": "sum"},
                    {"metric": "won_value", "aggregation": "average"},
                ]
            )
        )
        total, average = (card["label"] for card in page["kpis"])
        self.assertNotEqual(total, average)
        self.assertIn("average per lead", average)

    def test_a_card_compares_with_the_days_before_its_period(self):
        card = crm_kpi(self.report(filters={"period": "last_30_days"}), "total_leads")
        # the five leads were made 40 days ago: none in the last 30, all in the 30 before
        self.assertEqual((card["value"], card["previous"]), (0, 5))
        self.assertEqual(card["compared_to"], "vs the 30 days before")
        all_time = crm_kpi(self.report(), "total_leads")
        self.assertIsNone(all_time["previous"], "all time has nothing before it")

    def test_a_card_carries_its_last_six_months(self):
        page = self.report()
        trend = crm_kpi(page, "total_leads")["trend"]
        self.assertEqual(len(trend), 6)
        self.assertEqual(len(page["trend_months"]), 6)
        self.assertEqual(page["trend_months"][-1], getdate().strftime("%Y-%m"))
        self.assertEqual(sum(trend), 5, "the five leads, in the month they were made")
