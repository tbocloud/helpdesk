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


SALES_ONLY = "sales.only@crm-sync.example"


class TestCRMBothWays(TestCRMUserSync):
    def test_crm_users_missing_in_helpdesk_become_agents(self):
        self.crm.users[SALES_ONLY] = {
            "name": SALES_ONLY,
            "full_name": "Sara Sales",
            "enabled": 1,
            "roles": [{"role": "Sales User"}],
        }
        result = self.sync()

        self.assertIn(SALES_ONLY, result["added_to_helpdesk"])
        self.assertEqual(frappe.db.get_value("HD Agent", SALES_ONLY, "is_active"), 1)
        self.assertIn("Agent", frappe.get_roles(SALES_ONLY))
        # someone already in helpdesk is left alone
        self.assertNotIn(SYNCED, result["added_to_helpdesk"])

    def test_only_users_we_created_are_disabled_when_they_leave(self):
        self.sync()  # creates NEW in the CRM
        frappe.db.set_value("HD Agent", NEW, "is_active", 0)
        frappe.db.set_value("HD Agent", SYNCED, "is_active", 0)

        result = self.sync()

        self.assertEqual(result["disabled_in_crm"], [NEW])
        self.assertEqual(self.crm.users[NEW]["enabled"], 0)
        # SYNCED was created in the CRM directly, so it stays enabled there
        self.assertEqual(self.crm.users[SYNCED]["enabled"], 1)


class TestCRMCustomers(TestCRMUserSync):
    def test_missing_customers_are_added_on_each_side_only(self):
        from helpdesk.integrations.crm.customers import sync_customers
        from helpdesk.test_utils import create_customer

        create_customer("Helpdesk Only Co")
        create_customer("Shared Co")
        self.crm.orgs = [
            {"name": "CRM Only Co", "organization_name": "CRM Only Co"},
            {"name": "shared co", "organization_name": "shared co "},
        ]
        with patch(FROM_SETTINGS, return_value=self.crm):
            result = sync_customers()

        self.assertIn("Helpdesk Only Co", result["created_in_crm"])
        self.assertNotIn("Shared Co", result["created_in_crm"])
        self.assertEqual(result["created_in_helpdesk"], ["CRM Only Co"])
        self.assertTrue(frappe.db.exists("HD Customer", "CRM Only Co"))

        # a second run adds nothing
        with patch(FROM_SETTINGS, return_value=self.crm):
            again = sync_customers()
        self.assertEqual(again["created_in_crm"], [])
        self.assertEqual(again["created_in_helpdesk"], [])

    def test_a_failed_agent_leaves_no_half_made_user(self):
        self.crm.users[SALES_ONLY] = {
            "name": SALES_ONLY,
            "enabled": 1,
            "roles": [{"role": "Sales User"}],
        }
        with patch(
            "helpdesk.integrations.crm.users.frappe.get_doc",
            side_effect=_fail_on_agent(frappe.get_doc),
        ):
            result = self.sync()
        self.assertTrue(any(SALES_ONLY in f for f in result["failed"]))
        self.assertFalse(frappe.db.exists("User", SALES_ONLY))


def _fail_on_agent(get_doc):
    """get_doc that refuses to build an HD Agent, like a validation error would."""

    def wrapped(*args, **kwargs):
        if args and isinstance(args[0], dict) and args[0].get("doctype") == "HD Agent":
            raise frappe.ValidationError("agent refused")
        return get_doc(*args, **kwargs)

    return wrapped
