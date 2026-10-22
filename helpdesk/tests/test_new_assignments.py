"""A task given to someone tells them once, and stays marked New (or Reassigned) in
My Work and My Tasks until they open it.

See docs/workspace-pages.md, "New tasks".
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.test_utils import (
    TEST_TEAMS_DIRECT_URL,
    call_as_user,
    create_customer,
    enable_chat_notifications,
    get_assignment_notices,
    get_assignment_state,
    hand_over_task_as,
    hold_commits,
    make_assigned_task,
    make_project,
    make_task_template,
    make_tasky_user,
    reassign_task_as,
    run_as_user,
)

CUSTOMER = "Malabar Cashew Exports"
PM = ("meera.iyer@new-tasks.example", "Meera Iyer")
LEAD = ("joseph.thomas@new-tasks.example", "Joseph Thomas")
DEV = ("aswin.kumar@new-tasks.example", "Aswin Kumar")
CONSULTANT = ("divya.raj@new-tasks.example", "Divya Raj")
OUTSIDER = ("sajan.paul@new-tasks.example", "Sajan Paul")


class NewAssignmentsCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        make_tasky_user(*PM, roles=("Project Manager",))
        for person in (LEAD, DEV, CONSULTANT, OUTSIDER):
            make_tasky_user(*person)
        self.project = make_project(
            f"{CUSTOMER} - Go-live",
            members=[
                (LEAD[0], "Developer"),
                (DEV[0], "Developer"),
                (CONSULTANT[0], "Functional Consultant"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])

    def give(self, subject: str, assignee: str = DEV[0], by: str = PM[0]) -> str:
        return make_assigned_task(self.project, subject, assignee, by)


class TestAssignmentNotice(NewAssignmentsCase):
    def test_a_new_task_tells_the_assignee_once(self):
        task = self.give("Configure GST e-invoicing")

        notice = frappe.get_last_doc(
            "HD Notification",
            filters={"user_to": DEV[0], "notification_type": "Assignment"},
        )
        self.assertEqual(
            notice.message,
            "Meera Iyer assigned you a new task: Configure GST e-invoicing",
        )
        self.assertEqual(notice.reference_name, task)
        self.assertEqual(notice.user_from, PM[0])
        self.assertEqual(notice.link, f"/my-work?task={task}")
        self.assertEqual(len(get_assignment_notices(DEV[0], task)), 1)

    def test_reassigning_says_so(self):
        task = self.give("Payroll setup", CONSULTANT[0])
        reassign_task_as(PM[0], task, DEV[0])

        self.assertEqual(
            get_assignment_notices(DEV[0], task),
            ["Meera Iyer reassigned a task to you: Payroll setup"],
        )

    def test_a_task_coming_back_says_again(self):
        task = self.give("Payroll setup")
        reassign_task_as(PM[0], task, CONSULTANT[0])
        reassign_task_as(PM[0], task, DEV[0])

        self.assertEqual(
            get_assignment_notices(DEV[0], task),
            [
                "Meera Iyer assigned you a new task: Payroll setup",
                "Meera Iyer assigned you Payroll setup again",
            ],
        )

    def test_no_notice_for_assigning_yourself(self):
        task = self.give("Review the UAT script", LEAD[0], by=LEAD[0])

        self.assertEqual(get_assignment_notices(LEAD[0], task), [])

    def test_hand_over_sends_only_its_own_notice(self):
        task = self.give("Bank reconciliation")
        hand_over_task_as(DEV[0], task, CONSULTANT[0])

        self.assertEqual(get_assignment_notices(CONSULTANT[0], task), [])
        self.assertTrue(
            frappe.db.exists(
                "HD Notification",
                {
                    "user_to": CONSULTANT[0],
                    "reference_name": task,
                    "message": ("like", "%handed you a task%"),
                },
            )
        )

    def test_asking_for_help_sends_only_its_own_notice(self):
        task = self.give("Bank reconciliation")
        help_task = call_as_user(
            DEV[0],
            "helpdesk.tasky.api.request_help",
            task=task,
            teammate=CONSULTANT[0],
            task_name="Share the bank statement format",
        )["help_task"]["name"]

        self.assertEqual(get_assignment_notices(CONSULTANT[0], help_task), [])
        self.assertTrue(
            frappe.db.exists(
                "HD Notification",
                {
                    "user_to": CONSULTANT[0],
                    "reference_name": help_task,
                    "message": ("like", "%needs your help%"),
                },
            )
        )

    def test_a_checklist_sends_one_notice_per_person(self):
        template = make_task_template(
            "New tasks rollout",
            [
                {"task_name": "Chart of accounts", "category": "Functional"},
                {"task_name": "Opening balances", "category": "Functional"},
            ],
        ).name
        run_as_user(
            PM[0],
            lambda: frappe.call(
                "helpdesk.tasky.api.generate_checklist",
                project=self.project,
                template=template,
            ),
        )

        self.assertEqual(
            get_assignment_notices(CONSULTANT[0], self.project),
            [f"Meera Iyer assigned you 2 new tasks in {CUSTOMER} - Go-live"],
        )

    def test_chat_gets_one_message_per_assignment(self):
        enable_chat_notifications("Microsoft Teams")
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True}
        with patch(
            "helpdesk.chat_notifications.requests.post", return_value=response
        ) as post:
            self.give("Configure GST e-invoicing")

        direct = [
            c
            for c in post.call_args_list
            if c.args[0] == TEST_TEAMS_DIRECT_URL
            and c.kwargs["json"]["recipient"] == DEV[0]
        ]
        self.assertEqual(len(direct), 1)
        card = direct[0].kwargs["json"]["attachments"][0]["content"]
        self.assertIn("assigned you a new task", card["body"][0]["text"])

    def test_frappes_own_notice_opens_the_task_in_helpdesk(self):
        task = self.give("Configure GST e-invoicing")

        link = frappe.db.get_value(
            "Notification Log",
            {"for_user": DEV[0], "document_type": "Task", "document_name": task},
            "link",
        )
        self.assertTrue(link.endswith(f"/helpdesk/my-work?task={task}"))


class TestNewMark(NewAssignmentsCase):
    def test_a_new_task_is_new_until_opened(self):
        task = self.give("Configure GST e-invoicing")
        self.assertEqual(get_assignment_state(DEV[0], task), "new")
        self.assertEqual(get_assignment_state(DEV[0], task, "my_tasks"), "new")

        call_as_user(DEV[0], "helpdesk.tasky.new_assignments.mark_task_seen", task=task)

        self.assertIsNone(get_assignment_state(DEV[0], task))
        self.assertIsNone(get_assignment_state(DEV[0], task, "my_tasks"))

    def test_seen_is_per_person(self):
        task = self.give("Configure GST e-invoicing")
        call_as_user(PM[0], "helpdesk.tasky.new_assignments.mark_task_seen", task=task)
        call_as_user(PM[0], "helpdesk.tasky.new_assignments.mark_task_seen", task=task)

        self.assertEqual(get_assignment_state(DEV[0], task), "new")
        self.assertEqual(
            frappe.db.count("HD Task Seen", {"user": PM[0], "task": task}), 1
        )

    def test_a_task_coming_back_is_marked_reassigned(self):
        task = self.give("Payroll setup")
        call_as_user(DEV[0], "helpdesk.tasky.new_assignments.mark_task_seen", task=task)
        reassign_task_as(PM[0], task, CONSULTANT[0])
        reassign_task_as(PM[0], task, DEV[0])

        self.assertEqual(get_assignment_state(DEV[0], task), "reassigned")
        self.assertEqual(get_assignment_state(CONSULTANT[0], task, "my_tasks"), None)

    def test_a_task_reassigned_from_someone_else_is_new_to_me(self):
        task = self.give("Payroll setup", CONSULTANT[0])
        reassign_task_as(PM[0], task, DEV[0])

        self.assertEqual(get_assignment_state(DEV[0], task), "new")

    def test_someone_elses_work_carries_no_mark(self):
        task = self.give("Configure GST e-invoicing")

        items = call_as_user(LEAD[0], "helpdesk.api.work.get_my_work", user=DEV[0])[
            "items"
        ]
        row = next(i for i in items if i["name"] == task)
        self.assertNotIn("assignment_state", row)

    def test_only_people_who_can_read_the_task_mark_it_seen(self):
        task = self.give("Configure GST e-invoicing")

        with self.assertRaises(frappe.PermissionError):
            call_as_user(
                OUTSIDER[0], "helpdesk.tasky.new_assignments.mark_task_seen", task=task
            )
        self.assertFalse(frappe.db.exists("HD Task Seen", {"user": OUTSIDER[0]}))
