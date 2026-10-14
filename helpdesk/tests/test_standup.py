import json
from datetime import datetime, time
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime

from helpdesk import home_plan, standup
from helpdesk.content_team import ensure_role
from helpdesk.test_utils import (
    TEST_TEAMS_CHANNEL_URL,
    add_company_holiday,
    call_as_user,
    call_mobile_as,
    enable_chat_notifications,
    get_standup_notices,
    hold_commits,
    log_hours,
    make_assigned_ticket,
    make_assignment,
    make_department,
    make_done_task,
    make_hd_leave,
    make_project,
    make_standup,
    make_task,
    make_task_in_status,
    make_tasky_user,
    make_ticket_communication,
    run_as_user,
    set_standup_settings,
    set_work_settings,
    standup_calendar,
    start_task_timer,
)

DEV = ("dev.su@standup.example", "Anu Varghese")
DEV2 = ("dev2.su@standup.example", "Biju Thomas")
LEAD = ("lead.su@standup.example", "Celine Joseph")
HEAD = ("head.su@standup.example", "Dileep Nair")
HELPER = ("helper.su@standup.example", "Elsa Mathew")
IDLE = ("idle.su@standup.example", "Faisal Rahman")
AWAY = ("away.su@standup.example", "Gita Menon")
OUTSIDER = ("outsider.su@standup.example", "Hari Kumar")
DEPARTMENT = "Standup Delivery"
OTHER_DEPARTMENT = "Standup Growth"
# Monday 12 Oct 2026; the test calendar has Sundays off
MONDAY = "2026-10-12"
SATURDAY = "2026-10-10"
FRIDAY = "2026-10-09"
THURSDAY = "2026-10-08"
TUESDAY = "2026-10-13"
DEPARTMENT_CHANNEL_URL = TEST_TEAMS_CHANNEL_URL.replace(
    "sig=test-channel", "sig=test-standup-delivery"
)


class StandupCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(frappe.clear_document_cache, standup.SETTINGS, standup.SETTINGS)
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        # tasks keep the due dates the tests give them
        set_work_settings(ai_task_estimates=0, ai_task_descriptions=0)
        for user in (DEV, DEV2, LEAD, HEAD, HELPER, IDLE, AWAY, OUTSIDER):
            make_tasky_user(*user)
        make_department(DEPARTMENT, heads=[{"user": HEAD[0]}])
        make_department(OTHER_DEPARTMENT)
        self.project = make_project(
            "Stand-up Rollout",
            members=[
                (DEV[0], "Developer"),
                (DEV2[0], "Developer"),
                (LEAD[0], "Developer"),
                (IDLE[0], "Developer"),
                (AWAY[0], "Developer"),
            ],
        ).name
        frappe.db.set_value(
            "Project",
            self.project,
            {"project_lead": LEAD[0], "custom_department": DEPARTMENT},
        )
        self.today = getdate(now_datetime())
        set_standup_settings(
            departments=[{"department": DEPARTMENT}],
            team_view_heads=1,
            team_view_leads=1,
            team_view_project_managers=1,
            opened_on=None,
            reminded_on=None,
            posted_on=None,
        )

    def task(self, subject, assignee=DEV, due=None, **values):
        """A task in the project given to `assignee`, with `values` set straight."""
        name = make_task(self.project, subject, due).name
        if assignee:
            make_assignment("Task", name, assignee[0])
        if values:
            frappe.db.set_value("Task", name, values, update_modified=False)
        return name

    def titles(self, rows):
        return [r["title"] for r in rows]


class TestWorkingDays(StandupCase):
    def test_yesterday_is_the_previous_working_day(self):
        self.assertEqual(
            standup_calendar(MONDAY).previous_working_day(), getdate(SATURDAY)
        )
        # Saturday off as well: Friday's work is "yesterday" on Monday
        self.assertEqual(
            standup_calendar(MONDAY, holidays=[SATURDAY]).previous_working_day(),
            getdate(FRIDAY),
        )
        # a holiday on Monday: Tuesday looks back past it and the Sunday
        self.assertEqual(
            standup_calendar(TUESDAY, holidays=[MONDAY]).previous_working_day(),
            getdate(SATURDAY),
        )

    def test_the_hub_calendar_skips_saturdays_off_and_holidays(self):
        set_work_settings(weekly_off="Sunday", saturdays_off="All")
        add_company_holiday(FRIDAY, "Standup test holiday")
        calendar = standup.WorkCalendar(getdate(MONDAY))
        self.assertEqual(calendar.previous_working_day(), getdate(THURSDAY))

    def test_yesterday_items_come_from_the_previous_working_day(self):
        friday = make_done_task(self.project, "Friday's GST report", DEV[0], FRIDAY)
        make_done_task(self.project, "Thursday's import", DEV[0], THURSDAY)
        filled = standup.autofill(
            DEV[0], MONDAY, standup_calendar(MONDAY, holidays=[SATURDAY])
        )
        self.assertEqual(filled["previous_day"], FRIDAY)
        self.assertEqual(self.titles(filled["yesterday"]), ["Friday's GST report"])
        self.assertEqual(filled["yesterday"][0]["reference_name"], friday)
        self.assertEqual(filled["yesterday"][0]["detail"], "Completed")


class TestAutofill(StandupCase):
    def test_yesterday_today_and_blockers_from_own_work(self):
        calendar = standup_calendar(self.today)
        previous = calendar.previous_working_day()
        tomorrow = calendar.next_working_day()
        make_done_task(self.project, "Configure GST", DEV[0], previous)
        resolved = make_assigned_ticket(
            "Invoice prints the wrong GSTIN",
            DEV[0],
            status="Resolved",
            status_category="Resolved",
            resolution_date=f"{previous} 15:00:00",
        )
        replied = make_assigned_ticket("Stock entry fails after closing", DEV[0])
        reply = run_as_user(
            DEV[0],
            lambda: make_ticket_communication(
                replied, "Sent the fix", DEV[0], sent_or_received="Sent"
            ),
        )
        frappe.db.set_value(
            "Communication", reply.name, "creation", f"{previous} 11:00:00"
        )
        log_hours(DEV[0], self.project, 6.5, previous)

        self.task("Bank reconciliation", due=self.today)
        working = self.task("Payroll export", due=add_days(self.today, 5))
        start_task_timer(working, hours_ago=1)
        self.task("Opening balances", due=tomorrow)
        self.task("Item master", due=add_days(self.today, -3))
        self.task("Later work", due=add_days(self.today, 20))

        self.task(
            "Customer GST file",
            status="On Hold",
            hold_reason="Waiting on customer",
            hold_note="They send it on Friday",
            hold_since=add_days(self.today, -2),
        )
        blocking = self.task("API keys from the client", assignee=DEV2)
        self.task("Connect the bank feed", depends_on_task=blocking)
        self.task("Go-live checklist", due=add_days(self.today, -1), is_key=1)
        frappe.cache.set_value(
            home_plan.plan_cache_key(DEV[0]),
            {"steps": [{"text": "Finish the bank reconciliation first."}]},
        )
        self.addCleanup(frappe.cache.delete_value, home_plan.plan_cache_key(DEV[0]))

        with patch.object(standup, "call_haiku") as ai:
            filled = standup.autofill(DEV[0], self.today, calendar)
        ai.assert_not_called()

        yesterday = {r["title"]: r["detail"] for r in filled["yesterday"]}
        self.assertEqual(yesterday["Configure GST"], "Completed")
        self.assertEqual(yesterday["Invoice prints the wrong GSTIN"], "Resolved")
        self.assertEqual(yesterday["Stock entry fails after closing"], "Replied")
        self.assertEqual(filled["hours"], 6.5)
        self.assertEqual(
            {r["reference_name"] for r in filled["yesterday"] if r["kind"] == "ticket"},
            {resolved, replied},
        )

        today = self.titles(filled["today"])
        self.assertEqual(
            today,
            [
                "Item master",
                "Bank reconciliation",
                "Payroll export",
                "Opening balances",
                "Finish the bank reconciliation first.",
            ],
        )
        details = {r["title"]: r["detail"] for r in filled["today"]}
        self.assertEqual(details["Payroll export"], "In progress, timer running")
        self.assertEqual(details["Bank reconciliation"], "Due today")

        blockers = {r["title"]: r["detail"] for r in filled["blockers"]}
        self.assertEqual(
            blockers["Customer GST file"],
            "On hold 2 day(s): Waiting on customer · They send it on Friday",
        )
        self.assertEqual(
            blockers["Connect the bank feed"], "Waiting on API keys from the client"
        )
        self.assertTrue(blockers["Go-live checklist"].startswith("Key task, overdue"))
        # every item links to its record
        self.assertTrue(
            all(
                r["reference_name"]
                for s in ("yesterday", "blockers")
                for r in filled[s]
            )
        )

    def test_someone_elses_work_is_not_listed(self):
        self.task("Bank reconciliation", assignee=DEV2, due=self.today)
        filled = standup.autofill(DEV[0], self.today, standup_calendar(self.today))
        self.assertNotIn("Bank reconciliation", self.titles(filled["today"]))


class TestDrafts(StandupCase):
    def open(self):
        settings = standup.get_settings()
        return standup.open_drafts(settings, self.today, standup_calendar(self.today))

    def test_drafts_for_people_with_work_once(self):
        self.task("Bank reconciliation", due=self.today)
        self.task("Payroll export", assignee=AWAY, due=self.today)
        make_hd_leave(AWAY[0], self.today, add_days(self.today, 1))

        created = self.open()
        mine = standup.standup_name(DEV[0], self.today)
        self.assertIn(mine, created)
        self.assertFalse(
            frappe.db.exists(standup.STANDUP, standup.standup_name(AWAY[0], self.today))
        )
        # a member with no open work and nothing done yesterday gets none
        self.assertFalse(
            frappe.db.exists(standup.STANDUP, standup.standup_name(IDLE[0], self.today))
        )
        doc = frappe.get_doc(standup.STANDUP, mine)
        self.assertEqual(doc.status, "Draft")
        self.assertEqual(doc.department, DEPARTMENT)
        self.assertEqual(
            get_standup_notices(DEV[0], mine),
            ["Your stand-up is ready, check it and submit (1 min)"],
        )

        self.assertNotIn(mine, self.open())
        self.assertEqual(
            frappe.db.count(standup.STANDUP, {"user": DEV[0], "date": self.today}),
            1,
        )
        self.assertEqual(len(get_standup_notices(DEV[0], mine)), 1)

    def test_idle_people_with_work_done_yesterday_get_one(self):
        previous = standup_calendar(self.today).previous_working_day()
        make_done_task(self.project, "Configure GST", IDLE[0], previous)
        self.assertIn(standup.standup_name(IDLE[0], self.today), self.open())

    def test_departments_not_in_the_stand_up_are_left_out(self):
        self.task("Bank reconciliation", due=self.today)
        set_standup_settings(departments=[{"department": OTHER_DEPARTMENT}])
        self.assertNotIn(standup.standup_name(DEV[0], self.today), self.open())


class TestSubmit(StandupCase):
    def test_edit_and_submit(self):
        kept = self.task("Bank reconciliation", due=self.today)
        dropped = self.task("Payroll export", due=self.today)
        self.task(
            "Customer GST file", status="On Hold", hold_reason="Other", hold_note="x"
        )
        foreign = self.task("Not mine", assignee=DEV2, due=self.today)
        mine = call_as_user(DEV[0], "helpdesk.api.standup.get_my_standup")
        self.assertIsNone(mine["standup"]["name"])
        today = mine["standup"]["today"]
        self.assertEqual({r["reference_name"] for r in today}, {kept, dropped})

        values = {
            "today": [
                next(r for r in today if r["reference_name"] == kept),
                # linked work that wasn't on the stand-up can't be added
                {
                    "kind": "task",
                    "title": "Not mine",
                    "reference_doctype": "Task",
                    "reference_name": foreign,
                },
                {"title": "Call Malabar Traders about <b>the</b> GST file"},
            ],
            "blockers": [{"title": "Waiting for VPN access"}],
            "notes": {"yesterday": "Mostly the GST setup"},
            "needs_help": 1,
        }
        result = call_as_user(
            DEV[0], "helpdesk.api.standup.submit_standup", values=values
        )
        doc = frappe.get_doc(standup.STANDUP, result["standup"]["name"])
        self.assertEqual(doc.status, "Submitted")
        self.assertTrue(doc.submitted_on)
        self.assertTrue(doc.needs_help)
        self.assertEqual(doc.yesterday_note, "Mostly the GST setup")
        self.assertEqual(
            [(r.kind, r.title, r.reference_name) for r in doc.today],
            [
                ("task", "Bank reconciliation", kept),
                ("note", "Call Malabar Traders about the GST file", None),
            ],
        )
        # blockers sent replace the filled-in ones
        self.assertEqual([r.title for r in doc.blockers], ["Waiting for VPN access"])
        self.assertTrue(result["editable"])

    def test_past_days_are_read_only(self):
        self.task("Bank reconciliation", due=self.today)
        yesterday = add_days(self.today, -1)
        make_standup(DEV[0], yesterday, DEPARTMENT, status="Submitted")
        past = call_as_user(
            DEV[0], "helpdesk.api.standup.get_my_standup", date=str(yesterday)
        )
        self.assertFalse(past["editable"])
        self.assertEqual(past["standup"]["status"], "Submitted")

    def test_no_stand_up_outside_the_departments_in_it(self):
        self.task("Bank reconciliation", due=self.today)
        set_standup_settings(departments=[{"department": OTHER_DEPARTMENT}])
        mine = call_as_user(DEV[0], "helpdesk.api.standup.get_my_standup")
        self.assertIsNone(mine["standup"])
        self.assertFalse(mine["editable"])
        with self.assertRaises(frappe.ValidationError):
            call_as_user(DEV[0], "helpdesk.api.standup.save_standup", values={})

    def test_nothing_is_saved_while_switched_off(self):
        set_standup_settings(enabled=0)
        with self.assertRaises(frappe.ValidationError):
            call_as_user(DEV[0], "helpdesk.api.standup.save_standup", values={})


class TestReminder(StandupCase):
    def test_the_reminder_goes_once(self):
        draft = make_standup(DEV[0], self.today, DEPARTMENT).name
        done = make_standup(DEV2[0], self.today, DEPARTMENT, status="Submitted").name
        set_standup_settings(opened_on=self.today)
        settings = standup.get_settings()
        at = datetime.combine(self.today, time(10, 5))
        with patch.object(standup, "post_summaries"):
            standup.process(settings, at)
            standup.process(standup.get_settings(), at)
            standup.send_reminders(standup.get_settings(), self.today)
        self.assertEqual(
            get_standup_notices(DEV[0], draft),
            ["Your stand-up isn't submitted yet. It goes to your team at 10:30."],
        )
        self.assertEqual(get_standup_notices(DEV2[0], done), [])

    def test_the_long_steps_run_on_the_long_queue(self):
        at = datetime.combine(self.today, time(10, 45))
        with patch("frappe.enqueue") as enqueue, patch.object(
            standup, "send_reminders"
        ):
            standup.process(standup.get_settings(), at)
        self.assertEqual(
            [c.args[0] for c in enqueue.call_args_list],
            ["helpdesk.standup.open_drafts_job", "helpdesk.standup.post_summaries_job"],
        )
        for call in enqueue.call_args_list:
            self.assertEqual(call.kwargs["queue"], "long")
            self.assertEqual(call.kwargs["day"], str(self.today))

    def test_nothing_runs_before_its_time(self):
        settings = standup.get_settings()
        early = datetime.combine(self.today, time(8, 45))
        with patch.object(standup, "open_drafts") as opened:
            standup.process(settings, early)
        opened.assert_not_called()


class TestSummary(StandupCase):
    def setUp(self):
        super().setUp()
        enable_chat_notifications(teams_channel_webhook=TEST_TEAMS_CHANNEL_URL)
        self.addCleanup(
            frappe.clear_document_cache, "HD Chat Settings", "HD Chat Settings"
        )
        set_standup_settings(
            departments=[
                {"department": DEPARTMENT, "channel_webhook": DEPARTMENT_CHANNEL_URL}
            ]
        )
        held = self.task("Customer GST file", status="On Hold")
        make_standup(
            DEV[0],
            self.today,
            DEPARTMENT,
            yesterday=[{"kind": "note", "title": "Configured GST"}],
            today=[{"kind": "note", "title": "Bank reconciliation"}],
        )
        make_standup(
            DEV2[0],
            self.today,
            DEPARTMENT,
            status="Submitted",
            needs_help=1,
            today=[{"kind": "note", "title": "Payroll export"}],
            blockers=[
                {
                    "kind": "task",
                    "title": "Customer GST file",
                    "detail": "On hold 3 day(s): Waiting on customer",
                    "reference_doctype": "Task",
                    "reference_name": held,
                    "project": self.project,
                }
            ],
        )
        post = patch("helpdesk.chat_notifications.requests.post")
        self.post = post.start()
        self.post.return_value = MagicMock(status_code=202)
        self.addCleanup(post.stop)
        ai_on = patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True)
        ai_on.start()
        self.addCleanup(ai_on.stop)

    def posted_text(self):
        self.assertEqual(self.post.call_count, 1)
        url = self.post.call_args.args[0]
        card = self.post.call_args.kwargs["json"]["attachments"][0]["content"]
        return url, card["body"][0]["text"]

    def test_blockers_first_and_drafts_marked_auto(self):
        with patch.object(standup, "call_haiku", side_effect=Exception("AI is down")):
            standup.post_summaries(standup.get_settings(), self.today)
        url, text = self.posted_text()
        self.assertEqual(url, DEPARTMENT_CHANNEL_URL)
        lines = [line for line in text.split("\n") if line]
        self.assertTrue(lines[0].startswith(f"**Stand-up · {DEPARTMENT}"))
        # no headline when the AI fails: the blockers come right after the title
        self.assertEqual(lines[1], "**Blockers and help needed (1)**")
        self.assertIn("Biju Thomas (needs help): [Customer GST file]", lines[2])
        self.assertLess(
            lines.index("**Blockers and help needed (1)**"),
            lines.index("**Anu Varghese (auto)**"),
        )
        self.assertIn("**Biju Thomas**", lines)
        self.assertIn("Today: Bank reconciliation", text)
        self.assertIn(
            f"/helpdesk/standup?team=Standup+Delivery&date={self.today}", text
        )
        self.assertEqual(
            frappe.db.get_value(
                standup.STANDUP, standup.standup_name(DEV[0], self.today), "status"
            ),
            "Auto-posted",
        )

    def test_ai_headline_with_the_number_guard(self):
        answer = {
            "response": {
                "lines": [
                    "Anu Varghese configured GST.",
                    "Biju Thomas needs help with the Customer GST file.",
                    "The team closed 37 tasks.",
                ]
            }
        }
        with patch.object(standup, "call_haiku", return_value=answer):
            standup.post_summaries(standup.get_settings(), self.today)
        _url, text = self.posted_text()
        lines = [line for line in text.split("\n") if line]
        self.assertEqual(lines[1], "Anu Varghese configured GST.")
        self.assertEqual(lines[2], "Biju Thomas needs help with the Customer GST file.")
        self.assertNotIn("37 tasks", text)

    def test_departments_left_out_are_not_posted(self):
        set_standup_settings(departments=[{"department": OTHER_DEPARTMENT}])
        with patch.object(standup, "call_haiku", side_effect=Exception("down")):
            posted = standup.post_summaries(standup.get_settings(), self.today)
        self.assertEqual(posted, {})
        self.post.assert_not_called()

    def test_without_a_department_channel_the_escalation_channel(self):
        set_standup_settings(departments=[{"department": DEPARTMENT}])
        with patch.object(standup, "call_haiku", side_effect=Exception("down")):
            standup.post_summaries(standup.get_settings(), self.today)
        url, _text = self.posted_text()
        self.assertEqual(url, TEST_TEAMS_CHANNEL_URL)


class TestPermissions(StandupCase):
    def setUp(self):
        super().setUp()
        self.held = self.task("Customer GST file", status="On Hold")
        self.mine = make_standup(
            DEV[0],
            self.today,
            DEPARTMENT,
            today=[{"kind": "note", "title": "Bank reconciliation"}],
            blockers=[
                {
                    "kind": "task",
                    "title": "Customer GST file",
                    "reference_doctype": "Task",
                    "reference_name": self.held,
                    "project": self.project,
                }
            ],
        )

    def team(self, user, team=DEPARTMENT, **kwargs):
        return call_as_user(
            user, "helpdesk.api.standup.get_team_standup", team=team, **kwargs
        )

    def test_members_see_their_department_read_only(self):
        view = self.team(DEV2[0])
        self.assertFalse(view["can_lead"])
        self.assertEqual([p["user"] for p in view["people"]], [DEV[0]])
        self.assertNotIn("plan_vs_done", view["people"][0])
        with self.assertRaises(frappe.PermissionError):
            self.team(DEV2[0], OTHER_DEPARTMENT)
        with self.assertRaises(frappe.PermissionError):
            call_as_user(DEV2[0], "helpdesk.api.standup.nudge", name=self.mine.name)
        with self.assertRaises(frappe.PermissionError):
            call_as_user(
                DEV2[0],
                "helpdesk.api.standup.get_standup_history",
                user=DEV[0],
            )

    def test_heads_and_leads_get_the_team_view(self):
        self.assertTrue(self.team(HEAD[0])["can_lead"])
        self.assertTrue(self.team(LEAD[0])["can_lead"])
        call_as_user(LEAD[0], "helpdesk.api.standup.nudge", name=self.mine.name)
        self.assertIn(
            "Celine Joseph is waiting for your stand-up: check it and submit (1 min)",
            get_standup_notices(DEV[0], self.mine.name),
        )
        history = call_as_user(
            HEAD[0], "helpdesk.api.standup.get_standup_history", user=DEV[0]
        )
        self.assertEqual([h["name"] for h in history["items"]], [self.mine.name])

    def test_settings_decide_who_leads(self):
        set_standup_settings(team_view_leads=0)
        self.assertFalse(self.team(LEAD[0])["can_lead"])
        with self.assertRaises(frappe.PermissionError):
            self.team(OUTSIDER[0])

    def test_plan_against_done(self):
        previous = standup_calendar(self.today).previous_working_day()
        planned = self.task("Payroll export")
        frappe.db.delete(standup.STANDUP, {"name": self.mine.name})
        link = {"kind": "task", "reference_doctype": "Task", "project": self.project}
        make_standup(
            DEV[0],
            previous,
            DEPARTMENT,
            today=[
                {**link, "title": "Payroll export", "reference_name": planned},
                {**link, "title": "Customer GST file", "reference_name": self.held},
            ],
        )
        make_standup(
            DEV[0],
            self.today,
            DEPARTMENT,
            yesterday=[{**link, "title": "Payroll export", "reference_name": planned}],
        )
        person = self.team(HEAD[0])["people"][0]
        self.assertEqual(
            person["plan_vs_done"], {"planned": 2, "done": 1, "unplanned": 0}
        )

    def test_department_walls(self):
        ensure_role()
        walled = make_tasky_user(
            "walled.su@standup.example", "Indu Pillai", roles=("ERP Employee",)
        )
        make_department("Digital")
        for department in ("Digital", DEPARTMENT):
            doc = frappe.get_doc("HD Department", department)
            doc.append("heads", {"user": walled})
            doc.save(ignore_permissions=True)
        self.assertNotIn("Digital", standup.team_departments(walled))
        self.assertIn(DEPARTMENT, standup.team_departments(walled))
        frappe.db.set_value("Project", self.project, "custom_department", "Digital")
        view = self.team(walled)
        self.assertEqual(view["people"][0]["blockers"], [])
        self.assertEqual(view["blockers"], [])


class TestBlockerActions(StandupCase):
    def setUp(self):
        super().setUp()
        self.held = self.task("Customer GST file", status="On Hold")
        self.mine = make_standup(
            DEV[0],
            self.today,
            DEPARTMENT,
            blockers=[
                {
                    "kind": "task",
                    "title": "Customer GST file",
                    "reference_doctype": "Task",
                    "reference_name": self.held,
                    "project": self.project,
                },
                {"kind": "note", "title": "Waiting for VPN access"},
            ],
        )
        self.task_row = self.mine.blockers[0].name
        self.note_row = self.mine.blockers[1].name

    def test_assign_help(self):
        row = call_as_user(
            LEAD[0],
            "helpdesk.api.standup.assign_help",
            name=self.mine.name,
            row=self.task_row,
            helper=HELPER[0],
        )
        self.assertEqual(row["helper"], HELPER[0])
        self.assertTrue(
            frappe.db.exists(
                "ToDo",
                {
                    "reference_type": "Task",
                    "reference_name": self.held,
                    "allocated_to": HELPER[0],
                    "status": "Open",
                },
            )
        )
        notices = frappe.get_all(
            "HD Notification",
            filters={"user_to": HELPER[0], "reference_name": self.held},
            pluck="message",
        )
        self.assertIn(
            "Celine Joseph asked you to help Anu Varghese: Customer GST file", notices
        )
        # a blocker in words: the helper is told, nothing is assigned
        call_as_user(
            HEAD[0],
            "helpdesk.api.standup.assign_help",
            name=self.mine.name,
            row=self.note_row,
            helper=DEV2[0],
        )
        self.assertEqual(
            get_standup_notices(DEV2[0], self.mine.name),
            ["Dileep Nair asked you to help Anu Varghese: Waiting for VPN access"],
        )
        with self.assertRaises(frappe.PermissionError):
            call_as_user(
                DEV2[0],
                "helpdesk.api.standup.assign_help",
                name=self.mine.name,
                row=self.note_row,
                helper=HELPER[0],
            )

    def test_create_task_from_blocker(self):
        result = call_as_user(
            LEAD[0],
            "helpdesk.api.standup.create_task_from_blocker",
            name=self.mine.name,
            row=self.note_row,
            project=self.project,
            subject="Get VPN access for Anu",
            assigned_to=HELPER[0],
        )
        task = frappe.get_doc("Task", result["task"])
        self.assertEqual(task.subject, "Get VPN access for Anu")
        self.assertIn("Waiting for VPN access", task.description)
        self.assertEqual(result["blocker"]["help_task"], task.name)
        self.mine.reload()
        self.assertEqual(self.mine.blockers[1].help_task, task.name)


class TestMobile(StandupCase):
    def test_shapes(self):
        task = self.task("Bank reconciliation", due=self.today)
        answer = call_mobile_as(DEV[0], "get_my_standup")
        self.assertEqual(answer["v"], 1)
        data = answer["data"]
        for key in ("enabled", "date", "editable", "post_at", "standup", "teams"):
            self.assertIn(key, data)
        row = data["standup"]["today"][0]
        self.assertEqual(row["reference_name"], task)
        self.assertEqual(row["app_route"], f"/task/{task}")
        for key in ("id", "kind", "title", "detail", "route", "auto"):
            self.assertIn(key, row)

        saved = call_mobile_as(
            DEV[0],
            "save_standup",
            values=json.dumps({"today": [row], "needs_help": 1}),
        )["data"]["standup"]
        self.assertEqual(saved["status"], "Draft")
        self.assertTrue(saved["needs_help"])
        submitted = call_mobile_as(DEV[0], "submit_standup")["data"]["standup"]
        self.assertEqual(submitted["status"], "Submitted")

        team = call_mobile_as(HEAD[0], "get_team_standup", team=DEPARTMENT)["data"]
        for key in ("team", "can_lead", "people", "blockers", "counts", "on_leave"):
            self.assertIn(key, team)
        self.assertEqual(team["counts"]["submitted"], 1)
        self.assertEqual(team["people"][0]["today"][0]["app_route"], f"/task/{task}")
