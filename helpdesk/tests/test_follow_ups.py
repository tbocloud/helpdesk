from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, getdate

from helpdesk import follow_ups
from helpdesk.test_utils import (
    FOLLOW_UP_MONDAY,
    call_as_user,
    follow_up_context,
    get_follow_up_notices,
    hold_commits,
    make_assigned_ticket,
    make_assignment,
    make_department,
    make_hd_leave,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
    run_as_user,
    set_follow_up_settings,
    set_work_settings,
)

DEV = ("dev.fu@follow-ups.example", "Anu Varghese")
LEAD = ("lead.fu@follow-ups.example", "Biju Thomas")
PM = ("pm.fu@follow-ups.example", "Celine Joseph")
COORD = ("coord.fu@follow-ups.example", "Dileep Nair")
HEAD = ("head.fu@follow-ups.example", "Elsa Mathew")
MANAGER = ("manager.fu@follow-ups.example", "Faisal Rahman")
DEPARTMENT = "Follow-up Delivery"
# FOLLOW_UP_MONDAY is Monday 12 Oct 2026, 11:00; the test calendar has Sundays off
FRIDAY = "2026-10-09"
THURSDAY = "2026-10-08"
WEDNESDAY = "2026-10-07"
LAST_MONDAY = "2026-10-05"
SATURDAY = "2026-10-10"
TUESDAY = "2026-10-13"
SETTINGS = "HD Follow Up Settings"


class FollowUpCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(follow_ups.clear_cache)
        self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        channel = patch("helpdesk.chat_notifications.post_escalation")
        self.channel = channel.start()
        self.addCleanup(channel.stop)
        mail = patch("frappe.sendmail")
        self.sendmail = mail.start()
        self.addCleanup(mail.stop)
        # the plan for today has its own tests (test_home_plan)
        plan = patch.object(follow_ups, "plan_steps", return_value=[])
        plan.start()
        self.addCleanup(plan.stop)
        # tasks keep the due dates the tests give them
        set_work_settings(ai_task_estimates=0, ai_task_descriptions=0)

        for user in (DEV, LEAD, COORD, HEAD):
            make_tasky_user(*user)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_department(DEPARTMENT, heads=[{"user": HEAD[0]}])
        self.project = make_project(
            "Follow-up Rollout",
            members=[
                (DEV[0], "Developer"),
                (LEAD[0], "Developer"),
                (COORD[0], "Project Coordinator"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value(
            "Project",
            self.project,
            {"project_lead": LEAD[0], "custom_department": DEPARTMENT},
        )

    def task(self, subject, due=None, assignee=DEV, **values):
        """A task the project manager gives `assignee`, with `values` set straight."""

        def create():
            name = make_task(self.project, subject, due).name
            if assignee:
                make_assignment("Task", name, assignee[0])
            return name

        name = run_as_user(PM[0], create)
        if values:
            frappe.db.set_value("Task", name, values, update_modified=False)
        return name

    def found(self, name, ctx=None, rule=None, **settings):
        ctx = ctx or follow_up_context(**settings)
        return [
            f
            for f in follow_ups.evaluate(ctx)
            if f.name == str(name) and (rule is None or f.rule == rule)
        ]

    def one(self, name, rule, ctx=None, **settings):
        found = self.found(name, ctx, rule, **settings)
        self.assertEqual(len(found), 1, found)
        return found[0]


class TestOverdueLadder(FollowUpCase):
    def test_each_level_adds_people(self):
        l1 = self.one(self.task("Import item master", FRIDAY), "overdue")
        l2 = self.one(self.task("Configure GST", WEDNESDAY), "overdue")
        l3 = self.one(self.task("Opening balances", LAST_MONDAY), "overdue")

        self.assertEqual((l1.level, l1.days), (1, 2))
        self.assertEqual(set(l1.recipients), {DEV[0], PM[0], LEAD[0]})
        self.assertEqual(l2.level, 2)
        self.assertTrue(
            {DEV[0], PM[0], LEAD[0], COORD[0], HEAD[0]} <= set(l2.recipients)
        )
        self.assertNotIn(MANAGER[0], l2.recipients)
        self.assertEqual(l3.level, 3)
        self.assertIn(MANAGER[0], l3.recipients)
        self.assertIn("Escalated to head", l2.text)

    def test_key_tasks_and_milestones_escalate_one_level_sooner(self):
        key = self.one(self.task("Go-live", FRIDAY, is_key=1), "overdue")
        milestone = self.one(
            self.task("UAT sign-off", FRIDAY, is_milestone=1), "overdue"
        )

        self.assertEqual(key.level, 2)
        self.assertEqual(milestone.level, 2)
        self.assertTrue(key.immediate)
        self.assertEqual(
            self.one(
                self.task("Data import", FRIDAY, is_key=1),
                "overdue",
                key_tasks_escalate_faster=0,
            ).level,
            1,
        )

    def test_weekends_and_holidays_are_not_counted(self):
        task = self.task("Bank reconciliation", THURSDAY)

        # Friday, Saturday and Monday; Sunday is off
        self.assertEqual(self.one(task, "overdue").days, 3)
        on_holiday = follow_up_context(holidays=[FRIDAY])
        self.assertEqual(self.one(task, "overdue", on_holiday).days, 2)
        self.assertEqual(self.one(task, "overdue", on_holiday).level, 1)

    def test_it_stops_when_completed_or_on_hold(self):
        done = self.task("Payroll setup", LAST_MONDAY)
        held = self.task("Stock opening", LAST_MONDAY)
        frappe.db.set_value("Task", done, "status", "Completed")
        frappe.db.set_value("Task", held, {"status": "On Hold", "hold_since": FRIDAY})

        self.assertEqual(self.found(done, rule="overdue"), [])
        self.assertEqual(self.found(held, rule="overdue"), [])


class TestTaskRules(FollowUpCase):
    def test_due_on_the_next_working_day(self):
        task = self.task("Share UAT build", TUESDAY)
        self.assertEqual(self.one(task, "due_tomorrow").recipients, [DEV[0]])

        # on Saturday the next working day is Monday
        saturday = follow_up_context(datetime(2026, 10, 10, 11, 0))
        monday_task = self.task("Collect sign-off", "2026-10-12")
        self.assertEqual(len(self.found(monday_task, saturday, "due_tomorrow")), 1)

    def test_due_today_not_started_morning_then_afternoon(self):
        task = self.task("Send invoice", "2026-10-12")

        morning = self.one(task, "due_today")
        three_pm = follow_up_context(datetime(2026, 10, 12, 15, 0))
        afternoon = self.one(task, "due_today", three_pm)
        self.assertEqual(morning.stage, "morning")
        # the clock and the setting it is compared with, should this ever fail
        self.assertEqual(
            afternoon.stage,
            "afternoon",
            (three_pm.now, three_pm.settings.afternoon_nudge_at),
        )

        frappe.db.set_value("Task", task, "status", "Working")
        self.assertEqual(self.found(task, rule="due_today"), [])

    def test_untouched_nudges_the_assignee_then_the_assigner(self):
        task = self.task("Write test cases", TUESDAY)
        todo = {"reference_type": "Task", "reference_name": task}

        frappe.db.set_value("ToDo", todo, "creation", f"{FRIDAY} 10:00:00")
        nudge = self.one(task, "untouched")
        self.assertEqual((nudge.level, nudge.recipients), (0, [DEV[0]]))

        frappe.db.set_value("ToDo", todo, "creation", f"{WEDNESDAY} 10:00:00")
        self.assertEqual(set(self.one(task, "untouched").recipients), {DEV[0], PM[0]})

        run_as_user(
            DEV[0],
            lambda: frappe.get_doc("Task", task).add_comment(
                "Comment", "Starting after the client call"
            ),
        )
        self.assertEqual(self.found(task, rule="untouched"), [])

    def test_waiting_review_reminds_the_reviewer_then_the_lead(self):
        task = self.task("Customize print format", TUESDAY, status="Pending Review")
        frappe.db.set_value(
            "Task", task, "modified", f"{FRIDAY} 10:00:00", update_modified=False
        )
        first = self.one(task, "review")
        self.assertEqual((first.level, first.recipients), (1, [COORD[0], LEAD[0]]))
        self.assertNotIn(DEV[0], first.recipients)

    def test_on_hold_asks_the_holder_and_waiting_on_customer_asks_to_follow_up(self):
        task = self.task(
            "Price list import",
            TUESDAY,
            status="On Hold",
            hold_since=WEDNESDAY,
            hold_by=LEAD[0],
            hold_reason="Waiting on customer",
        )
        held = self.one(task, "hold")
        self.assertEqual(set(held.recipients), {LEAD[0], DEV[0]})
        self.assertIn("follow up with them", held.text)
        self.assertEqual(self.found(task, rule="hold", hold_days=5), [])

    def test_no_due_date_asks_the_assigner(self):
        task = self.task("Plan training", None, creation=f"{WEDNESDAY} 09:00:00")
        self.assertEqual(self.one(task, "no_due_date").recipients, [PM[0]])

    def test_overdue_blocker_hears_who_is_waiting(self):
        blocker = self.task("Chart of accounts", FRIDAY)
        waiting = self.task("Opening entries", TUESDAY, assignee=COORD)
        frappe.db.set_value("Task", waiting, "depends_on_task", blocker)

        alert = self.one(blocker, "blocked")
        self.assertEqual(alert.recipients, [DEV[0]])
        self.assertIn("Opening entries", alert.text)


class TestTicketRules(FollowUpCase):
    def ticket(self, subject, assignee=DEV, **values):
        values = {"sla": None, "response_by": None, "status_category": "Open", **values}
        if assignee:
            return make_assigned_ticket(subject, assignee[0], **values)
        name = str(make_ticket(subject=subject).name)
        frappe.db.set_value("HD Ticket", name, {"_assign": None, **values})
        frappe.db.delete(
            "ToDo", {"reference_type": "HD Ticket", "reference_name": name}
        )
        return name

    def sla(self, hours_used, hours_left):
        return self.ticket(
            "Invoice mismatch",
            first_responded_on=FOLLOW_UP_MONDAY,
            service_level_agreement_creation=add_to_date(
                FOLLOW_UP_MONDAY, hours=-hours_used
            ),
            resolution_by=add_to_date(FOLLOW_UP_MONDAY, hours=hours_left),
        )

    def test_sla_warnings_then_breach_climb_the_ladder(self):
        half = self.one(self.sla(5, 5), "sla")
        late = self.one(self.sla(8, 2), "sla")
        breach = self.one(self.sla(10, -1), "sla")

        self.assertEqual((half.stage, half.recipients), ("resolution:50", [DEV[0]]))
        self.assertEqual(late.level, 1)
        # without a support department, the team lead is the Agent Managers
        self.assertIn(MANAGER[0], late.recipients)
        self.assertEqual((breach.severity, breach.level), ("breach", 2))
        self.assertTrue(breach.immediate)
        self.assertEqual(self.found(self.sla(1, 9), rule="sla"), [])

    def test_support_department_heads_are_the_team_lead(self):
        late = self.one(self.sla(8, 2), "sla", ticket_department=DEPARTMENT)
        self.assertIn(HEAD[0], late.recipients)
        self.assertNotIn(MANAGER[0], late.recipients)

    def test_unassigned_ticket_alerts_the_managers(self):
        old = self.ticket(
            "Printer setup", None, creation=add_to_date(FOLLOW_UP_MONDAY, hours=-2)
        )
        new = self.ticket(
            "VPN down", None, creation=add_to_date(FOLLOW_UP_MONDAY, minutes=-10)
        )
        self.assertIn(MANAGER[0], self.one(old, "unassigned").recipients)
        self.assertEqual(self.found(new, rule="unassigned"), [])

    def test_customer_replied_nudges_then_escalates(self):
        def replied(hours):
            return self.ticket(
                "Stock report wrong",
                first_responded_on=add_to_date(FOLLOW_UP_MONDAY, days=-2),
                last_agent_response=add_to_date(FOLLOW_UP_MONDAY, days=-1),
                last_customer_response=add_to_date(FOLLOW_UP_MONDAY, hours=-hours),
            )

        nudge = self.one(replied(5), "customer_replied")
        self.assertEqual((nudge.level, nudge.recipients), (0, [DEV[0]]))
        self.assertEqual(self.one(replied(9), "customer_replied").level, 1)
        self.assertEqual(self.found(replied(1), rule="customer_replied"), [])

    def waiting_on_customer(self, **values):
        return self.ticket(
            "Need your approval",
            status="Replied",
            status_category="Paused",
            raised_by="buyer@follow-ups.example",
            last_agent_response=f"{WEDNESDAY} 10:00:00",
            **values,
        )

    def test_waiting_on_customer_asks_the_assignee_when_emails_are_off(self):
        ticket = self.waiting_on_customer()
        nudge = self.one(ticket, "awaiting_customer")
        self.assertEqual(nudge.recipients, [DEV[0]])

    def test_customer_gets_one_follow_up_email_then_the_assignee_is_asked_to_close(
        self,
    ):
        ticket = self.waiting_on_customer()
        ctx = follow_up_context(customer_follow_up_email=1)
        with patch(
            "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.HDTicket.reply_via_agent"
        ) as reply:
            follow_ups.process(ctx)
        # other tickets in the database may be waiting too; count this one's
        [mine] = [
            c for c in reply.call_args_list if f"#{ticket}:" in c.kwargs["message"]
        ]
        self.assertEqual(mine.kwargs["to"], "buyer@follow-ups.example")
        self.assertTrue(
            frappe.db.get_value("HD Ticket", ticket, "custom_customer_followed_up_on")
        )

        # the email went; nothing more until the auto-close wait is over
        self.assertEqual(
            self.found(ticket, follow_up_context(customer_follow_up_email=1)), []
        )
        frappe.db.set_value(
            "HD Ticket", ticket, "custom_customer_followed_up_on", "2026-09-01 10:00:00"
        )
        frappe.db.set_value(
            "HD Ticket", ticket, "last_agent_response", "2026-09-01 10:00:00"
        )
        close = self.one(
            ticket, "awaiting_customer", follow_up_context(customer_follow_up_email=1)
        )
        self.assertEqual(close.stage, "close")

        # with HD Settings' auto-close on for this status, the daily job closes it
        frappe.db.set_single_value(
            "HD Settings", {"auto_close_tickets": 1, "auto_close_status": "Replied"}
        )
        self.assertEqual(
            self.found(ticket, follow_up_context(customer_follow_up_email=1)), []
        )


class TestLeave(FollowUpCase):
    """Approved leave (HD Leave, synced from the CRM site): nobody on leave is nudged or
    escalated to; when the assignee is away, who covers for them hears instead."""

    def test_assignee_on_leave_goes_straight_to_the_assigner_and_lead(self):
        make_hd_leave(DEV[0], "2026-10-12", "2026-10-14")
        task = self.task("Send invoice", "2026-10-12")

        nudge = self.one(task, "due_today")

        self.assertNotIn(DEV[0], nudge.recipients)
        self.assertEqual(set(nudge.recipients), {PM[0], LEAD[0]})
        self.assertIn("Anu Varghese is on leave until Wed 14 Oct", nudge.text)
        # still the assignee's work, so it counts as theirs
        self.assertEqual(nudge.owners, [DEV[0]])

    def test_escalation_skips_a_head_on_leave(self):
        make_hd_leave(HEAD[0], "2026-10-12", "2026-10-12")

        l2 = self.one(self.task("Configure GST", WEDNESDAY), "overdue")

        self.assertEqual(l2.level, 2)
        self.assertNotIn(HEAD[0], l2.recipients)
        self.assertIn(DEV[0], l2.recipients)
        self.assertNotIn("on leave", l2.text)

    def test_ticket_assignee_on_leave_goes_to_the_team_lead(self):
        make_hd_leave(DEV[0], "2026-10-12", "2026-10-12")
        ticket = make_assigned_ticket(
            "Invoice mismatch",
            DEV[0],
            sla=None,
            response_by=None,
            status_category="Open",
            first_responded_on=FOLLOW_UP_MONDAY,
            service_level_agreement_creation=add_to_date(FOLLOW_UP_MONDAY, hours=-5),
            resolution_by=add_to_date(FOLLOW_UP_MONDAY, hours=5),
        )

        half = self.one(ticket, "sla")

        self.assertNotIn(DEV[0], half.recipients)
        self.assertIn(MANAGER[0], half.recipients)
        self.assertIn("is on leave until", half.text)

    def test_a_half_day_still_counts_as_working(self):
        make_hd_leave(DEV[0], "2026-10-12", "2026-10-12", half_day=1)
        task = self.task("Send invoice", "2026-10-12")
        self.assertEqual(self.one(task, "due_today").recipients, [DEV[0]])

    def test_nobody_on_leave_gets_a_digest(self):
        make_hd_leave(DEV[0], "2026-10-12", "2026-10-12")
        self.task("Bank import", WEDNESDAY)
        with patch.object(follow_ups, "deliver_digest", return_value="chat") as deliver:
            follow_ups.process(follow_up_context(datetime(2026, 10, 12, 9, 31)))

        people = {c.args[0] for c in deliver.call_args_list}
        self.assertNotIn(DEV[0], people)
        self.assertIn(PM[0], people)


class TestDelivery(FollowUpCase):
    def test_one_notice_per_person_and_item_a_day_updated_not_duplicated(self):
        task = self.task("Import customers", FRIDAY)
        follow_ups.process(follow_up_context())
        follow_ups.process(follow_up_context())

        [notice] = get_follow_up_notices(DEV[0], task)
        self.assertEqual(notice.dedupe_key, "follow-up:2026-10-12:overdue:L1")
        frappe.db.set_value("HD Notification", notice.name, "read", 1)

        # later the same day it climbs a level: the same notice, unread again
        frappe.db.set_value("Task", task, "exp_end_date", WEDNESDAY)
        follow_ups.process(follow_up_context())
        [notice] = get_follow_up_notices(DEV[0], task)
        self.assertEqual(notice.dedupe_key, "follow-up:2026-10-12:overdue:L2")
        self.assertFalse(notice.read)

        # a new day is a new notice
        follow_ups.process(follow_up_context(datetime(2026, 10, 13, 11, 0)))
        self.assertEqual(len(get_follow_up_notices(DEV[0], task)), 2)

    def test_pings_go_out_only_for_l2_breaches_and_key_work(self):
        follow_ups.process(follow_up_context())
        low = self.task("Item groups", FRIDAY)
        # assigning the task emails the assignee; only follow-up emails count from here
        self.sendmail.reset_mock()

        follow_ups.process(follow_up_context())
        self.assertNotIn(DEV[0], self.emailed())

        frappe.db.set_value("Task", low, "exp_end_date", WEDNESDAY)
        follow_ups.process(follow_up_context())
        self.assertEqual(self.emailed().count(DEV[0]), 1)
        follow_ups.process(follow_up_context())
        self.assertEqual(self.emailed().count(DEV[0]), 1)
        self.assertTrue(
            any("Item groups" in c.args[0] for c in self.channel.call_args_list)
        )

    def emailed(self):
        return [c.kwargs.get("recipients") for c in self.sendmail.call_args_list]

    def test_levels_are_recorded_and_reset_on_completion(self):
        task = self.task("Tax templates", WEDNESDAY)
        follow_ups.process(follow_up_context())
        self.assertEqual(
            frappe.db.get_value("Task", task, ["escalation_level", "escalated_on"]),
            (2, getdate("2026-10-12")),
        )

        doc = frappe.get_doc("Task", task)
        doc.status = "Completed"
        doc.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Task", task, "escalation_level"), 0)

    def test_breached_ticket_level_is_recorded(self):
        ticket = make_assigned_ticket(
            "Payroll run failed",
            DEV[0],
            sla=None,
            response_by=None,
            status_category="Open",
            first_responded_on=FOLLOW_UP_MONDAY,
            service_level_agreement_creation=add_to_date(FOLLOW_UP_MONDAY, hours=-9),
            resolution_by=add_to_date(FOLLOW_UP_MONDAY, hours=-1),
        )
        follow_ups.process(follow_up_context())
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket, "custom_escalation_level"), 2
        )

    def test_quiet_hours_send_nothing_but_breaches_when_allowed(self):
        task = self.task("Holiday work", WEDNESDAY)
        holiday = [FOLLOW_UP_MONDAY.date()]

        follow_ups.process(follow_up_context(holidays=holiday))
        self.assertEqual(get_follow_up_notices(DEV[0], task), [])

        ticket = make_assigned_ticket(
            "Server down",
            DEV[0],
            sla=None,
            response_by=None,
            status_category="Open",
            first_responded_on=FOLLOW_UP_MONDAY,
            service_level_agreement_creation=add_to_date(FOLLOW_UP_MONDAY, hours=-9),
            resolution_by=add_to_date(FOLLOW_UP_MONDAY, hours=-1),
        )
        follow_ups.process(
            follow_up_context(holidays=holiday, breach_pings_outside_hours=1)
        )
        self.assertEqual(get_follow_up_notices(DEV[0], task), [])
        self.assertEqual(len(get_follow_up_notices(DEV[0], ticket)), 1)


class TestDigest(FollowUpCase):
    def test_digest_groups_items_once_per_time_with_the_morning_plan(self):
        self.task("Bank import", WEDNESDAY)
        self.task("Share build", TUESDAY)
        nine_thirty = datetime(2026, 10, 12, 9, 31)
        with patch.object(
            follow_ups, "deliver_digest", return_value="chat"
        ) as deliver, patch.object(
            follow_ups, "plan_steps", return_value=["Finish Bank import first."]
        ):
            follow_ups.process(follow_up_context(nine_thirty))
            follow_ups.process(follow_up_context(datetime(2026, 10, 12, 9, 46)))

        mine = [c for c in deliver.call_args_list if c.args[0] == DEV[0]]
        self.assertEqual(len(mine), 1)
        headings = [heading for heading, _rows in mine[0].args[2]]
        self.assertTrue(headings[0].startswith("Escalated"))
        self.assertTrue(any(h.startswith("Due now") for h in headings))
        self.assertEqual(headings[-1], "Your plan for today")

    def test_chat_text_links_every_item(self):
        text = follow_ups.chat_text(
            "Anu, 1 item(s) need you",
            [("Overdue (1)", [("Overdue 2 working day(s): Go-live", "/my-work")])],
        )
        self.assertIn("[Overdue 2 working day(s): Go-live](", text)
        self.assertIn("/helpdesk/my-work)", text)


class TestSwitchedOff(FollowUpCase):
    def test_turning_follow_ups_off_clears_the_badges(self):
        task = self.task("Bank feeds", WEDNESDAY)
        follow_ups.process(follow_up_context())
        self.assertEqual(frappe.db.get_value("Task", task, "escalation_level"), 2)

        set_follow_up_settings(enabled=0)
        follow_ups.run()
        self.assertEqual(frappe.db.get_value("Task", task, "escalation_level"), 0)


class TestSettingsAccess(FollowUpCase):
    def test_only_admins_change_the_settings(self):
        with self.assertRaises(frappe.PermissionError):
            call_as_user(
                DEV[0],
                "helpdesk.api.follow_ups.save_settings",
                values={"hold_days": 9},
            )
        saved = call_as_user(
            MANAGER[0],
            "helpdesk.api.follow_ups.save_settings",
            values={"hold_days": 9, "digest_times": "15:30,9:30"},
        )
        self.assertEqual(saved["hold_days"], 9)
        self.assertEqual(saved["digest_times"], "09:30, 15:30")

    def test_afternoon_nudge_defaults_to_14_00_and_is_stored_as_hh_mm(self):
        # a Time field would get the current time on a new document, not its default
        self.assertEqual(frappe.new_doc(SETTINGS).afternoon_nudge_at, "14:00")
        self.assertEqual(
            set_follow_up_settings(afternoon_nudge_at="9:05:00").afternoon_nudge_at,
            "09:05",
        )
        with self.assertRaises(frappe.ValidationError):
            set_follow_up_settings(afternoon_nudge_at="after lunch")

    def test_the_ladder_must_climb(self):
        with self.assertRaises(frappe.ValidationError):
            set_follow_up_settings(ladder_l1_days=4, ladder_l2_days=2)

    def test_test_digest_goes_only_to_the_caller(self):
        with patch.object(
            follow_ups, "deliver_digest", return_value="email"
        ) as deliver:
            result = call_as_user(
                MANAGER[0], "helpdesk.api.follow_ups.send_test_digest"
            )
        self.assertEqual(result["via"], "email")
        self.assertEqual([c.args[0] for c in deliver.call_args_list], [MANAGER[0]])
        with self.assertRaises(frappe.PermissionError):
            call_as_user(DEV[0], "helpdesk.api.follow_ups.send_test_digest")
