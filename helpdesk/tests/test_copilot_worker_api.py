# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The worker API: role-gated, POST only, every call after the claim checked against the lease."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api import copilot_worker as api
from helpdesk.copilot import runs
from helpdesk.test_utils import (
    FakeWorker,
    create_customer,
    create_user,
    hold_commits,
    make_copilot_run,
    make_copilot_settings,
    make_ticket,
)


class TestWorkerApi(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_copilot_settings(enabled=1)
        customer = create_customer("Worker API Co").name
        frappe.db.set_value("HDS Copilot Run", {"state": "Queued"}, "state", "Cancelled")
        self.ticket = make_ticket(subject="Worker API", customer=customer)
        self.run = make_copilot_run(self.ticket.name, queued_at=add_to_date(now_datetime(), minutes=-1))

    def test_endpoints_accept_post_only(self):
        for fn in (api.claim_job, api.heartbeat, api.post_events, api.submit_result):
            self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"], fn.__name__)

    def test_only_a_copilot_worker_may_call(self):
        user = create_user("not.a.worker@example.com")
        frappe.set_user(user.name)
        with self.assertRaises(frappe.PermissionError):
            api.claim_job("w1")

    def test_the_round_trip(self):
        worker = FakeWorker("w1")
        job = worker.claim()
        self.assertEqual(job["run"], self.run.name)
        self.assertEqual(job["context"]["ticket"]["subject"], "Worker API")
        self.assertEqual(worker.heartbeat("investigate")["action"], "continue")
        self.assertEqual(worker.events([{"seq": 1, "type": "tool_call", "payload": {"tool": "get_doc"}}]), {"acked": [1]})
        self.assertEqual(worker.events([{"seq": 1, "type": "tool_call"}]), {"acked": [1]})
        self.assertEqual(frappe.db.count("HDS Copilot Event", {"run": self.run.name, "seq": 1}), 1)
        result = worker.report("bug")
        self.assertEqual((result["state"], result["root_cause"]), ("Preparing Fix", "bug"))
        with self.assertRaises(frappe.PermissionError):
            worker.heartbeat()

    def test_a_wrong_token_is_refused(self):
        FakeWorker("w1").claim()
        with self.assertRaises(frappe.PermissionError):
            api.post_events(self.run.name, "nope", [{"seq": 1}])

    def test_a_failure_fails_the_run_and_tells_people(self):
        worker = FakeWorker("w1")
        worker.claim()
        with patch.object(runs, "tell_people") as tell:
            result = worker.fail("the sandbox did not start")
        self.assertEqual(result["state"], "Failed")
        tell.assert_called_once()
        self.assertEqual(frappe.db.get_value("HDS Copilot Run", self.run.name, "failure_reason"), "the sandbox did not start")

    def test_an_empty_queue_gives_nothing(self):
        runs.transition(self.run, "Cancelled", runs.AGENT)
        self.assertEqual(api.claim_job("w1"), {})
