# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Setting and data corrections: checked by the customer's site, approved by a senior, applied record by record."""

import csv
import importlib.util
import io
import json
import time
import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import copilot as api
from helpdesk.copilot import approval_key, changes, customer, router, runs
from helpdesk.test_utils import (
    FakeCustomerSite,
    create_agent,
    create_customer,
    fake_investigation,
    hold_commits,
    make_copilot_settings,
    make_customer_project,
    make_support_connection,
    make_ticket,
)

KEY = "site-approval-key"
SETTINGS = "Selling Settings"


def price(name: str, rate: float) -> dict:
    return {
        "doctype": "Item Price",
        "name": name,
        "values": {"price_list_rate": rate},
        "why": "imported with a wrong rate",
    }


class ChangeCase(FrappeTestCase):
    shadow = 0

    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.approver = create_agent("change.approver@example.com").name
        self.senior = create_agent("change.senior@example.com").name
        make_copilot_settings(
            enabled=1,
            shadow_mode=self.shadow,
            min_confidence=0.6,
            handover_project=None,
            approvers=[
                {"user": self.approver, "senior": 0, "active": 1},
                {"user": self.senior, "senior": 1, "active": 1},
            ],
        )
        self.customer = create_customer("Correction Co").name
        connection = make_support_connection(self.customer)
        connection.approval_key = KEY
        connection.save(ignore_permissions=True)
        self.connection = connection.name
        make_customer_project(self.customer, "Correction Co support")
        self.ticket = make_ticket(
            subject="Quotations pick the wrong price list", customer=self.customer
        )
        self.site = FakeCustomerSite(key=KEY).install(self)
        self.site.add(SETTINGS, SETTINGS, {"selling_price_list": "Wholesale"})
        self.notified = []
        patcher = patch(
            "helpdesk.work_reminders.notify_users",
            side_effect=lambda *a, **k: self.notified.append(a),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # a fix task has no due date, so it would ask the real AI for an estimate
        patcher = patch("helpdesk.task_estimates.ai_estimate", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def diagnosed(self, records=None, set_aside=None, category="wrong_setting"):
        run = runs.start_run(self.ticket.name)
        run = runs.transition(run, "Investigating", runs.WORKER)
        default = [
            {
                "doctype": SETTINGS,
                "name": SETTINGS,
                "values": {"selling_price_list": "Standard Selling"},
                "why": "the default price list for new quotations",
            }
        ]
        router.route(
            run,
            fake_investigation(
                category,
                0.9,
                change_set={
                    "summary": "Selling Settings name the Wholesale price list for new quotations.",
                    "customer_note": "New quotations now use your Standard Selling price list.",
                    "found_by": "Selling Settings, read on the site",
                    "changes": default if records is None else records,
                    "set_aside": set_aside or [],
                },
            ),
        )
        return self.current_run()

    def current_run(self):
        return frappe.get_doc(
            "HDS Copilot Run", customer.latest_run(self.ticket.name).name
        )

    def change_set(self):
        return frappe.get_doc(changes.CHANGE_SET, self.current_run().change_set)

    def decide(self, user, approve=True, note=""):
        frappe.set_user(user)
        try:
            return api.decide_fix(self.ticket.name, int(approve), note)
        finally:
            frappe.set_user("Administrator")

    def events(self, event_type):
        return [
            json.loads(p)
            for p in frappe.get_all(
                "HDS Copilot Event",
                filters={"run": self.current_run().name, "event_type": event_type},
                pluck="payload",
                order_by="creation asc",
            )
        ]

    def prices(self, *names, rate=10):
        for name in names:
            self.site.add("Item Price", name, {"price_list_rate": rate})


class TestTheCheck(ChangeCase):
    def test_a_wrong_setting_is_checked_by_the_site_and_waits_for_a_senior(self):
        run = self.diagnosed()

        cs = self.change_set()
        self.assertEqual(
            (cs.kind, cs.status, cs.ready_count, cs.total),
            ("Config Change", "Checked", 1, 1),
        )
        self.assertEqual(
            json.loads(cs.items[0].old_values)["values"],
            {"selling_price_list": "Wholesale"},
        )
        approval = frappe.get_doc("HDS Copilot Approval", run.approval)
        self.assertEqual(
            (run.state, approval.kind, approval.sensitive, approval.assigned_to),
            ("Awaiting Approval", "Config Change", 1, self.senior),
        )
        self.assertFalse(run.task)  # a setting needs no developer
        self.assertEqual([tool for tool, _args in self.site.calls], ["check_change"])
        self.assertEqual(
            self.site.value(SETTINGS, SETTINGS, "selling_price_list"), "Wholesale"
        )

    def test_submitted_documents_and_the_sites_refusals_are_set_aside(self):
        self.prices("IP-1", "IP-2")
        self.site.add("Sales Invoice", "SINV-1", {"remarks": "x"}, docstatus=1)
        self.site.problems[
            ("Item Price", "IP-2")
        ] = "Item Price is not on this site's write list (HDS Support Settings)."
        self.diagnosed(
            [
                price("IP-1", 15),
                {
                    "doctype": "Sales Invoice",
                    "name": "SINV-1",
                    "values": {"remarks": "y"},
                },
                price("IP-2", 15),
            ]
        )

        cs = self.change_set()
        self.assertEqual(
            [item.check_result for item in cs.items], ["ready", "set aside", "problem"]
        )
        card = changes.card(cs)
        self.assertIn("Submitted", card["set_aside"][0]["why"])
        self.assertIn("write list", card["records"][2]["note"])
        self.assertEqual(cs.risk_level, "high")  # an invoice is at stake
        self.assertEqual(self.current_run().state, "Awaiting Approval")

    def test_nothing_the_site_would_take_means_no_approval(self):
        self.site.problems[(SETTINGS, SETTINGS)] = "Write operations are disabled"
        run = self.diagnosed()
        self.assertEqual((run.state, run.approval), ("Preparing Fix", None))
        self.assertTrue(self.notified)

    def test_damaged_data_waits_for_the_code_fix(self):
        self.prices("IP-1")
        run = self.diagnosed([price("IP-1", 15)], category="data_damaged_by_bug")
        self.assertTrue(run.task)  # the developer's fix task: the code goes first
        self.assertEqual((self.change_set().status, run.approval), ("Checked", None))

    def test_the_report_keeps_to_the_rules(self):
        too_many = [price(f"IP-{i}", 1) for i in range(changes.MAX_RECORDS + 1)]
        for records, reason in (
            (
                [{"doctype": "Item", "name": "I-1", "action": "delete", "values": {}}],
                "never delete",
            ),
            (
                [
                    {
                        "doctype": "User",
                        "name": "a@example.com",
                        "values": {"enabled": 0},
                    }
                ],
                "never changes User",
            ),
            (too_many, "at most"),
            (
                [{"doctype": "Item", "name": "I-1", "values": {}}],
                "must change something",
            ),
        ):
            with self.assertRaises(frappe.ValidationError) as caught:
                changes.validate_report({"changes": records})
            self.assertIn(reason, str(caught.exception))
        self.assertIsNone(changes.validate_report({"changes": []}))
        self.assertTrue(
            changes.validate_report(
                {
                    "set_aside": [
                        {"doctype": "Sales Invoice", "name": "S-1", "why": "submitted"}
                    ]
                }
            )
        )


class TestApplying(ChangeCase):
    def test_only_a_senior_approves_and_it_is_applied_at_once(self):
        self.diagnosed()
        with self.assertRaises(frappe.PermissionError):
            self.decide(self.approver)

        result = self.decide(self.senior)

        self.assertEqual(result["decision"]["outcome"], "approved")
        self.assertEqual(
            self.site.value(SETTINGS, SETTINGS, "selling_price_list"),
            "Standard Selling",
        )
        cs, run = self.change_set(), self.current_run()
        self.assertEqual(
            (cs.status, cs.applied_count, run.state), ("Applied", 1, "Resolved")
        )
        signed = self.site.approvals[0]
        self.assertEqual(
            (signed["approved_by"], signed["change_set"], signed["ticket"]),
            (self.senior, cs.name, self.ticket.name),
        )
        stage = self.events("stage")[-1]
        self.assertEqual(stage["stage"], "Resolved")
        self.assertIn("Standard Selling price list", stage["message"])

    def test_a_record_people_changed_since_the_check_is_left_alone(self):
        self.prices("IP-1", "IP-2", "IP-3")
        self.diagnosed([price(name, 15) for name in ("IP-1", "IP-2", "IP-3")])
        self.site.records[("Item Price", "IP-2")]["values"]["price_list_rate"] = 11

        self.decide(self.senior)

        cs = self.change_set()
        self.assertEqual(
            [item.apply_result for item in cs.items], ["applied", "skipped", "applied"]
        )
        self.assertEqual(self.site.value("Item Price", "IP-2", "price_list_rate"), 11)
        self.assertEqual((cs.status, self.current_run().state), ("Applied", "Resolved"))

    def test_a_refusal_stops_it_and_a_person_takes_over(self):
        self.prices("IP-1", "IP-2", "IP-3")
        self.diagnosed([price(name, 15) for name in ("IP-1", "IP-2", "IP-3")])
        self.site.refusals[("Item Price", "IP-2")] = "the rate must be positive"

        self.decide(self.senior)

        cs = self.change_set()
        self.assertEqual(
            [item.apply_result or "" for item in cs.items], ["applied", "refused", ""]
        )
        self.assertEqual(self.site.value("Item Price", "IP-3", "price_list_rate"), 10)
        self.assertEqual(
            (cs.status, self.current_run().state), ("Stopped", "Escalated")
        )
        self.assertIn("must be positive", cs.error)
        self.assertTrue(self.notified)

    def test_a_site_without_an_approval_key_takes_nothing(self):
        from frappe.utils.password import remove_encrypted_password

        remove_encrypted_password(
            "HDS Support Connection", self.connection, "approval_key"
        )
        self.diagnosed()
        self.decide(self.senior)

        cs = self.change_set()
        self.assertEqual(cs.status, "Stopped")
        self.assertIn("connects it to TBO Support again", cs.error)
        self.assertEqual(
            self.site.value(SETTINGS, SETTINGS, "selling_price_list"), "Wholesale"
        )

    def test_a_missing_record_is_created(self):
        self.diagnosed(
            [
                {
                    "action": "create",
                    "doctype": "Item Price",
                    "values": {
                        "item_code": "ITEM-1",
                        "price_list": "Standard Selling",
                        "price_list_rate": 15,
                    },
                }
            ]
        )
        self.decide(self.senior)
        self.assertEqual(self.change_set().items[0].new_name, "Item Price-NEW-1")


class TestTheDecision(ChangeCase):
    def test_rejected_with_a_reason(self):
        self.diagnosed()
        with self.assertRaises(frappe.ValidationError):
            self.decide(self.senior, approve=False)

        self.decide(self.senior, approve=False, note="Wholesale is right for them")

        self.assertEqual(
            (self.change_set().status, self.current_run().state),
            ("Rejected", "Preparing Fix"),
        )
        self.assertEqual(
            self.site.value(SETTINGS, SETTINGS, "selling_price_list"), "Wholesale"
        )

    def test_the_approval_stands_for_what_was_checked(self):
        self.diagnosed()
        self.site.records[(SETTINGS, SETTINGS)]["values"][
            "selling_price_list"
        ] = "Retail"
        changes.check(self.change_set())  # checked again: the old value is another now

        result = self.decide(self.senior)

        self.assertEqual(result["decision"]["outcome"], "superseded")
        self.assertEqual(
            self.site.value(SETTINGS, SETTINGS, "selling_price_list"), "Retail"
        )

    def test_applied_by_hand_reads_the_records_back(self):
        self.diagnosed()
        self.site.records[(SETTINGS, SETTINGS)]["values"][
            "selling_price_list"
        ] = "Standard Selling"  # the senior did it on the site

        frappe.set_user(self.senior)
        try:
            api.change_set_applied_by_hand(self.ticket.name)
        finally:
            frappe.set_user("Administrator")

        cs = self.change_set()
        self.assertEqual(
            (cs.status, cs.items[0].apply_note, self.current_run().state),
            ("Applied", "by hand", "Resolved"),
        )
        self.assertFalse(
            [call for call in self.site.calls if call[0] == "apply_change"]
        )

    def test_the_card_and_the_csv(self):
        self.diagnosed()
        frappe.set_user(self.senior)
        try:
            fix = api.get_run(self.ticket.name)["fix"]
        finally:
            frappe.set_user("Administrator")

        shown = fix["change_set"]
        self.assertEqual(
            shown["records"][0]["changes"],
            [
                {
                    "field": "selling_price_list",
                    "old": "Wholesale",
                    "new": "Standard Selling",
                }
            ],
        )
        self.assertEqual(
            (fix["approval"]["kind"], fix["can_decide"]), ("Config Change", True)
        )
        api.download_change_set(shown["name"])
        rows = list(csv.reader(io.StringIO(frappe.response["result"])))
        self.assertEqual(
            rows[1][:6],
            [
                SETTINGS,
                SETTINGS,
                "update",
                "selling_price_list",
                "Wholesale",
                "Standard Selling",
            ],
        )


class TestShadow(ChangeCase):
    shadow = 1

    def test_a_shadow_run_shows_its_correction_and_never_asks(self):
        run = self.diagnosed()
        self.assertEqual(
            (self.change_set().status, run.state, run.approval),
            ("Checked", "Preparing Fix", None),
        )
        self.assertFalse(run.task)


class TestTheSiteReadsOurSignature(FrappeTestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("helpdesk_client"),
        "the connector is not in this bench",
    )
    def test_the_hub_signs_and_digests_as_the_customers_site_checks(self):
        from helpdesk_client.mcp import write_guard

        change = {
            "item": "ITEM-1",
            "action": "update",
            "doctype": "Item Price",
            "name": "IP-1",
            "values": {"price_list_rate": 15.5},
        }
        expect = {"values": {"price_list_rate": 10.0}, "rows": {}}
        self.assertEqual(
            approval_key.change_digest(change, expect),
            write_guard.change_digest(write_guard.parse_change(change), expect),
        )
        token = approval_key.sign(KEY, {"v": 1, "exp": time.time() + 60, "records": []})
        with patch.object(write_guard, "approval_key", return_value=KEY):
            self.assertEqual(write_guard.read_approval(token)["v"], 1)
