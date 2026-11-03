from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime

from helpdesk import adoption
from helpdesk import team_dashboard as td
from helpdesk.api import adoption as api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRM,
    adoption_finding,
    adoption_person,
    age_content_post,
    age_ticket,
    call_batches_report,
    create_customer,
    enable_leads,
    hold_commits,
    log_hours,
    make_assigned_ticket,
    make_assignment,
    make_content_edits,
    make_content_post,
    make_done_task,
    make_hd_leave,
    make_project,
    make_sales_employee,
    make_standup,
    make_task,
    make_tasky_user,
    make_time_session,
    sales_person,
    set_follow_up_settings,
)

FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
ADMIN = "Administrator"
BOSS = "adopt.boss@tbo.example"
COORDINATOR = "adopt.coordinator@tbo.example"
OUTSIDER = "adopt.outsider@tbo.example"
DEV = "adopt.dev@tbo.example"
QUIET = "adopt.quiet@tbo.example"
AWAY = "adopt.away@tbo.example"
BDE = "adopt.bde@tbo.example"
BDE_IDLE = "adopt.bde.idle@tbo.example"
TODAY = getdate()
MONDAY = TODAY - timedelta(days=TODAY.weekday())


class AdoptionCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, ADMIN)
        self.addCleanup(td.clear_cache)
        make_tasky_user(BOSS, "Bina Boss", roles=("Agent Manager",))
        make_tasky_user(DEV, "Dev Anand")
        make_tasky_user(COORDINATOR, "Cora Coordinator")
        make_tasky_user(QUIET, "Quincy Quiet")
        make_tasky_user(AWAY, "Asha Away")
        make_tasky_user(OUTSIDER, "Olive Outsider")
        self.project = make_project(
            "Adoption - Website",
            members=[(DEV, "Developer"), (COORDINATOR, "Project Coordinator")],
        ).name

    def report(self, period="this_week", user=ADMIN):
        frappe.set_user(user)
        try:
            return api.get_adoption(period)
        finally:
            frappe.set_user(ADMIN)


class TestPeriods(FrappeTestCase):
    def test_this_week_runs_monday_to_today(self):
        self.assertEqual(
            adoption.period_bounds("this_week", "2026-11-04"),
            (getdate("2026-11-02"), getdate("2026-11-04")),
        )

    def test_last_week_is_the_whole_week_before(self):
        self.assertEqual(
            adoption.period_bounds("last_week", "2026-11-04"),
            (getdate("2026-10-26"), getdate("2026-11-01")),
        )

    def test_last_30_ends_today(self):
        start, end = adoption.period_bounds("last_30", "2026-11-04")
        self.assertEqual((end - start).days, 29)

    def test_an_unknown_period_is_refused(self):
        self.assertRaises(frappe.ValidationError, adoption.period_bounds, "decade")


class TestWhoMayLook(AdoptionCase):
    def test_managers_and_coordinators_may_open_it(self):
        self.assertTrue(adoption.can_see_adoption(ADMIN))
        self.assertTrue(adoption.can_see_adoption(BOSS))
        self.assertTrue(adoption.can_see_adoption(COORDINATOR))
        self.assertIn("findings", self.report(user=COORDINATOR))

    def test_the_management_role_may_open_it(self):
        if not frappe.db.exists("Role", adoption.MANAGEMENT_ROLE):
            frappe.get_doc(
                {"doctype": "Role", "role_name": adoption.MANAGEMENT_ROLE}
            ).insert(ignore_permissions=True)
        frappe.get_doc("User", OUTSIDER).add_roles(adoption.MANAGEMENT_ROLE)
        self.assertTrue(adoption.can_see_adoption(OUTSIDER))

    def test_other_agents_are_refused(self):
        self.assertFalse(adoption.can_see_adoption(DEV))
        frappe.set_user(DEV)
        self.assertRaises(frappe.PermissionError, api.get_adoption)

    def test_an_unknown_period_is_refused_by_the_endpoint(self):
        self.assertRaises(frappe.ValidationError, api.get_adoption, "decade")

    def test_the_digest_goes_to_the_same_people(self):
        people = adoption.recipients()
        self.assertIn(BOSS, people)
        self.assertIn(COORDINATOR, people)
        self.assertNotIn(DEV, people)


class TestDelivery(AdoptionCase):
    def test_overdue_work_names_who_holds_it(self):
        for i in range(3):
            task = make_task(self.project, f"Late {i}", add_days(TODAY, -5)).name
            make_assignment("Task", task, DEV)
        found = adoption_finding(self.report(), "overdue")
        self.assertIn("open tasks are overdue", found["title"])
        self.assertIn(DEV, [p["user"] for p in found["who"]])
        self.assertEqual(found["link"], "/overview")

    def test_projects_without_a_lead_are_counted(self):
        found = adoption_finding(self.report(), "no-lead")
        self.assertIn("have no lead", found["title"])

    def test_people_who_did_nothing_are_quiet_but_not_those_on_leave(self):
        make_hd_leave(AWAY, MONDAY, add_days(MONDAY, 4))
        make_done_task(self.project, "Shipped", DEV, TODAY, due=TODAY)
        report = self.report()
        quiet = [p["user"] for p in adoption_finding(report, "quiet-people")["who"]]
        self.assertIn(QUIET, quiet)
        self.assertNotIn(DEV, quiet)
        self.assertNotIn(AWAY, quiet)
        self.assertTrue(adoption_person(report, QUIET)["quiet"])
        self.assertFalse(adoption_person(report, AWAY)["quiet"])
        self.assertTrue(adoption_person(report, AWAY)["on_leave"])
        self.assertEqual(adoption_person(report, DEV)["tasks_done"], 1)

    def test_standups_split_into_written_and_posted_by_the_system(self):
        with patch("helpdesk.standup.is_enabled", return_value=True):
            make_standup(DEV, TODAY, status="Submitted")
            make_standup(QUIET, TODAY, status="Auto-posted")
            report = self.report()
        self.assertEqual(adoption_person(report, DEV)["standups_written"], 1)
        self.assertEqual(adoption_person(report, QUIET)["standups_written"], 0)
        found = adoption_finding(report, "standups")
        self.assertIn("stand-ups", found["title"] + found["detail"])

    def test_a_full_day_in_one_session_or_typed_by_hand_is_checked(self):
        task = make_task(self.project, "Long one").name
        start = now_datetime().replace(hour=9, minute=0, second=0, microsecond=0)
        make_time_session(task, DEV, start, start + timedelta(hours=8))
        log_hours(QUIET, self.project, 9, TODAY)
        found = adoption_finding(self.report(), "long-hours")
        self.assertEqual(found["severity"], "watch")
        users = [p["user"] for p in found["who"]]
        self.assertIn(DEV, users)
        self.assertIn(QUIET, users)

    def test_the_people_table_counts_timer_hours_and_last_activity(self):
        task = make_task(self.project, "Timed").name
        start = now_datetime().replace(hour=9, minute=0, second=0, microsecond=0)
        make_time_session(task, DEV, start, start + timedelta(hours=2))
        row = adoption_person(self.report(), DEV)
        self.assertEqual(row["hours"], 2)
        self.assertEqual(row["last_activity"], str(TODAY))
        self.assertFalse(row["quiet"])


class TestContent(AdoptionCase):
    def setUp(self):
        super().setUp()
        self.customer = create_customer("Adoption Resorts").name

    def post(self, title, **values):
        return make_content_post(title, self.customer, **values).name

    def test_posts_stuck_in_drafting_name_their_writers(self):
        post = self.post("Stuck", status="Drafting", writer=DEV)
        age_content_post(post, STUCK_DAYS + 3)
        found = adoption_finding(self.report(), "stuck-drafts")
        self.assertIn("Drafting", found["title"])
        self.assertIn(DEV, [p["user"] for p in found["who"]])

    def test_a_fresh_draft_is_not_stuck(self):
        self.post("Fresh", status="Drafting", writer=DEV)
        found = adoption_finding(self.report(), "stuck-drafts")
        self.assertNotIn(DEV, [p["user"] for p in (found or {"who": []})["who"]])

    def test_nothing_sent_to_a_client_is_flagged(self):
        frappe.db.set_value(
            "HD Content Post", {"status": "Client Review"}, "status", "Drafting"
        )
        self.post("Waiting", status="Drafting")
        found = adoption_finding(self.report(), "no-client-review")
        self.assertEqual(found["severity"], "attention")

    def test_a_post_in_client_review_clears_it(self):
        self.post("With the client", status="Client Review")
        self.assertIsNone(adoption_finding(self.report(), "no-client-review"))

    def test_one_person_making_most_edits_is_flagged(self):
        post = self.post("Edited")
        make_content_edits(post, DEV, 400)
        found = adoption_finding(self.report(), "edit-concentration")
        self.assertEqual([p["user"] for p in found["who"]], [DEV])


class TestSupport(AdoptionCase):
    def test_tickets_without_a_reply_and_sla_breaches(self):
        quiet = make_assigned_ticket("Nobody answered", DEV)
        age_ticket(quiet, 30)
        late = make_assigned_ticket("Promise broken", DEV)
        age_ticket(late, 2, agreement_status="Failed")
        report = self.report()
        no_reply = adoption_finding(report, "no-reply")
        self.assertIn(DEV, [p["user"] for p in no_reply["who"]])
        breach = adoption_finding(report, "sla-breach")
        self.assertIn(DEV, [p["user"] for p in breach["who"]])
        self.assertEqual(breach["severity"], "attention")


class TestAccounts(AdoptionCase):
    def test_test_looking_personal_and_duplicate_accounts_are_found(self):
        make_tasky_user("someone.real@gmail.com", "Sam Real")
        make_tasky_user("demo.agent@tbo.example", "Demo Agent")
        make_tasky_user("twin.one@tbo.example", "Tina Twin")
        make_tasky_user("twin.two@tbo.example", "Tina Twin")
        report = self.report()
        odd = [p["user"] for p in adoption_finding(report, "odd-accounts")["who"]]
        self.assertIn("someone.real@gmail.com", odd)
        self.assertIn("demo.agent@tbo.example", odd)
        self.assertNotIn(DEV, odd)
        twins = [p["user"] for p in adoption_finding(report, "duplicate-names")["who"]]
        self.assertEqual(
            set(twins) & {"twin.one@tbo.example", "twin.two@tbo.example"},
            {"twin.one@tbo.example", "twin.two@tbo.example"},
        )


class TestSales(AdoptionCase):
    def setUp(self):
        super().setUp()
        make_sales_employee(BDE, "Shahana Sales")
        make_sales_employee(BDE_IDLE, "Ivan Idle")
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["get_sales_activity"] = {
            "currency": "INR",
            "people": [sales_person(BDE, calls=0, contacted=0, new=2)],
        }
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def batches(self, **recorded):
        people = [
            {
                "user": BDE,
                "user_name": "Shahana Sales",
                "size": 100,
                "called": 0,
                "connected": 0,
                "overdue": 0,
            },
        ]
        people[0].update(recorded)
        self.crm.lead_answers["get_call_batches_report"] = call_batches_report(people)

    def test_nobody_recording_results_says_who_and_what_to_do(self):
        self.batches()
        report = self.report()
        found = adoption_finding(report, "sales-outcomes-none")
        self.assertEqual(found["severity"], "attention")
        self.assertIn("Shahana recorded 0 call results", found["title"])
        self.assertIn("tap the result", found["action_hint"])
        self.assertEqual([p["user"] for p in found["who"]], [BDE])
        self.assertTrue(report["sales_available"])

    def test_few_results_is_a_watch(self):
        self.batches(called=20)
        found = adoption_finding(self.report(), "sales-outcomes-few")
        self.assertEqual(found["severity"], "watch")

    def test_results_recorded_is_good_news(self):
        self.batches(called=90)
        found = adoption_finding(self.report(), "sales-outcomes")
        self.assertEqual(found["severity"], "good")

    def test_a_salesperson_with_no_activity_is_idle_and_quiet(self):
        self.batches(called=90)
        report = self.report()
        found = adoption_finding(report, "sales-idle")
        self.assertIn(BDE_IDLE, [p["user"] for p in found["who"]])
        self.assertTrue(adoption_person(report, BDE_IDLE)["quiet"])
        self.assertFalse(adoption_person(report, BDE)["quiet"])

    def test_calls_and_stage_changes_are_checked_per_person(self):
        self.crm.lead_answers["get_sales_activity"] = {
            "currency": "INR",
            "people": [
                sales_person(BDE, calls=0, contacted=0, new=2),
                sales_person(BDE_IDLE, calls=5, contacted=3),
            ],
        }
        report = self.report()
        calls = adoption_finding(report, "sales-calls")
        self.assertEqual([p["user"] for p in calls["who"]][0], BDE)
        stages = adoption_finding(report, "sales-stages")
        self.assertEqual([p["user"] for p in stages["who"]], [BDE])
        self.assertEqual(adoption_person(report, BDE_IDLE)["calls"], 5)

    def test_an_unreachable_erp_site_leaves_sales_out_and_the_rest_in(self):
        self.crm.lead_error = CRMError("down")
        report = self.report()
        self.assertFalse(report["sales_available"])
        self.assertFalse([f for f in report["findings"] if f["area"] == "Sales"])
        self.assertTrue(adoption_finding(report, "no-lead"))
        self.assertFalse(adoption_person(report, BDE)["quiet"])

    def test_an_older_erp_site_without_batches_still_shows_activity(self):
        self.crm.lead_answers["get_call_batches_report"] = CRMError(
            "x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x"
        )
        report = self.report()
        self.assertTrue(report["sales_available"])
        self.assertIsNone(adoption_finding(report, "sales-outcomes-none"))

    def test_leads_turned_off_leaves_sales_out(self):
        frappe.db.set_single_value("HD CRM Settings", "enable_leads", 0)
        report = self.report()
        self.assertFalse(report["sales_available"])
        self.assertEqual(self.crm.lead_calls, [])


class TestDigest(AdoptionCase):
    def setUp(self):
        super().setUp()
        # the settings doctype gained its switch in this change
        frappe.reload_doc("helpdesk", "doctype", "hd_follow_up_settings")

    def run_digest(self):
        with patch("helpdesk.follow_ups.deliver_digest") as deliver:
            adoption.send_weekly_digest()
        return deliver

    def test_the_top_findings_go_to_the_people_who_may_open_the_page(self):
        set_follow_up_settings(enabled=1, adoption_digest=1)
        deliver = self.run_digest()
        sent_to = [call.args[0] for call in deliver.call_args_list]
        self.assertIn(BOSS, sent_to)
        self.assertIn(COORDINATOR, sent_to)
        self.assertNotIn(DEV, sent_to)
        _user, _subject, sections = deliver.call_args_list[0].args
        rows = sections[0][1]
        self.assertLessEqual(len(rows), adoption.DIGEST_FINDINGS + 1)
        self.assertEqual(rows[-1][1], "/adoption")

    def test_the_switch_turns_it_off(self):
        set_follow_up_settings(enabled=1, adoption_digest=0)
        self.assertFalse(self.run_digest().called)

    def test_nothing_goes_out_while_follow_ups_are_off(self):
        set_follow_up_settings(enabled=0, adoption_digest=1)
        self.assertFalse(self.run_digest().called)

    def test_good_news_is_not_a_digest(self):
        self.assertEqual(
            adoption.digest_sections({"findings": [{"severity": "good"}]}), []
        )


STUCK_DAYS = adoption.STUCK_DRAFT_DAYS
