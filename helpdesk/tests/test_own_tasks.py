"""Inside a project, its managers see every task and everyone else only their own.

See docs/workspace-pages.md "Who sees which tasks" and "Handing a task over".
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from helpdesk.content_team import DM_EMPLOYEE_ROLE, ERP_EMPLOYEE_ROLE
from helpdesk.test_utils import (
    create_customer,
    get_reminder_messages,
    get_visible_tasks,
    hold_commits,
    make_assigned_task,
    make_content_post,
    make_content_user,
    make_project,
    make_task,
    make_tasky_user,
    run_as_user,
    set_content_settings,
)

CUSTOMER = "Galom International Trading"
PM = ("leena.varghese@own-tasks.example", "Leena Varghese")
LEAD = ("rahul.nair@own-tasks.example", "Rahul Nair")
CONSULTANT = ("anjali.varma@own-tasks.example", "Anjali Varma")
DEV = ("vishnu.prasad@own-tasks.example", "Vishnu Prasad")
# a Project Manager by role, on the team as a consultant: sees all, manages nothing
PM_MEMBER = ("deepa.menon@own-tasks.example", "Deepa Menon")
# `_` is a LIKE wildcard: this ID must not match nikhilxdas
UNDERSCORE = ("nikhil_das@own-tasks.example", "Nikhil Das")
LOOKALIKE = ("nikhilxdas@own-tasks.example", "Nikhil Xavier Das")


def call(user, method, **kwargs):
    return run_as_user(user, lambda: frappe.call(method, **kwargs))


def names(tasks) -> set[str]:
    return {t["name"] for t in tasks}


class OwnTasksCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*PM_MEMBER, roles=("Project Manager",))
        for person in (LEAD, CONSULTANT, DEV, UNDERSCORE, LOOKALIKE):
            make_tasky_user(*person)

        self.project = make_project(
            f"{CUSTOMER} - ERP Rollout",
            members=[
                (LEAD[0], "Developer"),
                (CONSULTANT[0], "Functional Consultant"),
                (DEV[0], "Developer"),
                (PM_MEMBER[0], "Functional Consultant"),
                (UNDERSCORE[0], "Developer"),
                (LOOKALIKE[0], "Developer"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])

        setup = {"custom_phase": "Setup"}
        # given to the consultant by the PM
        self.mine = make_assigned_task(
            self.project, "HR setup", CONSULTANT[0], PM[0], **setup
        )
        # the consultant gave this one to the developer
        self.given = make_assigned_task(
            self.project, "Sales incentive notification", DEV[0], CONSULTANT[0], **setup
        )
        # the consultant noted this one down and hasn't given it to anyone yet
        self.noted = run_as_user(
            CONSULTANT[0],
            lambda: make_task(self.project, "Pending bills report testing", **setup),
        ).name
        # someone else's work, none of the consultant's business
        self.other = make_assigned_task(
            self.project, "iOS App Store release", DEV[0], PM[0], **setup
        )
        self.own = {self.mine, self.given, self.noted}


class TestWhoSeesWhichTasks(OwnTasksCase):
    def test_a_member_sees_assigned_given_and_noted_tasks_only(self):
        user = CONSULTANT[0]
        self.assertEqual(get_visible_tasks(user, self.project), self.own)

        board = call(user, "helpdesk.tasky.api.get_kanban_tasks", project=self.project)[
            "columns"
        ]
        self.assertEqual(
            {t["name"] for column in board.values() for t in column}, self.own
        )
        checklist = call(
            user,
            "helpdesk.tasky.api.get_phase_tasks",
            project=self.project,
            phase="Setup",
        )
        self.assertEqual(names(checklist), self.own)
        dashboard = call(
            user, "helpdesk.tasky.api.get_project_dashboard", project=self.project
        )
        self.assertEqual(names(dashboard["tasks"]), self.own)
        self.assertEqual(dashboard["stats"]["total"], 3)
        picker = call(
            user, "helpdesk.tasky.api.get_project_tasks", project=self.project
        )
        self.assertNotIn(self.other, names(picker))
        detail = call(
            user, "helpdesk.tasky.api.get_project_detail", project=self.project
        )
        self.assertFalse(detail["sees_all_tasks"])

    def test_opening_someone_elses_task_directly_is_refused(self):
        def read(task):
            return frappe.has_permission("Task", "read", doc=task, user=CONSULTANT[0])

        self.assertFalse(read(self.other))
        self.assertTrue(read(self.given))
        self.assertTrue(read(self.noted))
        with self.assertRaises(frappe.PermissionError):
            call(CONSULTANT[0], "helpdesk.tasky.api.get_task_detail", task=self.other)

    def test_the_overview_of_a_lead_elsewhere_keeps_to_their_own_tasks_here(self):
        elsewhere = make_project("TBO Internal - Website", owner=PM[0]).name
        frappe.db.set_value("Project", elsewhere, "project_lead", CONSULTANT[0])

        overview = call(
            CONSULTANT[0], "helpdesk.api.work.get_overview", project=self.project
        )
        listed = names(overview["buckets"]["all"])
        self.assertIn(self.mine, listed)
        self.assertNotIn(self.other, listed)

    def test_managers_the_lead_and_project_managers_on_the_team_see_everything(self):
        for user in (PM[0], LEAD[0], PM_MEMBER[0]):
            with self.subTest(user=user):
                self.assertIn(self.other, get_visible_tasks(user, self.project))
                detail = call(
                    user, "helpdesk.tasky.api.get_project_detail", project=self.project
                )
                self.assertTrue(detail["sees_all_tasks"])
        # seeing everything gives a Project Manager on the team no manager powers
        self.assertFalse(
            call(
                PM_MEMBER[0],
                "helpdesk.tasky.api.get_project_detail",
                project=self.project,
            )["can_manage"]
        )

    def test_a_project_manager_off_the_team_sees_nothing_of_it(self):
        outsider = make_tasky_user(
            "omar.khalid@own-tasks.example", "Omar Khalid", roles=("Project Manager",)
        )
        self.assertEqual(get_visible_tasks(outsider, self.project), set())

    def test_an_underscore_in_a_user_id_is_not_a_wildcard(self):
        theirs = make_assigned_task(
            self.project, "Bank report to Metta", LOOKALIKE[0], PM[0]
        )
        self.assertNotIn(theirs, get_visible_tasks(UNDERSCORE[0], self.project))
        self.assertFalse(
            frappe.has_permission("Task", "read", doc=theirs, user=UNDERSCORE[0])
        )
        self.assertIn(theirs, get_visible_tasks(LOOKALIKE[0], self.project))

    def test_finished_work_stays_visible_to_whoever_did_it(self):
        frappe.get_doc("Task", self.mine).db_set("status", "Completed")
        frappe.db.set_value(
            "ToDo",
            {"reference_type": "Task", "reference_name": self.mine},
            "status",
            "Closed",
        )
        self.assertIn(self.mine, get_visible_tasks(CONSULTANT[0], self.project))


class TestHandingOver(OwnTasksCase):
    def hand_over(self, user, task, teammate, reason="Moving to the Galom go-live"):
        return call(
            user,
            "helpdesk.tasky.api.hand_over_task",
            task=task,
            teammate=teammate,
            reason=reason,
        )

    def test_the_assignee_hands_over_and_loses_sight_of_it(self):
        self.hand_over(CONSULTANT[0], self.mine, DEV[0])

        doc = frappe.get_doc("Task", self.mine)
        self.assertEqual(doc.assignees(), [DEV[0]])
        # the PM gave it out and still did: the teammate's ToDo names them, not the hander
        assigned_by = frappe.db.get_value(
            "ToDo",
            {
                "reference_type": "Task",
                "reference_name": self.mine,
                "allocated_to": DEV[0],
                "status": "Open",
            },
            "assigned_by",
        )
        self.assertEqual(assigned_by, PM[0])
        self.assertNotIn(self.mine, get_visible_tasks(CONSULTANT[0], self.project))
        self.assertFalse(
            frappe.has_permission("Task", "read", doc=self.mine, user=CONSULTANT[0])
        )

        for user, text in (
            (DEV[0], "handed you a task"),
            (LEAD[0], "Galom go-live"),
            (PM[0], "Galom go-live"),
        ):
            with self.subTest(user=user):
                self.assertTrue(
                    any(text in m for m in get_reminder_messages(user, self.mine))
                )
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Task", "reference_name": self.mine},
            pluck="content",
        )
        self.assertTrue(any("Handed over by Anjali Varma" in c for c in comments))

    def test_only_the_assignee_or_the_projects_managers_hand_over(self):
        # sees every task, but neither has it nor runs the project
        with self.assertRaises(frappe.PermissionError):
            self.hand_over(PM_MEMBER[0], self.other, CONSULTANT[0])
        with self.assertRaises(frappe.PermissionError):
            self.hand_over(CONSULTANT[0], self.given, LEAD[0])

        self.hand_over(LEAD[0], self.other, CONSULTANT[0])
        self.assertEqual(
            frappe.get_doc("Task", self.other).assignees(), [CONSULTANT[0]]
        )
        self.assertIn(self.other, get_visible_tasks(CONSULTANT[0], self.project))


class TestContentTeams(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        create_customer(CUSTOMER)
        set_content_settings(default_task_mode="One task per person")
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        self.writer = make_content_user(
            "riya.thomas@own-tasks.example", "Riya Thomas", DM_EMPLOYEE_ROLE
        )
        self.designer = make_content_user(
            "jasir.ali@own-tasks.example", "Jasir Ali", DM_EMPLOYEE_ROLE
        )
        self.erp = make_content_user(
            "ajay.kumar@own-tasks.example", "Ajay Kumar", ERP_EMPLOYEE_ROLE
        )
        self.project = make_project(f"{CUSTOMER} - Social media").name
        frappe.db.set_value(
            "Project",
            self.project,
            {"customer": CUSTOMER, "project_type": "Content Calendar"},
        )
        self.post = make_content_post(
            "Onam offer",
            CUSTOMER,
            status="Drafting",
            publish_on=add_days(now_datetime(), 10),
            writer=self.writer,
            designer=self.designer,
        )

    def task_of(self, role):
        return frappe.db.get_value(
            "Task", {"content_post": self.post.name, "content_role": role}, "name"
        )

    def test_content_people_see_only_their_own_part(self):
        visible = get_visible_tasks(self.writer, self.project)
        self.assertIn(self.task_of("Writer"), visible)
        self.assertNotIn(self.task_of("Designer"), visible)

    def test_erp_people_never_see_content_tasks(self):
        # a content task ERP was put on (the project has no department to wall it)
        task = make_task(
            self.project, "Onam offer: caption", content_post=self.post.name
        )
        frappe.get_doc(
            {
                "doctype": "ToDo",
                "allocated_to": self.erp,
                "reference_type": "Task",
                "reference_name": task.name,
                "description": task.subject,
            }
        ).insert(ignore_permissions=True)
        self.assertNotIn(task.name, get_visible_tasks(self.erp))
        self.assertFalse(frappe.has_permission("Task", "read", doc=task, user=self.erp))

    def test_a_content_task_is_handed_to_anyone_and_the_post_follows(self):
        # the designer isn't on the content calendar project's team
        task = self.task_of("Writer")
        call(
            self.writer,
            "helpdesk.tasky.api.hand_over_task",
            task=task,
            teammate=self.designer,
            reason="On leave for Onam",
        )

        self.assertEqual(frappe.get_doc("Task", task).assignees(), [self.designer])
        post = frappe.get_doc("HD Content Post", self.post.name)
        self.assertEqual(post.writer, self.designer)
        # the post's next save keeps the task where it went
        post.save(ignore_permissions=True)
        self.assertEqual(frappe.get_doc("Task", task).assignees(), [self.designer])
        self.assertNotIn(task, get_visible_tasks(self.writer, self.project))


class TestDepartmentWallSettings(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.agent = make_tasky_user(*DEV)
        self.manager = make_tasky_user(
            "sreeja.pillai@own-tasks.example", "Sreeja Pillai", roles=("Agent Manager",)
        )

    def walls(self):
        return call(
            self.manager,
            "helpdesk.api.departments.get_department_walls",
            users=[self.agent],
        )[self.agent]

    def set_wall(self, role, user=None):
        return call(
            user or self.manager,
            "helpdesk.api.departments.set_department_wall",
            user=self.agent,
            role=role,
        )

    def test_an_agent_manager_sets_one_wall_at_a_time(self):
        self.assertEqual(self.walls(), [])
        self.set_wall(ERP_EMPLOYEE_ROLE)
        self.assertEqual(self.walls(), [ERP_EMPLOYEE_ROLE])
        self.set_wall(DM_EMPLOYEE_ROLE)
        self.assertEqual(self.walls(), [DM_EMPLOYEE_ROLE])
        self.set_wall("")
        self.assertEqual(self.walls(), [])
        self.assertIn("Agent", frappe.get_roles(self.agent))

    def test_only_managers_set_walls_and_only_wall_roles(self):
        with self.assertRaises(frappe.PermissionError):
            self.set_wall(ERP_EMPLOYEE_ROLE, user=self.agent)
        with self.assertRaises(frappe.ValidationError):
            self.set_wall("System Manager")
