# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.test_utils import (
    call_mobile_as,
    disable_mobile_push,
    enable_mobile_push,
    get_pushed_messages,
    graph_response,
    hold_commits,
    make_assigned_ticket,
    make_assignment,
    make_planned_task,
    make_project,
    make_task_in_status,
    make_tasky_user,
    register_device_as,
)
from helpdesk.work_reminders import new_notification

PM = ("pm@mobile-api.example", "Anjali Pillai")
DEV_A = ("dev.a@mobile-api.example", "Rahul Nair")
DEV_B = ("dev.b@mobile-api.example", "Meera Joseph")
ADMIN = ("manager@mobile-api.example", "Arun Menon")
TOKEN_A = "ExponentPushToken[mobile-api-dev-a]"
POST = "helpdesk.mobile_push.requests.post"


class TestMobileAPI(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(disable_mobile_push)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*ADMIN, roles=("Agent Manager",))
        for user in (DEV_A, DEV_B):
            make_tasky_user(*user)
        self.project = make_project(
            "Mobile API - Field App",
            members=[
                (PM[0], "Project Manager"),
                (DEV_A[0], "Developer"),
                (DEV_B[0], "Developer"),
            ],
            owner=PM[0],
        ).name
        self.task_a = make_planned_task(
            self.project, "Sync the price list", DEV_A[0], 0, add_days(nowdate(), -1)
        )
        self.task_b = make_planned_task(
            self.project, "Fix the invoice print", DEV_B[0], 0, add_days(nowdate(), 2)
        )

    # --- shapes and own work ---

    def test_home_bundle_has_me_counts_and_own_tasks(self):
        bundle = call_mobile_as(DEV_A[0], "get_home_bundle")
        self.assertEqual(bundle["v"], 1)
        data = bundle["data"]
        self.assertEqual(data["me"]["user"], DEV_A[0])
        self.assertFalse(data["me"]["is_manager"])
        self.assertFalse(data["me"]["can"]["team"])
        self.assertEqual(data["counts"]["tasks_overdue"], 1)
        for key in ("open_tickets", "awaiting_reply", "tasks_due_today"):
            self.assertIn(key, data["counts"])
        names = [t["name"] for t in data["tasks"]["data"]]
        self.assertEqual(names, [self.task_a])
        self.assertFalse(data["tasks"]["has_more"])

    def test_member_sees_only_their_own_tasks(self):
        page = call_mobile_as(DEV_A[0], "get_tasks")
        self.assertEqual([t["name"] for t in page["data"]], [self.task_a])
        task = page["data"][0]
        self.assertEqual(task["group"], "overdue")
        self.assertEqual(task["project_name"], "Mobile API - Field App")
        self.assertEqual(task["timer"]["state"], "idle")
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(DEV_A[0], "get_task", task=self.task_b)

    def test_task_list_pages_with_a_cursor(self):
        second = make_planned_task(
            self.project, "Map the GST fields", DEV_A[0], 0, add_days(nowdate(), 3)
        )
        first = call_mobile_as(DEV_A[0], "get_tasks", limit=1)
        self.assertTrue(first["has_more"])
        rest = call_mobile_as(
            DEV_A[0], "get_tasks", cursor=first["next_cursor"], limit=1
        )
        self.assertEqual(
            [first["data"][0]["name"], rest["data"][0]["name"]], [self.task_a, second]
        )
        self.assertIsNone(rest["next_cursor"])

    def test_task_actions_go_through_the_task_rules(self):
        task = call_mobile_as(DEV_A[0], "start_task", task=self.task_a)["data"]
        self.assertEqual(
            (task["status"], task["timer"]["state"]), ("Working", "running")
        )
        task = call_mobile_as(DEV_A[0], "pause_task", task=self.task_a)["data"]
        self.assertEqual(task["timer"]["state"], "paused")
        task = call_mobile_as(
            DEV_A[0],
            "hold_task",
            task=self.task_a,
            reason="Waiting on customer",
            note="Price list pending",
        )["data"]
        self.assertEqual(
            (task["group"], task["hold_reason"]), ("on_hold", "Waiting on customer")
        )
        task = call_mobile_as(DEV_A[0], "resume_task", task=self.task_a)["data"]
        self.assertNotEqual(task["status"], "On Hold")
        task = call_mobile_as(
            DEV_A[0],
            "complete_task",
            task=self.task_a,
            hours_worked=1.5,
            notes="Synced",
        )["data"]
        self.assertEqual(task["status"], "Completed")
        self.assertTrue(any(a["kind"] == "time" for a in task["activity"]))

        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(DEV_B[0], "start_task", task=self.task_a)

    def test_reviews_are_for_the_project_manager(self):
        review = make_task_in_status(self.project, "Approve the logo", "Pending Review")
        make_assignment("Task", review, DEV_A[0])

        approvals = call_mobile_as(PM[0], "get_approvals")["data"]
        self.assertIn(review, [a["ref"] for a in approvals])
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(DEV_A[0], "get_approvals")
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(DEV_A[0], "review_task", task=review, approve=True)

        task = call_mobile_as(PM[0], "review_task", task=review, approve=True)["data"]
        self.assertEqual(task["status"], "Completed")

    # --- manager endpoints ---

    def test_manager_endpoints_refuse_members(self):
        for method in (
            "get_team",
            "get_projects_health",
            "get_sla_summary",
            "get_escalations",
        ):
            with self.subTest(method=method), self.assertRaises(frappe.PermissionError):
                call_mobile_as(DEV_A[0], method)
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(DEV_A[0], "get_team_member", user=DEV_B[0])
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(
                DEV_B[0], "nudge", doctype="Task", name=self.task_a, message="Any news?"
            )

    def test_manager_sees_the_team_and_projects(self):
        team = call_mobile_as(PM[0], "get_team")["data"]
        people = {p["user"]: p for p in team["people"]}
        self.assertEqual(people[DEV_A[0]]["overdue"], 1)
        member = call_mobile_as(PM[0], "get_team_member", user=DEV_A[0])["data"]
        self.assertEqual([t["name"] for t in member], [self.task_a])
        health = call_mobile_as(PM[0], "get_projects_health")["data"]
        self.assertIn(self.project, [p["name"] for p in health])
        self.assertIn(
            "breaching_soon", call_mobile_as(PM[0], "get_sla_summary")["data"]
        )
        # escalations follow Overview → Follow-ups: System and Agent Managers only
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(PM[0], "get_escalations")
        self.assertIsInstance(call_mobile_as(ADMIN[0], "get_escalations")["data"], list)

    def test_manager_nudges_the_assignee(self):
        result = call_mobile_as(
            PM[0], "nudge", doctype="Task", name=self.task_a, message="Any news?"
        )
        self.assertEqual([p["user"] for p in result["data"]["notified"]], [DEV_A[0]])
        notices = frappe.get_all(
            "HD Notification",
            filters={"user_to": DEV_A[0], "reference_name": self.task_a},
            pluck="message",
        )
        self.assertTrue(any("Any news?" in m for m in notices))

    # --- tickets ---

    def test_ticket_views_and_notes(self):
        mine = make_assigned_ticket("Mobile API: printer offline", DEV_A[0])
        make_assigned_ticket("Mobile API: VPN down", DEV_B[0])

        names = [
            t["name"]
            for t in call_mobile_as(DEV_A[0], "get_tickets", view="mine")["data"]
        ]
        self.assertEqual(names, [mine])
        with self.assertRaises(frappe.ValidationError):
            call_mobile_as(DEV_A[0], "get_tickets", view="everything")

        ticket = call_mobile_as(
            DEV_A[0], "comment_ticket", ticket=mine, message="Called the customer"
        )["data"]
        notes = [m for m in ticket["conversation"] if m["kind"] == "note"]
        self.assertEqual(notes[-1]["body"], "Called the customer")
        self.assertIn("Closed", ticket["statuses"])
        with self.assertRaises(frappe.ValidationError):
            call_mobile_as(DEV_A[0], "set_ticket_status", ticket=mine, status="Lost")

    def test_reply_refuses_someone_elses_file(self):
        mine = make_assigned_ticket("Mobile API: attachment", DEV_A[0])
        other = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": "payslip.txt",
                "is_private": 1,
                "content": b"private",
            }
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            call_mobile_as(
                DEV_A[0],
                "reply_ticket",
                ticket=mine,
                message="Hi",
                attachments=[other.name],
            )

    # --- notifications ---

    def test_notifications_are_own_only(self):
        own = new_notification(DEV_A[0], "Task", self.task_a, "Due today", None)
        other = new_notification(DEV_B[0], "Task", self.task_b, "Due today", None)

        page = call_mobile_as(DEV_A[0], "get_notifications")
        names = [n["name"] for n in page["data"]]
        self.assertIn(own.name, names)
        self.assertNotIn(other.name, names)
        item = next(n for n in page["data"] if n["name"] == own.name)
        self.assertEqual(item["app_route"], f"/task/{self.task_a}")

        call_mobile_as(
            DEV_A[0], "mark_notifications_read", names=[own.name, other.name]
        )
        self.assertEqual(frappe.db.get_value("HD Notification", own.name, "read"), 1)
        self.assertEqual(frappe.db.get_value("HD Notification", other.name, "read"), 0)

    # --- devices ---

    def test_devices_are_own_only(self):
        device = register_device_as(DEV_A[0], TOKEN_A)
        self.assertEqual(device["token_type"], "Expo")
        register_device_as(DEV_A[0], TOKEN_A, platform="android")
        rows = frappe.get_all(
            "HD Mobile Device", filters={"token": TOKEN_A}, fields=["user", "platform"]
        )
        self.assertEqual(rows, [{"user": DEV_A[0], "platform": "android"}])

        removed = call_mobile_as(DEV_B[0], "unregister_device", token=TOKEN_A)["data"][
            "removed"
        ]
        self.assertFalse(removed)
        self.assertTrue(frappe.db.exists("HD Mobile Device", {"token": TOKEN_A}))
        self.assertTrue(
            call_mobile_as(DEV_A[0], "unregister_device", token=TOKEN_A)["data"][
                "removed"
            ]
        )
        self.assertFalse(frappe.db.exists("HD Mobile Device", {"token": TOKEN_A}))

        fcm = register_device_as(DEV_B[0], "fcm-raw-token-123", platform="android")
        self.assertEqual(fcm["token_type"], "FCM")
        with self.assertRaises(frappe.ValidationError):
            register_device_as(DEV_B[0], "fcm-raw-token-123", platform="windows")

    def test_a_token_signed_in_by_someone_else_moves_to_them(self):
        register_device_as(DEV_A[0], TOKEN_A)
        register_device_as(DEV_B[0], TOKEN_A)
        self.assertEqual(
            frappe.get_all(
                "HD Mobile Device", filters={"token": TOKEN_A}, pluck="user"
            ),
            [DEV_B[0]],
        )

    # --- push ---

    def test_push_is_sent_once_per_notification(self):
        register_device_as(DEV_A[0], TOKEN_A)
        enable_mobile_push()
        with patch(
            POST, return_value=graph_response({"data": [{"status": "ok"}]})
        ) as post:
            notice = new_notification(DEV_A[0], "Task", self.task_a, "Due today", None)
        messages = get_pushed_messages(post, notice.name)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["to"], TOKEN_A)
        self.assertEqual(messages[0]["title"], "Due today")
        self.assertEqual(
            {k: messages[0]["data"][k] for k in ("site", "doctype", "name")},
            {"site": "hub", "doctype": "Task", "name": self.task_a},
        )
        self.assertEqual(messages[0]["data"]["app_route"], f"/task/{self.task_a}")

    def test_no_push_when_the_setting_is_off(self):
        register_device_as(DEV_A[0], TOKEN_A)
        disable_mobile_push()
        with patch(POST) as post:
            notice = new_notification(DEV_A[0], "Task", self.task_a, "Due today", None)
        self.assertEqual(get_pushed_messages(post, notice.name), [])

    def test_a_failed_push_never_breaks_the_notification(self):
        register_device_as(DEV_A[0], TOKEN_A)
        enable_mobile_push()
        with patch(POST, side_effect=ConnectionError("Expo is down")):
            notice = new_notification(DEV_A[0], "Task", self.task_a, "Due today", None)
        self.assertTrue(frappe.db.exists("HD Notification", notice.name))
        self.assertTrue(
            frappe.db.exists(
                "Error Log",
                {"method": "Mobile push failed", "reference_name": notice.name},
            )
        )

    def test_an_uninstalled_app_loses_its_token(self):
        register_device_as(DEV_A[0], TOKEN_A)
        enable_mobile_push()
        gone = {"status": "error", "details": {"error": "DeviceNotRegistered"}}
        with patch(POST, return_value=graph_response({"data": [gone]})):
            new_notification(DEV_A[0], "Task", self.task_a, "Due today", None)
        self.assertFalse(frappe.db.exists("HD Mobile Device", {"token": TOKEN_A}))
