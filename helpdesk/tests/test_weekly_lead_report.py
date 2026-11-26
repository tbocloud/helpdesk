from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from helpdesk import divisions
from helpdesk.api import weekly_lead_report as api
from helpdesk.helpdesk.doctype.hd_crm_source.hd_crm_source import HDCRMSource
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeWeeklyLeadERP,
    enable_leads,
    hold_commits,
    make_crm_source,
    make_division,
    make_tasky_user,
    weekly_report_lead,
)
from helpdesk.weekly_lead_report import report_division, week_start

SAM = "sam.weekly@example.com"  # KSA Division Sales User
SARA = "sara.weekly@example.com"  # another KSA Division Sales User
ADA = "ada.weekly@example.com"  # KSA Division Admin
IAN = "ian.weekly@example.com"  # India employee
FROM, TO = "2026-11-22", "2026-11-28"  # a week, Sunday to Saturday


class WeeklyLeadReportCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        for table in ("HD Division", "HD Division Member", "HD CRM Source"):
            frappe.db.delete(table)
        frappe.db.delete("DefaultValue", {"defkey": divisions.ACTIVE_DEFAULT})
        frappe.clear_cache()
        enable_leads()
        for email, name in (
            (SAM, "Sam Seller"),
            (SARA, "Sara Seller"),
            (ADA, "Ada Admin"),
            (IAN, "Ian India"),
        ):
            make_tasky_user(email, name)
        source = make_crm_source("KSA ERP")
        self.ksa = make_division(
            "KSA",
            "KSA",
            members=[
                (SAM, divisions.DIVISION_SALES_USER),
                (SARA, divisions.DIVISION_SALES_USER),
                (ADA, divisions.DIVISION_ADMIN),
            ],
            country="Saudi Arabia",
            currency="SAR",
            crm_source=source.name,
            weekly_lead_report=1,
        )
        make_division("IND", "India", members=[(IAN, divisions.DIVISION_SALES_USER)])
        self.erp = FakeWeeklyLeadERP(
            leads=[
                weekly_report_lead(
                    "CRM-LEAD-1",
                    "Pacific Blue",
                    lead_owner=SAM,
                    lead_name="Jabir",
                    job_title="Operations manager",
                    mobile_no="594339581",
                    email_id="jabir@pacificblue.example",
                    industry="Trading",
                    custom_lead_segment="Digital",
                    custom_conversion_possibility="Medium",
                    custom_visits_this_week=1,
                    custom_follow_up_plan="Yes",
                    custom_comment="<p>Wants a demo</p>",
                ),
                weekly_report_lead(
                    "CRM-LEAD-2", "Oryx", lead_owner=SAM, phone="538444796"
                ),
                weekly_report_lead("CRM-LEAD-3", "GTGC", lead_owner=SARA),
                # last week's
                weekly_report_lead(
                    "CRM-LEAD-4",
                    "NAFCO",
                    lead_owner=SAM,
                    modified="2026-11-21 23:59:00",
                ),
                weekly_report_lead("CRM-LEAD-5", "Oryx Annex"),
            ],
            quotations=[
                {
                    "name": "QTN-1",
                    "party_name": "CRM-LEAD-1",
                    "grand_total": 1000,
                    "currency": "SAR",
                    "transaction_date": "2026-11-01",
                },
                {
                    "name": "QTN-2",
                    "party_name": "CRM-LEAD-1",
                    "grand_total": 1500.5,
                    "currency": "SAR",
                    "transaction_date": "2026-11-20",
                },
            ],
            visible={
                SAM: {"CRM-LEAD-1", "CRM-LEAD-2"},
                SARA: {"CRM-LEAD-3"},
                ADA: {"CRM-LEAD-1", "CRM-LEAD-2", "CRM-LEAD-3"},
            },
        )
        client = patch.object(HDCRMSource, "client", return_value=self.erp)
        client.start()
        self.addCleanup(client.stop)

    def week_as(self, user: str, salesperson: str | None = None) -> dict:
        frappe.set_user(user)
        return api.get_report(FROM, TO, salesperson)

    def lead(self, name: str) -> dict:
        return self.erp.leads[name]


class TestWeek(WeeklyLeadReportCase):
    def test_a_week_starts_on_sunday(self):
        self.assertEqual(week_start("2026-11-22"), date(2026, 11, 22))
        self.assertEqual(week_start("2026-11-25"), date(2026, 11, 22))
        self.assertEqual(week_start("2026-11-28"), date(2026, 11, 22))
        self.assertEqual(week_start("2026-11-29"), date(2026, 11, 29))


class TestAccess(WeeklyLeadReportCase):
    def test_only_a_division_that_keeps_it_has_the_report(self):
        self.assertEqual(report_division(SAM), "KSA")
        self.assertEqual(report_division(ADA), "KSA")
        self.assertIsNone(report_division(IAN), "India doesn't keep it")
        self.ksa.db_set("weekly_lead_report", 0)
        self.assertIsNone(report_division(SAM))

    def test_someone_without_the_report_is_refused(self):
        frappe.set_user(IAN)
        with self.assertRaises(frappe.PermissionError):
            api.get_report(FROM, TO)

    def test_leads_off_closes_the_report(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        self.assertIsNone(report_division(SAM))


class TestReading(WeeklyLeadReportCase):
    def test_a_row_is_a_lead_of_theirs_updated_that_week(self):
        week = self.week_as(SAM)
        self.assertFalse(week["sees_team"])
        self.assertEqual((week["from_date"], week["to_date"]), (FROM, TO))
        self.assertEqual(
            [r["company_name"] for r in week["rows"]],
            ["Oryx", "Pacific Blue"],
            "not Sara's lead, nor the one last updated last week",
        )

    def test_rows_hold_the_template_columns_from_the_lead(self):
        pacific = next(
            r for r in self.week_as(SAM)["rows"] if r["lead"] == "CRM-LEAD-1"
        )
        self.assertEqual(pacific["contact_name"], "Jabir")
        self.assertEqual(pacific["designation"], "Operations manager")
        self.assertEqual(pacific["contact_number"], "594339581")
        self.assertEqual(pacific["business"], "Trading")
        self.assertEqual(pacific["requirement"], "Digital")
        self.assertEqual(pacific["requirement_label"], "Digital Marketing")
        self.assertTrue(pacific["quoted"])
        self.assertEqual(pacific["quotation"], "QTN-2", "the latest")
        self.assertEqual(pacific["quoted_value"], 1500.5)
        self.assertEqual(pacific["quotation_count"], 2)
        self.assertEqual(pacific["conversion"], "Medium")
        self.assertEqual(pacific["visits"], 1)
        self.assertEqual(pacific["follow_up"], "Yes")
        self.assertEqual(pacific["remarks"], "Wants a demo")
        oryx = next(r for r in self.week_as(SAM)["rows"] if r["lead"] == "CRM-LEAD-2")
        self.assertFalse(oryx["quoted"])
        self.assertEqual((oryx["visits"], oryx["follow_up"]), (0, ""))
        self.assertEqual(
            oryx["contact_number"], "538444796", "the phone, with no mobile"
        )

    def test_a_salesperson_sees_only_their_own_leads(self):
        week = self.week_as(SAM, salesperson=SARA)
        self.assertEqual({r["salesperson"] for r in week["rows"]}, {SAM})
        self.assertEqual(week["people"], [])

    def test_the_division_admin_sees_everyone_and_leads_with_no_owner(self):
        week = self.week_as(ADA)
        self.assertTrue(week["sees_team"])
        self.assertEqual(
            [(r["salesperson_name"], r["lead"]) for r in week["rows"]],
            [
                ("No owner", "CRM-LEAD-5"),
                ("Sam Seller", "CRM-LEAD-2"),
                ("Sam Seller", "CRM-LEAD-1"),
                ("Sara Seller", "CRM-LEAD-3"),
            ],
        )
        self.assertIn(SARA, [p["user"] for p in week["people"]])
        only_sara = api.get_report(FROM, TO, salesperson=SARA)
        self.assertEqual([r["salesperson"] for r in only_sara["rows"]], [SARA])

    def test_the_erp_site_failing_is_told(self):
        self.erp.error = CRMError("Couldn't reach the site")
        frappe.set_user(SAM)
        with patch.object(frappe, "log_error"):
            with self.assertRaisesRegex(frappe.ValidationError, "Couldn't reach"):
                api.get_report(FROM, TO)


class TestEditing(WeeklyLeadReportCase):
    def test_the_sheet_fields_are_written_to_the_lead(self):
        frappe.set_user(SAM)
        api.update_lead(
            "CRM-LEAD-2",
            {
                "designation": " Purchase manager ",
                "requirement": "Erpnext",
                "conversion": "High",
                "visits": "2",
                "follow_up": "No",
                "remarks": "  Price <ok>\nSign Sunday ",
            },
        )
        lead = self.lead("CRM-LEAD-2")
        self.assertEqual(lead["job_title"], "Purchase manager")
        self.assertEqual(lead["custom_lead_segment"], "Erpnext")
        self.assertEqual(lead["custom_conversion_possibility"], "High")
        self.assertEqual(lead["custom_visits_this_week"], 2)
        self.assertEqual(lead["custom_follow_up_plan"], "No")
        self.assertEqual(lead["custom_comment"], "Price &lt;ok&gt;<br>Sign Sunday")

    def test_values_outside_the_template_are_refused(self):
        frappe.set_user(SAM)
        for values, message in (
            ({"conversion": "Maybe"}, "High, Medium"),
            ({"visits": 100}, "0 to 99"),
            ({"follow_up": "Later"}, "Yes or No"),
            ({"requirement": "Hardware"}, "ERPNext or Digital"),
        ):
            with self.assertRaisesRegex(frappe.ValidationError, message):
                api.update_lead("CRM-LEAD-2", values)

    def test_a_lead_the_site_hides_is_neither_read_nor_changed(self):
        frappe.set_user(SAM)
        with self.assertRaisesRegex(frappe.ValidationError, "No permission"):
            api.update_lead("CRM-LEAD-3", {"conversion": "High"})
        self.assertNotIn("custom_conversion_possibility", self.lead("CRM-LEAD-3"))
        with self.assertRaisesRegex(frappe.ValidationError, "No permission"):
            api.get_lead_sheet("CRM-LEAD-3")

    def test_the_lead_page_reads_one_leads_sheet(self):
        frappe.set_user(SAM)
        sheet = api.get_lead_sheet("CRM-LEAD-1")
        self.assertEqual(
            (sheet["designation"], sheet["conversion"], sheet["visits"]),
            ("Operations manager", "Medium", 1),
        )


class TestExport(WeeklyLeadReportCase):
    def test_the_week_exports_in_the_template_columns(self):
        frappe.set_user(ADA)
        with patch.object(api, "send_xlsx") as send:
            api.export_report(FROM, TO)
        _, columns, rows, lines, filename = send.call_args.args
        labels = [c["label"] for c in columns]
        self.assertEqual(
            labels[:2], ["Name", "Contact Number"], "no salesperson column"
        )
        self.assertEqual(labels[-1], "Remarks")
        pacific = next(r for r in rows if r[0] == "Pacific Blue")
        self.assertEqual(pacific[labels.index("Requirement")], "Digital Marketing")
        self.assertEqual(pacific[labels.index("Quoted (Yes/No)")], "Yes")
        self.assertEqual(pacific[labels.index("Quoted (Value)")], "1,500.50 SAR")
        self.assertEqual(pacific[labels.index("Quotation Number")], "QTN-2")
        self.assertEqual(pacific[labels.index("Number of Visits This Week")], 1)
        self.assertEqual(pacific[labels.index("Future Follow-up Plan")], "Yes")
        self.assertIn("Everyone", lines)
        self.assertEqual(filename, f"lead-report-{FROM}-to-{TO}")
        self.assertTrue(
            frappe.db.exists(
                "Activity Log",
                {"subject": ["like", "Exported the lead report%"]},
            )
        )

    def test_a_salespersons_export_is_their_own(self):
        frappe.set_user(SAM)
        with patch.object(api, "send_xlsx") as send:
            api.export_report(FROM, TO, salesperson=SARA)
        _, columns, rows, lines, _ = send.call_args.args
        self.assertEqual(sorted(r[0] for r in rows), ["Oryx", "Pacific Blue"])
        self.assertIn("Sam Seller", lines)


class TestFilters(WeeklyLeadReportCase):
    def leads(self, **filters) -> list[str]:
        frappe.set_user(ADA)
        return sorted(r["lead"] for r in api.get_report(FROM, TO, **filters)["rows"])

    def test_each_filter_narrows_the_rows(self):
        self.assertEqual(self.leads(search="jabir"), ["CRM-LEAD-1"], "the contact")
        self.assertEqual(self.leads(search="5384"), ["CRM-LEAD-2"], "a number")
        self.assertEqual(self.leads(requirement="Digital"), ["CRM-LEAD-1"])
        self.assertEqual(self.leads(conversion="Medium"), ["CRM-LEAD-1"])
        self.assertEqual(self.leads(follow_up="Yes"), ["CRM-LEAD-1"])
        self.assertEqual(self.leads(quoted="Yes"), ["CRM-LEAD-1"])
        self.assertEqual(
            self.leads(quoted="No"), ["CRM-LEAD-2", "CRM-LEAD-3", "CRM-LEAD-5"]
        )

    def test_not_set_keeps_the_leads_with_the_field_empty(self):
        self.assertEqual(
            self.leads(conversion="not_set"), ["CRM-LEAD-2", "CRM-LEAD-3", "CRM-LEAD-5"]
        )

    def test_filters_add_up_and_the_people_stay_whole(self):
        frappe.set_user(ADA)
        week = api.get_report(FROM, TO, conversion="Medium", quoted="No")
        self.assertEqual(week["rows"], [])
        self.assertIn(SARA, [p["user"] for p in week["people"]], "for the picker")

    def test_the_file_holds_the_filtered_rows_and_says_so(self):
        frappe.set_user(ADA)
        with patch.object(api, "send_xlsx") as send:
            api.export_report(FROM, TO, requirement="Digital", quoted="Yes")
        _, _, rows, lines, _ = send.call_args.args
        self.assertEqual([r[0] for r in rows], ["Pacific Blue"])
        self.assertIn("Requirement: Digital Marketing", lines)
        self.assertIn("Quoted: Yes", lines)


class TestPeriod(WeeklyLeadReportCase):
    def test_any_period_reads_the_leads_updated_in_it(self):
        frappe.set_user(ADA)
        one_day = api.get_report("2026-11-21", "2026-11-21")
        self.assertEqual([r["lead"] for r in one_day["rows"]], ["CRM-LEAD-4"])
        both = api.get_report("2026-11-21", "2026-11-24")
        self.assertEqual(len(both["rows"]), 5)

    def test_no_dates_is_this_week(self):
        frappe.set_user(SAM)
        report = api.get_report()
        self.assertEqual(getdate(report["from_date"]), week_start())
        self.assertEqual((getdate(report["to_date"]) - week_start()).days, 6)

    def test_a_backwards_or_too_long_period_is_refused(self):
        frappe.set_user(SAM)
        with self.assertRaisesRegex(frappe.ValidationError, "after the to date"):
            api.get_report("2026-11-28", "2026-11-22")
        with self.assertRaisesRegex(frappe.ValidationError, "366 days"):
            api.get_report("2025-01-01", "2026-11-28")
