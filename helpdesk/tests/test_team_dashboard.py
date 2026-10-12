import json
from datetime import date, timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import team_dashboard as td
from helpdesk.api import departments
from helpdesk.content_team import ensure_role
from helpdesk.tasky.permissions import department_heads
from helpdesk.test_utils import (
    call_team_dashboard,
    get_reminder_messages,
    hold_commits,
    log_hours,
    make_assignment,
    make_department,
    make_done_task,
    make_done_ticket_task,
    make_project,
    make_self_made_done_task,
    make_task,
    make_tasky_user,
    make_team_champion,
    rate_task_as,
    score_stats,
    set_department_heads_as,
)

# a week far from the real calendar, so only this test's records fall in it
TODAY = date(2031, 3, 11)  # a Tuesday
WEEK = ("2031-03-10", "2031-03-16")
ANU = "anu.menon@tbo-dash.test"
RAHUL = "rahul.nair@tbo-dash.test"
DEEPA = "deepa.varma@tbo-dash.test"
SANA = "sana.dm@tbo-dash.test"
KIRAN = "kiran.erp@tbo-dash.test"
MANAGER = "meera.manager@tbo-dash.test"
DAY = "2031-03-10"


class TestScoring(FrappeTestCase):
    def test_on_time_delivery_beats_long_hours(self):
        on_time = score_stats(
            tasks=5, dated=5, on_time=5, weight=5, weight_on_time=5, hours=10
        )
        late = score_stats(tasks=5, dated=5, weight=5, hours=200)
        self.assertGreater(
            td.score(on_time, "week")["score"], td.score(late, "week")["score"]
        )

    def test_hours_alone_score_nothing(self):
        result = td.score(score_stats(hours=120), "week")
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["eligible"])

    def test_hours_are_capped_at_a_tenth_of_delivery(self):
        result = td.score(score_stats(tasks=4, dated=4, weight=4, hours=500), "week")
        hours = next(b for b in result["breakdown"] if b["key"] == "hours")
        self.assertEqual(hours["points"], 0.2)

    def test_minimum_activity_before_anyone_is_champion(self):
        one = score_stats(tasks=1, dated=1, on_time=1, weight=3, weight_on_time=3)
        self.assertFalse(td.score(one, "week")["eligible"])
        three = score_stats(tasks=3, dated=3, on_time=3, weight=3, weight_on_time=3)
        self.assertTrue(td.score(three, "week")["eligible"])
        self.assertFalse(td.score(three, "month")["eligible"])

    def test_overdue_and_slips_cost_points(self):
        clean = score_stats(tasks=3, dated=3, on_time=3, weight=3, weight_on_time=3)
        behind = {**clean, "overdue": 2, "slips": 2}
        self.assertEqual(
            td.score(clean, "week")["score"] - td.score(behind, "week")["score"], 3
        )
        ranked = td.rank({"behind": behind, "clean": clean}, "week")
        self.assertEqual(td.champion_of(ranked)["user"], "clean")

    def test_reasons_explain_the_score(self):
        result = td.score(
            score_stats(tasks=3, key=1, dated=3, on_time=3, weight=4, weight_on_time=4),
            "week",
        )
        self.assertEqual(len(result["reasons"]), 2)
        self.assertIn("Tasks done: 3", result["reasons"][0])


class TestWeightAndQuality(FrappeTestCase):
    def test_weight_comes_from_the_task(self):
        self.assertEqual(td.task_weight({})["weight"], 1)
        big = td.task_weight({"key": True, "estimate": 8, "priority": "High"})
        self.assertEqual(big["weight"], 3.25)
        self.assertEqual(big["reasons"], ["key", "8h estimate", "High priority"])
        # bounded: a long estimate counts up to 16 hours
        most = td.task_weight({"key": True, "estimate": 400, "priority": "Urgent"})
        self.assertEqual(most["weight"], 4.5)

    def test_a_self_made_task_cant_be_inflated_by_its_doer(self):
        tiny = td.task_weight({"self_made": True})
        self.assertEqual(tiny["weight"], 0.5)
        # key, priority and a long estimate the doer set themselves add (almost) nothing
        inflated = td.task_weight(
            {"self_made": True, "key": True, "estimate": 40, "priority": "Urgent"}
        )
        self.assertEqual(inflated["weight"], 1.0)

    def test_ten_tiny_own_tasks_dont_beat_two_big_key_tasks(self):
        def person(task: dict, count: int) -> dict:
            weight = td.task_weight(task)["weight"]
            return score_stats(
                tasks=count,
                dated=count,
                on_time=count,
                weight=weight * count,
                weight_on_time=weight * count,
            )

        gamer = person({"self_made": True}, 10)
        builder = person({"key": True, "estimate": 8, "priority": "High"}, 2)
        self.assertGreater(
            td.score(builder, "week")["score"], td.score(gamer, "week")["score"]
        )
        ranked = td.rank({"gamer": gamer, "builder": builder}, "week")
        self.assertEqual(td.champion_of(ranked)["user"], "builder")
        # one big task alone still isn't enough to be champion
        self.assertFalse(td.score(person({"key": True}, 1), "today")["eligible"])

    def test_quality_multiplier(self):
        self.assertEqual(td.task_quality({})["quality"], 1)
        self.assertEqual(td.task_quality({})["reasons"], ["not rated"])
        self.assertEqual(td.task_quality({"rating": "Excellent"})["quality"], 1.25)
        self.assertEqual(td.task_quality({"rating": "Needs rework"})["quality"], 0.5)
        self.assertEqual(
            td.task_quality({"rating": "Good", "sent_back": 1})["quality"], 0.85
        )
        # bounded below, and never above Excellent
        self.assertEqual(
            td.task_quality({"rating": "Needs rework", "came_back": 5})["quality"],
            0.25,
        )
        self.assertLessEqual(
            td.task_quality({"rating": "Excellent", "came_back": 0})["quality"], 1.25
        )

    def test_quality_shows_in_the_score(self):
        plain = score_stats(tasks=3, dated=3, on_time=3, weight=3, weight_on_time=3)
        excellent = {**plain, "value": 3.75, "value_on_time": 3.75, "excellent": 3}
        rework = {**plain, "value": 1.5, "value_on_time": 1.5, "rework": 3}
        scores = [td.score(s, "week") for s in (rework, plain, excellent)]
        self.assertEqual([s["score"] for s in scores], [1.5, 3, 3.8])
        quality = next(b for b in scores[2]["breakdown"] if b["key"] == "quality")
        self.assertIn("3 rated excellent", quality["detail"])


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

    def test_months_run_from_the_first_to_their_last_day(self):
        for day, last in (
            ("2026-02-14", date(2026, 2, 28)),
            ("2028-02-14", date(2028, 2, 29)),
            ("2026-09-30", date(2026, 9, 30)),
            ("2026-10-01", date(2026, 10, 31)),
        ):
            start, end = td.period_bounds("month", day)
            self.assertEqual((start.day, end), (1, last))

    def test_weeks_are_clipped_to_their_month(self):
        # October 2026 starts on a Thursday and ends on a Saturday
        weeks = []
        day = date(2026, 10, 1)
        while day.month == 10:
            weeks.append(td.period_bounds("week", day))
            day = weeks[-1][1] + timedelta(days=1)
        self.assertEqual(
            [(s.day, e.day) for s, e in weeks],
            [(1, 4), (5, 11), (12, 18), (19, 25), (26, 31)],
        )
        # the week of Monday 28 September is cut at the month's end
        self.assertEqual(
            td.period_bounds("week", "2026-09-29"),
            (date(2026, 9, 28), date(2026, 9, 30)),
        )

    def test_a_clipped_week_is_compared_with_the_same_days(self):
        start, end = td.period_bounds("week", "2026-10-03")
        # Thursday 1 to Saturday 3 against the same weekdays a week earlier
        self.assertEqual(
            td.comparison_bounds("week", start, end, "2026-10-03"),
            (date(2026, 9, 24), date(2026, 9, 26)),
        )
        self.assertEqual(
            td.comparison_bounds("today", date(2026, 10, 1), date(2026, 10, 1)),
            (date(2026, 9, 30), date(2026, 9, 30)),
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

    def test_dm_and_erp_see_each_other(self):
        # the department walls don't apply on the Scoreboard, so the teams can compete
        make_tasky_user(KIRAN, "Kiran Pillai", ("ERP Employee",))
        campaign = make_project(
            "Spice Route Instagram campaign",
            members=[(SANA, "Developer"), (DEEPA, "Developer")],
        ).name
        frappe.db.set_value("Project", campaign, "custom_department", "Digital")
        make_done_task(campaign, "Onam reel storyboard", SANA, "2031-03-10")
        with patch("helpdesk.ai_suggestion.is_ai_configured", return_value=False):
            td.clear_cache()
            td.close_period("week", *WEEK)

        dm = call_team_dashboard(SANA, TODAY, period="week")
        self.assertIn("ERP", dm["access"]["departments"])
        erp = next(d for d in dm["departments"] if d["department"] == "ERP")
        self.assertEqual(erp["champion"]["user"], ANU)
        self.assertEqual({p["user"]: p for p in dm["people"]}[ANU]["tasks"], 3)
        self.assertIn(self.project, [p["project"] for p in dm["projects"]])
        erp_only = call_team_dashboard(SANA, TODAY, period="week", department="ERP")
        self.assertEqual(erp_only["summary"]["tasks"], 4)

        erp_view = call_team_dashboard(KIRAN, TODAY, period="week")
        self.assertIn("Digital", erp_view["access"]["departments"])
        self.assertIn("Digital", [d["department"] for d in erp_view["departments"]])
        self.assertEqual({p["user"]: p for p in erp_view["people"]}[SANA]["tasks"], 1)
        self.assertIn(campaign, [p["project"] for p in erp_view["projects"]])
        digital = call_team_dashboard(KIRAN, TODAY, period="week", department="Digital")
        self.assertIn(SANA, [p["user"] for p in digital["people"]])

        # and the whole team's stored champions, ERP included
        later = call_team_dashboard(SANA, "2031-03-18", period="week")
        self.assertEqual(later["history"][0]["user"], ANU)

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

    def test_day_champion_and_heads_are_told_once_without_ai(self):
        make_tasky_user(MANAGER, "Meera Iyer", ("Agent Manager",))
        set_department_heads_as("Administrator", "ERP", [RAHUL])
        with (
            patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True),
            patch.object(td, "call_haiku") as ai,
        ):
            td.clear_cache()
            td.close_period("today", DAY, DAY)
            td.close_period("today", DAY, DAY)
        ai.assert_not_called()
        erp = frappe.get_doc(
            "HD Team Champion",
            {"period_type": "Day", "period_start": DAY, "department": "ERP"},
        )
        self.assertEqual(erp.user, ANU)
        self.assertFalse(erp.analysis)
        self.assertEqual(len(get_reminder_messages(ANU, erp.name)), 1)
        told = get_reminder_messages(RAHUL, erp.name)
        self.assertEqual(len(told), 1)
        self.assertIn("Anu Menon", told[0])
        team = frappe.db.get_value(
            "HD Team Champion",
            {
                "period_type": "Day",
                "period_start": DAY,
                "department": ("is", "not set"),
            },
        )
        self.assertEqual(len(get_reminder_messages(MANAGER, team)), 1)

    def test_heads_come_from_the_setting_and_the_dm_head_role(self):
        set_department_heads_as("Administrator", "ERP", [RAHUL, RAHUL])
        set_department_heads_as("Administrator", "Digital", [ANU])
        self.assertEqual(department_heads("ERP"), [RAHUL])
        digital = department_heads("Digital")
        self.assertLessEqual({ANU, DEEPA}, set(digital))
        self.assertNotIn(RAHUL, digital)
        erp = next(d for d in departments.get_departments() if d.name == "ERP")
        self.assertEqual(erp.heads, [{"user": RAHUL, "full_name": "Rahul Nair"}])
        self.assertEqual(erp.head_roles, [])

    def test_only_admins_set_heads(self):
        for user in (RAHUL, DEEPA, SANA):
            self.assertRaises(
                frappe.PermissionError,
                set_department_heads_as,
                user,
                "ERP",
                [user],
            )
        self.assertFalse({RAHUL, DEEPA, SANA} & set(department_heads("ERP")))

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

    def test_rating_is_for_the_assigner_and_reviewers_never_the_doer(self):
        task = frappe.db.get_value(
            "Task", {"project": self.project, "is_key": 1}, "name"
        )
        # Anu did it; Rahul is only a teammate
        for user in (ANU, RAHUL):
            self.assertRaises(
                frappe.PermissionError, rate_task_as, user, task, "Excellent"
            )
        # the project's lead reviews it, so may rate it
        frappe.db.set_value("Project", self.project, "project_lead", RAHUL)
        result = rate_task_as(RAHUL, task, "Excellent")
        self.assertEqual(result["rating"], "Excellent")
        self.assertEqual(result["rated_by"], RAHUL)
        self.assertEqual(result["quality"], 1.25)
        # a form save can't change it behind the API's back
        doc = frappe.get_doc("Task", task)
        doc.quality_rating = "Needs rework"
        self.assertRaises(frappe.PermissionError, doc.save)

        anu = {
            p["user"]: p
            for p in call_team_dashboard(
                "Administrator", TODAY, period="week", department="ERP"
            )["people"]
        }[ANU]
        self.assertEqual(anu["excellent"], 1)
        quality = next(b for b in anu["breakdown"] if b["key"] == "quality")
        # the key task weighs 2, so Excellent adds a quarter of it
        self.assertEqual(quality["points"], 0.5)

    def test_reopened_tasks_and_ticket_comebacks_lower_quality(self):
        task = make_task(self.project, "Stock valuation report", "2031-03-12").name
        make_assignment("Task", task, ANU)
        doc = frappe.get_doc("Task", task)
        doc.status = "Completed"
        doc.save()
        doc.status = "Open"
        doc.save()
        self.assertEqual(doc.reopen_count, 1)

        ticket, from_ticket = make_done_ticket_task(
            self.project, "Invoice print shows old GSTIN", ANU, "2031-03-11"
        )
        reopened = frappe.get_doc("HD Ticket", ticket)
        reopened.status = "Open"
        reopened.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Task", from_ticket, "reopen_count"), 1)
        self.assertEqual(td.task_score(from_ticket)["quality"], 0.75)

    def test_weighted_work_shows_next_to_the_task_count(self):
        for i in range(4):
            make_self_made_done_task(
                self.project, f"Tidy my notes {i}", RAHUL, "2031-03-11", "2031-03-12"
            )
        data = call_team_dashboard(
            "Administrator", TODAY, period="week", department="ERP"
        )
        people = {p["user"]: p for p in data["people"]}
        # Anu: three tasks, one key; Rahul: one late plus four of his own at half
        self.assertEqual((people[ANU]["tasks"], people[ANU]["weight"]), (3, 4))
        self.assertEqual((people[RAHUL]["tasks"], people[RAHUL]["weight"]), (5, 3))
        self.assertEqual(people[RAHUL]["self_made"], 4)
        self.assertEqual(data["summary"]["weight"], 7)
        self.assertEqual(data["champion"]["user"], ANU)

    def test_a_closed_month_shows_the_champion_kept_when_it_closed(self):
        # Anu did February's work, but Rahul was kept as February's champion:
        # the stored record wins, so history never shifts with a new formula
        for i in range(3):
            make_done_task(
                self.project, f"February close {i}", ANU, "2031-02-20", "2031-02-25"
            )
        make_team_champion("Month", "2031-02-01", "2031-02-28", RAHUL, 12.5)
        # two more in March, so Anu reaches the month's minimum weighted work (5)
        for i in range(2):
            make_done_task(
                self.project, f"March close {i}", ANU, "2031-03-10", "2031-03-12"
            )

        february = call_team_dashboard(
            "Administrator", TODAY, period="month", day="2031-02-15"
        )
        self.assertTrue(february["period"]["closed"])
        self.assertEqual(february["period"]["start"], "2031-02-01")
        self.assertEqual(february["champion"]["user"], RAHUL)
        self.assertTrue(february["champion"]["stored"])
        self.assertEqual(february["summary"]["tasks"], 3)

        march = call_team_dashboard("Administrator", TODAY, period="month")
        self.assertTrue(march["period"]["current"])
        self.assertEqual(march["champion"]["user"], ANU)
        self.assertEqual(march["previous_champion"]["user"], RAHUL)
        self.assertEqual(march["previous_champion"]["score"], 12.5)
        self.assertEqual(march["previous_champion"]["reasons"], ["Tasks done: 2"])

    def test_a_future_day_is_refused(self):
        self.assertRaises(
            frappe.ValidationError,
            call_team_dashboard,
            "Administrator",
            TODAY,
            period="month",
            day="2031-04-01",
        )

    def test_the_year_compares_its_months(self):
        make_team_champion("Month", "2031-02-01", "2031-02-28", RAHUL, 12.5)
        # two more in March, so Anu reaches the month's minimum weighted work (5)
        for i in range(2):
            make_done_task(
                self.project, f"March close {i}", ANU, "2031-03-10", "2031-03-12"
            )
        data = call_team_dashboard("Administrator", TODAY, period="year")
        months = data["months"]
        self.assertEqual(len(months), 12)
        self.assertEqual(months[1]["champion"]["user"], RAHUL)
        self.assertEqual((months[2]["tasks"], months[2]["champion"]["user"]), (6, ANU))
        self.assertTrue(months[3]["future"])
        anu = next(p for p in data["people"] if p["user"] == ANU)
        self.assertEqual(anu["months"][2]["tasks"], 5)
        self.assertIsNone(anu["months"][11])


class TestDepartmentGroups(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        ensure_role()
        frappe.cache.delete_keys(f"{td.CACHE_PREFIX}_")
        make_department("ERP")
        make_department("Digital")
        make_department("GrowthX")
        frappe.db.set_value("HD Department", "GrowthX", "parent_department", "ERP")
        make_tasky_user(ANU, "Anu Menon")
        make_tasky_user(RAHUL, "Rahul Nair")
        erp = make_project("Kerala Spices ERP rollout", members=[(ANU, "Developer")])
        growth = make_project("Lead funnel revamp", members=[(RAHUL, "Developer")])
        frappe.db.set_value("Project", erp.name, "custom_department", "ERP")
        frappe.db.set_value("Project", growth.name, "custom_department", "GrowthX")
        for i in range(3):
            make_done_task(erp.name, f"GST setup {i}", ANU, DAY, due="2031-03-12")
        for i in range(4):
            make_done_task(growth.name, f"Landing page {i}", RAHUL, DAY, "2031-03-12")

    def test_a_group_rolls_up_its_departments(self):
        data = call_team_dashboard("Administrator", TODAY, period="week")
        groups = {g["group"]: g["departments"] for g in data["access"]["groups"]}
        self.assertEqual(groups["ERP"][0], "ERP")
        self.assertIn("GrowthX", groups["ERP"])
        rows = data["departments"]
        group_row = next(
            r for r in rows if r["department"] == "ERP" and r["kind"] == "group"
        )
        self.assertEqual((group_row["department"], group_row["tasks"]), ("ERP", 7))
        self.assertEqual(group_row["champion"]["user"], RAHUL)
        growth = next(r for r in rows if r["department"] == "GrowthX")
        self.assertEqual(growth["parent"], "ERP")
        erp_alone = next(
            r for r in rows if r["department"] == "ERP" and r["kind"] == "department"
        )
        self.assertEqual((erp_alone["tasks"], erp_alone["champion"]["user"]), (3, ANU))

        group = call_team_dashboard("Administrator", TODAY, period="week", group="ERP")
        self.assertEqual(group["group"], "ERP")
        self.assertEqual(group["summary"]["tasks"], 7)
        self.assertLessEqual({ANU, RAHUL}, {p["user"] for p in group["people"]})
        # GrowthX is a department, not a group
        self.assertRaises(
            frappe.ValidationError,
            call_team_dashboard,
            "Administrator",
            TODAY,
            period="week",
            group="GrowthX",
        )

    def test_group_champions_are_stored_once(self):
        with patch("helpdesk.ai_suggestion.is_ai_configured", return_value=False):
            td.clear_cache()
            td.close_period("week", *WEEK)
            td.close_period("week", *WEEK)
        group = frappe.get_doc("HD Team Champion", f"week-{WEEK[0]}-group_erp")
        self.assertTrue(group.is_group)
        self.assertEqual(group.user, RAHUL)
        self.assertEqual(
            frappe.get_doc("HD Team Champion", f"week-{WEEK[0]}-erp").user, ANU
        )
        self.assertEqual(len(get_reminder_messages(RAHUL, group.name)), 1)
        history = call_team_dashboard(
            "Administrator", "2031-03-18", period="week", group="ERP"
        )["history"]
        self.assertEqual(history[0]["user"], RAHUL)
