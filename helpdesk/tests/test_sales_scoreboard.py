from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import team_dashboard as td
from helpdesk.helpdesk.doctype.hd_department.hd_department import (
    ensure_default_departments,
)
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRM,
    call_team_dashboard,
    enable_leads,
    hold_commits,
    make_done_task,
    make_project,
    make_tasky_user,
    sales_person,
    score_stats,
)

TODAY = date(2031, 3, 11)  # a Tuesday, far from the real calendar
WEEK = ("2031-03-10", "2031-03-16")
NIYA = "niya.sales@tbo-sales.test"
JOEL = "joel.sales@tbo-sales.test"
DEV = "dev.web@tbo-sales.test"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class TestSalesScore(FrappeTestCase):
    def test_sales_work_scores_and_qualifies_like_tasks(self):
        busy = score_stats(
            sales_contacted=8, sales_meetings=2, sales_proposals=1, sales_won=1
        )
        result = td.score(busy, "week")
        parts = {b["key"]: b["points"] for b in result["breakdown"]}
        self.assertEqual(parts["sales_activity"], 2)
        self.assertEqual((parts["sales_meetings"], parts["sales_proposals"]), (3, 1.5))
        self.assertEqual(parts["sales_won"], 4)
        self.assertTrue(result["eligible"])
        self.assertIn("Meetings with minutes: 2", " ".join(result["reasons"]))
        # a few calls alone don't make a champion
        self.assertFalse(td.score(score_stats(sales_contacted=4), "week")["eligible"])

    def test_the_deal_size_counts_but_is_capped_per_win(self):
        small = score_stats(sales_won=1, sales_won_value=100000)
        huge = score_stats(sales_won=1, sales_won_value=50000000)
        self.assertEqual(td.score(small, "week")["score"], 5)
        self.assertEqual(td.score(huge, "week")["score"], 8)

    def test_pending_minutes_and_overdue_follow_ups_cost_points(self):
        clean = score_stats(sales_meetings=2, sales_proposals=1)
        behind = {**clean, "sales_mom_pending": 2, "sales_follow_ups_overdue": 2}
        self.assertEqual(
            td.score(clean, "week")["score"] - td.score(behind, "week")["score"], 2
        )


class TestSalesOnTheScoreboard(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(td.clear_cache)
        ensure_default_departments()
        make_tasky_user(NIYA, "Niya Thomas")
        make_tasky_user(JOEL, "Joel Mathew")
        make_tasky_user(DEV, "Dev Anand")
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["get_sales_activity"] = {
            "currency": "INR",
            "people": [
                sales_person(
                    NIYA,
                    contacted=10,
                    moms_submitted=2,
                    quotations_sent=2,
                    won=1,
                    won_value=300000,
                    new=4,
                ),
                sales_person(JOEL, contacted=3, mom_pending=2),
            ],
        }
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Dev builds websites and also follows up a lead or two
        project = make_project("Spice Route website", members=[(DEV, "Developer")]).name
        frappe.db.set_value("Project", project, "custom_department", "Web Development")
        for i in range(3):
            make_done_task(project, f"Build page {i}", DEV, WEEK[0], due=WEEK[1])

    def test_salespeople_rank_in_crm_under_sales(self):
        data = call_team_dashboard("Administrator", TODAY, period="week")
        self.assertEqual(data["sales"]["status"], "ok")
        self.assertEqual(data["sales"]["department"], "CRM")
        # the CRM site is asked as the hub, for everyone, with the page's period
        ((method, post, params),) = {
            (m, p, tuple(sorted(a.items())))
            for m, p, a in self.crm.lead_calls
            if a.get("from_date") == WEEK[0]
        }
        self.assertEqual((method, post), ("get_sales_activity", False))
        self.assertNotIn("acting_user", dict(params))

        rows = data["departments"]
        sales_group = next(
            r for r in rows if r["department"] == "Sales" and r["kind"] == "group"
        )
        crm = next(r for r in rows if r["department"] == "CRM")
        self.assertEqual(crm["parent"], "Sales")
        self.assertEqual(crm["champion"]["user"], NIYA)
        self.assertEqual(sales_group["champion"]["user"], NIYA)
        self.assertEqual(crm["sales"]["won"], 1)
        self.assertEqual(crm["sales"]["conversion"], 25)
        web = next(r for r in rows if r["department"] == "Web Development")
        self.assertEqual((web["parent"], web["tasks"]), ("Digital", 3))

        people = {p["user"]: p for p in data["people"]}
        self.assertEqual(people[NIYA]["department"], "CRM")
        self.assertEqual(people[NIYA]["sales"]["contacted"], 10)
        self.assertIsNone(people[DEV]["sales"])
        # Joel's two meetings without minutes cost him more than his calls earn
        self.assertLess(people[JOEL]["score"], 0)
        self.assertIn("sales", data["rules"])

    def test_closed_periods_store_the_crm_champion(self):
        with patch("helpdesk.ai_suggestion.is_ai_configured", return_value=False):
            td.clear_cache()
            td.close_period("week", *WEEK)
        self.assertEqual(
            frappe.get_doc("HD Team Champion", f"week-{WEEK[0]}-crm").user, NIYA
        )
        self.assertEqual(
            frappe.get_doc("HD Team Champion", f"week-{WEEK[0]}-group_sales").user, NIYA
        )

    def test_an_unreachable_erp_site_leaves_the_rest_working(self):
        self.crm.lead_error = CRMError("down", None)
        data = call_team_dashboard("Administrator", TODAY, period="week")
        self.assertEqual(data["sales"]["status"], "unavailable")
        self.assertIn("Couldn't reach the ERP site", data["sales"]["message"])
        crm = next(r for r in data["departments"] if r["department"] == "CRM")
        self.assertIsNone(crm["sales"])
        self.assertIsNone(crm["champion"])
        web = next(
            r for r in data["departments"] if r["department"] == "Web Development"
        )
        self.assertEqual(web["tasks"], 3)
        self.assertEqual(data["champion"]["user"], DEV)

    def test_nothing_is_asked_while_leads_are_off(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        data = call_team_dashboard("Administrator", TODAY, period="week")
        self.assertEqual(data["sales"]["status"], "off")
        self.assertEqual(self.crm.lead_calls, [])
