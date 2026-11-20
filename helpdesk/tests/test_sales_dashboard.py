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
