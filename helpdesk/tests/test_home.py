from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk.api.home import (
    _attention_groups,
    _open_tickets,
    _ticket_summary,
    get_home,
)
from helpdesk.api.work import get_overview
from helpdesk.test_utils import (
    create_customer,
    make_assigned_ticket,
    make_assignment,
    make_project,
    make_project_file,
    make_project_folder,
    make_task,
    make_tasky_user,
    make_ticket,
    mark_project_item,
)

LEAD = ("lead.home@home-dashboard.example", "Asha Kurian")
DEV = ("dev.home@home-dashboard.example", "Vivek Nair")
CUSTOMER = "Home Dashboard Traders"


class TestHome(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        # code under test commits (e.g. assignment); keep everything in this
        # test's transaction so other test modules don't see its project and task
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        create_customer(CUSTOMER)
        make_tasky_user(*LEAD)
        make_tasky_user(*DEV)
        self.project = make_project(
            f"{CUSTOMER} - Rollout",
            members=[(LEAD[0], "Developer"), (DEV[0], "Developer")],
        ).name
        frappe.db.set_value(
            "Project", self.project, {"project_lead": LEAD[0], "customer": CUSTOMER}
        )
        self.overdue = make_task(
            self.project, "Import opening stock", add_days(nowdate(), -2)
        ).name
        make_assignment("Task", self.overdue, DEV[0])

    def as_user(self, user):
        frappe.set_user(user[0])
        try:
            return get_home()
        finally:
            frappe.set_user("Administrator")

    def test_lead_sees_the_whole_business(self):
        breached = make_ticket(subject="Invoice totals wrong", customer=CUSTOMER)
        # assignment rules may have picked an agent; this ticket must be unassigned
        frappe.db.set_value(
            "HD Ticket",
            breached.name,
            {
                "resolution_by": add_to_date(now_datetime(), hours=-3),
                "_assign": None,
            },
        )

        home = self.as_user(LEAD)

        company = home["company"]
        self.assertIsNotNone(company)
        self.assertIn(self.overdue, [i["name"] for i in company["attention"]])
        self.assertIn(self.project, [p["name"] for p in company["projects"]])
        project = next(p for p in company["projects"] if p["name"] == self.project)
        self.assertEqual(project["overdue"], 1)
        tickets = company["tickets"]
        self.assertGreaterEqual(tickets["sla_breached"], 1)
        self.assertGreaterEqual(tickets["unassigned"], 1)
        self.assertGreaterEqual(tickets["new_today"], 1)
        self.assertIn(CUSTOMER, [r["customer"] for r in tickets["by_customer"]])
        # a project lead is not an admin
        self.assertIsNone(home["systems"])

    def test_developer_sees_only_their_own_work(self):
        home = self.as_user(DEV)

        self.assertIsNone(home["company"])
        self.assertIsNone(home["systems"])
        self.assertEqual(home["mine"]["counts"]["overdue"], 1)
        self.assertEqual([i["name"] for i in home["mine"]["items"]], [self.overdue])

    def test_admins_also_see_system_health(self):
        home = get_home()

        systems = home["systems"]
        self.assertIsNotNone(systems)
        for key in ("connections", "mailboxes", "teams", "chat", "ai"):
            self.assertIn(key, systems)

    def test_your_day_has_only_my_own_work(self):
        due_today = make_task(self.project, "Post the launch reel", nowdate()).name
        make_assignment("Task", due_today, LEAD[0])
        later = make_task(self.project, "Plan next quarter", add_days(nowdate(), 30))
        make_assignment("Task", later.name, DEV[0])
        mine = make_assigned_ticket("Login fails", DEV[0], customer=CUSTOMER)
        theirs = make_assigned_ticket("Report is slow", LEAD[0], customer=CUSTOMER)

        day = self.as_user(DEV)["day"]

        self.assertEqual(
            [i["name"] for i in day["close_first"]["items"]], [self.overdue]
        )
        # due after the coming week: not listed, but still open work
        self.assertEqual(day["coming_up"]["count"], 0)
        self.assertGreaterEqual(day["summary"]["open"], 3)
        replies = [i["name"] for i in day["replies"]["items"]]
        self.assertIn(mine, replies)
        self.assertNotIn(theirs, replies)
        lead_day = self.as_user(LEAD)["day"]
        self.assertIn(due_today, [i["name"] for i in lead_day["close_first"]["items"]])

    def test_approvals_wait_for_the_project_lead_only(self):
        frappe.db.set_value("Task", self.overdue, "status", "Pending Review")

        lead_approvals = self.as_user(LEAD)["day"]["approvals"]
        dev_day = self.as_user(DEV)["day"]

        self.assertEqual([i["name"] for i in lead_approvals["items"]], [self.overdue])
        self.assertTrue(lead_approvals["items"][0]["can_approve"])
        self.assertEqual(dev_day["approvals"]["count"], 0)
        # a task in review is waiting on the reviewer, not on its assignee
        self.assertEqual(dev_day["close_first"]["count"], 0)
        self.assertEqual(
            [i["name"] for i in dev_day["waiting"]["items"]], [self.overdue]
        )

    def test_files_for_me_skip_my_own_uploads(self):
        make_project_file(self.project, "brief.md", for_users=[DEV[0]], user=LEAD[0])

        dev_files = self.as_user(DEV)["day"]["files"]
        lead_files = self.as_user(LEAD)["day"]["files"]

        self.assertEqual([f["file_name"] for f in dev_files["items"]], ["brief.md"])
        self.assertEqual(dev_files["items"][0]["project"], self.project)
        self.assertEqual(lead_files["count"], 0)

    def test_files_for_me_skip_files_in_a_superseded_folder(self):
        old = make_project_folder(self.project, "Spec v1", user=LEAD[0])
        make_project_file(
            self.project, "spec.md", for_users=[DEV[0]], user=LEAD[0], folder=old
        )
        make_project_file(self.project, "brief.md", for_users=[DEV[0]], user=LEAD[0])
        mark_project_item(LEAD[0], self.project, "folder", old)

        dev_files = self.as_user(DEV)["day"]["files"]

        self.assertEqual([f["file_name"] for f in dev_files["items"]], ["brief.md"])

    def test_quiet_day_is_all_zero(self):
        quiet = ("quiet.home@home-dashboard.example", "Nila Menon")
        make_tasky_user(*quiet)

        day = self.as_user(quiet)["day"]

        for section in (
            "close_first",
            "in_progress",
            "waiting",
            "coming_up",
            "no_date",
            "given_out",
            "projects",
            "replies",
            "approvals",
            "files",
        ):
            self.assertEqual(day[section], {"count": 0, "items": []})

    def test_needs_attention_is_grouped_by_reason(self):
        unassigned = make_ticket(subject="Printer offline", customer=CUSTOMER).name
        frappe.db.set_value("HD Ticket", unassigned, "_assign", None)
        waiting = make_assigned_ticket(
            "Send the GST file",
            DEV[0],
            customer=CUSTOMER,
            status="Replied",
            status_category="Paused",
            last_agent_response=add_days(now_datetime(), -5),
        )
        frappe.set_user(LEAD[0])
        # only this test's records, so other tests' tickets can't fill the groups
        buckets = get_overview(project=self.project)["buckets"]
        tickets = [t for t in _open_tickets() if t.customer == CUSTOMER]

        groups = {g["key"]: g for g in _attention_groups(buckets, tickets)}

        # nothing is at risk, so that reason is left out
        self.assertEqual(
            list(groups), ["overdue", "unassigned_tickets", "waiting_on_customer"]
        )
        self.assertEqual(
            [i["name"] for i in groups["overdue"]["items"]], [self.overdue]
        )
        self.assertEqual(groups["overdue"]["items"][0]["customer"], CUSTOMER)
        self.assertEqual(
            [i["name"] for i in groups["unassigned_tickets"]["items"]],
            [str(unassigned)],
        )
        waiting_items = groups["waiting_on_customer"]["items"]
        self.assertEqual([i["name"] for i in waiting_items], [waiting])
        self.assertGreaterEqual(waiting_items[0]["waiting_days"], 4)
        self.assertEqual(_ticket_summary(tickets)["waiting_on_customer"], 1)

    def test_lead_home_has_the_new_sections(self):
        company = self.as_user(LEAD)["company"]

        for key in ("attention_groups", "ending_soon", "people_busy", "free_people"):
            self.assertIn(key, company)
        self.assertIn("overdue", [g["key"] for g in company["attention_groups"]])

    def test_projects_ending_soon(self):
        frappe.db.set_value(
            "Project", self.project, "expected_end_date", add_days(nowdate(), 5)
        )

        ending = self.as_user(LEAD)["company"]["ending_soon"]

        project = next(p for p in ending if p["name"] == self.project)
        self.assertEqual(project["days_left"], 5)
