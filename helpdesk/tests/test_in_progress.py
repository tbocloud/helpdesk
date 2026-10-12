"""The In progress page: every started task and every post in production, in lanes.
See docs/workspace-pages.md "In progress"."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk.content_team import (
    DM_COORDINATOR_ROLE,
    DM_EMPLOYEE_ROLE,
    ERP_EMPLOYEE_ROLE,
)
from helpdesk.tasky.permissions import CONTENT_DEPARTMENT
from helpdesk.test_utils import (
    call_mobile_as,
    create_customer,
    get_in_progress_as,
    hold_commits,
    make_assignment,
    make_content_post,
    make_content_user,
    make_customer_project,
    make_department,
    make_project,
    make_started_task,
    make_task,
    make_tasky_user,
    set_content_settings,
    start_task_timer,
)

CUSTOMER = "Kuttanad Rice Mills"
OTHER_CUSTOMER = "Vembanad Boat Tours"
CONTENT_CUSTOMER = "Thekkady Tea Estates"
ERP = "ERP"
PM = ("pm@in-progress.example", "Leena Varghese")
LEAD = ("lead@in-progress.example", "Nikhil Das")
COORD = ("coord@in-progress.example", "Shabna Rasheed")
DEV_A = ("dev.a@in-progress.example", "Rahul Nair")
DEV_B = ("dev.b@in-progress.example", "Meera Joseph")
DEV_C = ("dev.c@in-progress.example", "Joel Mathew")
ADMIN = ("manager@in-progress.example", "Arun Menon")
WRITER = ("writer@in-progress.example", "Riya Thomas")
DESIGNER = ("designer@in-progress.example", "Anu Varghese")
MARKETER = ("marketer@in-progress.example", "Biju Paul")
DM_COORD = ("dm.coord@in-progress.example", "Fathima Rizwana")


class TestInProgress(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        for customer in (CUSTOMER, OTHER_CUSTOMER, CONTENT_CUSTOMER):
            create_customer(customer)
        make_department(ERP)
        make_department(CONTENT_DEPARTMENT)
        set_content_settings(default_task_mode="One task per person")
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")

        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*ADMIN, roles=("Agent Manager",))
        for user in (LEAD, COORD, DEV_A, DEV_B, DEV_C):
            make_tasky_user(*user)
        for user in (WRITER, DESIGNER, MARKETER):
            make_content_user(*user, DM_EMPLOYEE_ROLE)
        make_content_user(*DM_COORD, DM_COORDINATOR_ROLE)

        self.make_projects()
        self.make_posts()

    def make_projects(self):
        self.project = make_project(
            f"{CUSTOMER} - ERP rollout",
            members=[
                (DEV_A[0], "Developer"),
                (DEV_B[0], "Developer"),
                (COORD[0], "Project Coordinator"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value(
            "Project",
            self.project,
            {"customer": CUSTOMER, "project_lead": LEAD[0], "custom_department": ERP},
        )
        today = nowdate()
        self.working = make_started_task(
            self.project, "Configure GST reports", DEV_A[0], due=add_days(today, 1)
        )
        start_task_timer(self.working, hours_ago=2, estimated_hours=8)
        self.late = make_started_task(
            self.project, "Migrate opening stock", DEV_B[0], due=add_days(today, -1)
        )
        self.review = make_started_task(
            self.project,
            "Sales order print format",
            DEV_A[0],
            "Pending Review",
            due=add_days(today, 2),
        )
        self.held = make_started_task(
            self.project,
            "Bank feed import",
            DEV_B[0],
            "On Hold",
            hold_reason="Waiting on customer",
        )
        self.escalated = make_started_task(
            self.project,
            "Payroll setup",
            DEV_A[0],
            due=add_days(today, 3),
            escalation_level=2,
        )
        # not started, and finished: neither is in progress
        self.not_started = make_task(self.project, "Train the store team").name
        make_assignment("Task", self.not_started, DEV_A[0])
        self.done = make_started_task(
            self.project, "Chart of accounts", DEV_A[0], "Completed"
        )

        self.other_project = make_customer_project(
            OTHER_CUSTOMER,
            f"{OTHER_CUSTOMER} - Booking app",
            members=[(DEV_C[0], "Developer")],
        )
        self.other = make_started_task(
            self.other_project, "Booking calendar", DEV_C[0], due=add_days(today, 4)
        )

    def make_posts(self):
        # the writer is on the client's project, so the post permission alone would
        # show them every post of the client
        self.content_project = make_customer_project(
            CONTENT_CUSTOMER,
            f"{CONTENT_CUSTOMER} - Content calendar",
            members=[(WRITER[0], "Developer")],
        )
        frappe.db.set_value(
            "Project",
            self.content_project,
            {
                "project_type": "Content Calendar",
                "custom_department": CONTENT_DEPARTMENT,
            },
        )
        now = now_datetime()

        def post(title, days, status="Drafting", **team):
            name = make_content_post(
                title,
                CONTENT_CUSTOMER,
                status="Drafting",
                publish_on=add_to_date(now, days=days),
                **team,
            ).name
            if status != "Drafting":
                frappe.db.set_value("HD Content Post", name, "status", status)
            return name

        self.drafting = post("Onam sadya offer", 5, writer=WRITER[0])
        self.client = post("Tea tasting reel", 1, "Client Review", designer=DESIGNER[0])
        self.missed = post("Monsoon trek carousel", -1, "Design", designer=DESIGNER[0])
        self.approved = post("Estate tour story", 3, "Approved", marketer=MARKETER[0])
        # an idea hasn't started and a scheduled post is done: neither is in production
        self.idea = make_content_post("Christmas plum cake", CONTENT_CUSTOMER).name
        self.scheduled = post("Harvest festival", 6, "Scheduled", writer=WRITER[0])

    # --- helpers for reading the answer ---

    @staticmethod
    def lanes(data) -> dict:
        return {(lane["kind"], lane["key"]): lane for lane in data["lanes"]}

    @staticmethod
    def task_names(data) -> set:
        return {t["name"] for lane in data["lanes"] for t in lane["tasks"]}

    @staticmethod
    def post_names(data) -> set:
        return {p["name"] for lane in data["lanes"] for p in lane["posts"]}

    @property
    def project_tasks(self) -> set:
        return {self.working, self.late, self.review, self.held, self.escalated}

    @property
    def production_posts(self) -> set:
        return {self.drafting, self.client, self.missed, self.approved}

    # --- grouping and counts ---

    def test_a_manager_sees_each_project_as_a_lane_with_its_counts(self):
        data = get_in_progress_as(PM[0])
        self.assertEqual(data["scope"], "team")
        self.assertEqual(data["group_by"], "project")
        lane = self.lanes(data)[("project", self.project)]
        self.assertEqual({t["name"] for t in lane["tasks"]}, self.project_tasks)
        self.assertEqual(lane["subtitle"], CUSTOMER)
        self.assertEqual(
            lane["counts"],
            {
                "in_progress": 3,
                "review": 1,
                "on_hold": 1,
                "overdue": 1,
                "escalated": 1,
                "posts": 0,
                "missed": 0,
                "at_risk": 0,
            },
        )
        # overdue first, then the escalated one
        self.assertEqual(
            [t["name"] for t in lane["tasks"]][:2], [self.late, self.escalated]
        )
        self.assertNotIn(("project", self.other_project), self.lanes(data))

    def test_the_summary_counts_the_whole_view(self):
        tasks = get_in_progress_as(PM[0], customer=CUSTOMER)["summary"]
        self.assertEqual(
            {k: tasks[k] for k in ("in_progress", "review", "on_hold", "overdue")},
            {"in_progress": 3, "review": 1, "on_hold": 1, "overdue": 1},
        )
        self.assertEqual(tasks["escalated"], 1)
        data = get_in_progress_as(PM[0], customer=CONTENT_CUSTOMER)
        self.assertEqual(
            {k: data["summary"][k] for k in ("posts", "missed", "at_risk")},
            {"posts": 4, "missed": 1, "at_risk": 1},
        )
        self.assertFalse(data["truncated"])

    def test_a_task_row_carries_its_timer_and_people(self):
        data = get_in_progress_as(PM[0])
        row = next(
            t
            for lane in data["lanes"]
            for t in lane["tasks"]
            if t["name"] == self.working
        )
        self.assertEqual(row["status"], "Working")
        self.assertTrue(row["custom_timer_start"])
        self.assertEqual(row["estimated_hours"], 8)
        self.assertEqual(row["assignee_names"], {DEV_A[0]: DEV_A[1]})
        held = next(
            t for lane in data["lanes"] for t in lane["tasks"] if t["name"] == self.held
        )
        self.assertEqual(held["hold_reason"], "Waiting on customer")

    def test_by_person_puts_each_task_and_post_with_whoever_has_it(self):
        data = get_in_progress_as(ADMIN[0], group_by="person")
        lanes = self.lanes(data)
        dev_a = lanes[("person", DEV_A[0])]
        self.assertEqual(dev_a["title"], DEV_A[1])
        self.assertEqual(
            {t["name"] for t in dev_a["tasks"]},
            {self.working, self.review, self.escalated},
        )
        self.assertEqual(
            {p["name"] for p in lanes[("person", WRITER[0])]["posts"]}, {self.drafting}
        )
        self.assertEqual(
            {p["name"] for p in lanes[("person", DESIGNER[0])]["posts"]}, {self.missed}
        )
        self.assertEqual(
            {p["name"] for p in lanes[("person", MARKETER[0])]["posts"]},
            {self.approved},
        )
        # waiting on the client, so on nobody's part
        waiting = {p["name"] for p in lanes[("content", "content")]["posts"]}
        self.assertIn(self.client, waiting)
        self.assertNotIn(self.drafting, waiting)

    def test_by_department_puts_content_in_the_digital_lane(self):
        data = get_in_progress_as(ADMIN[0], group_by="department")
        lanes = self.lanes(data)
        # an admin sees the whole site, so only this test's records are checked
        erp = {t["name"] for t in lanes[("department", ERP)]["tasks"]}
        self.assertLessEqual(self.project_tasks, erp)
        self.assertNotIn(self.other, erp)
        self.assertIn(
            self.other,
            {t["name"] for t in lanes[("department", "__none__")]["tasks"]},
        )
        self.assertLessEqual(
            self.production_posts,
            {p["name"] for p in lanes[("department", CONTENT_DEPARTMENT)]["posts"]},
        )

    def test_an_unknown_grouping_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            get_in_progress_as(ADMIN[0], group_by="customer")

    # --- visibility (#94) ---

    def test_the_lead_and_the_coordinator_see_the_whole_project(self):
        for user in (LEAD, COORD):
            data = get_in_progress_as(user[0])
            self.assertEqual(data["scope"], "team", user)
            self.assertEqual(self.task_names(data), self.project_tasks, user)
            # not in the content team
            self.assertEqual(self.post_names(data), set(), user)

    def test_a_member_sees_only_their_own_work(self):
        data = get_in_progress_as(DEV_A[0])
        self.assertEqual(data["scope"], "own")
        self.assertEqual(
            self.task_names(data), {self.working, self.review, self.escalated}
        )
        self.assertEqual(data["summary"]["in_progress"], 2)
        self.assertEqual(data["summary"]["posts"], 0)

    def test_an_admin_sees_every_project(self):
        data = get_in_progress_as(ADMIN[0])
        self.assertLessEqual(self.project_tasks | {self.other}, self.task_names(data))
        self.assertLessEqual(self.production_posts, self.post_names(data))
        self.assertNotIn(self.not_started, self.task_names(data))
        self.assertNotIn(self.done, self.task_names(data))

    def test_the_department_wall_keeps_another_departments_project_out(self):
        walled = make_content_user(
            "dm.lead@in-progress.example", "Sneha Kurian", DM_EMPLOYEE_ROLE
        )
        frappe.db.set_value("Project", self.project, "project_lead", walled)
        data = get_in_progress_as(walled)
        self.assertEqual(self.task_names(data) & self.project_tasks, set())

    # --- content ---

    def test_only_production_statuses_are_shown(self):
        posts = self.post_names(
            get_in_progress_as(DM_COORD[0], customer=CONTENT_CUSTOMER)
        )
        self.assertEqual(posts, self.production_posts)
        self.assertNotIn(self.idea, posts)
        self.assertNotIn(self.scheduled, posts)

    def test_a_content_member_sees_only_the_posts_they_are_on(self):
        self.assertEqual(
            self.post_names(get_in_progress_as(WRITER[0])), {self.drafting}
        )

    def test_no_posts_outside_the_content_team(self):
        erp = make_content_user(
            "erp.lead@in-progress.example", "Ajay Kumar", ERP_EMPLOYEE_ROLE
        )
        frappe.db.set_value("Project", self.content_project, "project_lead", erp)
        for user in (DEV_A[0], erp):
            data = get_in_progress_as(user)
            self.assertEqual(self.post_names(data), set(), user)
            self.assertNotIn(("content", "content"), self.lanes(data), user)

    def test_a_post_row_says_which_part_is_pending_and_who_has_it(self):
        data = get_in_progress_as(ADMIN[0])
        posts = {p["name"]: p for lane in data["lanes"] for p in lane["posts"]}
        drafting = posts[self.drafting]
        self.assertEqual(drafting["customer"], CONTENT_CUSTOMER)
        self.assertEqual(drafting["platforms"], ["Instagram"])
        self.assertEqual([p["role"] for p in drafting["pending"]], ["writer"])
        self.assertEqual(
            drafting["pending"][0]["people"],
            [{"user": WRITER[0], "full_name": WRITER[1]}],
        )
        self.assertIsNone(drafting["waiting_on"])
        self.assertFalse(drafting["is_missed"])

        client = posts[self.client]
        self.assertEqual(client["pending"], [])
        self.assertEqual(client["waiting_on"], "Client approval")
        self.assertTrue(client["at_risk"])

        missed = posts[self.missed]
        self.assertTrue(missed["is_missed"])
        self.assertEqual([p["role"] for p in missed["pending"]], ["designer"])
        self.assertEqual(
            [p["role"] for p in posts[self.approved]["pending"]], ["marketer"]
        )

    # --- filters ---

    def test_customer_and_department_filters(self):
        other = get_in_progress_as(ADMIN[0], customer=OTHER_CUSTOMER)
        self.assertEqual(self.task_names(other), {self.other})
        self.assertEqual(self.post_names(other), set())

        erp = get_in_progress_as(ADMIN[0], department=ERP)
        self.assertLessEqual(self.project_tasks, self.task_names(erp))
        self.assertNotIn(self.other, self.task_names(erp))
        self.assertEqual(self.post_names(erp), set())

        digital = get_in_progress_as(ADMIN[0], department=CONTENT_DEPARTMENT)
        self.assertEqual(self.task_names(digital) & self.project_tasks, set())
        self.assertLessEqual(self.production_posts, self.post_names(digital))

        content = get_in_progress_as(ADMIN[0], customer=CONTENT_CUSTOMER)
        self.assertEqual(self.post_names(content), self.production_posts)

    def test_person_filter(self):
        dev_b = get_in_progress_as(ADMIN[0], person=DEV_B[0])
        self.assertEqual(self.task_names(dev_b), {self.late, self.held})
        self.assertEqual(self.post_names(dev_b), set())

        designer = get_in_progress_as(ADMIN[0], person=DESIGNER[0])
        self.assertEqual(self.task_names(designer), set())
        self.assertEqual(self.post_names(designer), {self.client, self.missed})

    def test_only_overdue_or_escalated_keeps_the_summary_whole(self):
        data = get_in_progress_as(PM[0], customer=CUSTOMER, only_overdue=1)
        self.assertEqual(self.task_names(data), {self.late, self.escalated})
        self.assertEqual(data["summary"]["in_progress"], 3)
        self.assertEqual(data["summary"]["on_hold"], 1)
        posts = get_in_progress_as(PM[0], customer=CONTENT_CUSTOMER, only_overdue=1)
        self.assertEqual(self.post_names(posts), {self.missed})
        self.assertEqual(posts["summary"]["posts"], 4)

    def test_hide_on_hold(self):
        data = get_in_progress_as(PM[0], hide_on_hold=1)
        self.assertNotIn(self.held, self.task_names(data))
        self.assertIn(self.late, self.task_names(data))
        self.assertEqual(data["summary"]["on_hold"], 1)

    # --- the TBO Smart app ---

    def test_the_mobile_endpoint_wraps_the_same_answer(self):
        answer = call_mobile_as(PM[0], "get_in_progress", group_by="person")
        self.assertEqual(answer["v"], 1)
        data = answer["data"]
        self.assertEqual(
            set(data), {"scope", "group_by", "summary", "lanes", "truncated"}
        )
        self.assertEqual(data["group_by"], "person")
        lane = data["lanes"][0]
        self.assertEqual(
            set(lane), {"key", "kind", "title", "subtitle", "tasks", "posts", "counts"}
        )
        self.assertEqual(
            self.task_names(data), self.task_names(get_in_progress_as(PM[0]))
        )
