# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Who gets "Open in TBO Copilot" on tasks (testing fixes 7): the people who may use the desktop
app, by the desktop sign-in's own rule."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import copilot_desktop
from helpdesk.test_utils import create_agent, hold_commits, run_as_user


class TestWhoMayUseTheDesktop(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.agent = create_agent("desktop.agent@example.com").name
        self.other = create_agent("desktop.other@example.com").name

    def settings(self, enabled=1, allowed=()):
        patcher = patch.object(
            copilot_desktop,
            "_settings",
            return_value=frappe._dict(
                enabled=enabled,
                allowed_people=[frappe._dict(user=u) for u in allowed],
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def with_role(self, user):
        doc = frappe.get_doc("User", user)
        if not frappe.db.exists("Role", copilot_desktop.ROLE):
            frappe.get_doc(
                {"doctype": "Role", "role_name": copilot_desktop.ROLE, "desk_access": 1}
            ).insert(ignore_permissions=True)
        doc.add_roles(copilot_desktop.ROLE)

    def test_a_site_without_the_desktop_app_shows_nobody_the_button(self):
        with patch.object(copilot_desktop, "_settings", return_value=None):
            self.assertFalse(copilot_desktop.may_use_desktop(self.agent))

    def test_the_desktop_switched_off_shows_nobody_the_button(self):
        self.settings(enabled=0, allowed=[self.agent])
        self.assertFalse(copilot_desktop.may_use_desktop(self.agent))

    def test_the_allowed_people_list_decides_when_it_is_used(self):
        self.settings(allowed=[self.agent])
        self.with_role(self.other)  # the role does not count while the list is used
        self.assertTrue(copilot_desktop.may_use_desktop(self.agent))
        self.assertFalse(copilot_desktop.may_use_desktop(self.other))

    def test_without_a_list_the_role_decides(self):
        self.settings()
        self.with_role(self.agent)
        self.assertTrue(copilot_desktop.may_use_desktop(self.agent))
        self.assertFalse(copilot_desktop.may_use_desktop(self.other))

    def test_only_active_agents_and_never_the_administrator(self):
        self.settings(allowed=[self.agent, "Administrator"])
        frappe.db.set_value("HD Agent", self.agent, "is_active", 0)
        self.assertFalse(copilot_desktop.may_use_desktop(self.agent))
        # even as an active agent: the desktop signs in only a person's own account
        if not frappe.db.exists("HD Agent", "Administrator"):
            frappe.get_doc(
                {
                    "doctype": "HD Agent",
                    "user": "Administrator",
                    "agent_name": "Administrator",
                    "is_active": 1,
                }
            ).insert(ignore_permissions=True)
        frappe.db.set_value("HD Agent", "Administrator", "is_active", 1)
        self.assertFalse(copilot_desktop.may_use_desktop("Administrator"))

    def test_the_task_dialogs_ask_as_the_person(self):
        self.settings(allowed=[self.agent])
        self.assertEqual(
            run_as_user(self.agent, copilot_desktop.desktop), {"may_use": True}
        )
        self.assertEqual(
            run_as_user(self.other, copilot_desktop.desktop), {"may_use": False}
        )
