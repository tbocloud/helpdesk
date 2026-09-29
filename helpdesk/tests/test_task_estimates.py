from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk import task_estimates
from helpdesk.api import work
from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    create_customer,
    make_assignment,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
    run_as_user,
    set_work_settings,
)

CUSTOMER = "Cedar Trading FZE"
PM = ("pm.estimate@estimates.example", "Anu Joseph")
DEV = ("dev.estimate@estimates.example", "Rahul Nair")
SUPPORT = ("support.estimate@estimates.example", "Sneha Paul")


def ai_answer(days, hours=0, reason="Report customisation"):
    return {
        "response": {"working_days": days, "estimated_hours": hours, "reason": reason}
    }


class EstimateCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

        create_customer(CUSTOMER)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*DEV)
        make_tasky_user(*SUPPORT)
        set_work_settings(ai_task_estimates=1, max_task_days=15, weekly_off="Sunday")
        project = make_project(
            "Cedar ERP", members=[(DEV[0], "Developer")], owner=PM[0]
        )
        project.db_set({"project_type": "ERP Implementation", "customer": CUSTOMER})
        self.project = project.name

    def add_task(self, **kwargs):
        return run_as_user(
            PM[0],
            lambda: tasky.add_task(
                project=self.project,
                task_name=kwargs.pop("name", "Sales register report"),
                **kwargs,
            ),
        )["name"]


class TestWorkingDays(EstimateCase):
    def test_weekly_off_is_skipped(self):
        # 3 Oct 2026 is a Saturday
        self.assertEqual(
            str(task_estimates.add_working_days("2026-10-03", 2)), "2026-10-05"
        )
        set_work_settings(weekly_off="Friday and Saturday")
        self.assertEqual(
            str(task_estimates.add_working_days("2026-10-02", 2)), "2026-10-05"
        )


class TestEstimates(EstimateCase):
    def test_ai_sets_due_date_and_hours_for_undated_task(self):
        with patch.object(task_estimates, "call_haiku", return_value=ai_answer(3, 10)):
            task = self.add_task(assigned_to=DEV[0])

        doc = frappe.get_doc("Task", task)
        self.assertEqual(
            getdate(doc.exp_end_date), task_estimates.add_working_days(nowdate(), 3)
        )
        self.assertEqual(doc.custom_estimated_hours, 10)
        self.assertTrue(doc.ai_estimated)
        self.assertEqual(doc.estimate_note, "Report customisation")
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Task", "reference_name": task},
            pluck="content",
        )
        self.assertTrue(any("AI estimate" in c for c in comments))

    def test_estimate_is_capped(self):
        with patch.object(task_estimates, "call_haiku", return_value=ai_answer(90)):
            task = self.add_task()
        self.assertEqual(
            getdate(frappe.db.get_value("Task", task, "exp_end_date")),
            task_estimates.add_working_days(nowdate(), 15),
        )

    def test_without_ai_the_project_type_default_is_used(self):
        with patch.object(
            task_estimates, "call_haiku", side_effect=RuntimeError("no key")
        ), patch.object(frappe, "log_error"):
            task = self.add_task()
        doc = frappe.get_doc("Task", task)
        self.assertEqual(
            getdate(doc.exp_end_date),
            task_estimates.add_working_days(
                nowdate(), task_estimates.TYPICAL_DAYS["ERP Implementation"]
            ),
        )
        self.assertIn("typical time", doc.estimate_note)

    def test_finished_tasks_teach_the_fallback(self):
        start = add_days(nowdate(), -30)
        for i in range(3):
            done = make_task(
                self.project,
                f"Old report {i}",
                exp_start_date=start,
                custom_category="Functional",
            )
            done.db_set({"status": "Completed", "completed_on": add_days(start, 4)})

        with patch.object(
            task_estimates, "call_haiku", side_effect=RuntimeError("no key")
        ), patch.object(frappe, "log_error"):
            task = self.add_task(category="Functional")
        self.assertEqual(
            getdate(frappe.db.get_value("Task", task, "exp_end_date")),
            task_estimates.add_working_days(nowdate(), 5),
        )

    def test_dates_people_set_are_kept(self):
        due = add_days(nowdate(), 20)
        with patch.object(task_estimates, "call_haiku") as ai:
            task = self.add_task(due_date=due)
        self.assertFalse(ai.called)
        self.assertEqual(
            str(frappe.db.get_value("Task", task, "exp_end_date")), str(getdate(due))
        )

    def test_turned_off_means_no_estimate(self):
        set_work_settings(ai_task_estimates=0)
        with patch.object(task_estimates, "call_haiku") as ai:
            task = self.add_task()
        self.assertFalse(ai.called)
        self.assertIsNone(frappe.db.get_value("Task", task, "exp_end_date"))

    def test_task_from_a_ticket_is_estimated_too(self):
        ticket = make_ticket(subject="Add VAT column", customer=CUSTOMER)
        make_assignment("HD Ticket", ticket.name, SUPPORT[0])
        with patch.object(task_estimates, "call_haiku", return_value=ai_answer(2)):
            task = run_as_user(
                SUPPORT[0],
                lambda: work.create_task_from_ticket(
                    ticket=ticket.name, project=self.project
                ),
            )["task"]["name"]
        self.assertEqual(
            getdate(frappe.db.get_value("Task", task, "exp_end_date")),
            task_estimates.add_working_days(nowdate(), 2),
        )

    def test_completion_date_is_recorded(self):
        task = make_task(self.project, "Print format", add_days(nowdate(), 2))
        task.status = "Completed"
        task.save(ignore_permissions=True)
        self.assertEqual(str(task.completed_on), nowdate())
        task.status = "Open"
        task.save(ignore_permissions=True)
        self.assertIsNone(task.completed_on)
