from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import task_descriptions
from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    ai_description_answer,
    create_customer,
    hold_commits,
    make_project,
    make_task,
    make_task_template,
    make_tasky_user,
    run_as_user,
    set_work_settings,
)

CUSTOMER = "Juniper Foods LLC"
PM = ("pm.describe@descriptions.example", "Meera Das")
DEV = ("dev.describe@descriptions.example", "Arjun Menon")
OUTSIDER = ("outsider.describe@descriptions.example", "Kiran Rao")
DRAFT = (
    "Set up single sign-on so staff log in with their company accounts.\n\n"
    "Steps\n- Confirm the identity provider with the customer\n- Configure it\n\n"
    "Done when\n- A test user signs in"
)


class AITaskDescriptionCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(task_descriptions.drop_pending)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        task_descriptions.drop_pending()

        create_customer(CUSTOMER)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*DEV)
        make_tasky_user(*OUTSIDER)
        set_work_settings(ai_task_descriptions=1, ai_task_estimates=0)
        project = make_project(
            "Juniper ERP", members=[(DEV[0], "Developer")], owner=PM[0]
        )
        project.db_set({"customer": CUSTOMER, "notes": "<p>ERPNext rollout</p>"})
        self.project = project.name

        ai_on = patch.object(task_descriptions, "is_ai_configured", return_value=True)
        self.ai_on = ai_on.start()
        self.addCleanup(ai_on.stop)

    def add_task(self, **kwargs):
        name = kwargs.pop("name", "Enable SSO")
        return run_as_user(
            PM[0],
            lambda: tasky.add_task(project=self.project, task_name=name, **kwargs),
        )["name"]


class TestBackgroundDescriptions(AITaskDescriptionCase):
    def test_empty_task_gets_ai_description_and_mark(self):
        task = self.add_task(phase="Setup")
        self.assertIn(task, task_descriptions.pending_tasks())

        with patch.object(
            task_descriptions, "call_haiku", return_value=ai_description_answer(DRAFT)
        ) as call:
            task_descriptions.describe_tasks([task])

        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.description, DRAFT)
        self.assertTrue(doc.custom_ai_description)
        self.assertTrue(tasky.get_task_detail(task)["ai_description"])
        prompt = call.call_args.args[1]
        self.assertIn("Juniper ERP", prompt)
        self.assertIn(CUSTOMER, prompt)
        self.assertIn("ERPNext rollout", prompt)

    def test_description_written_before_the_job_is_kept(self):
        task = self.add_task()
        run_as_user(PM[0], lambda: tasky.update_task(task, description="Our own notes"))

        with patch.object(
            task_descriptions, "call_haiku", return_value=ai_description_answer(DRAFT)
        ) as call:
            task_descriptions.describe_tasks([task])

        call.assert_not_called()
        doc = frappe.get_doc("Task", task)
        self.assertEqual(doc.description, "Our own notes")
        self.assertFalse(doc.custom_ai_description)

    def test_text_typed_while_the_ai_was_writing_is_kept(self):
        task = self.add_task()
        frappe.db.set_value("Task", task, "description", "Typed meanwhile")

        self.assertFalse(task_descriptions.save_if_still_empty(task, "", DRAFT))
        self.assertEqual(
            frappe.db.get_value("Task", task, "description"), "Typed meanwhile"
        )

    def test_setting_off_queues_nothing(self):
        set_work_settings(ai_task_descriptions=0)
        task = self.add_task()
        self.assertNotIn(task, task_descriptions.pending_tasks())

    def test_described_task_or_no_ai_is_not_queued(self):
        self.add_task(description="Already described")
        self.ai_on.return_value = False
        self.add_task(name="Configure taxes")
        self.assertEqual(task_descriptions.pending_tasks(), [])

    def test_template_tasks_go_out_in_batches(self):
        template = make_task_template(
            "Juniper rollout",
            [
                {"task_name": f"Step {i}", "category": "Functional"}
                for i in range(task_descriptions.BATCH_SIZE + 2)
            ],
        )
        tasky.generate_checklist(self.project, template.name)
        self.assertEqual(
            len(task_descriptions.pending_tasks()), task_descriptions.BATCH_SIZE + 2
        )

        with patch.object(frappe, "enqueue") as enqueue:
            task_descriptions.enqueue_pending()

        self.assertEqual(
            [len(c.kwargs["tasks"]) for c in enqueue.call_args_list],
            [task_descriptions.BATCH_SIZE, 2],
        )
        self.assertEqual(task_descriptions.pending_tasks(), [])

    def test_editing_an_ai_description_removes_the_mark(self):
        task = make_task(self.project, "Map chart of accounts", description=DRAFT)
        frappe.db.set_value("Task", task.name, "custom_ai_description", 1)

        run_as_user(
            PM[0],
            lambda: tasky.update_task(task.name, description=DRAFT + "\nAlso GST."),
        )
        self.assertFalse(
            frappe.db.get_value("Task", task.name, "custom_ai_description")
        )

        run_as_user(
            PM[0],
            lambda: tasky.update_task(
                task.name, description=DRAFT, ai_description=True
            ),
        )
        self.assertTrue(frappe.db.get_value("Task", task.name, "custom_ai_description"))


class TestDraftEndpoint(AITaskDescriptionCase):
    def draft(self, user, **kwargs):
        return run_as_user(
            user,
            lambda: task_descriptions.draft_task_description(
                task_name="Enable SSO", **kwargs
            ),
        )

    def test_member_gets_a_draft_and_nothing_is_saved(self):
        make_task(self.project, "Install the app", custom_phase="Setup")
        with patch.object(
            task_descriptions,
            "call_haiku",
            return_value=ai_description_answer("**Goal**\n* Do it"),
        ) as call:
            result = self.draft(
                DEV[0], project=self.project, phase="Setup", category="DevOps"
            )

        self.assertEqual(result["description"], "Goal\n- Do it")
        self.assertIn("Install the app", call.call_args.args[1])
        self.assertFalse(frappe.db.exists("Task", {"subject": "Enable SSO"}))

    def test_outsider_is_refused(self):
        with patch.object(task_descriptions, "call_haiku") as call:
            self.assertRaises(
                frappe.PermissionError, self.draft, OUTSIDER[0], project=self.project
            )
        call.assert_not_called()

    def test_member_cannot_draft_for_someone_elses_task(self):
        task = make_task(self.project, "Lead's own task")
        with patch.object(task_descriptions, "call_haiku") as call:
            self.assertRaises(
                frappe.PermissionError, self.draft, DEV[0], task=task.name
            )
        call.assert_not_called()

    def test_ai_not_set_up_gives_a_clear_error(self):
        self.ai_on.return_value = False
        with patch.object(task_descriptions, "call_haiku") as call:
            with self.assertRaisesRegex(frappe.ValidationError, "AI isn't set up"):
                self.draft(PM[0], project=self.project)
        call.assert_not_called()
        self.assertFalse(task_descriptions.get_ai_status()["available"])
