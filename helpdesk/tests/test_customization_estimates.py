import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk.api import customization
from helpdesk.task_estimates import add_working_days
from helpdesk.test_utils import create_agent, create_contact, hold_commits, make_ticket

AGENT = "estimator@customization.example"
CUSTOMER_EMAIL = "owner@customization-client.example"
OTHER_EMAIL = "someone.else@customization-client.example"


class CustomizationCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(AGENT, "Esti", "Mator")
        create_contact("Client Owner", CUSTOMER_EMAIL)
        create_contact("Someone Else", OTHER_EMAIL)
        frappe.db.set_single_value("HD Work Settings", "dev_hours_per_day", 6)
        self.ticket = make_ticket(
            subject="Add a status filter to the Daily Sales report",
            raised_by=CUSTOMER_EMAIL,
        ).name

    def field(self, name):
        return frappe.db.get_value("HD Ticket", self.ticket, name)


class TestTriageEstimate(CustomizationCase):
    def test_ai_marks_a_customization_and_keeps_its_estimate_once(self):
        customization.record_triage_estimate(
            self.ticket,
            {
                "request_type": "customization",
                "estimate_hours": 10,
                "estimate_note": "One report",
            },
        )
        self.assertEqual(self.field("ticket_type"), "Customization")
        self.assertEqual(self.field("custom_estimate_hours"), 10)
        self.assertEqual(self.field("custom_estimate_status"), "Estimated")

        # a re-triage doesn't overwrite an estimate that already exists
        customization.record_triage_estimate(
            self.ticket, {"request_type": "customization", "estimate_hours": 40}
        )
        self.assertEqual(self.field("custom_estimate_hours"), 10)

    def test_an_issue_is_left_alone(self):
        customization.record_triage_estimate(
            self.ticket, {"request_type": "issue", "estimate_hours": 5}
        )
        self.assertNotEqual(self.field("ticket_type"), "Customization")
        self.assertFalse(self.field("custom_estimate_status"))

    def test_hours_become_working_days(self):
        self.assertEqual(customization.delivery_for(10), add_working_days(nowdate(), 2))
        self.assertEqual(customization.delivery_for(3), add_working_days(nowdate(), 1))


class TestEstimateFlow(CustomizationCase):
    def send(self, hours=10, delivery=None):
        frappe.set_user(AGENT)
        delivery = delivery or str(add_working_days(nowdate(), 2))
        result = customization.send_estimate(
            self.ticket, hours, delivery, "Report change only"
        )
        frappe.set_user("Administrator")
        return result

    def test_agent_sends_and_customer_approves(self):
        sent = self.send()
        self.assertEqual(sent["status"], "Sent")
        self.assertEqual(self.field("ticket_type"), "Customization")
        reply = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Ticket", "reference_name": self.ticket},
            fields=["content"],
            order_by="creation desc",
            limit=1,
        )[0].content
        self.assertIn("10", reply)
        self.assertIn(f"/helpdesk/my-tickets/{self.ticket}", reply)

        frappe.set_user(CUSTOMER_EMAIL)
        seen = customization.get_estimate(self.ticket)
        self.assertTrue(seen["can_decide"])
        decided = customization.decide_estimate(self.ticket, 1)
        frappe.set_user("Administrator")

        self.assertEqual(decided["status"], "Approved")
        self.assertEqual(self.field("custom_estimate_decided_by"), CUSTOMER_EMAIL)
        self.assertTrue(
            frappe.db.exists(
                "HD Ticket Comment",
                {
                    "reference_ticket": self.ticket,
                    "content": ("like", "%Estimate approved%"),
                },
            )
        )

    def test_another_customer_cannot_decide(self):
        self.send()
        frappe.set_user(OTHER_EMAIL)
        with self.assertRaises(frappe.PermissionError):
            customization.decide_estimate(self.ticket, 1)

    def test_customer_cannot_approve_before_it_is_sent(self):
        customization.record_triage_estimate(
            self.ticket, {"request_type": "customization", "estimate_hours": 4}
        )
        frappe.set_user(CUSTOMER_EMAIL)
        with self.assertRaises(frappe.ValidationError):
            customization.decide_estimate(self.ticket, 1)

    def test_late_approval_moves_the_date(self):
        self.send()
        frappe.db.set_value(
            "HD Ticket", self.ticket, "custom_agreed_delivery", add_days(nowdate(), -3)
        )
        frappe.set_user(AGENT)
        customization.decide_estimate(self.ticket, 1)
        self.assertEqual(
            getdate(self.field("custom_agreed_delivery")),
            customization.delivery_for(10),
        )

    def test_sending_a_date_in_the_past_is_refused(self):
        frappe.set_user(AGENT)
        with self.assertRaises(frappe.ValidationError):
            customization.send_estimate(self.ticket, 5, add_days(nowdate(), -1))

    def test_approved_estimate_fills_the_task(self):
        from helpdesk.api.work import create_task_from_ticket
        from helpdesk.test_utils import make_project

        self.send(hours=10)
        frappe.set_user(AGENT)
        customization.decide_estimate(self.ticket, 1)
        frappe.set_user("Administrator")
        project = make_project("Customization Client - Support").name
        task = create_task_from_ticket(self.ticket, project)["task"]
        doc = frappe.get_doc("Task", task["name"])
        self.assertEqual(
            getdate(doc.exp_end_date), getdate(self.field("custom_agreed_delivery"))
        )
        self.assertEqual(doc.custom_estimated_hours, 10)


SCOPE = "A Sales Invoice cannot be submitted without a Sales Team row."
CHECKS = "- a normal invoice without one cannot be submitted\n2) a credit note without one can\n\n"


class TestTheWrittenScope(CustomizationCase):
    """The customer approves what will be built, not only the hours (Phase 8)."""

    def send(self, scope=SCOPE, checks=CHECKS, hours=4):
        frappe.set_user(AGENT)
        result = customization.send_estimate(
            self.ticket,
            hours,
            str(add_working_days(nowdate(), 1)),
            "",
            scope,
            checks,
        )
        frappe.set_user("Administrator")
        return result

    def approve(self):
        frappe.set_user(CUSTOMER_EMAIL)
        result = customization.decide_estimate(self.ticket, 1)
        frappe.set_user("Administrator")
        return result

    def doc(self):
        return frappe.get_doc("HD Ticket", self.ticket)

    def test_the_scope_and_checks_go_to_the_customer(self):
        sent = self.send()

        self.assertEqual(sent["scope"], SCOPE)
        # one check per line, bullets and numbers dropped
        self.assertEqual(
            sent["checks"],
            [
                "a normal invoice without one cannot be submitted",
                "a credit note without one can",
            ],
        )
        reply = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Ticket", "reference_name": self.ticket},
            pluck="content",
            order_by="creation desc",
            limit=1,
        )[0]
        self.assertIn("What we will build", reply)
        self.assertIn("<li>a credit note without one can</li>", reply)
        frappe.set_user(CUSTOMER_EMAIL)
        seen = customization.get_estimate(self.ticket)
        self.assertEqual((seen["scope"], len(seen["checks"])), (SCOPE, 2))

    def test_checks_without_a_scope_are_refused(self):
        with self.assertRaises(frappe.ValidationError):
            self.send(scope="")

    def test_the_approval_keeps_what_was_approved(self):
        self.send()
        self.assertIsNone(customization.approved_scope(self.doc()))

        decided = self.approve()

        self.assertTrue(decided["scope_approved"])
        approved = customization.approved_scope(self.doc())
        self.assertEqual(
            (approved["scope"], approved["hours"], approved["approved_by"]),
            (SCOPE, 4, CUSTOMER_EMAIL),
        )
        self.assertEqual(len(approved["checks"]), 2)

    def test_a_scope_edited_after_the_approval_no_longer_counts(self):
        self.send()
        self.approve()
        for field, value in (
            ("custom_estimate_scope", SCOPE + " Also on POS."),
            ("custom_estimate_checks", "a POS invoice without one cannot be submitted"),
            ("custom_estimate_hours", 6),
        ):
            original = self.doc().get(field)
            frappe.db.set_value("HD Ticket", self.ticket, field, value)
            self.assertIsNone(customization.approved_scope(self.doc()), field)
            self.assertFalse(customization.get_estimate(self.ticket)["scope_approved"])
            frappe.db.set_value("HD Ticket", self.ticket, field, original)
        self.assertTrue(customization.approved_scope(self.doc()))

    def test_sending_it_again_needs_a_new_approval_and_a_decline_keeps_none(self):
        self.send()
        self.approve()
        self.send(scope=SCOPE + " Also on POS.")
        self.assertIsNone(customization.approved_scope(self.doc()))

        frappe.set_user(CUSTOMER_EMAIL)
        customization.decide_estimate(self.ticket, 0)
        frappe.set_user("Administrator")
        self.assertFalse(self.doc().custom_estimate_scope_hash)

    def test_copilots_draft_fills_an_empty_scope_until_it_is_sent(self):
        customization.fill_scope(self.ticket, SCOPE, ["first check", "second check"])
        self.assertEqual(self.doc().custom_estimate_checks, "first check\nsecond check")

        customization.fill_scope(self.ticket, "Something else", "another")
        self.assertEqual(
            self.doc().custom_estimate_scope, SCOPE
        )  # a person's text stays
