from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate, nowdate

from helpdesk.api import sales_targets as api
from helpdesk.integrations.crm.leads import LeadsUnavailableError
from helpdesk.sales_targets import measured
from helpdesk.test_utils import (
    FakeCRM,
    enable_leads,
    hold_commits,
    make_presales_executive,
    make_sales_head,
    make_sales_target,
)

HEAD = "head@targets.example"
PERSON = "presales@targets.example"
OTHER = "other.presales@targets.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
THIS_MONTH = getdate(nowdate()).strftime("%Y-%m")
NEXT_MONTH = add_months(getdate(nowdate()), 1).strftime("%Y-%m")

CRITERIA = [
    {
        "criterion": "Target Amount",
        "value_type": "Amount",
        "target": 500000,
        "measure": "won_value",
    },
    {
        "criterion": "Quality Target",
        "value_type": "Percent",
        "target": 20,
        "measure": "meeting_rate",
    },
    {
        "criterion": "Client Meeting",
        "value_type": "Number",
        "target": 10,
        "measure": "meetings",
    },
    {
        "criterion": "Sales KPI",
        "value_type": "Text",
        "target": "3 case studies published",
    },
]
TOTALS = {
    "won_value": 120000,
    "meetings": 7,
    "contacted": 40,
    "quotations_sent": 3,
    "won": 2,
    "lost": 2,
    "new": 15,
}


class TestSalesTargetProgress(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_sales_head(HEAD, "Hana Head")
        make_presales_executive(PERSON, "Priya Presales")
        make_presales_executive(OTHER, "Omar Presales")
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["get_overview"] = {"totals": TOTALS}
        self.crm.lead_answers["get_proposal_money"] = {"totals": {"advances": 50000}}
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(HEAD)
        make_sales_target(PERSON, THIS_MONTH, CRITERIA)

    def test_each_measure_reads_its_figure_and_rates_carry_what_they_divide(self):
        money = {"advances": 50000}
        self.assertEqual(measured("won_value", TOTALS, money)["achieved"], 120000)
        self.assertEqual(measured("collected", TOTALS, money)["achieved"], 50000)
        self.assertEqual(measured("proposals", TOTALS, money)["achieved"], 3)
        self.assertEqual(measured("new_leads", TOTALS, money)["achieved"], 15)
        self.assertEqual(
            measured("meeting_rate", TOTALS, money),
            {"achieved": 17.5, "parts": {"meetings": 7, "contacted": 40}},
        )
        self.assertEqual(measured("win_rate", TOTALS, money)["achieved"], 50.0)
        # nothing to divide by: no rate rather than 0%
        self.assertIsNone(measured("meeting_rate", {}, money)["achieved"])

    def test_the_person_reads_their_month_counted_from_their_own_leads(self):
        frappe.set_user(PERSON)
        progress = api.get_progress(THIS_MONTH, fresh=1)
        self.assertEqual(progress["state"], "counted")
        self.assertEqual(progress["criteria"]["Client Meeting"]["achieved"], 7)
        self.assertEqual(progress["criteria"]["Quality Target"]["achieved"], 17.5)
        self.assertNotIn("Sales KPI", progress["criteria"])
        ((method, _post, params),) = self.crm.lead_calls
        self.assertEqual(method, "get_overview")
        self.assertEqual(
            (params["acting_user"], params["owner"], params["period"]),
            (PERSON, PERSON, "custom"),
        )
        self.assertEqual(params["from_date"], f"{THIS_MONTH}-01")
        self.assertEqual(params["to_date"], nowdate())

    def test_money_collected_is_read_only_when_a_target_counts_it(self):
        criteria = [{**CRITERIA[0], "measure": "collected"}]
        make_sales_target(PERSON, THIS_MONTH, criteria)
        progress = api.get_progress(THIS_MONTH, employee=PERSON, fresh=1)
        self.assertEqual(progress["criteria"]["Target Amount"]["achieved"], 50000)
        self.assertIn("get_proposal_money", [m for m, _p, _a in self.crm.lead_calls])

    def test_a_month_not_begun_counts_nothing(self):
        make_sales_target(PERSON, NEXT_MONTH, CRITERIA)
        progress = api.get_progress(NEXT_MONTH, employee=PERSON)
        self.assertEqual(progress, {"state": "not_started"})
        self.assertEqual(self.crm.lead_calls, [])

    def test_an_erp_refusal_is_said_on_the_page_not_raised(self):
        self.crm.lead_answers["get_overview"] = LeadsUnavailableError("no sales role")
        progress = api.get_progress(THIS_MONTH, employee=PERSON, fresh=1)
        self.assertEqual(progress["state"], "unavailable")
        self.assertTrue(progress["reason"])

    def test_only_a_head_reads_someone_elses_progress(self):
        frappe.set_user(OTHER)
        with self.assertRaises(frappe.PermissionError):
            api.get_progress(THIS_MONTH, employee=PERSON)
        frappe.set_user(HEAD)
        team = api.get_team_progress(THIS_MONTH, fresh=1)
        self.assertEqual(list(team), [PERSON])

    def test_a_measure_must_fit_the_value_type(self):
        wrong = [{**CRITERIA[2], "measure": "won_value"}]
        with self.assertRaises(frappe.ValidationError):
            make_sales_target(PERSON, THIS_MONTH, wrong)


class TestSalesKPI(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_sales_head(HEAD, "Hana Head")
        make_presales_executive(PERSON, "Priya Presales")
        frappe.set_user(HEAD)
        make_sales_target(PERSON, THIS_MONTH, CRITERIA)

    def kpi(self, target):
        return next(c for c in target["criteria"] if c["criterion"] == "Sales KPI")

    def test_the_person_marks_it_done_and_the_head_confirms(self):
        frappe.set_user(PERSON)
        kpi = self.kpi(
            api.mark_kpi_done(THIS_MONTH, "Sales KPI", 1, "Published three on the blog")
        )
        self.assertEqual(
            (kpi["kpi_status"], kpi["kpi_note"]),
            ("Done", "Published three on the blog"),
        )
        frappe.set_user(HEAD)
        target = api.confirm_kpi(THIS_MONTH, PERSON, "Sales KPI", 1)
        self.assertEqual(self.kpi(target)["kpi_confirmed_by"], HEAD)
        # ticking off and confirming leave the assigner as it was
        self.assertEqual(target["assigned_by"], HEAD)
        frappe.set_user(PERSON)
        with self.assertRaises(frappe.ValidationError):
            api.mark_kpi_done(THIS_MONTH, "Sales KPI", 0)

    def test_only_a_kpi_marked_done_can_be_confirmed(self):
        with self.assertRaises(frappe.ValidationError):
            api.confirm_kpi(THIS_MONTH, PERSON, "Sales KPI", 1)
        with self.assertRaises(frappe.ValidationError):
            api.confirm_kpi(THIS_MONTH, PERSON, "Client Meeting", 1)

    def test_reassigning_keeps_a_kpi_done_unless_it_was_reworded(self):
        frappe.set_user(PERSON)
        api.mark_kpi_done(THIS_MONTH, "Sales KPI", 1)
        frappe.set_user(HEAD)
        make_sales_target(PERSON, THIS_MONTH, CRITERIA)
        mine = api.targets_for(getdate(f"{THIS_MONTH}-01"), [PERSON])[PERSON]
        self.assertEqual(self.kpi(mine)["kpi_status"], "Done")
        reworded = [*CRITERIA[:3], {**CRITERIA[3], "target": "5 case studies"}]
        make_sales_target(PERSON, THIS_MONTH, reworded)
        mine = api.targets_for(getdate(f"{THIS_MONTH}-01"), [PERSON])[PERSON]
        self.assertEqual(self.kpi(mine)["kpi_status"], "")
