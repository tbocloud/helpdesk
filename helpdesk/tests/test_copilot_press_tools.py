# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Press tools through Copilot (Phase 18): the reads, the backup that runs at once, the actions
that wait for an approval card and run after Approve, and the never list. The Phase 2 client
itself is tested in test_copilot_press."""

import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import copilot_press as api
from helpdesk.copilot import actions, assistant, press_tools
from helpdesk.copilot.press import PressError
from helpdesk.test_utils import create_agent, hold_commits, make_copilot_settings

SITES = [
    {
        "name": "galom.tbo365.cloud",
        "status": "Active",
        "group": "bench-group-1",
        "server": "f1",
        "plan": "Standard",
        "bench": "bench-0020",
    },
    {
        "name": "galom-test.tbo365.cloud",
        "status": "Active",
        "group": "bench-group-1",
        "server": "f1",
        "plan": "Standard",
        "bench": "bench-0020",
    },
    {
        "name": "demoerp.tbo365.cloud",
        "status": "Active",
        "group": "bench-group-1",
        "server": "f1",
        "plan": "Standard",
        "bench": "bench-0020",
    },
]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakePress:
    """Press as the tests see it: the methods Copilot may call, and what they were asked."""

    def __init__(self):
        self.calls = []
        self.jobs = [
            {
                "name": "48213",
                "job_type": "Backup Site",
                "status": "Success",
                "creation": "2026-11-12 01:30:00",
                "duration": "0:00:41",
                "site": "demoerp.tbo365.cloud",
            },
            {
                "name": "48214",
                "job_type": "Restart Bench",
                "status": "Success",
                "creation": "2026-11-12 02:16:00",
                "duration": "0:00:41",
                "bench": "bench-0020",
            },
        ]

    def __call__(self, method, **args):
        self.calls.append((method, args))
        if method == "press.api.client.get_list":
            return self.get_list(args)
        if method == "press.api.site.get":
            return {
                "name": args["name"],
                "status": "Active",
                "group": "bench-group-1",
                "server": "f1",
                "frappe_version": "Version 15",
                "info": {"last_deployed": "2026-11-09 21:10:00"},
            }
        if method == "press.api.site.current_plan":
            return {
                "current_plan": {"name": "Standard", "plan_title": "Standard"},
                "usage_in_percent": {"cpu": 12, "disk": 20, "database": 38},
            }
        if method == "press.api.site.installed_apps":
            return [
                {
                    "app": "frappe",
                    "branch": "version-15",
                    "hash": "a1b2c3d4e5",
                    "tag": "v15.42.0",
                },
                {"app": "galom", "branch": "main", "hash": "0123456789"},
            ]
        if method == "press.api.site.backup":
            return "Site Backup 48213"
        if method == "press.api.bench.restart":
            return None
        if method in press_tools.NEVER:
            raise AssertionError(f"{method} must never be called")
        return {}

    def get_list(self, args):
        doctype, filters = args["doctype"], args.get("filters") or {}
        if doctype == "Site":
            rows = SITES
            if filters.get("name"):
                rows = [s for s in rows if s["name"] == filters["name"]]
            if isinstance(filters.get("name"), list):
                needle = filters["name"][1].strip("%")
                rows = [s for s in SITES if needle in s["name"]]
            return [dict(r) for r in rows]
        if doctype == "Site Backup":
            return [
                {
                    "name": "SB-1",
                    "creation": "2026-11-12 01:30:00",
                    "with_files": 0,
                    "offsite": 1,
                }
            ]
        if doctype == "Site Update":
            return [
                {"name": "SU-1", "status": "Success", "creation": "2026-11-09 21:10:00"}
            ]
        if doctype == "Agent Job":
            rows = [
                j
                for j in self.jobs
                if all(
                    j.get(k) == v
                    for k, v in filters.items()
                    if k in ("site", "bench", "job_type")
                )
            ]
            return rows[: args.get("limit") or 20]
        return []


class PressCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.one = create_agent("press.one@example.com").name
        self.two = create_agent("press.two@example.com").name
        self.senior = create_agent("press.senior@example.com").name
        make_copilot_settings(
            enabled=1,
            press_url="https://press.example.com",
            press_api_key="key",
            press_api_secret="secret",
            approvers=[
                {"user": self.one, "senior": 0, "active": 1},
                {"user": self.two, "senior": 0, "active": 1},
                {"user": self.senior, "senior": 1, "active": 1},
            ],
        )
        self.press = FakePress()
        self.sent, self.enqueued, self.intents = [], [], {}
        for target, kw in (
            ("helpdesk.copilot.press.call", {"side_effect": self.press}),
            (
                "helpdesk.copilot.press_tools.ping",
                {"return_value": {"ok": True, "code": 200, "ms": 310}},
            ),
            ("helpdesk.copilot.press_tools.time.sleep", {"return_value": None}),
            (
                "helpdesk.copilot.actions.send_card",
                {"side_effect": lambda person, approval: self.sent.append(person)},
            ),
            ("helpdesk.work_reminders.notify_users", {"return_value": None}),
            (
                "helpdesk.copilot.assistant.send",
                {
                    "side_effect": lambda user, reply, **links: self.sent.append(
                        (user, reply["lines"])
                    )
                },
            ),
            ("frappe.enqueue", {"side_effect": self.enqueue}),
            ("helpdesk.ai_engine.call_haiku", {"side_effect": self.fake_ai}),
        ):
            patcher = patch(target, **kw)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.cache.delete_keys("copilot-chat:")

    def enqueue(self, method, **kwargs):
        self.enqueued.append(method)
        if isinstance(method, str) and method.endswith("execute_approved"):
            press_tools.execute_approved(kwargs["name"])

    def fake_ai(self, system_prompt, user_message, ticket_name=None, job=None):
        text = user_message.rsplit("<<<\n", 1)[-1].rsplit("\n>>>", 1)[0]
        return {"response": self.intents.get(text, {"intent": "unclear"}), "cost": 0}

    def say(self, text, intent):
        self.intents[text] = intent
        return assistant.receive(self.one, "Web", text)

    def calls(self, method):
        return [args for m, args in self.press.calls if m == method]


class TestReads(PressCase):
    def test_site_status_composes_plan_health_apps_and_backups(self):
        status = press_tools.site_status("galom.tbo365.cloud")
        self.assertEqual(status["status"], "Active")
        self.assertEqual(status["bench"], "bench-0020")
        self.assertEqual(status["plan"]["name"], "Standard")
        self.assertEqual(status["plan"]["database_pct"], 38)
        self.assertEqual(
            status["apps"][0],
            {
                "app": "frappe",
                "branch": "version-15",
                "hash": "a1b2c3d",
                "tag": "v15.42.0",
            },
        )
        self.assertEqual(status["last_backup"]["name"], "SB-1")
        self.assertEqual(status["last_update"]["status"], "Success")
        self.assertTrue(status["ping"]["ok"])

    def test_find_site_prefers_the_exact_name_then_the_prefix(self):
        self.assertEqual(
            [s["name"] for s in press_tools.find_site("galom.tbo365.cloud")],
            ["galom.tbo365.cloud"],
        )
        self.assertEqual(
            [s["name"] for s in press_tools.find_site("galom")], ["galom.tbo365.cloud"]
        )
        self.assertEqual(len(press_tools.find_site("galom-")), 1)
        self.assertEqual(len(press_tools.find_site("tbo365")), 3)
        self.assertEqual(press_tools.find_site("nothing"), [])

    def test_jobs_and_failed_jobs_read_agent_jobs(self):
        self.assertEqual(
            press_tools.jobs(site="demoerp.tbo365.cloud")[0]["job_type"], "Backup Site"
        )
        press_tools.failed_jobs(6)
        args = self.calls("press.api.client.get_list")[-1]
        self.assertEqual(args["doctype"], "Agent Job")
        self.assertEqual(args["filters"]["status"], "Failure")


class TestActions(PressCase):
    def test_the_levels_are_as_approved(self):
        self.assertEqual(press_tools.ACTIONS["backup"]["level"], press_tools.LOGGED)
        for name in ("restart_bench", "update_site", "migrate_site", "change_plan"):
            self.assertEqual(
                (press_tools.ACTIONS[name]["level"], press_tools.ACTIONS[name]["risk"]),
                (press_tools.APPROVAL, "normal"),
            )
        for name in ("deploy", "restore", "new_site"):
            self.assertEqual(
                (press_tools.ACTIONS[name]["level"], press_tools.ACTIONS[name]["risk"]),
                (press_tools.APPROVAL, "senior"),
            )

    def test_the_never_list_names_no_method_the_code_calls(self):
        sources = ""
        for path in (
            "copilot/press_tools.py",
            "copilot/press.py",
            "copilot/mcp/tools_press.py",
            "api/copilot_press.py",
            "copilot/assistant.py",
        ):
            with open(os.path.join(HERE, path)) as f:
                sources += f.read()
        for method in press_tools.NEVER:
            self.assertEqual(
                sources.count(f'"{method}"'),
                1,
                f"{method} appears outside the NEVER list",
            )
        with self.assertRaises(frappe.ValidationError):
            press_tools.run("archive", "galom.tbo365.cloud", self.one, "Web")

    def test_a_backup_runs_now_and_is_logged(self):
        done = press_tools.run("backup", "demoerp.tbo365.cloud", self.one, "Web")
        self.assertTrue(done["ran"])
        self.assertEqual(
            self.calls("press.api.site.backup"), [{"name": "demoerp.tbo365.cloud"}]
        )
        self.assertIn("job 48213 success", done["text"])
        row = frappe.get_all(
            "HDS Copilot Call Log",
            filters={"user": self.one, "tool": "press_backup"},
            fields=["status", "kind"],
        )
        self.assertEqual((row[0].status, row[0].kind), ("OK", "Web"))
        self.assertEqual(frappe.db.count(actions.ACTION, {"kind": "Press"}), 0)

    def test_a_restart_asks_first_and_runs_after_approve(self):
        asked = press_tools.run("restart_bench", "bench-0020", self.one, "Teams")
        self.assertEqual(self.calls("press.api.bench.restart"), [])
        approval = frappe.get_doc(actions.ACTION, asked["approval"])
        self.assertEqual(
            (approval.kind, approval.status, approval.risk, approval.assigned_to),
            ("Press", "Pending", "normal", self.two),
        )
        self.assertIn('press.api.bench.restart name="bench-0020"', approval.details)
        self.assertEqual(self.sent, [self.two])
        actions.decide(approval.name, self.two, True, via="Teams")
        self.assertEqual(
            self.calls("press.api.bench.restart"), [{"name": "bench-0020"}]
        )
        approval.reload()
        self.assertEqual(approval.status, "Executed")
        self.assertIn("job 48214 success", approval.execution_log)
        told = [s for s in self.sent if isinstance(s, tuple)]
        self.assertEqual(told[0][0], self.one)
        self.assertIn("Restart bench-0020", told[0][1][0])

    def test_a_deploy_needs_a_senior(self):
        asked = press_tools.run("deploy", "bench-group-1", self.one, "Web")
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, asked["approval"], "assigned_to"),
            self.senior,
        )

    def test_a_tampered_payload_never_runs(self):
        asked = press_tools.run("restart_bench", "bench-0020", self.one, "Web")
        approval = frappe.get_doc(actions.ACTION, asked["approval"])
        approval.db_set(
            "payload",
            '{"action": "restart_bench", "method": "press.api.site.archive", "args": {"name": "galom.tbo365.cloud"}}',
        )
        actions.decide(approval.name, self.two, True)
        approval.reload()
        self.assertEqual(approval.status, "Failed")
        self.assertEqual(self.calls("press.api.site.archive"), [])
        self.assertEqual(self.calls("press.api.bench.restart"), [])

    def test_press_refusals_reach_the_record(self):
        asked = press_tools.run("update_site", "galom.tbo365.cloud", self.one, "Web")
        with patch(
            "helpdesk.copilot.press.call", side_effect=PressError(403, "Not permitted")
        ):
            actions.decide(asked["approval"], self.two, True)
        self.assertEqual(
            frappe.db.get_value(actions.ACTION, asked["approval"], "status"), "Failed"
        )

    def test_the_api_refuses_a_logged_action_as_an_approval(self):
        frappe.set_user(self.one)
        with self.assertRaises(frappe.ValidationError):
            api.request_action("backup", "demoerp.tbo365.cloud")
        result = api.request_action(
            "change_plan", "demoerp.tbo365.cloud", extra='{"plan": "Pro"}'
        )
        self.assertEqual(result["status"], "Pending")
        self.assertIn("Pro", result["title"])
        table = api.actions_table()
        self.assertEqual(table["actions"]["deploy"]["risk"], "senior")
        self.assertIn("press.api.site.archive", table["never"])


class TestChat(PressCase):
    def test_status_of_a_site_in_chat(self):
        replies = self.say(
            "what's the status of galom?", {"intent": "press_status", "site": "galom"}
        )
        self.assertIn("galom.tbo365.cloud", replies[0]["title"])
        self.assertIn("answers in 310 ms", replies[0]["title"])
        self.assertIn("Plan Standard", replies[0]["lines"][0])
        self.assertEqual(replies[0]["tone"], "good")

    def test_a_backup_in_chat_runs_at_once(self):
        replies = self.say(
            "take a backup of demoerp", {"intent": "press_backup", "site": "demoerp"}
        )
        self.assertEqual(
            self.calls("press.api.site.backup"), [{"name": "demoerp.tbo365.cloud"}]
        )
        self.assertIn("job 48213 success", replies[0]["lines"][0])

    def test_a_restart_in_chat_asks_an_approver(self):
        replies = self.say(
            "restart the bench of galom",
            {
                "intent": "press_action",
                "site": "galom",
                "press_action": "restart_bench",
            },
        )
        self.assertIn("Asked", replies[0]["title"])
        self.assertIn("Restart bench-0020", replies[0]["title"])
        self.assertEqual(
            frappe.db.count(actions.ACTION, {"kind": "Press", "status": "Pending"}), 1
        )
        self.assertEqual(self.calls("press.api.bench.restart"), [])

    def test_an_unknown_site_asks_which(self):
        replies = self.say(
            "status of nothing", {"intent": "press_status", "site": "nothing"}
        )
        self.assertIn("Which site", replies[0]["lines"][0])
        replies = self.say(
            "status of tbo365", {"intent": "press_status", "site": "tbo365"}
        )
        self.assertIn("Which site do you mean", replies[0]["title"])
