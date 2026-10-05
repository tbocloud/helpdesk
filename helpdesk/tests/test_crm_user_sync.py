from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import crm as crm_api
from helpdesk.integrations.crm import users as crm_users
from helpdesk.test_utils import FakeCRM, create_agent, hold_commits

NEW = "new.agent@crm-sync.example"
DISABLED = "returning.agent@crm-sync.example"
SYNCED = "synced.agent@crm-sync.example"
INACTIVE = "left.agent@crm-sync.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class TestCRMUserSync(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        for email, first in (
            (NEW, "Nia"),
            (DISABLED, "Rafi"),
            (SYNCED, "Sana"),
            (INACTIVE, "Lena"),
        ):
            create_agent(email, first, "Agent")
        frappe.db.set_value("HD Agent", INACTIVE, "is_active", 0)
        frappe.db.set_single_value(
            "HD CRM Settings",
            {
                "enabled": 1,
                "sync_users": 1,
                "crm_role": "Sales User",
                "send_welcome_email": 1,
            },
        )
        self.crm = FakeCRM(
            users=[
                {"name": DISABLED, "enabled": 0},
                {"name": SYNCED, "roles": [{"role": "Sales User"}]},
            ]
        )

    def sync(self):
        with patch(FROM_SETTINGS, return_value=self.crm):
            return crm_users.sync_users()

    def test_creates_enables_and_gives_crm_roles(self):
        result = self.sync()

        self.assertIn(NEW, result["created"])
        self.assertTrue(self.crm.users[NEW]["welcome_email"])
        self.assertIn(DISABLED, result["enabled"])
        self.assertEqual(self.crm.users[DISABLED]["enabled"], 1)
        # one call for everyone who needed a role, with the role from settings
        ((emails, role),) = self.crm.role_calls
        self.assertIn(NEW, emails)
        self.assertIn(DISABLED, emails)
        self.assertNotIn(SYNCED, emails)
        self.assertEqual(role, "Sales User")
        # an agent who left isn't created
        self.assertNotIn(INACTIVE, self.crm.users)
        self.assertIn(
            "created", frappe.db.get_single_value("HD CRM Settings", "last_sync_result")
        )

    def test_a_second_run_changes_nothing(self):
        self.sync()
        result = self.sync()
        self.assertEqual(result["created"], [])
        self.assertEqual(result["role_added"], [])

    def test_one_failing_user_is_reported_not_raised(self):
        self.crm.failing = {NEW}
        result = self.sync()
        self.assertTrue(any(NEW in f for f in result["failed"]))
        self.assertIn(DISABLED, result["enabled"])
        self.assertIn(
            "Failed", frappe.db.get_single_value("HD CRM Settings", "last_sync_result")
        )

    def test_bots_and_administrator_are_skipped(self):
        emails = {u["email"] for u in crm_users.helpdesk_users()}
        self.assertNotIn("Administrator", emails)
        self.assertNotIn(INACTIVE, emails)
        self.assertIn(NEW, emails)

    def test_a_new_agent_queues_a_sync(self):
        with patch.object(frappe, "enqueue") as enqueue:
            create_agent("brand.new@crm-sync.example", "Brand", "New")
        self.assertTrue(
            any(
                call.args and call.args[0] == crm_users.SYNC_JOB
                for call in enqueue.call_args_list
            )
        )

    def test_only_admins_manage_the_connection(self):
        frappe.set_user(NEW)
        with self.assertRaises(frappe.PermissionError):
            crm_api.test_connection()
        frappe.set_user("Administrator")
        with patch(FROM_SETTINGS, return_value=self.crm):
            self.assertTrue(crm_api.test_connection()["ok"])

    def test_turning_on_needs_credentials(self):
        settings = frappe.get_single("HD CRM Settings")
        settings.enabled = 1
        settings.site_url = ""
        with self.assertRaises(frappe.ValidationError):
            settings.save()
