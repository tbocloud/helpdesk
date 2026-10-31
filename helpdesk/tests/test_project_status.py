from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, getdate, now_datetime, nowdate

from helpdesk import follow_ups, project_status, project_status_ai
from helpdesk.api import project_status as api
from helpdesk.test_utils import (
    age_project,
    follow_up_context,
    get_follow_up_notices,
    hold_commits,
    make_held_task,
    make_project,
    make_status_update,
    make_task,
    make_task_in_status,
    make_tasky_user,
    run_as_user,
    set_follow_up_settings,
    set_status_report_recipients,
    status_split_answer,
)

PM = ("pm.status@status-report.example", "Meera Das")
LEAD = ("lead.status@status-report.example", "Biju Thomas")
COORD = ("coord.status@status-report.example", "Archana Nair")
DEV = ("dev.status@status-report.example", "Arjun Menon")
OUTSIDER = ("outsider.status@status-report.example", "Kiran Rao")
SYSTEM_MANAGER = ("sysman.status@status-report.example", "Sanil Kumar")
SPLIT = "helpdesk.project_status_ai.call_haiku"
AI_ON = "helpdesk.project_status_ai.is_ai_configured"
DELIVER = "helpdesk.follow_ups.deliver_digest"


class StatusReportCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(follow_ups.clear_cache)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        self.addCleanup(
            frappe.clear_document_cache, follow_ups.SETTINGS, follow_ups.SETTINGS
        )
        for user in (LEAD, COORD, DEV, OUTSIDER):
            make_tasky_user(*user)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*SYSTEM_MANAGER, roles=("System Manager",))
        self.project = self.make_project("Galom Mobile App", "Galom Trading")
        self.other = self.make_project("Avera IoT", "Avera Systems")

    def make_project(self, name, customer):
        if not frappe.db.exists("HD Customer", customer):
            frappe.get_doc(
                {"doctype": "HD Customer", "customer_name": customer}
            ).insert(ignore_permissions=True)
        project = make_project(
            name,
            members=[
                (LEAD[0], "Developer"),
                (COORD[0], "Project Coordinator"),
                (DEV[0], "Developer"),
            ],
            owner=PM[0],
        )
        project.db_set({"project_lead": LEAD[0], "customer": customer})
        return project.name

    def row(self, project=None, user="Administrator"):
        project = project or self.project
        rows = run_as_user(user, project_status.project_rows)
        found = [r for r in rows if r["project"] == project]
        return found[0] if found else None

    def write(self, user, **values):
        item = {"project": self.project, "stage": "Testing / UAT", **values}
        return run_as_user(user, lambda: project_status.save_updates([item]))


class TestWhoMayWrite(StatusReportCase):
    def test_the_people_who_coordinate_the_project_write_its_update(self):
        for user in (PM[0], LEAD[0], COORD[0], SYSTEM_MANAGER[0]):
            self.assertEqual(len(self.write(user)), 1, user)

    def test_a_member_or_outsider_cannot_write(self):
        for user in (DEV[0], OUTSIDER[0]):
            with self.assertRaises(frappe.PermissionError, msg=user):
                self.write(user)

    def test_the_bulk_check_agrees_with_can_coordinate_project(self):
        from helpdesk.tasky.permissions import can_coordinate_project

        for user in (PM[0], LEAD[0], COORD[0], DEV[0], OUTSIDER[0], SYSTEM_MANAGER[0]):
            allowed = project_status.writable_projects(user, [self.project, self.other])
            for project in (self.project, self.other):
                self.assertEqual(
                    project in allowed, can_coordinate_project(project, user), user
                )

    def test_one_project_the_user_may_not_write_refuses_the_whole_save(self):
        not_yours = make_project("Not Yours").name
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                COORD[0],
                lambda: api.save_status_updates(
                    [
                        {"project": self.project, "stage": "Testing / UAT"},
                        {"project": not_yours, "stage": "Live"},
                    ]
                ),
            )

    def test_a_member_sees_their_projects_but_cannot_write_them(self):
        row = self.row(user=DEV[0])
        self.assertFalse(row["can_write"])
        self.assertIsNone(self.row(user=OUTSIDER[0]))
        self.assertTrue(self.row(user=COORD[0])["can_write"])

    def test_the_history_is_kept_and_an_update_is_never_edited(self):
        first = make_status_update(self.project, days_ago=3, stage="Development")
        make_status_update(self.project, stage="Testing / UAT")
        history = run_as_user(COORD[0], lambda: api.get_status_history(self.project))
        self.assertEqual([h.stage for h in history], ["Testing / UAT", "Development"])
        first.update_text = "changed"
        with self.assertRaises(frappe.ValidationError):
            first.save(ignore_permissions=True)

    def test_a_closed_project_has_no_status_to_report(self):
        frappe.db.set_value("Project", self.project, "status", "Completed")
        with self.assertRaises(frappe.ValidationError):
            make_status_update(self.project)

    def test_an_outsider_cannot_read_the_history(self):
        make_status_update(self.project)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_status_history(self.project))


class TestWaitingSince(StatusReportCase):
    def test_a_new_wait_starts_today_and_the_same_wait_keeps_its_day(self):
        first = make_status_update(self.project, waiting_on="Client")
        self.assertEqual(str(first.waiting_since), nowdate())
        frappe.db.set_value(
            "HD Project Status Update",
            first.name,
            "waiting_since",
            add_days(nowdate(), -5),
        )
        again = make_status_update(self.project, waiting_on="Client")
        self.assertEqual(str(again.waiting_since), str(add_days(nowdate(), -5)))
        internal = make_status_update(self.project, waiting_on="Internal")
        self.assertEqual(str(internal.waiting_since), nowdate())

    def test_waiting_on_nothing_has_no_day(self):
        update = make_status_update(
            self.project, waiting_on="Nothing", waiting_since=nowdate()
        )
        self.assertIsNone(update.waiting_since)


class TestFacts(StatusReportCase):
    def test_tasks_done_total_overdue_and_held_with_reasons(self):
        yesterday = add_days(nowdate(), -1)
        make_task_in_status(self.project, "Done one", "Completed")
        make_task(self.project, "Late one", yesterday)
        make_task(self.project, "Fine one", add_days(nowdate(), 5))
        make_task_in_status(self.project, "Cancelled one", "Cancelled")
        make_held_task(self.project, "Needs data", "Waiting on customer", days_ago=4)

        facts = self.row()["facts"]

        self.assertEqual((facts["done"], facts["total"], facts["overdue"]), (1, 4, 1))
        self.assertEqual(
            [(h["subject"], h["reason"], h["days"]) for h in facts["held"]],
            [("Needs data", "Waiting on customer", 4)],
        )

    def test_a_held_task_is_never_overdue(self):
        task = make_held_task(self.project, "Paused", "Leave")
        frappe.db.set_value("Task", task, "exp_end_date", add_days(nowdate(), -3))
        self.assertEqual(self.row()["facts"]["overdue"], 0)

    def test_next_milestone_is_the_earliest_open_one(self):
        make_task(self.project, "Later", add_days(nowdate(), 20), is_milestone=1)
        make_task(self.project, "Sooner", add_days(nowdate(), 9), is_milestone=1)
        done = make_task_in_status(self.project, "Done", "Completed")
        frappe.db.set_value(
            "Task", done, {"is_milestone": 1, "exp_end_date": nowdate()}
        )

        milestone = self.row()["facts"]["next_milestone"]

        self.assertEqual(milestone["subject"], "Sooner")
        self.assertEqual(str(milestone["due"]), add_days(nowdate(), 9))

    def test_days_waiting_on_the_client_come_from_the_update_then_the_held_tasks(self):
        make_held_task(self.project, "Needs data", "Waiting on customer", days_ago=6)
        self.assertEqual(self.row()["facts"]["client_wait_days"], 6)

        update = make_status_update(self.project, waiting_on="Client")
        frappe.db.set_value(
            "HD Project Status Update",
            update.name,
            "waiting_since",
            add_days(nowdate(), -2),
        )
        self.assertEqual(self.row()["facts"]["client_wait_days"], 2)

    def test_update_age_and_last_activity(self):
        self.assertIsNone(self.row()["update_age"])
        self.assertTrue(self.row()["stale"])
        make_task(self.project, "Any task")
        make_status_update(self.project, days_ago=3)
        row = self.row()
        self.assertEqual(row["update_age"], 3)
        self.assertFalse(row["stale"])
        self.assertEqual(row["facts"]["last_activity"], getdate())
        make_status_update(self.project, days_ago=project_status.STALE_DAYS + 1)
        # the newest update counts, not the old one made after it
        self.assertEqual(self.row()["update_age"], 3)


class TestContradictions(StatusReportCase):
    def codes(self, project=None):
        return [f["code"] for f in self.row(project)["flags"]]

    def test_live_or_support_with_overdue_tasks(self):
        make_task(self.project, "Late", add_days(nowdate(), -2))
        for stage in ("Live", "Support"):
            make_status_update(self.project, stage=stage)
            self.assertEqual(self.codes(), ["live_with_overdue"], stage)
        make_status_update(self.project, stage="Development")
        self.assertEqual(self.codes(), [])

    def test_waiting_on_nothing_while_tasks_are_held_for_the_client(self):
        make_held_task(self.project, "Needs data", "Waiting on customer")
        make_status_update(self.project, waiting_on="Nothing")
        self.assertEqual(self.codes(), ["client_hold_not_waiting"])
        make_status_update(self.project, waiting_on="Client")
        self.assertEqual(self.codes(), [])

    def test_a_task_held_for_another_reason_is_no_contradiction(self):
        make_held_task(self.project, "Away", "Leave")
        make_status_update(self.project, waiting_on="Nothing")
        self.assertEqual(self.codes(), [])

    def test_project_on_hold_but_stage_says_otherwise(self):
        frappe.db.set_value("Project", self.project, "status", "On hold")
        make_status_update(self.project, stage="Development")
        self.assertEqual(self.codes(), ["project_on_hold"])
        make_status_update(self.project, stage="On hold")
        self.assertEqual(self.codes(), [])

    def test_a_project_on_hold_without_an_update_shows_the_on_hold_stage(self):
        frappe.db.set_value("Project", self.project, "status", "On hold")
        row = self.row()
        self.assertEqual(row["stage"], "On hold")
        self.assertIsNone(row["update_age"])


class TestAttentionOrder(StatusReportCase):
    def test_overdue_and_contradictions_first_then_stale_then_waiting_then_the_rest(
        self,
    ):
        names = {
            key: self.make_project(f"Order {key}", "Galom Trading")
            for key in ("fine", "waiting", "stale", "overdue", "paused")
        }
        make_status_update(names["fine"], days_ago=1)
        make_status_update(names["waiting"], days_ago=1, waiting_on="Client")
        make_status_update(names["stale"], days_ago=20)
        make_status_update(names["overdue"], days_ago=1)
        make_task(names["overdue"], "Late", add_days(nowdate(), -1))
        make_status_update(names["paused"], days_ago=20, stage="On hold")
        wanted = [names[k] for k in ("overdue", "stale", "waiting", "fine", "paused")]

        rows = run_as_user("Administrator", project_status.project_rows)

        shown = [r["project"] for r in rows if r["project"] in wanted]
        self.assertEqual(shown, wanted)


class TestSplit(StatusReportCase):
    TEXT = (
        "Galum mobile app done, Gayathri's tasks complete, waiting for client "
        "confirmation. Avera UAT ongoing, corrections within 2 days. ADKA is on hold."
    )

    def projects(self):
        return [
            {
                "project": self.project,
                "project_name": "Galom Mobile App",
                "customer": "Galom Trading",
            },
            {
                "project": self.other,
                "project_name": "Avera IoT",
                "customer": "Avera Systems",
            },
        ]

    def split(self, *updates, text=None):
        with patch(AI_ON, return_value=True), patch(
            SPLIT, return_value=status_split_answer(*updates)
        ) as ai:
            result = project_status_ai.split_update(text or self.TEXT, self.projects())
        self.ai = ai
        return result

    def test_a_misheard_name_still_finds_its_project(self):
        (galom,) = self.split(
            {
                "project": "Galum",
                "stage": "Testing / UAT",
                "waiting_on": "Client",
                "update": "- Mobile app done\n- Awaiting client confirmation",
            }
        )
        self.assertEqual(galom["project"], self.project)
        self.assertEqual(galom["stage"], "Testing / UAT")
        self.assertEqual(galom["waiting_on"], "Client")
        self.assertEqual(galom["update_text"].splitlines()[0], "- Mobile app done")

    def test_the_client_name_or_first_word_also_finds_the_project(self):
        found = self.split(
            {"project": "avera", "update": "- UAT ongoing"},
            {"project": "Galom Trading", "update": "- Done"},
        )
        self.assertEqual({r["project"] for r in found}, {self.other, self.project})

    def test_projects_not_mentioned_or_not_known_are_left_out(self):
        found = self.split(
            {"project": "ADKA UAE", "update": "- On hold"},
            {"project": self.other, "update": "- UAT ongoing"},
        )
        self.assertEqual([r["project"] for r in found], [self.other])
        sent = frappe.parse_json(self.ai.call_args.args[1])
        self.assertEqual(
            [p["id"] for p in sent["PROJECTS"]], [self.project, self.other]
        )

    def test_a_date_the_text_never_gave_is_dropped(self):
        in_a_week = str(add_days(nowdate(), 7))
        (row,) = self.split(
            {
                "project": self.other,
                "update": "- UAT ongoing",
                "next_step": "Client corrections",
                "next_step_date": in_a_week,
                "next_step_date_words": "next Friday",
            }
        )
        self.assertIsNone(row["next_step_date"])
        self.assertEqual(row["next_step"], "Client corrections")

    def test_a_date_with_its_words_in_the_text_is_kept(self):
        in_two_days = str(add_days(nowdate(), 2))
        (row,) = self.split(
            {
                "project": self.other,
                "update": "- UAT ongoing",
                "next_step_date": in_two_days,
                "next_step_date_words": "within 2 days",
            }
        )
        self.assertEqual(row["next_step_date"], in_two_days)

    def test_a_past_or_far_off_date_is_dropped(self):
        for date in (
            str(add_days(nowdate(), -3)),
            str(add_days(nowdate(), 900)),
            "soon",
        ):
            (row,) = self.split(
                {
                    "project": self.other,
                    "update": "- UAT ongoing",
                    "next_step_date": date,
                    "next_step_date_words": "within 2 days",
                }
            )
            self.assertIsNone(row["next_step_date"], date)

    def test_a_stage_or_wait_outside_the_options_is_dropped(self):
        (row,) = self.split(
            {"project": self.other, "stage": "Almost there", "waiting_on": "Gayathri"}
        )
        self.assertIsNone(row["stage"])
        self.assertIsNone(row["waiting_on"])

    def test_a_number_the_text_never_said_is_flagged_for_a_check(self):
        (row,) = self.split(
            {"project": self.other, "update": "- 14 of 20 modules tested"}
        )
        self.assertTrue(row["needs_check"])
        (row,) = self.split({"project": self.other, "update": "- UAT ongoing 2 days"})
        self.assertFalse(row["needs_check"])

    def test_two_mentions_of_one_project_become_one_row(self):
        (row,) = self.split(
            {"project": "Avera", "update": "- UAT ongoing", "stage": "Testing / UAT"},
            {
                "project": "Avera IoT",
                "update": "- Not live",
                "next_step": "Corrections",
            },
        )
        self.assertEqual(row["update_text"], "- UAT ongoing\n- Not live")
        self.assertEqual(
            (row["stage"], row["next_step"]), ("Testing / UAT", "Corrections")
        )

    def test_a_name_two_projects_share_points_to_neither(self):
        twin = {"project": "P-2", "project_name": "Avera Portal", "customer": None}
        index = project_status_ai.alias_index([*self.projects(), twin])
        self.assertNotIn("avera", index)
        self.assertEqual(
            project_status_ai.match_project("avera iot", index), self.other
        )

    def test_nothing_is_saved(self):
        self.split({"project": self.other, "update": "- UAT ongoing"})
        self.assertFalse(
            frappe.db.exists("HD Project Status Update", {"project": self.other})
        )

    def test_an_empty_text_or_missing_ai_says_so(self):
        with self.assertRaises(frappe.ValidationError):
            project_status_ai.split_update("  ", self.projects())
        with patch(AI_ON, return_value=False), self.assertRaises(
            frappe.ValidationError
        ):
            project_status_ai.split_update(self.TEXT, self.projects())

    def test_the_endpoint_offers_only_projects_the_user_may_write(self):
        with patch(AI_ON, return_value=True), patch(
            SPLIT,
            return_value=status_split_answer(
                {"project": self.other, "update": "- UAT"}
            ),
        ) as ai:
            with self.assertRaises(frappe.ValidationError):
                run_as_user(DEV[0], lambda: api.split_status_update(self.TEXT))
            result = run_as_user(COORD[0], lambda: api.split_status_update(self.TEXT))
        ai.assert_called_once()
        self.assertEqual([r["project"] for r in result["updates"]], [self.other])


class TestFridayReport(StatusReportCase):
    def test_default_recipients_are_system_managers_and_coordinators(self):
        recipients = project_status.report_recipients()
        self.assertIn(SYSTEM_MANAGER[0], recipients)
        self.assertIn(COORD[0], recipients)
        self.assertNotIn(DEV[0], recipients)
        self.assertNotIn("Administrator", recipients)

    def test_the_settings_list_replaces_the_default(self):
        set_status_report_recipients(PM[0], DEV[0])
        self.assertEqual(project_status.report_recipients(), sorted([PM[0], DEV[0]]))

    def test_a_disabled_recipient_is_left_out(self):
        frappe.db.set_value("User", DEV[0], "enabled", 0)
        set_status_report_recipients(PM[0], DEV[0])
        self.assertEqual(project_status.report_recipients(), [PM[0]])

    def test_everyone_listed_gets_the_report_with_attention_first(self):
        make_status_update(self.project, days_ago=1, stage="Live")
        make_task(self.project, "Late", add_days(nowdate(), -1))
        make_status_update(self.other, days_ago=1, waiting_on="Client")
        set_status_report_recipients(PM[0], LEAD[0])

        with patch(DELIVER) as deliver:
            project_status.send_weekly_report()

        self.assertEqual(
            [c.args[0] for c in deliver.call_args_list], sorted([PM[0], LEAD[0]])
        )
        subject, sections = deliver.call_args_list[0].args[1:]
        self.assertIn("Project status report", subject)
        headings = [h for h, _rows in sections]
        self.assertTrue(headings[0].startswith("Needs attention"))
        galom = [
            t for _h, rows in sections for t, _p in rows if "Galom Mobile App" in t
        ]
        self.assertIn("Live", galom[0])
        self.assertIn("1 overdue", galom[0])

    def test_one_failed_message_does_not_stop_the_rest(self):
        set_status_report_recipients(PM[0], LEAD[0])
        with patch(DELIVER, side_effect=[RuntimeError("mail down"), None]) as deliver:
            project_status.send_weekly_report()
        self.assertEqual(deliver.call_count, 2)

    def test_it_is_scheduled_for_friday_5pm(self):
        from helpdesk import hooks

        self.assertEqual(
            hooks.scheduler_events["cron"]["0 17 * * 5"],
            ["helpdesk.project_status.send_weekly_report"],
        )


class TestStaleReminder(StatusReportCase):
    def found(self, project=None, **settings):
        ctx = follow_up_context(now_datetime(), **settings)
        return [
            f
            for f in follow_ups.evaluate(ctx)
            if f.rule == "stale_status" and f.name == (project or self.project)
        ]

    def test_an_update_older_than_a_week_asks_the_lead_and_the_coordinators(self):
        make_status_update(self.project, days_ago=8)
        (found,) = self.found()
        self.assertEqual(set(found.recipients), {LEAD[0], COORD[0]})
        self.assertNotIn(DEV[0], found.recipients)
        self.assertEqual(found.days, 8)
        self.assertEqual(found.link, f"/project-status?project={self.project}")

    def test_a_fresh_update_asks_nobody(self):
        make_status_update(self.project, days_ago=project_status.STALE_DAYS)
        self.assertEqual(self.found(), [])

    def test_a_project_that_never_had_an_update_is_asked_after_a_week(self):
        age_project(self.project, 5)
        self.assertEqual(self.found(), [])
        age_project(self.project, 12)
        self.assertEqual(self.found()[0].days, 12)

    def test_a_paused_project_needs_no_weekly_update(self):
        make_status_update(self.project, days_ago=30, stage="On hold")
        self.assertEqual(self.found(), [])

    def test_a_project_that_is_not_open_is_not_asked(self):
        make_status_update(self.project, days_ago=30)
        frappe.db.set_value("Project", self.project, "status", "Completed")
        self.assertEqual(self.found(), [])

    def test_the_switch_turns_it_off(self):
        make_status_update(self.project, days_ago=30)
        self.assertEqual(self.found(project_status=0), [])

    def test_without_a_lead_the_managers_are_asked(self):
        make_status_update(self.project, days_ago=30)
        frappe.db.set_value("Project", self.project, "project_lead", None)
        (found,) = self.found()
        self.assertIn(PM[0], found.recipients)
        self.assertIn(COORD[0], found.recipients)

    def test_one_notice_per_person_and_project_and_it_stays_read(self):
        make_status_update(self.project, days_ago=8)
        ctx = follow_up_context(now_datetime())
        with patch("helpdesk.chat_notifications.post_escalation"):
            follow_ups.post_notices(follow_ups.evaluate(ctx), ctx.today)
            (notice,) = get_follow_up_notices(LEAD[0], self.project)
            frappe.db.set_value("HD Notification", notice.name, "read", 1)
            follow_ups.post_notices(follow_ups.evaluate(ctx), ctx.today)

        notices = get_follow_up_notices(LEAD[0], self.project)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].read, 1)
        self.assertIn("No status update for 8 days", notices[0].message)
        self.assertEqual(len(get_follow_up_notices(COORD[0], self.project)), 1)
        self.assertEqual(get_follow_up_notices(DEV[0], self.project), [])

    def test_writing_the_update_ends_the_reminder(self):
        make_status_update(self.project, days_ago=30)
        self.assertTrue(self.found())
        make_status_update(self.project)
        self.assertEqual(self.found(), [])

    def test_the_setting_is_on_by_default(self):
        self.assertEqual(
            frappe.get_meta("HD Follow Up Settings")
            .get_field("project_status")
            .default,
            "1",
        )
        self.assertTrue(set_follow_up_settings().project_status)
