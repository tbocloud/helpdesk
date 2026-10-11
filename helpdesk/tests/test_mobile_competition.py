# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk import competition, follow_ups
from helpdesk import team_dashboard as td
from helpdesk.content_team import ensure_role
from helpdesk.test_utils import (
    call_mobile_as,
    call_mobile_on,
    get_reminder_messages,
    hold_commits,
    make_assignment,
    make_department,
    make_done_task,
    make_follow_up,
    make_project,
    make_task,
    make_tasky_user,
    set_department_heads_as,
    set_follow_up_settings,
)

# a week far from the real calendar, so only this test's records fall in it
TODAY = date(2031, 3, 12)  # a Wednesday
WEEK = ("2031-03-10", "2031-03-16")
ANU = "anu.menon@compete.test"
RAHUL = "rahul.nair@compete.test"
PLAIN = "plain.agent@compete.test"
ERP = "kiran.erp@compete.test"
DM = "sana.dm@compete.test"
COORD = "devi.coord@compete.test"
LEAD = "jose.lead@compete.test"
HEAD = "meera.head@compete.test"
AGENT_MANAGER = "arun.manager@compete.test"
SYSTEM_MANAGER = "lakshmi.system@compete.test"
NO_AI = patch("helpdesk.ai_suggestion.is_ai_configured", return_value=False)


class CompetitionCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        ensure_role()
        frappe.cache.delete_keys(f"{td.CACHE_PREFIX}_")
        make_department("ERP")
        make_department("Digital")
        make_tasky_user(ANU, "Anu Menon")
        make_tasky_user(RAHUL, "Rahul Nair")
        self.project = make_project(
            "Kerala Spices ERP rollout",
            members=[(ANU, "Developer"), (RAHUL, "Developer")],
        ).name
        frappe.db.set_value("Project", self.project, "custom_department", "ERP")


class TestCapabilities(CompetitionCase):
    def test_capabilities_follow_the_roles(self):
        make_tasky_user(PLAIN, "Priya Plain")
        make_tasky_user(ERP, "Kiran Pillai", ("ERP Employee",))
        make_tasky_user(DM, "Sana Rafeeq", ("DM Employee",))
        make_tasky_user(COORD, "Devi Coordinator")
        make_tasky_user(LEAD, "Jose Lead")
        make_tasky_user(HEAD, "Meera Head")
        make_tasky_user(AGENT_MANAGER, "Arun Manager", ("Agent Manager",))
        make_tasky_user(SYSTEM_MANAGER, "Lakshmi System", ("System Manager",))
        led = make_project("Galom go-live", members=[(COORD, "Project Coordinator")])
        frappe.db.set_value("Project", led.name, "project_lead", LEAD)
        set_department_heads_as("Administrator", "ERP", [HEAD])

        def caps(user):
            return call_mobile_as(user, "get_me")["data"]["capabilities"]

        plain = caps(PLAIN)
        self.assertEqual(
            {k: plain[k] for k in ("tickets", "content", "manage_team")},
            {"tickets": False, "content": False, "manage_team": False},
        )
        self.assertFalse(plain["approve_reviews"])
        self.assertTrue(plain["scoreboard"])
        self.assertEqual(
            (plain["departments_headed"], plain["projects_managed"]), ([], [])
        )

        erp = caps(ERP)
        self.assertTrue(erp["tickets"])
        self.assertFalse(erp["content"])
        dm = caps(DM)
        self.assertFalse(dm["tickets"])
        self.assertTrue(dm["content"])

        coordinator = caps(COORD)
        self.assertTrue(coordinator["approve_reviews"])
        self.assertEqual(coordinator["projects_managed"], [])
        self.assertFalse(coordinator["manage_team"])

        lead = caps(LEAD)
        self.assertTrue(lead["approve_reviews"])
        self.assertEqual(lead["projects_managed"], [led.name])
        self.assertFalse(lead["manage_team"])

        head = caps(HEAD)
        self.assertTrue(head["manage_team"])
        self.assertEqual(head["departments_headed"], ["ERP"])
        self.assertFalse(head["admin"])

        for user in (AGENT_MANAGER, SYSTEM_MANAGER):
            admin = caps(user)
            self.assertTrue(admin["admin"])
            self.assertTrue(admin["manage_team"])
            self.assertTrue(admin["tickets"])

        bundle = call_mobile_as(HEAD, "get_home_bundle")["data"]
        self.assertEqual(bundle["me"]["capabilities"]["departments_headed"], ["ERP"])


class TestCompetition(CompetitionCase):
    def test_rank_and_change_since_last_week(self):
        # last week to the same point (Mon 3 to Wed 5 March): Rahul ahead
        for day in ("2031-03-03", "2031-03-04", "2031-03-05"):
            make_done_task(self.project, "Configure the GST print", RAHUL, day, day)
        make_done_task(
            self.project, "Configure the GST print", ANU, "2031-03-05", "2031-03-04"
        )
        # this week: Anu ahead
        for day in ("2031-03-10", "2031-03-11", "2031-03-12"):
            make_done_task(
                self.project, "Configure the GST print", ANU, day, "2031-03-12"
            )
        make_done_task(
            self.project, "Configure the GST print", RAHUL, "2031-03-11", "2031-03-10"
        )

        anu = call_mobile_on(ANU, TODAY, "get_competition", period="week")["data"]
        self.assertEqual((anu["me"]["rank"], anu["me"]["rank_delta"]), (1, 1))
        self.assertTrue(anu["me"]["is_champion"])
        self.assertEqual(anu["team"]["champion"], ANU)
        rahul = next(r for r in anu["team"]["leaders"] if r["user"] == RAHUL)
        self.assertEqual((rahul["rank"], rahul["rank_delta"]), (2, -1))
        erp = next(d for d in anu["departments"] if d["department"] == "ERP")
        self.assertEqual(erp["leaders"][0]["user"], ANU)
        self.assertEqual(erp["me"]["rank"], 1)

        # Rahul sees the same board, and how to catch Anu up from his own work
        open_task = make_task(
            self.project, "Bank reconciliation import", "2031-03-14", is_key=1
        ).name
        make_assignment("Task", open_task, RAHUL)
        board = call_mobile_on(RAHUL, TODAY, "get_competition", period="week")["data"]
        self.assertEqual(board["me"]["rank"], 2)
        move_up = board["move_up"]
        self.assertFalse(move_up["leader"])
        self.assertEqual(move_up["next"]["user"], ANU)
        self.assertGreater(move_up["gap"], 0)
        action = next(a for a in move_up["actions"] if a["task"] == open_task)
        self.assertGreater(action["points"], 0)
        self.assertIn("on time", action["text"])

    def test_on_time_streak_skips_weekends_and_holidays(self):
        holiday = date(2031, 3, 8)  # a Saturday off
        # Fri, (Sat off, Sun), Mon, Tue: all on time
        for day in ("2031-03-07", "2031-03-10", "2031-03-11"):
            make_done_task(self.project, "Configure the GST print", ANU, day, day)
        # due on the day off: counts on the next working day, not as a day of its own
        make_done_task(
            self.project, "Configure the GST print", ANU, "2031-03-08", "2031-03-08"
        )
        td.clear_cache()
        with patch.object(
            competition,
            "working_day_checker",
            return_value=lambda day: day.weekday() != 6 and day != holiday,
        ):
            streaks = competition.my_streaks(ANU, TODAY)
        # Wednesday has nothing due: it neither counts nor breaks the streak
        self.assertEqual(streaks["on_time_days"], 3)

        td.clear_cache()
        with patch.object(
            competition,
            "working_day_checker",
            return_value=lambda day: day.weekday() != 6,
        ):
            # with Saturday worked, the 8th is a day of its own
            self.assertEqual(competition.my_streaks(ANU, TODAY)["on_time_days"], 4)

        # something late on Monday breaks it
        make_done_task(
            self.project, "Configure the GST print", ANU, "2031-03-11", "2031-03-10"
        )
        td.clear_cache()
        with patch.object(
            competition,
            "working_day_checker",
            return_value=lambda day: day.weekday() != 6 and day != holiday,
        ):
            streaks = competition.my_streaks(ANU, TODAY)
        self.assertEqual(
            (streaks["on_time_days"], streaks["best_on_time_days"]), (1, 1)
        )

    def test_badges_are_awarded_once(self):
        for day in ("2031-03-10", "2031-03-11", "2031-03-12"):
            make_done_task(
                self.project,
                "Configure the GST print",
                ANU,
                day,
                "2031-03-12",
                is_key=1,
            )
        with NO_AI:
            for _run in range(2):
                td.clear_cache()
                td.close_period("week", *WEEK)
        awards = frappe.get_all(
            competition.BADGE,
            filters={"user": ANU, "period_start": WEEK[0]},
            fields=["name", "badge", "department"],
        )
        badges = sorted(a.badge for a in awards)
        self.assertEqual(
            badges, ["champion_week", "key_closer", "podium", "zero_overdue_week"]
        )
        key_closer = next(a.name for a in awards if a.badge == "key_closer")
        self.assertEqual(len(get_reminder_messages(ANU, key_closer)), 1)
        # the champion already heard "You're the … champion"
        champion = next(a.name for a in awards if a.badge == "champion_week")
        self.assertEqual(get_reminder_messages(ANU, champion), [])

        board = call_mobile_on(ANU, "2031-03-18", "get_competition", period="week")
        earned = board["data"]["badges"]["earned"]
        self.assertEqual(len(earned), 4)
        self.assertEqual(board["data"]["streaks"]["podium_weeks"], 1)

    def test_weekly_challenge_progress(self):
        # the rollback restores the settings, not their cached copy
        self.addCleanup(
            frappe.clear_document_cache, follow_ups.SETTINGS, follow_ups.SETTINGS
        )
        make_done_task(
            self.project,
            "Configure the GST print",
            ANU,
            "2031-03-11",
            "2031-03-12",
            is_key=1,
        )
        late = make_task(self.project, "Opening stock", "2031-03-14", is_key=1).name
        make_assignment("Task", late, RAHUL)
        plain = make_task(self.project, "Print format tweaks", "2031-03-13").name
        make_assignment("Task", plain, RAHUL)

        challenge = call_mobile_on(RAHUL, TODAY, "get_competition")["data"]["challenge"]
        self.assertEqual(challenge["title"], "Close every key task due this week")
        self.assertEqual((challenge["done"], challenge["goal"]), (1, 2))
        self.assertEqual([p["user"] for p in challenge["completed_by"]], [ANU])
        self.assertEqual(challenge["mine"], {"done": 0, "total": 1})
        self.assertFalse(challenge["complete"])

        set_follow_up_settings(weekly_challenge="Every task due this week")
        challenge = call_mobile_on(RAHUL, TODAY, "get_competition")["data"]["challenge"]
        self.assertEqual((challenge["done"], challenge["goal"]), (1, 3))

        set_follow_up_settings(weekly_challenge="Off")
        self.assertIsNone(
            call_mobile_on(RAHUL, TODAY, "get_competition")["data"]["challenge"]
        )

    def test_my_stats_trend(self):
        make_done_task(
            self.project, "Configure the GST print", ANU, "2031-03-11", "2031-03-12"
        )
        make_done_task(
            self.project, "Configure the GST print", ANU, "2031-03-04", "2031-03-03"
        )
        stats = call_mobile_on(ANU, TODAY, "get_my_stats", period="week")["data"]
        self.assertEqual(len(stats["trend"]), 8)
        self.assertEqual(stats["current"]["start"], WEEK[0])
        self.assertEqual(
            (stats["current"]["done"], stats["current"]["on_time"]), (1, 1)
        )
        self.assertEqual(
            (stats["previous"]["done"], stats["previous"]["on_time"]), (1, 0)
        )


class TestInsights(CompetitionCase):
    def setUp(self):
        super().setUp()
        make_tasky_user(HEAD, "Meera Head")
        make_tasky_user(AGENT_MANAGER, "Arun Manager", ("Agent Manager",))
        set_department_heads_as("Administrator", "ERP", [HEAD])
        make_done_task(
            self.project, "Configure the GST print", ANU, "2031-03-11", "2031-03-12"
        )
        open_task = make_task(self.project, "Cutover checklist", "2031-03-20").name
        make_assignment("Task", open_task, ANU)
        campaign = make_project("Spice Route campaign", members=[(RAHUL, "Developer")])
        frappe.db.set_value("Project", campaign.name, "custom_department", "Digital")
        make_done_task(campaign.name, "Onam reel", RAHUL, "2031-03-11", "2031-03-12")
        reel = make_task(campaign.name, "Diwali reel", "2031-03-20").name
        make_assignment("Task", reel, RAHUL)

    def test_insights_are_for_heads_and_managers_only(self):
        with self.assertRaises(frappe.PermissionError):
            call_mobile_on(ANU, TODAY, "get_insights")
        with self.assertRaises(frappe.PermissionError):
            call_mobile_on(HEAD, TODAY, "get_insights", department="Digital")

    def test_head_sees_their_department(self):
        with NO_AI:
            data = call_mobile_on(HEAD, TODAY, "get_insights", period="week")["data"]
        self.assertEqual(data["scope"]["departments"], ["ERP"])
        tiles = {t["key"]: t for t in data["tiles"]}
        # the Digital task is outside the head's departments
        self.assertEqual(tiles["tasks_done"]["value"], 1)
        self.assertEqual(tiles["on_time_pct"]["value"], 100)
        self.assertEqual(len(data["trend"]), 8)
        self.assertEqual(data["trend"][-1]["throughput"], 1)
        self.assertEqual(data["summary"]["source"], "rules")
        self.assertGreaterEqual(len(data["summary"]["bullets"]), 3)
        workload = {p["user"]: p for p in data["workload"]["people"]}
        self.assertEqual(workload[ANU]["open_tasks"], 1)
        self.assertNotIn(RAHUL, workload)

        with NO_AI:
            everyone = call_mobile_on(AGENT_MANAGER, TODAY, "get_insights")["data"]
        self.assertIsNone(everyone["scope"]["departments"])
        self.assertGreaterEqual(
            {t["key"]: t for t in everyone["tiles"]}["tasks_done"]["value"], 2
        )


class TestTaskBoosters(CompetitionCase):
    def test_quick_add_task_needs_a_place_on_the_project(self):
        task = call_mobile_as(
            ANU,
            "quick_add_task",
            project=self.project,
            subject="Call the customer about GST",
            due_date=add_days(nowdate(), 2),
        )["data"]
        self.assertEqual(task["assignees"], [ANU])
        make_tasky_user(PLAIN, "Priya Plain")
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(
                PLAIN, "quick_add_task", project=self.project, subject="Not mine"
            )

    def test_focus_puts_overdue_first(self):
        later = make_task(
            self.project, "Write the cutover plan", add_days(nowdate(), 3)
        )
        make_assignment("Task", later.name, ANU)
        late = make_task(
            self.project, "Import opening balances", add_days(nowdate(), -2)
        )
        make_assignment("Task", late.name, ANU)
        focus = call_mobile_as(ANU, "get_focus")["data"]
        self.assertEqual(focus[0]["name"], late.name)
        self.assertEqual(focus[0]["focus"], "close_first")
        self.assertEqual([t["name"] for t in focus], [late.name, later.name])


class TestSnooze(CompetitionCase):
    def setUp(self):
        super().setUp()
        self.task = make_task(
            self.project, "Map the GST fields", add_days(nowdate(), -1)
        ).name
        make_assignment("Task", self.task, ANU)
        self.until = add_days(nowdate(), 2)

    def snooze(self, user: str, found: list):
        with patch.object(follow_ups, "current", return_value=found):
            return call_mobile_as(
                user,
                "snooze_follow_up",
                item=f"Task:{self.task}",
                until=self.until,
                reason="Waiting for the customer's GSTIN list",
            )

    def test_snooze_quiets_only_low_levels(self):
        result = self.snooze(ANU, [make_follow_up("Task", self.task, ANU, level=1)])
        self.assertEqual(result["data"]["until"], str(self.until))
        low = make_follow_up("Task", self.task, ANU, level=1)
        high = make_follow_up("Task", self.task, ANU, level=2, severity="escalated")
        breach = make_follow_up("Task", self.task, ANU, severity="breach")
        kept = follow_ups.drop_snoozed([low, high, breach], nowdate())
        self.assertEqual([f.recipients for f in kept], [[], [ANU], [ANU]])
        # reminders start again on the day it was snoozed until
        self.assertEqual(
            follow_ups.drop_snoozed([low], self.until)[0].recipients, [ANU]
        )

    def test_escalated_work_and_others_work_cant_be_snoozed(self):
        with self.assertRaises(frappe.ValidationError):
            self.snooze(
                ANU,
                [make_follow_up("Task", self.task, ANU, level=2, severity="escalated")],
            )
        with self.assertRaises(frappe.PermissionError):
            self.snooze(RAHUL, [make_follow_up("Task", self.task, RAHUL, level=0)])
        self.assertFalse(frappe.db.exists(follow_ups.SNOOZE, {"user": ANU}))
