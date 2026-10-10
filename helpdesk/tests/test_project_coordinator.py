"""A Project Coordinator runs a project's tasks without managing the project.

See docs/workspace-pages.md "Who sees which tasks" and "What a Project Coordinator may do".
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.test_utils import (
    call_as_user,
    get_visible_tasks,
    hand_over_task_as,
    hold_commits,
    make_assigned_task,
    make_project,
    make_tasky_user,
    run_as_user,
)

PM = ("leena.varghese@coordinator.example", "Leena Varghese")
LEAD = ("rahul.nair@coordinator.example", "Rahul Nair")
COORDINATOR = ("sneha.pillai@coordinator.example", "Sneha Pillai")
DEV = ("vishnu.prasad@coordinator.example", "Vishnu Prasad")
CONSULTANT = ("anjali.varma@coordinator.example", "Anjali Varma")
# an active agent who isn't on the project's team
OUTSIDER = ("omar.khalid@coordinator.example", "Omar Khalid")
API = "helpdesk.tasky.api"


class CoordinatorCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*PM, roles=("Project Manager",))
        for person in (LEAD, COORDINATOR, DEV, CONSULTANT, OUTSIDER):
            make_tasky_user(*person)
        self.project = make_project(
            "Galom International Trading - ERP Rollout",
            members=[
                (LEAD[0], "Developer"),
                (COORDINATOR[0], "Project Coordinator"),
                (DEV[0], "Developer"),
                (CONSULTANT[0], "Functional Consultant"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value(
            "Project",
            self.project,
            {"project_lead": LEAD[0], "review_before_done": 1},
        )
        # the PM gave this to the developer: none of the coordinator's own work
        self.task = make_assigned_task(
            self.project, "Sales incentive notification", DEV[0], PM[0]
        )

    def call(self, method: str, **kwargs):
        return call_as_user(COORDINATOR[0], f"{API}.{method}", **kwargs)


class TestWhatACoordinatorMayDo(CoordinatorCase):
    def test_sees_every_task_of_the_project(self):
        self.assertIn(self.task, get_visible_tasks(COORDINATOR[0], self.project))
        detail = self.call("get_project_detail", project=self.project)
        self.assertTrue(detail["sees_all_tasks"])
        self.assertTrue(detail["can_coordinate"])
        self.assertTrue(detail["can_add_tasks"])
        # none of the project's own controls
        self.assertFalse(detail["can_manage"])
        self.assertFalse(detail["can_change_lead"])

    def test_creates_and_assigns_a_task_to_a_teammate(self):
        task = self.call(
            "add_task",
            project=self.project,
            task_name="Payroll parallel run",
            assigned_to=CONSULTANT[0],
        )
        self.assertEqual(
            frappe.get_doc("Task", task["name"]).assignees(), [CONSULTANT[0]]
        )

    def test_reassigns_moves_phase_and_reschedules(self):
        due = frappe.db.get_value("Task", self.task, "exp_end_date")
        self.call("update_task", task=self.task, assigned_to=CONSULTANT[0], phase="UAT")
        self.call(
            "update_task_plan",
            task=self.task,
            due_date=str(add_days(due, 3)),
            reason="Customer moved the UAT workshop",
        )
        doc = frappe.get_doc("Task", self.task)
        self.assertEqual(doc.assignees(), [CONSULTANT[0]])
        self.assertEqual(doc.custom_phase, "UAT")
        # a later date is recorded as a slip, as for leads
        self.assertEqual(doc.slip_count, 1)

    def test_hands_over_someone_elses_task(self):
        hand_over_task_as(COORDINATOR[0], self.task, CONSULTANT[0])
        self.assertEqual(frappe.get_doc("Task", self.task).assignees(), [CONSULTANT[0]])

    def test_puts_on_hold_and_resumes(self):
        self.call(
            "hold_task", task=self.task, reason="Other", note="Customer data pending"
        )
        held = frappe.db.get_value(
            "Task", self.task, ["status", "hold_by"], as_dict=True
        )
        self.assertEqual((held.status, held.hold_by), ("On Hold", COORDINATOR[0]))
        self.call("resume_task", task=self.task)
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Open")

    def test_approves_and_sends_back_reviews(self):
        frappe.db.set_value("Task", self.task, "status", "Pending Review")
        self.call("send_back_task", task=self.task, note="Add the Ajman branch")
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Open")

        frappe.db.set_value("Task", self.task, "status", "Pending Review")
        self.call("approve_task", task=self.task)
        # signed off, not sent round to review again
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), "Completed")

    def test_my_work_offers_plan_and_approve(self):
        task = make_assigned_task(
            self.project, "Weekly status call", COORDINATOR[0], PM[0]
        )
        frappe.db.set_value("Task", task, "status", "Pending Review")
        items = call_as_user(COORDINATOR[0], "helpdesk.api.work.get_my_work")["items"]
        item = next(i for i in items if i["name"] == task)
        self.assertTrue(item["can_plan"])
        self.assertTrue(item["can_approve"])


class TestWhatACoordinatorMayNotDo(CoordinatorCase):
    def assertRefused(self, method: str, **kwargs):
        with self.assertRaises(frappe.PermissionError):
            call_as_user(COORDINATOR[0], method, **kwargs)

    def test_project_settings_team_and_lead_stay_with_its_managers(self):
        self.assertRefused(
            f"{API}.update_project",
            project=self.project,
            project_name="Renamed by the coordinator",
        )
        self.assertRefused(f"{API}.set_project_lead", project=self.project, user=DEV[0])
        self.assertRefused(f"{API}.rotate_project_lead", project=self.project)

    def test_bringing_someone_onto_the_team_stays_with_its_managers(self):
        self.assertRefused(
            f"{API}.add_task",
            project=self.project,
            task_name="Store transfer report",
            assigned_to=OUTSIDER[0],
        )
        self.assertRefused(
            f"{API}.update_task", task=self.task, assigned_to=OUTSIDER[0]
        )
        self.assertNotIn(
            OUTSIDER[0],
            frappe.get_all("Project User", {"parent": self.project}, pluck="user"),
        )

    def test_no_deleting_signoff_or_recurring_schedules(self):
        self.assertFalse(
            frappe.has_permission("Task", "delete", doc=self.task, user=COORDINATOR[0])
        )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(COORDINATOR[0], lambda: frappe.delete_doc("Task", self.task))
        self.assertRefused(
            "helpdesk.api.project_signoff.create_signoff",
            project=self.project,
            module_title="Accounts",
            signatory_contact="",
            trainer=COORDINATOR[0],
        )
        self.assertRefused(
            "helpdesk.api.recurring_tasks.save_recurring_task",
            project=self.project,
            values={"title": "Monthly backup check"},
        )

    def test_the_role_counts_only_on_their_own_project(self):
        elsewhere = make_project(
            "TBO Internal - Website",
            members=[(COORDINATOR[0], "Developer"), (DEV[0], "Developer")],
            owner=PM[0],
        ).name
        task = make_assigned_task(elsewhere, "Contact form spam", DEV[0], PM[0])
        frappe.db.set_value("Task", task, "status", "Pending Review")
        self.assertNotIn(task, get_visible_tasks(COORDINATOR[0], elsewhere))
        self.assertRefused(f"{API}.approve_task", task=task)

    def test_other_members_still_run_only_their_own_work(self):
        frappe.db.set_value("Task", self.task, "status", "Pending Review")
        with self.assertRaises(frappe.PermissionError):
            call_as_user(CONSULTANT[0], f"{API}.approve_task", task=self.task)
        detail = call_as_user(
            CONSULTANT[0], f"{API}.get_project_detail", project=self.project
        )
        self.assertFalse(detail["can_coordinate"])


class TestWhoMayAddTasks(CoordinatorCase):
    """The New task button shows when `can_add_tasks`, and add_task follows the same rule."""

    def test_a_member_adds_a_task(self):
        detail = call_as_user(
            CONSULTANT[0], f"{API}.get_project_detail", project=self.project
        )
        self.assertTrue(detail["can_add_tasks"])
        self.assertFalse(detail["can_manage"])
        task = call_as_user(
            CONSULTANT[0],
            f"{API}.add_task",
            project=self.project,
            task_name="Pending bills report testing",
            assigned_to=CONSULTANT[0],
            due_date=str(add_days(nowdate(), 4)),
        )
        self.assertEqual(
            frappe.db.get_value("Task", task["name"], "project"), self.project
        )

    def test_someone_off_the_project_cant(self):
        with self.assertRaises(frappe.PermissionError):
            call_as_user(OUTSIDER[0], f"{API}.get_project_detail", project=self.project)
        with self.assertRaises(frappe.PermissionError):
            call_as_user(
                OUTSIDER[0],
                f"{API}.add_task",
                project=self.project,
                task_name="Not my project",
            )
