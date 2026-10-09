"""A task's Activity: its history in the task details window.

See docs/workspace-pages.md "Activity".
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    call_as_user,
    create_customer,
    get_task_activity_as,
    hold_commits,
    make_assigned_task,
    make_project,
    make_task,
    make_tasky_user,
    make_ticket,
    make_timesheet,
    record_versions,
    run_as_user,
    save_task_as,
    use_date_format,
)
from helpdesk.utils import add_assignment, remove_assignment

CUSTOMER = "Bayt Al Khaleej Foods"
PM = ("leena.varghese@task-activity.example", "Leena Varghese")
LEAD = ("rahul.nair@task-activity.example", "Rahul Nair")
DEV = ("vishnu.prasad@task-activity.example", "Vishnu Prasad")
# on the team, but the task is neither theirs nor given by them
TEAMMATE = ("anjali.varma@task-activity.example", "Anjali Varma")


class TaskActivityCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        record_versions(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(CUSTOMER)
        make_tasky_user(*PM, roles=("Project Manager",))
        for person in (LEAD, DEV, TEAMMATE):
            make_tasky_user(*person)
        self.project = make_project(
            f"{CUSTOMER} - ERP Rollout",
            members=[
                (LEAD[0], "Developer"),
                (DEV[0], "Developer"),
                (TEAMMATE[0], "Developer"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])
        self.task = make_assigned_task(
            self.project, "Configure VAT returns", DEV[0], PM[0]
        )


class TestTaskActivity(TaskActivityCase):
    def test_created_says_who_and_where_the_task_came_from(self):
        created = get_task_activity_as(DEV[0], self.task, "created")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["by"], PM[0])
        self.assertEqual(created[0]["by_name"], PM[1])
        self.assertEqual(created[0]["origin"], {"type": None, "name": None})

        ticket = make_ticket(subject="VAT report shows wrong totals", customer=CUSTOMER)
        from_ticket = run_as_user(
            PM[0],
            lambda: make_task(self.project, "Fix VAT totals", hd_ticket=ticket.name),
        ).name
        created = get_task_activity_as(PM[0], from_ticket, "created")[0]
        self.assertEqual(created["origin"], {"type": "ticket", "name": ticket.name})

    def test_assignments_show_who_gave_it_and_who_took_it_off(self):
        run_as_user(
            LEAD[0],
            lambda: add_assignment(
                {
                    "doctype": "Task",
                    "name": self.task,
                    "assign_to": [TEAMMATE[0]],
                    "description": "<p>Pair with Vishnu on the <b>ledger</b> mapping</p>",
                },
                ignore_permissions=True,
            ),
        )
        run_as_user(
            LEAD[0],
            lambda: remove_assignment(
                "Task", self.task, DEV[0], ignore_permissions=True
            ),
        )

        assigned = {
            i["to"]: i for i in get_task_activity_as(PM[0], self.task, "assigned")
        }
        self.assertEqual(assigned[DEV[0]]["by"], PM[0])
        self.assertEqual(assigned[DEV[0]]["to_name"], DEV[1])
        # Frappe's own "Assignment for Task ..." text says nothing
        self.assertIsNone(assigned[DEV[0]]["note"])
        self.assertEqual(assigned[TEAMMATE[0]]["by"], LEAD[0])
        self.assertEqual(
            assigned[TEAMMATE[0]]["note"], "Pair with Vishnu on the ledger mapping"
        )

        unassigned = get_task_activity_as(PM[0], self.task, "unassigned")
        self.assertEqual(len(unassigned), 1)
        self.assertEqual(unassigned[0]["to"], DEV[0])
        self.assertEqual(unassigned[0]["by"], LEAD[0])
        self.assertEqual(unassigned[0]["by_name"], LEAD[1])

    def test_status_and_estimate_changes(self):
        save_task_as(DEV[0], self.task, status="Working")
        save_task_as(LEAD[0], self.task, custom_estimated_hours=6)

        status = get_task_activity_as(DEV[0], self.task, "status")
        self.assertEqual(len(status), 1)
        self.assertEqual(
            (status[0]["from"], status[0]["to"], status[0]["by"]),
            ("Open", "Working", DEV[0]),
        )
        estimate = get_task_activity_as(DEV[0], self.task, "estimate")
        self.assertEqual(len(estimate), 1)
        self.assertEqual((estimate[0]["from"], estimate[0]["to"]), (0.0, 6.0))
        self.assertEqual(estimate[0]["by"], LEAD[0])

    def test_a_due_date_moved_later_shows_once_with_its_reason(self):
        old_due = str(frappe.db.get_value("Task", self.task, "exp_end_date"))
        new_due = add_days(old_due, 3)
        call_as_user(
            LEAD[0],
            "helpdesk.tasky.api.update_task_plan",
            task=self.task,
            due_date=new_due,
            reason="Client sent the trial balance late",
        )
        # the history has the date change too; the note replaces it
        self.assertTrue(
            frappe.db.exists(
                "Version",
                {
                    "ref_doctype": "Task",
                    "docname": self.task,
                    "data": ("like", "%exp_end_date%"),
                },
            )
        )

        items = get_task_activity_as(DEV[0], self.task)
        self.assertEqual([i for i in items if i["kind"] == "due"], [])
        notes = [i for i in items if i["kind"] == "note"]
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0]["text"].startswith("Due date moved"))
        self.assertIn("Client sent the trial balance late", notes[0]["text"])
        self.assertEqual(notes[0]["by"], LEAD[0])

    def test_a_due_date_moved_earlier_is_its_own_item(self):
        old_due = str(frappe.db.get_value("Task", self.task, "exp_end_date"))
        new_due = add_days(old_due, -2)
        save_task_as(LEAD[0], self.task, exp_end_date=new_due)

        due = get_task_activity_as(DEV[0], self.task, "due")
        self.assertEqual(len(due), 1)
        self.assertEqual(
            (due[0]["from"], due[0]["to"], due[0]["reason"]),
            (str(getdate(old_due)), str(getdate(new_due)), None),
        )

    def test_a_due_date_reads_right_in_a_day_first_date_format(self):
        # the history stores 05-10-2026, which month-first parsing reads as 10 May
        use_date_format(self, "dd-mm-yyyy")
        save_task_as(LEAD[0], self.task, exp_end_date="2026-10-05")

        due = get_task_activity_as(DEV[0], self.task, "due")
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["to"], "2026-10-05")

    def test_less_tracked_saves_dont_push_out_status_changes(self):
        save_task_as(DEV[0], self.task, status="Working")
        with patch("helpdesk.task_activity.MAX_ITEMS", 2):
            for n in range(3):
                save_task_as(DEV[0], self.task, description=f"Draft {n}")
            status = get_task_activity_as(DEV[0], self.task, "status")
        self.assertEqual([s["to"] for s in status], ["Working"])

    def test_saves_that_only_mention_a_tracked_field_dont_push_out_changes(self):
        save_task_as(DEV[0], self.task, status="Working")
        with patch("helpdesk.task_activity.MAX_ITEMS", 2):
            # the description holds a tracked field name, so these rows pass the SQL filter
            for n in range(3):
                save_task_as(DEV[0], self.task, description=f'"status" note {n}')
            status = get_task_activity_as(DEV[0], self.task, "status")
        self.assertEqual([s["to"] for s in status], ["Working"])

    def test_a_note_that_repeats_the_subject_is_not_shown(self):
        subject = frappe.db.get_value("Task", self.task, "subject")
        frappe.get_doc(
            {
                "doctype": "ToDo",
                "allocated_to": TEAMMATE[0],
                "reference_type": "Task",
                "reference_name": self.task,
                "description": subject,
            }
        ).insert(ignore_permissions=True)

        assigned = {
            i["to"]: i for i in get_task_activity_as(PM[0], self.task, "assigned")
        }
        self.assertIsNone(assigned[TEAMMATE[0]]["note"])

    def test_hold_shows_its_note_not_a_bare_status_change(self):
        run_as_user(
            DEV[0],
            lambda: tasky.hold_task(self.task, "Laptop / system issue", "Screen broke"),
        )

        items = get_task_activity_as(PM[0], self.task)
        self.assertEqual([i for i in items if i["kind"] == "status"], [])
        notes = [i["text"] for i in items if i["kind"] == "note"]
        self.assertEqual(notes, ["On hold: Laptop / system issue - Screen broke"])

    def test_info_notes_appear_as_plain_text(self):
        frappe.get_doc("Task", self.task).add_comment(
            "Info", frappe.utils.escape_html("Waiting on the client's <VAT> number")
        )
        notes = get_task_activity_as(DEV[0], self.task, "note")
        self.assertEqual(
            [n["text"] for n in notes], ["Waiting on the client's <VAT> number"]
        )

    def test_comments_are_added_and_shown(self):
        content = "Checked the <b>ledger</b>\nAll totals match"
        item = call_as_user(
            DEV[0],
            "helpdesk.tasky.api.add_task_comment",
            task=self.task,
            content=content,
        )
        self.assertEqual(item["kind"], "comment")
        self.assertEqual(item["text"], content)
        self.assertEqual((item["by"], item["by_name"]), (DEV[0], DEV[1]))
        self.assertTrue(item["name"])
        self.assertEqual(len(item["at"]), len("2026-10-10 10:00:00"))

        result = call_as_user(
            PM[0], "helpdesk.tasky.api.get_task_activity", task=self.task
        )
        self.assertTrue(result["can_comment"])
        comments = [i for i in result["items"] if i["kind"] == "comment"]
        self.assertEqual(comments, [item])

        with self.assertRaises(frappe.ValidationError):
            call_as_user(
                DEV[0],
                "helpdesk.tasky.api.add_task_comment",
                task=self.task,
                content="  ",
            )
        with self.assertRaises(frappe.ValidationError):
            call_as_user(
                DEV[0],
                "helpdesk.tasky.api.add_task_comment",
                task=self.task,
                content="x" * 5001,
            )

    def test_time_logged_on_the_task_shows_and_cancelled_time_does_not(self):
        day = add_days(nowdate(), -1)
        logged = make_timesheet(self.project, 2.5, f"{day} 10:00:00", task=self.task)
        frappe.db.set_value(
            "Timesheet", logged.name, "owner", DEV[0], update_modified=False
        )
        cancelled = make_timesheet(self.project, 4, f"{day} 14:00:00", task=self.task)
        frappe.db.set_value("Timesheet", cancelled.name, "docstatus", 2)

        time = get_task_activity_as(PM[0], self.task, "time")
        self.assertEqual(len(time), 1)
        self.assertEqual(
            (time[0]["hours"], time[0]["date"], time[0]["by"], time[0]["by_name"]),
            (2.5, str(getdate(day)), DEV[0], DEV[1]),
        )

    def test_someone_who_cannot_see_the_task_gets_neither(self):
        with self.assertRaises(frappe.PermissionError):
            get_task_activity_as(TEAMMATE[0], self.task)
        with self.assertRaises(frappe.PermissionError):
            call_as_user(
                TEAMMATE[0],
                "helpdesk.tasky.api.add_task_comment",
                task=self.task,
                content="Can I help?",
            )

    def test_newest_first(self):
        save_task_as(DEV[0], self.task, status="Working")
        call_as_user(
            DEV[0],
            "helpdesk.tasky.api.add_task_comment",
            task=self.task,
            content="Started on the VAT mapping",
        )

        items = get_task_activity_as(DEV[0], self.task)
        self.assertEqual(
            [i["kind"] for i in items], ["comment", "status", "assigned", "created"]
        )
        self.assertEqual(items, sorted(items, key=lambda i: i["at"], reverse=True))
