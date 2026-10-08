# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.tasky import api
from helpdesk.test_utils import (
    hold_commits,
    make_assigned_task,
    make_project,
    make_tasky_user,
    run_as_user,
)

PM = "pm.moves@task-moves.example"
LEAD = "lead.moves@task-moves.example"
DEV = "dev.moves@task-moves.example"
ASSIGNER = "assigner.moves@task-moves.example"
OUTSIDER = "outsider.moves@task-moves.example"


class TaskMovesCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(PM, "Leena Varghese", roles=("Project Manager",))
        make_tasky_user(LEAD, "Nikhil Das")
        make_tasky_user(DEV, "Fathima Rizwana")
        make_tasky_user(ASSIGNER, "Arun Kumar")
        make_tasky_user(OUTSIDER, "Joel Mathew")

        team = [(LEAD, "Developer"), (DEV, "Developer"), (ASSIGNER, "Developer")]
        self.source = make_project("Al Noor - Payroll", members=team, owner=PM).name
        frappe.db.set_value("Project", self.source, "project_lead", LEAD)
        self.target = make_project("Al Noor - HR", members=team, owner=PM).name

    def task(self, subject="Configure payroll", by=ASSIGNER, **kwargs):
        return make_assigned_task(self.source, subject, DEV, by, **kwargs)


class TestPausedTimerStaysPaused(TaskMovesCase):
    def test_a_paused_task_stays_paused_when_another_task_starts(self):
        first = self.task("Configure payroll")
        second = self.task("Import employees")
        run_as_user(DEV, lambda: api.move_task(task=first, new_status="Working"))
        frappe.db.set_value(
            "Task",
            first,
            "custom_timer_start",
            add_to_date(now_datetime(), hours=-1),
        )

        run_as_user(DEV, lambda: api.stop_timer(task=first))
        run_as_user(DEV, lambda: api.move_task(task=second, new_status="Working"))

        # the board shows a timer as running only while it has a start
        board = run_as_user(DEV, lambda: api.get_kanban_tasks(project=self.source))
        cards = {t["name"]: t for t in board["columns"]["Working"]}
        self.assertIsNone(cards[first]["custom_timer_start"])
        self.assertAlmostEqual(cards[first]["custom_timer_elapsed"], 1, delta=0.05)
        self.assertTrue(cards[second]["custom_timer_start"])

        run_as_user(DEV, lambda: api.start_timer(task=first))
        self.assertTrue(frappe.db.get_value("Task", first, "custom_timer_start"))

    def test_the_timer_only_resumes_on_a_task_in_progress(self):
        task = self.task()
        with self.assertRaises(frappe.ValidationError):
            run_as_user(DEV, lambda: api.start_timer(task=task))
        self.assertIsNone(frappe.db.get_value("Task", task, "custom_timer_start"))
