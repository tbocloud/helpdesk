from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk.api import sales_dashboard as api
from helpdesk.integrations.crm.leads import LeadsUnavailableError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    make_sales_employee,
)

MANAGER = "manager@salesdash.example"
SALES = "sales@salesdash.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
OVERVIEW = {
    "from_date": nowdate(),
    "to_date": nowdate(),
    "stale_days": 21,
    "totals": {"new": 11, "contacted": 1, "open": 2041, "won": 1},
    "pipeline": [{"stage": "New Lead", "type": "Open", "count": 1120}],
    "funnel": [{"step": "created", "count": 11, "rate": 100.0}],
    "ai": {"enabled": True, "high_intent": 4, "plan": {"rows": [{"name": "LD1"}]}},
}


def calling(user: str, called: int, reached: int, given: int = 50) -> dict:
    return {
        "user": user,
        "full_name": user,
        "given": given,
        "called": called,
        "reached": reached,
    }


class TestSalesDashboard(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(MANAGER, "Mira", "Manager")
        make_sales_employee(SALES, "Sia Sales")
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers.update(
            {
                "get_options": {"stages": [], "departments": []},
                "get_overview": OVERVIEW,
                "get_lead_analysis": {
                    "calling": [calling(SALES, 68, 30), calling(MANAGER, 5, 1)]
                },
                "get_my_calls": {"enabled": True, "today": {"called": 68}},
                "get_follow_up_counts": {"overdue": 3},
                "list_leads": {"rows": [{"name": "LD1"}], "total": 9},
                "get_call_batches_report": {
                    "people": [
                        {
                            "user": SALES,
                            "department": "StayVeX",
                            "batches": [
                                {
                                    "slot": "Afternoon",
                                    "starts_at": f"{nowdate()} 14:00:00",
                                    "size": 50,
                                    "called": 18,
                                },
                                {
                                    "slot": "Morning",
                                    "starts_at": f"{nowdate()} 10:00:00",
                                    "size": 50,
                                    "called": 50,
                                },
                            ],
                        }
                    ]
                },
            }
        )
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_team_page_is_cut_to_the_sales_team(self):
        frappe.set_user(MANAGER)
        page = api.get_team_dashboard(period="week", fresh=1)
        self.assertEqual(page["errors"], {})
        self.assertEqual(page["overview"]["totals"]["open"], 2041)
        self.assertEqual(page["overview"]["ai"]["high_intent"], 4)
        # the manager isn't a salesperson, so only Sia's row shows
        self.assertEqual(
            page["people"],
            [
                {
                    "user": SALES,
                    "full_name": SALES,
                    "given": 50,
                    "called": 68,
                    "contacted": 30,
                    "calls": 0,
                    "missed": 0,
                    "talk_seconds": 0,
                    "overdue": 0,
                }
            ],
        )
        days = page["week"]["days"]
        self.assertEqual(days[-1], nowdate())
        self.assertEqual(getdate(days[0]).weekday(), 0)
        self.assertEqual(page["week"]["people"][0]["called"], [68] * len(days))

    def test_batches_are_grouped_by_slot_in_the_order_they_start(self):
        frappe.set_user(MANAGER)
        page = api.get_team_dashboard(fresh=1)
        self.assertEqual(
            [(s["slot"], s["size"], s["called"]) for s in page["handed_out"]],
            [("Morning", 50, 50), ("Afternoon", 50, 18)],
        )

    def test_a_part_the_erp_site_refuses_leaves_the_rest(self):
        self.crm.lead_answers["get_call_batches_report"] = LeadsUnavailableError(
            "Only managers and department heads can open this."
        )
        frappe.set_user(MANAGER)
        page = api.get_team_dashboard(fresh=1)
        self.assertIsNone(page["handed_out"])
        self.assertIn("handed_out", page["errors"])
        self.assertTrue(page["people"])

    def test_a_bd_cannot_open_the_team_page(self):
        frappe.set_user(SALES)
        with self.assertRaises(frappe.PermissionError):
            api.get_team_dashboard()

    def test_a_bd_reads_their_own_day(self):
        frappe.set_user(SALES)
        page = api.get_my_dashboard(fresh=1)
        self.assertEqual(page["errors"], {})
        self.assertEqual(page["calls"]["today"], {"called": 68})
        self.assertEqual(page["month"]["totals"]["won"], 1)
        self.assertEqual(page["month"]["plan"], [{"name": "LD1"}])
        self.assertEqual(page["follow_ups"]["counts"]["overdue"], 3)
        # their own line only, never a teammate's
        (person,) = page["week"]["people"]
        self.assertEqual(person["user"], SALES)
        self.assertEqual(person["contacted"][-1], 30)
        overviews = [p for m, _post, p in self.crm.lead_calls if m == "get_overview"]
        self.assertEqual(overviews[0]["owner"], SALES)

    def test_sales_heads_and_managers_have_no_own_dashboard(self):
        for email, role in (
            ("head@salesdash.example", "Sales Head"),
            ("salesmanager@salesdash.example", "Sales Manager"),
        ):
            make_sales_employee(email, role, role, "Sales User")
            frappe.set_user(email)
            with self.assertRaises(frappe.PermissionError):
                api.get_my_dashboard()
            frappe.set_user("Administrator")

    def test_a_day_that_has_ended_is_read_once_an_hour(self):
        frappe.set_user(MANAGER)
        api.get_team_dashboard(fresh=1)
        first = [p for m, _post, p in self.crm.lead_calls if m == "get_lead_analysis"]
        self.crm.lead_calls.clear()
        api.get_team_dashboard(fresh=1)
        again = [p for m, _post, p in self.crm.lead_calls if m == "get_lead_analysis"]
        # the period's analysis and today are read again; earlier days come from the cache
        today = nowdate()
        self.assertTrue(all(p["from_date"] in (None, today) for p in again))
        self.assertEqual(len(first) - len(again), getdate(today).weekday())
        if getdate(today).weekday():
            yesterday = str(add_days(getdate(today), -1))
            self.assertIn(yesterday, [p["from_date"] for p in first])

    def test_a_department_and_source_reach_every_figure(self):
        frappe.set_user(MANAGER)
        api.get_team_dashboard(fresh=1)
        reads = [
            p
            for m, _post, p in self.crm.lead_calls
            if m in ("get_overview", "get_lead_analysis")
        ]
        # left out when not picked
        self.assertFalse(any("department" in p or "source" in p for p in reads))
        said = {"narrowed": {"department": "Elsewhere", "source": "Website"}}
        self.crm.lead_answers["get_overview"] = {**OVERVIEW, **said}
        self.crm.lead_answers["get_lead_analysis"] = {
            "calling": [calling(SALES, 4, 2)],
            **said,
        }
        self.crm.lead_calls.clear()
        page = api.get_team_dashboard(fresh=1, department="Elsewhere", source="Website")
        reads = [
            p
            for m, _post, p in self.crm.lead_calls
            if m in ("get_overview", "get_lead_analysis")
        ]
        # the overview, the period's calls and each day of the week
        self.assertGreaterEqual(len(reads), 3)
        self.assertTrue(
            all(
                (p["department"], p["source"]) == ("Elsewhere", "Website")
                for p in reads
            )
        )
        self.assertEqual(page["errors"], {})
        self.assertEqual(page["people"][0]["called"], 4)
        # the batches handed out are only StayVeX's
        self.assertEqual(page["handed_out"], [])

    def test_figures_the_erp_site_did_not_narrow_are_refused(self):
        # an older TBO Smart drops the arguments and answers with everyone's figures
        frappe.set_user(MANAGER)
        with self.assertRaises(LeadsUnavailableError):
            api.get_team_dashboard(fresh=1, source="Website")

    def test_the_period_before_is_the_same_days(self):
        # a running period is compared like for like, never with a whole one
        self.assertEqual(
            api.previous_bounds("today", "2026-11-25"),
            (getdate("2026-11-24"), getdate("2026-11-24")),
        )
        # a Wednesday: last week's Monday to Wednesday
        self.assertEqual(
            api.previous_bounds("week", "2026-11-25"),
            (getdate("2026-11-16"), getdate("2026-11-18")),
        )
        self.assertEqual(
            api.previous_bounds("month", "2026-11-25"),
            (getdate("2026-10-01"), getdate("2026-10-25")),
        )
        # 31 March against February: all of February, never into March
        self.assertEqual(
            api.previous_bounds("month", "2026-03-31"),
            (getdate("2026-02-01"), getdate("2026-02-28")),
        )

    def test_won_value_is_read_only_for_people_who_won(self):
        self.crm.lead_answers["get_overview"] = {
            **OVERVIEW,
            "totals": {**OVERVIEW["totals"], "won_value": 90000},
            "by_owner": [
                {"user": SALES, "full_name": "Sia Sales", "won": 2},
                {"user": MANAGER, "full_name": "Mira", "won": 4},
            ],
        }
        frappe.set_user(MANAGER)
        page = api.get_team_dashboard(period="month", fresh=1)
        # only the sales team, and only those with a won lead are asked
        self.assertEqual(
            page["revenue"],
            [{"user": SALES, "full_name": "Sia Sales", "won": 2, "won_value": 90000}],
        )
        owners = [
            p["owner"] for m, _post, p in self.crm.lead_calls if m == "get_overview"
        ]
        self.assertIn(SALES, owners)
        self.assertNotIn(MANAGER, owners)
        # the same days of last month, for the comparison
        previous = page["previous"]
        self.assertEqual(previous["from_date"], str(api.previous_bounds("month")[0]))

    def test_one_persons_view_has_no_podium(self):
        frappe.set_user(MANAGER)
        page = api.get_team_dashboard(owner=SALES, fresh=1)
        self.assertIsNone(page["revenue"])
        self.assertNotIn("revenue", page["errors"])

    def test_money_is_left_out_when_narrowed(self):
        self.crm.lead_answers["get_proposal_money"] = {
            "currency": "INR",
            "totals": {"advances": 5000, "to_collect": 12000, "overdue": 2000},
        }
        frappe.set_user(MANAGER)
        page = api.get_team_dashboard(fresh=1)
        self.assertEqual(page["money"]["advances"], 5000)
        self.assertEqual(page["money"]["to_collect"], 12000)
        said = {"narrowed": {"department": "Elsewhere"}}
        self.crm.lead_answers["get_overview"] = {**OVERVIEW, **said}
        self.crm.lead_answers["get_lead_analysis"] = {"calling": [], **said}
        self.crm.lead_calls.clear()
        page = api.get_team_dashboard(fresh=1, department="Elsewhere")
        # the ERP site doesn't count money per department, so it isn't asked
        self.assertIsNone(page["money"])
        self.assertFalse(
            [m for m, _post, _p in self.crm.lead_calls if m == "get_proposal_money"]
        )
