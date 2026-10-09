import json
from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import team_dashboard as td
from helpdesk.content_team import ensure_role
from helpdesk.test_utils import (
    call_team_dashboard,
    get_reminder_messages,
    hold_commits,
    log_hours,
    make_assignment,
    make_department,
    make_done_task,
    make_project,
    make_task,
    make_tasky_user,
)

# a week far from the real calendar, so only this test's records fall in it
TODAY = date(2031, 3, 11)  # a Tuesday
WEEK = ("2031-03-10", "2031-03-16")
ANU = "anu.menon@tbo-dash.test"
RAHUL = "rahul.nair@tbo-dash.test"
DEEPA = "deepa.varma@tbo-dash.test"
SANA = "sana.dm@tbo-dash.test"


def stats(**values) -> dict:
    return {**td.blank(), **values}


class TestScoring(FrappeTestCase):
    def test_on_time_delivery_beats_long_hours(self):
        on_time = stats(
            tasks=5, dated=5, on_time=5, weight=5, weight_on_time=5, hours=10
        )
        late = stats(tasks=5, dated=5, weight=5, hours=200)
        self.assertGreater(
            td.score(on_time, "week")["score"], td.score(late, "week")["score"]
        )

    def test_hours_alone_score_nothing(self):
        result = td.score(stats(hours=120), "week")
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["eligible"])

    def test_hours_are_capped_at_a_tenth_of_delivery(self):
        result = td.score(stats(tasks=4, dated=4, weight=4, hours=500), "week")
        hours = next(b for b in result["breakdown"] if b["key"] == "hours")
        self.assertEqual(hours["points"], 0.2)

    def test_minimum_activity_before_anyone_is_champion(self):
        one = stats(tasks=1, dated=1, on_time=1, weight=3, weight_on_time=3)
        self.assertFalse(td.score(one, "week")["eligible"])
        three = stats(tasks=3, dated=3, on_time=3, weight=3, weight_on_time=3)
        self.assertTrue(td.score(three, "week")["eligible"])
        self.assertFalse(td.score(three, "month")["eligible"])

    def test_overdue_and_slips_cost_points(self):
        clean = stats(tasks=3, dated=3, on_time=3, weight=3, weight_on_time=3)
        behind = {**clean, "overdue": 2, "slips": 2}
        self.assertEqual(
            td.score(clean, "week")["score"] - td.score(behind, "week")["score"], 3
        )
        ranked = td.rank({"behind": behind, "clean": clean}, "week")
        self.assertEqual(td.champion_of(ranked)["user"], "clean")

    def test_reasons_explain_the_score(self):
        result = td.score(
            stats(tasks=3, key=1, dated=3, on_time=3, weight=4, weight_on_time=4),
            "week",
        )
        self.assertEqual(len(result["reasons"]), 2)
        self.assertIn("Tasks done: 3", result["reasons"][0])


class TestPeriods(FrappeTestCase):
    def test_boundaries(self):
        self.assertEqual(
            td.period_bounds("week", "2026-10-11"),
            (date(2026, 10, 5), date(2026, 10, 11)),
        )
        self.assertEqual(
            td.period_bounds("quarter", "2026-11-15"),
            (date(2026, 10, 1), date(2026, 12, 31)),
        )
        self.assertEqual(
            td.period_bounds("half", "2026-06-30"),
            (date(2026, 1, 1), date(2026, 6, 30)),
        )
        self.assertEqual(
            td.period_bounds("half", "2026-07-01"),
            (date(2026, 7, 1), date(2026, 12, 31)),
        )
        self.assertEqual(
            td.period_bounds("year", "2026-02-28"),
            (date(2026, 1, 1), date(2026, 12, 31)),
        )

    def test_comparison_stops_at_the_same_point(self):
        start, end = td.period_bounds("week", TODAY)
        self.assertEqual(
            td.comparison_bounds("week", start, end, TODAY),
            (date(2031, 3, 3), date(2031, 3, 4)),
        )
        start, end = td.period_bounds("quarter", "2026-12-31")
        self.assertEqual(
            td.comparison_bounds("quarter", start, end, "2026-12-31"),
            (date(2026, 7, 1), date(2026, 9, 30)),
        )


class TestTeamDashboard(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        ensure_role()
        frappe.cache.delete_keys(f"{td.CACHE_PREFIX}_")
        make_department("ERP")
        make_department("Digital")
        make_tasky_user(ANU, "Anu Menon")
        make_tasky_user(RAHUL, "Rahul Nair")
        make_tasky_user(DEEPA, "Deepa Varma", ("Digital Marketing Head",))
        make_tasky_user(SANA, "Sana Rafeeq", ("DM Employee",))
        self.project = make_project(
            "Kerala Spices ERP rollout",
            members=[(ANU, "Developer"), (RAHUL, "Developer")],
        ).name
        frappe.db.set_value("Project", self.project, "custom_department", "ERP")
        # Anu: three tasks done on time, one of them key
        for i, day in enumerate(("2031-03-10", "2031-03-10", "2031-03-11")):
            make_done_task(
                self.project,
                f"Configure GST invoice print format {i}",
                ANU,
                day,
                due="2031-03-12",
                is_key=int(i == 0),
            )
        # Rahul: one task done late, and one overdue
        make_done_task(
            self.project, "Migrate opening stock", RAHUL, "2031-03-11", due="2031-03-05"
        )
        overdue = make_task(
            self.project, "Bank reconciliation import", "2031-03-09"
        ).name
        make_assignment("Task", overdue, RAHUL)
        log_hours(ANU, self.project, 5, "2031-03-10")
        log_hours(RAHUL, self.project, 30, "2031-03-11")

    def test_people_departments_and_projects(self):
        data = call_team_dashboard(
            "Administrator", TODAY, period="week", department="ERP"
        )
        self.assertTrue(data["access"]["can_refresh"])
        people = {p["user"]: p for p in data["people"]}
        self.assertEqual(people[ANU]["tasks"], 3)
        self.assertEqual(people[ANU]["key"], 1)
        self.assertEqual(people[ANU]["on_time_pct"], 100)
        self.assertEqual(people[ANU]["hours"], 5)
        self.assertEqual(people[RAHUL]["on_time_pct"], 0)
        self.assertEqual(people[RAHUL]["overdue"], 1)
        self.assertEqual(people[RAHUL]["hours"], 30)
        # thirty hours don't beat three tasks on time
        self.assertEqual(data["champion"]["user"], ANU)
        self.assertTrue(data["champion"]["breakdown"])
        self.assertEqual(data["summary"]["tasks"], 4)

        project = next(p for p in data["projects"] if p["project"] == self.project)
        self.assertEqual(project["members"], 2)
        self.assertEqual((project["done"], project["total"]), (4, 5))
        self.assertEqual(project["contributors"][0]["user"], ANU)
        self.assertEqual(project["hours"], 35)

        overall = call_team_dashboard("Administrator", TODAY, period="week")
        erp = next(d for d in overall["departments"] if d["department"] == "ERP")
        self.assertEqual(erp["tasks"], 4)
        self.assertEqual(erp["champion"]["user"], ANU)

    def test_plain_agent_sees_every_department_and_person(self):
        # everyone sees the whole scoreboard, so the team can compete
        data = call_team_dashboard(RAHUL, TODAY, period="week")
        self.assertFalse(data["access"]["can_refresh"])
        self.assertIn("ERP", data["access"]["departments"])
        people = {p["user"]: p for p in data["people"]}
        self.assertEqual(people[ANU]["tasks"], 3)
        self.assertEqual(people[RAHUL]["overdue"], 1)
        self.assertEqual(data["champion"]["user"], ANU)
        self.assertTrue(data["champion"]["breakdown"])
        erp = next(d for d in data["departments"] if d["department"] == "ERP")
        self.assertEqual(erp["champion"]["user"], ANU)
        self.assertIn(self.project, [p["project"] for p in data["projects"]])

        erp_only = call_team_dashboard(DEEPA, TODAY, period="week", department="ERP")
        self.assertIn(ANU, [p["user"] for p in erp_only["people"]])

    def test_only_managers_refresh_the_analysis(self):
        for user in (RAHUL, DEEPA):
            self.assertRaises(
                frappe.PermissionError,
                call_team_dashboard,
                user,
                TODAY,
                "refresh_analysis",
                period="week",
            )

    def test_hidden_department_stays_hidden(self):
        data = call_team_dashboard(SANA, TODAY, period="week")
        self.assertNotIn("ERP", data["access"]["departments"])
        self.assertNotIn("ERP", [d["department"] for d in data["departments"]])
        people = {p["user"]: p for p in data["people"]}
        self.assertEqual(people.get(ANU, {}).get("tasks", 0), 0)
        # the whole team's stored history and analysis include ERP
        self.assertEqual(data["history"], [])
        self.assertEqual(data["analysis"], {"status": "none"})
        self.assertRaises(
            frappe.PermissionError,
            call_team_dashboard,
            SANA,
            TODAY,
            period="week",
            department="ERP",
        )

    def test_champion_is_kept_and_announced_once(self):
        with patch("helpdesk.ai_suggestion.is_ai_configured", return_value=False):
            td.clear_cache()
            td.close_period("week", *WEEK)
            td.close_period("week", *WEEK)
        name = frappe.db.get_value(
            "HD Team Champion",
            {"period_type": "Week", "period_start": WEEK[0], "department": "ERP"},
        )
        record = frappe.get_doc("HD Team Champion", name)
        self.assertEqual(record.user, ANU)
        self.assertEqual(json.loads(record.analysis)["status"], "unavailable")
        self.assertEqual(len(get_reminder_messages(ANU, name)), 1)

        history = call_team_dashboard(
            "Administrator", "2031-03-18", period="week", department="ERP"
        )["history"]
        self.assertEqual(history[0]["user"], ANU)
        self.assertEqual(history[0]["start"], WEEK[0])

    def test_ai_failure_leaves_the_champion(self):
        with (
            patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True),
            patch.object(td, "call_haiku", side_effect=RuntimeError("provider down")),
        ):
            td.clear_cache()
            td.close_period("week", *WEEK)
        record = frappe.get_doc(
            "HD Team Champion",
            {"period_type": "Week", "period_start": WEEK[0], "department": "ERP"},
        )
        self.assertEqual(record.user, ANU)
        self.assertFalse(record.generated_by_ai)

    def test_refreshed_analysis_keeps_only_known_numbers(self):
        answer = {
            "response": {
                "summary": "Anu Menon is the champion with 3 tasks done, all on time.",
                "risks": [
                    "Rahul Nair has 1 task overdue now.",
                    "The team closed 987 tickets.",
                ],
                "needs_help": ["Rahul Nair: 1 task overdue."],
            }
        }
        with (
            patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True),
            patch.object(td, "call_haiku", return_value=answer),
        ):
            result = call_team_dashboard(
                "Administrator",
                TODAY,
                "refresh_analysis",
                period="week",
                department="ERP",
            )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["risks"], ["Rahul Nair has 1 task overdue now."])
        data = call_team_dashboard(
            "Administrator", TODAY, period="week", department="ERP"
        )
        self.assertTrue(data["analysis"]["current"])
        self.assertIn("Anu Menon", data["analysis"]["summary"])
