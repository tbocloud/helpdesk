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
