import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import home_plan
from helpdesk.test_utils import (
    call_as_user,
    hold_commits,
    make_member_day,
    make_project,
    make_tasky_user,
)

LEAD = ("lead.plan@home-plan.example", "Asha Kurian")
MEMBER = ("member.plan@home-plan.example", "Gayathri Sumithran")
TEAMMATE = ("mate.plan@home-plan.example", "Vivek Nair")
HOME = "helpdesk.api.home.get_home"
PLAN = "helpdesk.api.home.get_action_plan"


def names(section: dict) -> list[str]:
    return [i["name"] for i in section["items"]]


class TestHomePlan(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        for user in (LEAD, MEMBER, TEAMMATE):
            make_tasky_user(*user)
            self.addCleanup(home_plan.clear_cache, user[0])
            home_plan.clear_cache(user[0])
        self.project = make_project(
            "Kerala Traders - ERP rollout",
            members=[(MEMBER[0], "Developer"), (TEAMMATE[0], "Developer")],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])
        self.tasks = make_member_day(self.project, MEMBER[0], LEAD[0], TEAMMATE[0])

    def day(self, user=MEMBER):
        return call_as_user(user[0], HOME)["day"]

    def plan(self, user=MEMBER, **kwargs):
        return call_as_user(user[0], PLAN, **kwargs)

    def test_open_work_is_never_all_clear(self):
        """Regression: eight open tasks, none due today but one, showed "All clear"."""
        summary = self.day()["summary"]

        self.assertEqual(summary["open"], 8)
        self.assertEqual(summary["overdue"], 1)
        self.assertEqual(summary["due_today"], 1)
        self.assertEqual(summary["on_hold"], 2)
        self.assertEqual(summary["in_progress"], 2)
        self.assertEqual(summary["projects"], 1)

    def test_every_open_task_lands_in_one_section_in_priority_order(self):
        t = self.tasks
        day = self.day()

        self.assertEqual(
            names(day["close_first"]), [t["overdue"], t["due_today"], t["key_working"]]
        )
        self.assertEqual(names(day["in_progress"]), [t["paused"]])
        # the longest wait first
        self.assertEqual(names(day["waiting"]), [t["held_long"], t["held_short"]])
        self.assertEqual(names(day["coming_up"]), [t["coming_up"]])
        self.assertEqual(names(day["no_date"]), [t["no_date"]])
        self.assertEqual(names(day["given_out"]), [t["given_out"]])

        overdue = day["close_first"]["items"][0]
        self.assertEqual(overdue["assigned_by_name"], LEAD[1])
        self.assertEqual(day["close_first"]["items"][2]["timer"], "running")
        self.assertEqual(day["in_progress"]["items"][0]["timer"], "paused")
        held = day["waiting"]["items"][0]
        self.assertEqual(held["hold_reason"], "Waiting on customer")
        self.assertEqual(held["hold_note"], "Asked for the bank statement")
        self.assertEqual(held["hold_by_name"], MEMBER[1])
        self.assertEqual(held["hold_days"], 3)
        self.assertEqual(day["given_out"]["items"][0]["assignee_names"], [TEAMMATE[1]])

    def test_a_member_sees_only_her_own_numbers(self):
        day = self.day()

        everything = [
            i["name"] for key, s in day.items() if key != "summary" for i in s["items"]
        ]
        self.assertNotIn(self.tasks["teammate_own"], everything)
        project = day["projects"]["items"][0]
        self.assertEqual(project["name"], self.project)
        self.assertEqual((project["open"], project["overdue"]), (8, 1))
        self.assertIsNone(project["team_open"])

        facts = json.dumps(home_plan.plan_facts(day))
        self.assertNotIn("Fix the payroll script", facts)

    def test_the_lead_also_sees_the_project_totals(self):
        project = self.day(LEAD)["projects"]["items"][0]

        self.assertEqual((project["open"], project["overdue"]), (0, 0))
        # the member's eight, the one she gave out and the teammate's own
        self.assertEqual(project["team_open"], 10)
        self.assertEqual(project["team_overdue"], 3)

    @patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True)
    @patch("helpdesk.home_plan.call_haiku", side_effect=TimeoutError("provider down"))
    def test_plan_falls_back_to_the_rules_when_the_ai_fails(self, haiku, _configured):
        self.day()

        plan = self.plan()

        self.assertEqual(plan["source"], "rules")
        self.assertEqual(plan["reason"], "The AI couldn't be reached.")
        self.assertEqual(len(plan["steps"]), 5)
        self.assertIn("Fix the GST return", plan["steps"][0]["text"])
        self.assertEqual(plan["steps"][0]["task"], self.tasks["overdue"])
        # a failure isn't retried on every page load
        self.plan()
        self.assertEqual(haiku.call_count, 1)

    @patch("helpdesk.ai_suggestion.is_ai_configured", return_value=False)
    def test_plan_says_when_ai_is_off(self, _configured):
        plan = self.plan()

        self.assertEqual(plan["source"], "rules")
        self.assertEqual(plan["reason"], "AI isn't set up on this hub.")
        self.assertTrue(plan["steps"])

    @patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True)
    @patch("helpdesk.home_plan.call_haiku")
    def test_ai_steps_with_invented_numbers_are_dropped(self, haiku, _configured):
        haiku.return_value = {
            "response": {
                "steps": [
                    "1. Close Fix the GST return first, 2 days overdue.",
                    "Finish Post the Onam reel today.",
                    "Resume Draft the user manual and spend 4.5 hours on it.",
                    "Follow up with the customer on Reconcile the bank feed.",
                ]
            }
        }

        plan = self.plan()

        self.assertEqual(plan["source"], "ai")
        self.assertEqual(
            [s["text"] for s in plan["steps"]],
            [
                "Close Fix the GST return first, 2 days overdue.",
                "Finish Post the Onam reel today.",
                "Follow up with the customer on Reconcile the bank feed.",
            ],
        )

    @patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True)
    @patch("helpdesk.home_plan.call_haiku")
    def test_plan_is_cached_for_the_day_and_refresh_is_rate_limited(
        self, haiku, _configured
    ):
        haiku.return_value = {
            "response": {
                "steps": [
                    "Close Fix the GST return first.",
                    "Finish Post the Onam reel today.",
                    "Follow up on Reconcile the bank feed.",
                ]
            }
        }
        first = self.plan()
        again = self.plan()

        self.assertEqual(haiku.call_count, 1)
        self.assertEqual(again["steps"], first["steps"])
        self.assertFalse(again["stale"])

        # her work changed: the cached plan says so until she refreshes it
        frappe.db.set_value("Task", self.tasks["due_today"], "status", "Completed")
        self.assertTrue(self.plan()["stale"])

        refreshed = self.plan(refresh=True)
        self.assertEqual(haiku.call_count, 2)
        self.assertFalse(refreshed["stale"])
        with self.assertRaises(frappe.ValidationError):
            self.plan(refresh=True)

    def test_nothing_open_means_no_plan(self):
        quiet = ("quiet.plan@home-plan.example", "Nila Menon")
        make_tasky_user(*quiet)
        self.addCleanup(home_plan.clear_cache, quiet[0])

        day = self.day(quiet)
        plan = self.plan(quiet)

        self.assertEqual(day["summary"]["open"], 0)
        self.assertEqual(plan["steps"], [])
        self.assertIsNone(plan["reason"])
