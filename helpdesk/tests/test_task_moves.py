# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api import work
from helpdesk.tasky import api
from helpdesk.test_utils import (
    get_reminder_messages,
    get_task_comments,
    hold_commits,
    make_assigned_task,
    make_project,
    make_task,
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


class TestAssignedBy(TaskMovesCase):
    def test_task_payloads_name_who_assigned_it(self):
        task = self.task(by=LEAD)

        detail = run_as_user(DEV, lambda: api.get_task_detail(task=task))
        self.assertEqual(detail["assigned_by"], LEAD)
        self.assertEqual(detail["assigned_by_name"], "Nikhil Das")

        board = run_as_user(PM, lambda: api.get_kanban_tasks(project=self.source))
        card = next(t for t in board["columns"]["Open"] if t["name"] == task)
        self.assertEqual(card["assigned_by"], LEAD)

        mine = run_as_user(DEV, lambda: api.get_my_tasks())
        self.assertEqual(
            next(t for t in mine if t["name"] == task)["assigned_by"], LEAD
        )

        items = run_as_user(DEV, lambda: work.get_my_work())["items"]
        item = next(i for i in items if i["name"] == task)
        self.assertEqual(item["assigned_by_name"], "Nikhil Das")

    def test_the_latest_assignment_names_the_assigner(self):
        task = self.task(by=LEAD)
        run_as_user(PM, lambda: api.update_task(task=task, assigned_to=ASSIGNER))

        detail = api.get_task_detail(task=task)
        self.assertEqual(detail["assigned_to"], ASSIGNER)
        self.assertEqual(detail["assigned_by"], PM)

    def test_falls_back_to_the_creator_when_the_assignment_does_not_say(self):
        task = self.task()
        frappe.db.set_value("Task", task, "owner", PM, update_modified=False)
        todo = frappe.qb.DocType("ToDo")
        frappe.qb.update(todo).set(todo.assigned_by, None).where(
            todo.reference_name == task
        ).run()

        self.assertEqual(api.get_task_detail(task=task)["assigned_by"], PM)

    def test_an_unassigned_task_has_no_assigner(self):
        task = make_task(self.source, "Unassigned work").name
        detail = api.get_task_detail(task=task)
        self.assertIsNone(detail["assigned_by"])
        self.assertIsNone(detail["assigned_by_name"])


class TestMoveTask(TaskMovesCase):
    def test_the_assigner_moves_it_and_the_assignee_is_told(self):
        task = self.task()

        moved = run_as_user(
            ASSIGNER,
            lambda: api.move_task_to_project(task=task, project=self.target),
        )

        self.assertEqual(moved["project"], self.target)
        self.assertEqual(frappe.db.get_value("Task", task, "project"), self.target)
        self.assertEqual(frappe.db.get_value("Task", task, "_assign"), f'["{DEV}"]')
        self.assertTrue(get_task_comments(task, "Moved from Al Noor - Payroll%"))
        self.assertIn(
            "Arun Kumar moved Configure payroll to Al Noor - HR",
            get_reminder_messages(DEV, task),
        )

    def test_who_may_move_a_task(self):
        for user, allowed in (
            (ASSIGNER, True),
            (PM, True),
            (LEAD, True),
            ("Administrator", True),
            (DEV, False),
            (OUTSIDER, False),
        ):
            with self.subTest(user=user):
                task = self.task(f"Task moved by {user}")

                def move(task=task):
                    return api.move_task_to_project(task=task, project=self.target)

                if allowed:
                    run_as_user(user, move)
                    expected = self.target
                else:
                    with self.assertRaises(frappe.PermissionError):
                        run_as_user(user, move)
                    expected = self.source
                self.assertEqual(frappe.db.get_value("Task", task, "project"), expected)

    def test_the_assignee_cannot_move_a_task_they_gave_themselves(self):
        task = self.task(by=DEV)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                DEV, lambda: api.move_task_to_project(task=task, project=self.target)
            )

    def test_the_target_must_be_an_open_project_the_mover_can_add_tasks_to(self):
        task = self.task()
        elsewhere = make_project("Gulf Star - Rollout", owner=PM).name
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                ASSIGNER,
                lambda: api.move_task_to_project(task=task, project=elsewhere),
            )

        frappe.db.set_value("Project", elsewhere, "status", "Completed")
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM, lambda: api.move_task_to_project(task=task, project=elsewhere)
            )
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM, lambda: api.move_task_to_project(task=task, project=self.source)
            )
        self.assertEqual(frappe.db.get_value("Task", task, "project"), self.source)

    def test_closed_tasks_stay_in_their_project(self):
        task = self.task()
        frappe.db.set_value("Task", task, "status", "Completed")
        with self.assertRaises(frappe.ValidationError):
            api.move_task_to_project(task=task, project=self.target)

    def test_phase_and_dependencies_of_the_old_project_are_cleared(self):
        before = make_task(self.source, "Collect employee data").name
        task = self.task(custom_phase="Discovery")
        after = make_task(self.source, "Run first payroll").name
        frappe.db.set_value("Task", task, "depends_on_task", before)
        frappe.db.set_value("Task", after, "depends_on_task", task)
        make_task(self.target, "Leave policy", custom_phase="Build")

        moved = run_as_user(
            PM, lambda: api.move_task_to_project(task=task, project=self.target)
        )

        self.assertEqual(moved["phase_cleared"], "Discovery")
        self.assertEqual(moved["dependency_cleared"], before)
        self.assertEqual(moved["dependents_released"], 1)
        values = frappe.db.get_value(
            "Task", task, ["custom_phase", "depends_on_task"], as_dict=True
        )
        self.assertFalse(values.custom_phase)
        self.assertIsNone(values.depends_on_task)
        self.assertIsNone(frappe.db.get_value("Task", after, "depends_on_task"))
        self.assertTrue(get_task_comments(task, "%Phase Discovery cleared%"))

    def test_a_phase_the_target_has_is_kept(self):
        task = self.task(custom_phase="Build")
        make_task(self.target, "Leave policy", custom_phase="Build")

        moved = api.move_task_to_project(task=task, project=self.target)

        self.assertEqual(moved["phase_cleared"], "")
        self.assertEqual(frappe.db.get_value("Task", task, "custom_phase"), "Build")

    def test_the_assignee_joins_the_new_team_when_its_manager_moves_it(self):
        task = self.task()
        elsewhere = make_project("Gulf Star - Rollout", owner=PM).name

        moved = run_as_user(
            PM, lambda: api.move_task_to_project(task=task, project=elsewhere)
        )

        self.assertEqual(moved["not_on_team"], [])
        self.assertTrue(
            frappe.db.exists(
                "Project User",
                {"parent": elsewhere, "user": DEV, "parenttype": "Project"},
            )
        )

    def test_a_member_moving_it_is_told_the_assignee_is_not_on_the_new_team(self):
        task = self.task()
        elsewhere = make_project(
            "Gulf Star - Rollout", members=[(ASSIGNER, "Developer")], owner=PM
        ).name

        moved = run_as_user(
            ASSIGNER, lambda: api.move_task_to_project(task=task, project=elsewhere)
        )

        self.assertEqual(moved["not_on_team"], [DEV])
        self.assertFalse(
            frappe.db.exists(
                "Project User",
                {"parent": elsewhere, "user": DEV, "parenttype": "Project"},
            )
        )

    def test_payloads_say_who_may_move_a_task(self):
        task = self.task()
        as_assigner = run_as_user(ASSIGNER, lambda: api.get_task_detail(task=task))
        as_assignee = run_as_user(DEV, lambda: api.get_task_detail(task=task))
        self.assertTrue(as_assigner["can_move"])
        self.assertFalse(as_assignee["can_move"])


class TestRecentProjects(TaskMovesCase):
    def recent(self, user=DEV):
        return [p.name for p in run_as_user(user, api.get_recent_projects)]

    def open_project(self, project, user=DEV):
        run_as_user(user, lambda: api.record_project_view(project=project))

    def test_opened_projects_are_listed_newest_first(self):
        self.open_project(self.source)
        self.open_project(self.target)
        self.open_project(self.source)

        self.assertEqual(self.recent(), [self.source, self.target])
        self.assertEqual(self.recent(ASSIGNER), [])

    def test_only_the_latest_are_kept(self):
        projects = [
            make_project(f"Rollout {i}", members=[(DEV, "Developer")], owner=PM).name
            for i in range(api.RECENT_PROJECTS + 2)
        ]
        for i, project in enumerate(projects):
            self.open_project(project)
            # opened a minute apart, newest last, all before the next visit
            frappe.db.set_value(
                "View Log",
                {"viewed_by": DEV, "reference_name": project},
                "modified",
                add_to_date(now_datetime(), minutes=i - len(projects)),
                update_modified=False,
            )

        self.assertEqual(self.recent(), projects[::-1][: api.RECENT_PROJECTS])
        self.assertEqual(
            frappe.db.count(
                "View Log", {"viewed_by": DEV, "reference_doctype": "Project"}
            ),
            api.RECENT_PROJECTS,
        )

    def test_projects_the_user_can_no_longer_read_or_that_are_gone_drop_out(self):
        left = make_project("Al Noor - Audit", members=[(DEV, "Developer")], owner=PM)
        gone = make_project("Al Noor - Trial", members=[(DEV, "Developer")], owner=PM)
        for project in (self.source, left.name, gone.name):
            self.open_project(project)

        frappe.db.delete("Project User", {"parent": left.name, "user": DEV})
        frappe.delete_doc("Project", gone.name, ignore_permissions=True, force=True)

        self.assertEqual(self.recent(), [self.source])

    def test_a_project_the_user_cannot_read_is_not_recorded(self):
        with self.assertRaises(frappe.PermissionError):
            self.open_project(self.source, user=OUTSIDER)


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
