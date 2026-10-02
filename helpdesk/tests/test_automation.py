from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk import automation
from helpdesk.test_utils import make_meeting, make_tasky_user, make_ticket, run_as_user
from helpdesk.work_reminders import notify_users

AI = "tbo.ai@automation.example"
AGENT = ("agent.auto@automation.example", "Neha Raj")


class TestAutomationUser(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        make_tasky_user(*AGENT)
        frappe.db.set_single_value("HDS Hub Settings", "automation_user", None)

    def test_administrator_until_a_user_is_set(self):
        self.assertEqual(automation.automation_user(), "Administrator")

        user = automation.create_automation_user(AI)

        self.assertEqual(user, AI)
        self.assertEqual(automation.automation_user(), AI)
        self.assertEqual(frappe.db.get_value("User", AI, "full_name"), "TBO AI")
        roles = frappe.get_roles(AI)
        self.assertIn("Agent", roles)
        self.assertIn("Project Manager", roles)

        frappe.db.set_value("User", AI, "enabled", 0)
        self.assertEqual(automation.automation_user(), "Administrator")

    def test_only_system_managers_create_it_and_the_email_is_checked(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(AGENT[0], lambda: automation.create_automation_user(AI))
        with self.assertRaises(frappe.ValidationError):
            automation.create_automation_user("not-an-email")

    def test_jobs_act_as_the_automation_user_and_people_as_themselves(self):
        automation.create_automation_user(AI)

        self.assertEqual(automation.acting_user(), AI)  # tests run as Administrator
        self.assertEqual(run_as_user(AGENT[0], automation.acting_user), AGENT[0])

    def test_reminders_and_job_notes_are_credited_to_it(self):
        automation.create_automation_user(AI)
        ticket = make_ticket(subject="Automation credit")

        notify_users([AGENT[0]], "HD Ticket", ticket.name, "SLA due soon: test")
        meeting = make_meeting(
            "HD Ticket",
            ticket.name,
            add_to_date(now_datetime(), days=1),
            ["guest@customer.ae"],
        )
        meeting.note_on_reference("Teams meeting changed in Outlook: moved")

        self.assertEqual(
            frappe.db.get_value(
                "HD Notification",
                {"reference_name": str(ticket.name), "user_to": AGENT[0]},
                "user_from",
            ),
            AI,
        )
        self.assertEqual(
            frappe.db.get_value(
                "HD Ticket Comment",
                {"reference_ticket": ticket.name, "content": ("like", "%moved%")},
                "commented_by",
            ),
            AI,
        )


class TestAiDraftedReplies(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)

    def test_a_reply_from_an_ai_draft_is_tagged_but_stays_the_agents(self):
        ticket = make_ticket(subject="AI drafted reply", raised_by="buyer@customer.ae")

        ticket.reply_via_agent(message="<p>Drafted by AI</p>", ai_drafted=1)
        ticket.reply_via_agent(message="<p>Written by hand</p>")

        rows = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Ticket", "reference_name": ticket.name},
            fields=["content", "custom_ai_drafted", "sender"],
        )
        tagged = {r.content: r.custom_ai_drafted for r in rows}
        self.assertEqual(tagged["<p>Drafted by AI</p>"], 1)
        self.assertEqual(tagged["<p>Written by hand</p>"], 0)
