# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""HDS Copilot Settings: built-in stage messages, configured ones win, limits are checked."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.copilot import settings
from helpdesk.test_utils import hold_commits, make_copilot_settings


class TestCopilotSettings(FrappeTestCase):
    def setUp(self):
        hold_commits(self)

    def test_every_stage_has_a_built_in_message(self):
        # straight to the table, so validate does not seed the rows back
        frappe.db.delete("HDS Copilot Message Template", {"parent": "HDS Copilot Settings"})
        frappe.clear_document_cache("HDS Copilot Settings", "HDS Copilot Settings")
        for stage in settings.STAGES:
            self.assertEqual(settings.template_for(stage), settings.DEFAULT_TEMPLATES[stage])

    def test_a_configured_message_wins_over_the_built_in_one(self):
        make_copilot_settings(templates={"Resolved": "Done: {resolution}"})
        self.assertEqual(settings.template_for("Resolved"), "Done: {resolution}")
        self.assertEqual(
            settings.template_for("Received"), settings.DEFAULT_TEMPLATES["Received"]
        )

    def test_saving_seeds_the_missing_stages(self):
        doc = make_copilot_settings()
        self.assertEqual({r.stage for r in doc.message_templates}, set(settings.STAGES))

    def test_an_unknown_stage_is_refused(self):
        with self.assertRaises(ValueError):
            settings.template_for("Shipped")

    def test_limits_are_checked(self):
        with self.assertRaises(frappe.ValidationError):
            make_copilot_settings(lease_minutes=0)
        with self.assertRaises(frappe.ValidationError):
            make_copilot_settings(min_confidence=1.5)

    def test_disabled_by_default(self):
        frappe.db.set_single_value("HDS Copilot Settings", "enabled", 0)
        self.assertFalse(settings.is_enabled())
        frappe.db.set_single_value("HDS Copilot Settings", "enabled", 1)
        self.assertTrue(settings.is_enabled())
