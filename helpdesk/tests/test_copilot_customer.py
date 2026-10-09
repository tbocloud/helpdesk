# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""What the customer hears: stages on their site, explanations through the agent, confirm and reopen."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import client_api
from helpdesk.api import copilot as api
from helpdesk.copilot import customer, router, runs
from helpdesk.test_utils import (
    create_contact,
    create_customer,
    create_user,
    fake_investigation,
    hold_commits,
    make_copilot_settings,
    make_project,
    make_support_connection,
    make_ticket,
    make_ticket_communication,
)


class CustomerCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_copilot_settings(enabled=1, min_confidence=0.6)
        self.customer = create_customer("Copilot Customer Co").name
        self.conn = make_support_connection(self.customer, client_capabilities='["hub_api_v1"]').name
        self.ticket = make_ticket(subject="Customer side", customer=self.customer)
        self.ticket.db_set({"custom_qcs_connection": self.conn, "custom_client_ticket": "SUP-2026-00099"})
        self.pushed = []
        patcher = patch.object(client_api, "hub_api", side_effect=self.fake_hub_api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_hub_api(self, conn, method, payload=None):
        self.pushed.append((method, payload or {}))
        return {"ok": True}

    def stages(self):
        return [(p["stage"], p["message"]) for m, p in self.pushed if m == "add_update"]

    def investigated(self, category, confidence=0.9, ticket=None):
        run = runs.start_run((ticket or self.ticket).name)
        run = runs.transition(run, "Investigating", runs.WORKER)
        return router.route(run, fake_investigation(category, confidence))

    def ticket_value(self, field, ticket=None):
        return frappe.db.get_value("HD Ticket", (ticket or self.ticket).name, field)


class TestStages(CustomerCase):
    def test_stages_reach_the_customer_site_once(self):
        run = runs.start_run(self.ticket.name)
        runs.transition(run, "Investigating", runs.WORKER)
        self.assertEqual([s for s, _ in self.stages()], ["Received", "Working on it"])
        payload = self.pushed[0][1]
        self.assertEqual(payload["name"], "SUP-2026-00099")
        self.assertTrue(payload["hub_ref"].startswith(run.name))
        self.assertEqual(payload["author_name"], "TBO Copilot")

        router.route(frappe.get_doc("HDS Copilot Run", run.name), fake_investigation("bug"))
        self.assertEqual(len(self.stages()), 2)  # still "Working on it": nothing new to say
        self.assertEqual(self.ticket_value("custom_copilot_stage"), "Working on it")
        self.assertGreaterEqual(frappe.db.count("HD Ticket Comment", {"reference_ticket": self.ticket.name}), 3)

    def test_an_old_client_gets_no_call_and_the_hub_still_shows_the_stage(self):
        old = make_support_connection(create_customer("Old Client Co").name).name
        ticket = make_ticket(subject="Old client", customer="Old Client Co")
        ticket.db_set({"custom_qcs_connection": old, "custom_client_ticket": "SUP-2026-00001"})
        runs.start_run(ticket.name)
        self.assertEqual(self.pushed, [])
        self.assertEqual(self.ticket_value("custom_copilot_stage", ticket), "Received")


class TestExplanations(CustomerCase):
    def test_an_explanation_goes_to_the_card_and_the_agents_reply_answers_the_run(self):
        run = self.investigated("question")
        self.assertEqual(self.ticket_value("custom_ai_suggestion_status"), "Ready")
        self.assertIn("Delivery Note", self.ticket_value("custom_ai_suggested_reply"))
        self.assertIn(run.name, self.ticket_value("custom_ai_suggestion_note"))

        make_ticket_communication(self.ticket.name, "Here is how to print it", sent_or_received="Sent")
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Answered")
        stage, message = self.stages()[-1]
        self.assertEqual(stage, "Resolved")
        self.assertIn("Please confirm", message)
        self.assertIn("answer", message)

    def test_a_question_waits_for_the_customer_and_their_reply_starts_a_follow_up(self):
        run = self.investigated("unclear")
        self.assertIn("Which page is slow?", self.ticket_value("custom_ai_suggested_reply"))
        make_ticket_communication(self.ticket.name, "Which page is slow?", sent_or_received="Sent")
        self.assertEqual(self.stages()[-1][0], "Waiting for you")

        make_ticket_communication(self.ticket.name, "The stock report, every morning")
        follow_up = self.ticket_value("custom_copilot_run")
        self.assertNotEqual(follow_up, run.name)
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", follow_up, ["kind", "state"]), ("followup", "Queued"))
        self.assertEqual(self.stages()[-1][0], "Waiting for you")  # no "Received" for a follow-up

    def test_low_confidence_is_asked_about_not_fixed(self):
        run = self.investigated("bug", confidence=0.2)
        self.assertEqual((run.state, run.root_cause_category), ("Explaining", "unclear"))
        self.assertEqual(self.ticket_value("custom_ai_suggestion_status"), "Ready")


class TestHandOver(CustomerCase):
    def test_core_issue_makes_a_task_for_the_customers_developer(self):
        developer = create_user("dev.copilot@example.com").name
        frappe.db.set_value("HD Customer", self.customer, "custom_assigned_developer", developer)
        project = make_project("Copilot Customer Co support", owner=developer)
        project.db_set("customer", self.customer)

        run = self.investigated("core_issue")
        self.assertEqual(run.state, "Handed Over")
        self.assertTrue(run.task)
        self.assertEqual(frappe.db.get_value("Task", run.task, ["hd_ticket", "project"]), (self.ticket.name, project.name))
        self.assertEqual(run.handed_over_to, developer)
        self.assertEqual(self.stages()[-1][0], "With our team")
        self.assertNotEqual(self.ticket_value("status"), "Waiting on Task")

    def test_without_a_project_the_managers_are_told(self):
        with patch.object(runs, "tell_people") as tell:
            run = self.investigated("core_issue")
        self.assertEqual(run.state, "Handed Over")
        self.assertFalse(run.task)
        tell.assert_called_once()


class TestConfirmAndReopen(CustomerCase):
    def answered(self):
        run = self.investigated("question")
        make_ticket_communication(self.ticket.name, "Here is how", sent_or_received="Sent")
        return frappe.get_doc("HDS Copilot Run", run.name)

    def test_confirm_closes_the_ticket_and_the_run(self):
        run = self.answered()
        result = customer.decide_resolution(self.ticket.name, True, "works now")
        self.assertEqual(result["confirmation"], "Confirmed")
        self.assertEqual(self.ticket_value("status"), "Closed")
        self.assertEqual(self.ticket_value("custom_customer_confirmation"), "Confirmed")
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Closed")

    def test_reopen_escalates_and_hands_over(self):
        run = self.answered()
        with patch.object(runs, "tell_people") as tell:
            result = customer.decide_resolution(self.ticket.name, False, "the total is still wrong")
        self.assertEqual(result["confirmation"], "Reopened")
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Escalated")
        self.assertEqual(self.ticket_value("custom_customer_confirmation"), "Reopened")
        self.assertEqual(self.ticket_value("custom_copilot_stage"), "With our team")
        self.assertEqual(self.stages()[-1][0], "With our team")
        self.assertNotEqual(self.ticket_value("status"), "Closed")
        tell.assert_called_once()

    def test_reopen_needs_a_note(self):
        self.answered()
        with self.assertRaises(frappe.ValidationError):
            customer.decide_resolution(self.ticket.name, False, "")


class TestResolutionApi(CustomerCase):
    def test_write_endpoints_are_post_only(self):
        for fn in (api.start_run, api.cancel_run, api.decide_resolution):
            self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"], fn.__name__)

    def test_only_the_customer_or_an_agent_may_decide(self):
        raiser = create_contact("Copilot Raiser", "copilot.raiser@example.com", user=True)
        stranger = create_user("copilot.stranger@example.com").name
        self.ticket.db_set({"raised_by": "copilot.raiser@example.com", "contact": raiser["contact"]})
        run = self.investigated("question")
        make_ticket_communication(self.ticket.name, "Here is how", sent_or_received="Sent")

        frappe.set_user(stranger)
        with self.assertRaises(frappe.PermissionError):
            api.decide_resolution(self.ticket.name, 1)

        frappe.set_user("copilot.raiser@example.com")
        self.assertTrue(api.get_resolution(self.ticket.name)["can_decide"])
        result = api.decide_resolution(self.ticket.name, 1, "yes")
        self.assertEqual(result["confirmation"], "Confirmed")
        self.assertFalse(api.get_resolution(self.ticket.name)["can_decide"])
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", run.name, "state"), "Closed")

    def test_the_agent_dialog_sees_the_run(self):
        run = self.investigated("bug")
        info = api.get_run(self.ticket.name)
        self.assertEqual((info["run"], info["state"], info["root_cause"]), (run.name, "Preparing Fix", "bug"))
        self.assertTrue(info["can_cancel"])
        self.assertTrue(info["events"])
        api.cancel_run(self.ticket.name)
        info = api.get_run(self.ticket.name)
        self.assertEqual(info["state"], "Cancelled")
        self.assertTrue(info["can_start"])
