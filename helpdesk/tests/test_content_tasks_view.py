"""The content calendar's Tasks view: the period's role tasks as a work queue, the
"waiting on" line on each post, and the same list for the TBO Smart app.
See docs/content-calendar.md "Tasks view"."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.api.content_tasks import task_actions, task_stage
from helpdesk.content_team import (
    DM_COORDINATOR_ROLE,
    DM_EMPLOYEE_ROLE,
    ERP_EMPLOYEE_ROLE,
    ensure_role,
)
from helpdesk.test_utils import (
    call_mobile_as,
    create_customer,
    get_content_task,
    get_content_tasks_as,
    hold_commits,
    make_content_post,
    make_content_project,
    make_content_user,
    make_dm_head,
    make_tasky_user,
    set_content_settings,
    start_task_timer,
)

CUSTOMER = "Avera IoT Tasks View"
WRITER = ("writer@content-tasks-view.example", "Ajmal Rahman")
DESIGNER = ("designer@content-tasks-view.example", "Jasir Ali")
MARKETER = ("marketer@content-tasks-view.example", "Mufliha Basheer")
HEAD = ("head@content-tasks-view.example", "Sreeja Nair")
COORD = ("coord@content-tasks-view.example", "Fathima Rizwana")
ERP = ("erp@content-tasks-view.example", "Ajay Kumar")
OUTSIDER = ("dev@content-tasks-view.example", "Rahul Nair")


def by_name(data) -> dict:
    return {t["name"]: t for t in data["tasks"]}


class TestContentTasksView(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        ensure_role()
        create_customer(CUSTOMER)
        set_content_settings(
            default_task_mode="One task per person",
            writer_days_before=2,
            designer_days_before=1,
        )
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        for user in (WRITER, DESIGNER, MARKETER):
            make_content_user(*user, DM_EMPLOYEE_ROLE)
        make_dm_head(*HEAD)
        make_content_user(*COORD, DM_COORDINATOR_ROLE)
        # a content role doesn't get past the ERP wall
        make_tasky_user(*ERP, roles=(DM_EMPLOYEE_ROLE, ERP_EMPLOYEE_ROLE))
        make_tasky_user(*OUTSIDER)
        make_content_project(CUSTOMER)

        today = nowdate()
        self.start, self.end = add_days(today, -1), add_days(today, 20)
        self.draft = make_content_post(
            "Global Handwashing Day",
            CUSTOMER,
            status="Drafting",
            publish_on=f"{add_days(today, 5)} 10:00:00",
            writer=WRITER[0],
            designer=DESIGNER[0],
        ).name
        self.client = make_content_post(
            "Diwali offer",
            CUSTOMER,
            status="Drafting",
            publish_on=f"{add_days(today, 8)} 18:30:00",
            designer=DESIGNER[0],
            marketer=MARKETER[0],
        ).name
        # going live after the period, so its task isn't in it
        self.later = make_content_post(
            "Year-end roundup",
            CUSTOMER,
            status="Drafting",
            publish_on=f"{add_days(today, 40)} 10:00:00",
            writer=WRITER[0],
        ).name
        self.draft_writer = get_content_task(self.draft, "Writer")
        self.draft_designer = get_content_task(self.draft, "Designer")
        self.client_designer = get_content_task(self.client, "Designer")
        self.client_marketer = get_content_task(self.client, "Marketer")
        # the designer finished, then the post went to the client
        frappe.db.set_value("Task", self.client_designer, "status", "Completed")
        frappe.db.set_value("HD Content Post", self.client, "status", "Client Review")

    def as_user(self, user, **filters) -> dict:
        return get_content_tasks_as(user[0], self.start, self.end, **filters)

    @property
    def all_tasks(self) -> set:
        return {
            self.draft_writer,
            self.draft_designer,
            self.client_designer,
            self.client_marketer,
        }

    # --- who gets what ---

    def test_a_member_gets_only_their_own_tasks(self):
        writer = self.as_user(WRITER)
        self.assertFalse(writer["sees_all"])
        self.assertFalse(writer["can_edit"])
        self.assertEqual(set(by_name(writer)), {self.draft_writer})
        self.assertTrue(by_name(writer)[self.draft_writer]["mine"])
        self.assertEqual(
            set(by_name(self.as_user(DESIGNER))),
            {self.draft_designer, self.client_designer},
        )

    def test_the_head_and_the_coordinator_get_every_content_task(self):
        for user in (HEAD, COORD):
            data = self.as_user(user, customer=CUSTOMER)
            self.assertTrue(data["sees_all"], user)
            self.assertEqual(set(by_name(data)), self.all_tasks, user)
            self.assertFalse(by_name(data)[self.draft_writer]["mine"], user)
        self.assertTrue(self.as_user(COORD)["can_edit"])

    def test_outside_the_content_team_it_is_refused(self):
        for user in (ERP, OUTSIDER):
            with self.assertRaises(frappe.PermissionError, msg=user):
                self.as_user(user)

    def test_the_person_filter_keeps_the_tasks_assigned_to_them(self):
        data = self.as_user(COORD, customer=CUSTOMER, person=DESIGNER[0])
        self.assertEqual(
            set(by_name(data)), {self.draft_designer, self.client_designer}
        )
        # every card on the board still gets its parts line
        self.assertEqual(set(data["posts"]), {self.draft, self.client})

    def test_a_range_longer_than_two_months_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            get_content_tasks_as(WRITER[0], self.start, add_days(self.start, 90))

    # --- stages ---

    def test_tasks_are_grouped_by_stage(self):
        start_task_timer(self.draft_writer, hours_ago=1)
        frappe.db.set_value(
            "Task", self.draft_designer, {"status": "On Hold", "hold_reason": "Leave"}
        )
        data = self.as_user(COORD, customer=CUSTOMER)
        tasks = by_name(data)
        self.assertEqual(
            {name: tasks[name]["stage"] for name in self.all_tasks},
            {
                self.draft_writer: "in_progress",
                self.draft_designer: "on_hold",
                # not started, and the post sits with the client
                self.client_marketer: "review",
                self.client_designer: "done",
            },
        )
        self.assertEqual(
            tasks[self.client_marketer]["review_label"], "the client's approval"
        )
        self.assertEqual(tasks[self.draft_designer]["hold_reason"], "Leave")
        self.assertTrue(tasks[self.draft_writer]["custom_timer_start"])
        self.assertEqual(
            data["counts"],
            {"todo": 0, "in_progress": 1, "review": 1, "on_hold": 1, "done": 1},
        )
        # the queue runs in column order
        self.assertEqual(
            [t["stage"] for t in data["tasks"]],
            ["in_progress", "review", "on_hold", "done"],
        )

    def test_the_stage_rule(self):
        self.assertEqual(task_stage("Open", "Drafting"), "todo")
        self.assertEqual(task_stage("Overdue", "Design"), "todo")
        self.assertEqual(task_stage("Working", "Client Review"), "in_progress")
        self.assertEqual(task_stage("Open", "Head Review"), "review")
        self.assertEqual(task_stage("Pending Review", "Design"), "review")
        self.assertEqual(task_stage("On Hold", "Drafting"), "on_hold")
        self.assertEqual(task_stage("Completed", "Published"), "done")

    # --- actions ---

    def test_the_assignee_starts_pauses_and_completes_their_own_task(self):
        task = by_name(self.as_user(WRITER))[self.draft_writer]
        self.assertEqual(task["actions"], ["start", "complete", "hold"])
        start_task_timer(self.draft_writer, hours_ago=1)
        task = by_name(self.as_user(WRITER))[self.draft_writer]
        self.assertEqual(task["actions"], ["pause", "complete", "hold"])

    def test_a_coordinator_reassigns_but_does_not_work_the_task(self):
        task = by_name(self.as_user(COORD, customer=CUSTOMER))[self.draft_writer]
        self.assertEqual(task["actions"], ["reassign"])

    def test_the_action_rule(self):
        def actions(status, **kwargs):
            values = {
                "mine": True,
                "running": False,
                "blocked": False,
                "coordinates": False,
                "can_reassign": False,
                **kwargs,
            }
            return task_actions(status, **values)

        self.assertEqual(actions("Working"), ["resume_timer", "complete", "hold"])
        # a task waiting on another can't start or finish
        self.assertEqual(actions("Open", blocked=True), ["hold"])
        self.assertEqual(actions("On Hold"), ["resume"])
        self.assertEqual(
            actions("Pending Review", mine=False, coordinates=True), ["approve"]
        )
        self.assertEqual(actions("Completed", can_reassign=True), [])

    # --- waiting on ---

    def test_each_post_says_how_far_its_parts_are_and_who_it_waits_on(self):
        writer = self.as_user(WRITER)
        # a member sees how the post's other parts stand, not only their own
        self.assertNotIn(self.client, writer["posts"])
        draft = writer["posts"][self.draft]["progress"]
        self.assertEqual((draft["parts"], draft["done"]), (2, 0))
        self.assertEqual(draft["waiting_on"]["kind"], "part")
        self.assertEqual(draft["waiting_on"]["role"], "writer")
        self.assertEqual(
            draft["waiting_on"]["people"],
            [{"user": WRITER[0], "full_name": WRITER[1]}],
        )

        client = self.as_user(COORD, customer=CUSTOMER)["posts"][self.client]
        self.assertEqual(
            client["progress"],
            {
                "parts": 2,
                "done": 1,
                "waiting_on": {"kind": "review", "label": "the client's approval"},
            },
        )

        # the writer finishes and the post moves on to design
        frappe.db.set_value("Task", self.draft_writer, "status", "Completed")
        frappe.db.set_value("HD Content Post", self.draft, "status", "Design")
        draft = self.as_user(COORD, customer=CUSTOMER)["posts"][self.draft]["progress"]
        self.assertEqual((draft["parts"], draft["done"]), (2, 1))
        self.assertEqual(draft["waiting_on"]["role"], "designer")
        self.assertEqual(draft["waiting_on"]["task"], self.draft_designer)

    # --- the app ---

    def test_the_app_gets_the_same_list(self):
        answer = call_mobile_as(
            WRITER[0], "get_content_tasks", start=self.start, end=self.end
        )
        self.assertEqual(answer["v"], 1)
        data = answer["data"]
        self.assertEqual(
            set(data), {"sees_all", "can_edit", "tasks", "counts", "posts", "truncated"}
        )
        self.assertEqual([t["name"] for t in data["tasks"]], [self.draft_writer])
        task = data["tasks"][0]
        self.assertLessEqual(
            {
                "subject",
                "status",
                "stage",
                "role",
                "role_label",
                "post",
                "publish_on",
                "assignees",
                "assignee_names",
                "mine",
                "due",
                "is_overdue",
                "custom_timer_start",
                "custom_timer_elapsed",
                "actions",
            },
            set(task),
        )
        self.assertEqual(task["role"], "writer")
        self.assertEqual(task["assignee_names"], {WRITER[0]: WRITER[1]})
        post = data["posts"][self.draft]
        self.assertEqual(post["customer"], CUSTOMER)
        self.assertFalse(post["is_missed"])
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(
                OUTSIDER[0], "get_content_tasks", start=self.start, end=self.end
            )
