import gzip
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import session_replay, triage
from helpdesk.api.session_replay import get_session_replay
from helpdesk.test_utils import (
    REPLAY_ERROR_MESSAGE,
    create_agent,
    create_user,
    hold_commits,
    make_diagnostics,
    make_replay,
    make_replay_events,
    make_session_files,
    make_team,
    make_ticket,
    run_as_user,
)

EXPECTED_TIMELINE = [
    "t+0s opened /app/sales-invoice/new",
    't+5s typed in "Posting Date"',
    't+12s clicked "Save"',
    "t+13s server error: frappe.desk.form.save.savedocs → 417 ValidationError: "
    + REPLAY_ERROR_MESSAGE,
    f"t+13s message shown: Message: {REPLAY_ERROR_MESSAGE}",
    "t+14s console error: Uncaught TypeError: frm.doc is undefined",
    't+15s clicked "Close"',
    "t+20s raised the ticket",
]


class TestBuildTimeline(FrappeTestCase):
    def test_reads_like_the_customers_steps(self):
        timeline = session_replay.build_timeline(make_replay(), make_diagnostics())
        # the diagnostics' copy of the save error is already on the timeline
        self.assertEqual(timeline.split("\n"), EXPECTED_TIMELINE)

    def test_long_sessions_keep_the_last_steps(self):
        replay = make_replay(make_replay_events(filler_clicks=400))

        lines = session_replay.build_timeline(replay).split("\n")

        self.assertEqual(len(lines), session_replay.MAX_TIMELINE_LINES)
        self.assertIn("earlier steps omitted", lines[0])
        self.assertEqual(lines[-1], "t+20s raised the ticket")

    def test_lines_are_truncated(self):
        events = make_replay_events()
        events[7]["data"]["payload"]["message"] = "x" * 1000

        timeline = session_replay.build_timeline(make_replay(events))

        self.assertTrue(
            all(
                len(line) <= session_replay.MAX_LINE_CHARS
                for line in timeline.split("\n")
            )
        )

    def test_failed_requests_and_unknown_events_are_tolerated(self):
        replay = {
            "events": [
                {
                    "type": 6,
                    "timestamp": 1000,
                    "data": {
                        "plugin": "rrweb/network@1",
                        "payload": {
                            "requests": [
                                {
                                    "name": "https://erp.example.com/api/method/x?a=1",
                                    "method": "post",
                                    "status": 500,
                                },
                                {"url": "/api/method/ok", "responseStatus": 200},
                            ]
                        },
                    },
                },
                {
                    "type": 3,
                    "timestamp": 3000,
                    "data": {"source": 2, "type": 2, "id": 404},
                },
                {"type": 99, "timestamp": 4000, "data": {"odd": True}},
                "not an event",
            ]
        }

        self.assertEqual(
            session_replay.build_timeline(replay).split("\n"),
            [
                "t+0s request failed: POST /api/method/x → 500",
                "t+2s clicked on the page",
            ],
        )

    def test_request_failure_already_reported_as_call_error_is_not_repeated(self):
        events = make_replay_events()
        events.insert(
            8,
            {
                "type": 6,
                "timestamp": events[7]["timestamp"] + 50,
                "data": {
                    "plugin": "rrweb/network@1",
                    "payload": {
                        "requests": [
                            {
                                "name": "https://erp.example.com/api/method/frappe.desk.form.save.savedocs",
                                "initiatorType": "fetch",
                                "status": 417,
                            },
                            {
                                "name": "https://erp.example.com/assets/app.js",
                                "initiatorType": "script",
                            },
                        ]
                    },
                },
            },
        )

        self.assertEqual(
            session_replay.build_timeline(make_replay(events)).split("\n"),
            EXPECTED_TIMELINE,
        )

    def test_matches_replay_files_by_name(self):
        self.assertTrue(session_replay.is_replay_file("session-replay.json.gz"))
        self.assertTrue(session_replay.is_replay_file("session-replay.json3f2a1c.gz"))
        self.assertFalse(session_replay.is_replay_file("session-replay-notes.txt.gz"))
        self.assertTrue(session_replay.is_diagnostics_file("session-diagnostics.json"))
        self.assertFalse(session_replay.is_diagnostics_file("shot.png"))

    def test_diagnostics_alone_still_give_errors(self):
        timeline = session_replay.build_timeline(None, make_diagnostics())
        self.assertIn("417 ValidationError", timeline)
        self.assertEqual(session_replay.build_timeline(None, None), "")

    def test_diagnostics_summary(self):
        summary = session_replay.summarize_diagnostics(make_diagnostics())

        self.assertIn("Browser: Chrome 128 on macOS 14, viewport 1440×900", summary)
        self.assertIn("Page: New Sales Invoice (/app/sales-invoice/new)", summary)
        self.assertIn("Versions: erpnext 15.35.1, frappe 15.40.0", summary)
        self.assertIn(REPLAY_ERROR_MESSAGE, summary)


class TestLoadReplay(FrappeTestCase):
    def setUp(self):
        hold_commits(self)  # the code under test commits; keep the fixtures out of the site
        self.ticket = make_ticket(subject="Cannot save Sales Invoice")

    def test_reads_attached_files(self):
        make_session_files(self.ticket.name)

        replay = session_replay.load_replay(self.ticket.name)
        diagnostics = session_replay.load_diagnostics(self.ticket.name)

        self.assertEqual(len(replay["events"]), len(make_replay_events()))
        self.assertEqual(diagnostics["browser"], "Chrome 128")

    def test_corrupt_replay_is_ignored(self):
        frappe.get_doc(
            {
                "doctype": "File",
                "file_name": "session-replay.json.gz",
                "attached_to_doctype": "HD Ticket",
                "attached_to_name": self.ticket.name,
                "is_private": 1,
                "content": b"\x1f\x8b not really gzip",
            }
        ).insert(ignore_permissions=True)

        self.assertIsNone(session_replay.load_replay(self.ticket.name))

    def test_refuses_to_inflate_past_the_limit(self):
        bomb = gzip.compress(json.dumps(make_replay()).encode())

        with self.assertRaises(ValueError):
            session_replay.inflate(bomb, 100)

    def test_no_files_means_nothing_to_show(self):
        self.assertIsNone(session_replay.load_replay(self.ticket.name))
        self.assertEqual(session_replay.get_timeline(self.ticket.name), "")


class TestGetSessionReplay(FrappeTestCase):
    def setUp(self):
        hold_commits(self)  # the code under test commits; keep the fixtures out of the site
        self.ticket = make_ticket(subject="Cannot save Sales Invoice")
        self.files = make_session_files(self.ticket.name)

    def test_agent_gets_replay_diagnostics_and_timeline(self):
        agent = create_agent("replay-agent@example.com").name

        result = run_as_user(agent, lambda: get_session_replay(self.ticket.name))

        self.assertTrue(result["available"])
        self.assertEqual(result["replay_url"], self.files["replay"].file_url)
        self.assertEqual(result["diagnostics"]["os"], "macOS 14")
        self.assertIn('clicked "Save"', result["timeline"])
        self.assertIn("Chrome 128", result["summary"])
        # the private replay downloads for the same agent
        self.assertTrue(
            run_as_user(agent, lambda: self.files["replay"].is_downloadable())
        )

    def test_non_agent_is_denied(self):
        outsider = create_user("replay-outsider@example.com").name

        with self.assertRaises(frappe.PermissionError):
            run_as_user(outsider, lambda: get_session_replay(self.ticket.name))

    def test_agent_outside_the_tickets_team_is_denied(self):
        agent = create_agent("replay-other-team@example.com").name
        team = make_team(
            "Replay Restricted Team",
            members=[create_agent("replay-team@example.com").name],
        )
        frappe.db.set_value("HD Ticket", self.ticket.name, "agent_group", team.name)
        frappe.db.set_single_value(
            "HD Settings",
            {
                "restrict_tickets_by_agent_group": 1,
                "do_not_restrict_tickets_without_an_agent_group": 0,
            },
        )

        with self.assertRaises(frappe.PermissionError):
            run_as_user(agent, lambda: get_session_replay(self.ticket.name))
        self.assertFalse(
            run_as_user(agent, lambda: self.files["replay"].is_downloadable())
        )

    def test_diagnostics_without_replay(self):
        other = make_ticket(subject="Replay was too large to send")
        make_session_files(other.name, with_replay=False)

        result = get_session_replay(other.name)

        self.assertTrue(result["available"])
        self.assertIsNone(result["replay_url"])
        self.assertEqual(result["diagnostics"]["browser"], "Chrome 128")
        self.assertIn("417 ValidationError", result["timeline"])

    def test_ticket_without_replay(self):
        other = make_ticket(subject="No replay here")

        result = get_session_replay(other.name)

        self.assertFalse(result["available"])
        self.assertIsNone(result["replay_url"])


class TestTriageWithSessionReplay(FrappeTestCase):
    def setUp(self):
        hold_commits(self)  # the code under test commits; keep the fixtures out of the site
        self.ticket = make_ticket(
            subject="Cannot save Sales Invoice",
            description="Save fails with an error.",
        )

    def test_prompt_includes_timeline_and_diagnostics(self):
        make_session_files(self.ticket.name)

        prompt = triage._build_triage_input(self.ticket)

        self.assertIn(session_replay.TIMELINE_HEADING, prompt)
        self.assertIn('t+12s clicked "Save"', prompt)
        self.assertIn("t+20s raised the ticket", prompt)
        self.assertIn("Versions: erpnext 15.35.1", prompt)
        self.assertIn("steps_to_reproduce", triage.TRIAGE_SYSTEM_PROMPT)

    def test_prompt_session_part_stays_bounded(self):
        make_session_files(
            self.ticket.name, replay=make_replay(make_replay_events(filler_clicks=400))
        )

        context = session_replay.build_triage_context(
            self.ticket.name, triage.MAX_SESSION_CONTEXT_CHARS
        )

        self.assertLessEqual(len(context), triage.MAX_SESSION_CONTEXT_CHARS)
        self.assertIn("t+20s raised the ticket", context)

    def test_no_replay_no_session_section(self):
        self.assertNotIn(
            session_replay.TIMELINE_HEADING, triage._build_triage_input(self.ticket)
        )

    def test_comment_shows_steps_and_likely_cause(self):
        triage._post_triage_comment(
            self.ticket.name,
            {
                "priority": "Medium",
                "category": "Data",
                "summary": "Save fails on posting date validation.",
                "steps_to_reproduce": ["Open a new Sales Invoice", "Click Save"],
                "likely_cause": "Posting Date is before the Invoice Date.",
                "recommended_track": "manual",
            },
        )
        content = frappe.db.get_value(
            "HD Ticket Comment",
            {"reference_ticket": self.ticket.name},
            "content",
            order_by="creation desc",
        )
        self.assertIn("Steps to reproduce", content)
        self.assertIn("<li>Click Save</li>", content)
        self.assertIn("Likely cause:", content)

    @patch("frappe.enqueue")
    @patch("helpdesk.ai_engine.get_hub_settings")
    def test_triage_is_queued_after_commit(self, settings, enqueue):
        settings.return_value = MagicMock(auto_triage_enabled=1)
        frappe.db.set_value("HD Ticket", self.ticket.name, "custom_triage_status", "")
        self.ticket.reload()

        triage.auto_triage_ticket(self.ticket, "after_insert")

        self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])

    @patch("frappe.enqueue")
    @patch("helpdesk.ai_engine.get_hub_settings")
    def test_late_replay_retriages_once(self, settings, enqueue):
        settings.return_value = MagicMock(auto_triage_enabled=1)
        frappe.db.set_value(
            "HD Ticket",
            self.ticket.name,
            {"custom_triage_status": "Completed", "custom_triage_data": "{}"},
        )

        triage.retriage_with_session_replay(self.ticket.name)
        self.assertFalse(enqueue.call_args.kwargs["start_investigation"])

        enqueue.reset_mock()
        frappe.db.set_value(
            "HD Ticket",
            self.ticket.name,
            "custom_triage_data",
            json.dumps({"used_session_replay": True}),
        )
        triage.retriage_with_session_replay(self.ticket.name)
        frappe.db.set_value(
            "HD Ticket", self.ticket.name, "custom_triage_status", "Pending"
        )
        frappe.db.set_value("HD Ticket", self.ticket.name, "custom_triage_data", "{}")
        triage.retriage_with_session_replay(self.ticket.name)
        enqueue.assert_not_called()


class TestProductionFixes(FrappeTestCase):
    def setUp(self):
        hold_commits(self)  # the code under test commits; keep the fixtures out of the site

    def test_values_filled_in_by_the_page_are_not_typing(self):
        events = make_replay_events()
        events.append(
            {
                "type": 3,
                "timestamp": events[0]["timestamp"] + 2000,
                "data": {
                    "source": 5,
                    "id": 7,
                    "text": "••",
                    "isChecked": False,
                    "userTriggered": False,
                },
            }
        )
        events.sort(key=lambda e: e["timestamp"])

        timeline = session_replay.build_timeline(make_replay(events))

        self.assertNotIn("t+2s typed in", timeline)
        self.assertIn('t+5s typed in "Posting Date"', timeline)

    def test_empty_ai_answer_fails_instead_of_a_blank_triage(self):
        ticket = make_ticket(
            subject="Cannot save Sales Invoice", description="Save fails with an error."
        )
        empty = {
            "response": {"raw_response": "", "parse_error": True},
            "usage": {},
            "cost": 0,
        }
        with patch.object(triage, "call_haiku", return_value=empty), patch.object(
            frappe.cache, "set", return_value=True
        ), patch.object(frappe.db, "commit"), patch.object(
            frappe, "log_error"
        ) as log_error:
            triage.run_triage(ticket.name, start_investigation=False)

        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "custom_triage_status"),
            "Failed",
        )
        self.assertFalse(
            frappe.db.exists(
                "HD Ticket Comment",
                {"reference_ticket": ticket.name, "content": ("like", "%AI Triage%")},
            )
        )
        self.assertTrue(log_error.called)


class TestStuckTriageAndSyncState(FrappeTestCase):
    def setUp(self):
        hold_commits(self)  # the code under test commits; keep the fixtures out of the site

    def test_triage_left_in_progress_is_marked_failed(self):
        from frappe.utils import add_to_date, now_datetime

        stuck = make_ticket(subject="Stuck triage", description="Needs triage.")
        fresh = make_ticket(subject="Running triage", description="Needs triage.")
        frappe.db.set_value(
            "HD Ticket",
            stuck.name,
            {
                "custom_triage_status": "In Progress",
                "custom_triage_timestamp": add_to_date(now_datetime(), minutes=-30),
            },
        )
        frappe.db.set_value(
            "HD Ticket",
            fresh.name,
            {
                "custom_triage_status": "In Progress",
                "custom_triage_timestamp": now_datetime(),
            },
        )
        with patch.object(frappe, "log_error"):
            triage.fail_stuck_triages()

        self.assertEqual(
            frappe.db.get_value("HD Ticket", stuck.name, "custom_triage_status"),
            "Failed",
        )
        self.assertEqual(
            frappe.db.get_value("HD Ticket", fresh.name, "custom_triage_status"),
            "In Progress",
        )

    def test_damaged_sync_state_starts_over(self):
        from helpdesk.ticket_puller import _load_conv_state

        self.assertEqual(_load_conv_state("not json"), {})
        self.assertEqual(_load_conv_state(None), {})
        self.assertEqual(_load_conv_state("[1, 2]"), {})
        self.assertEqual(_load_conv_state('{"client": ["C1"]}'), {"client": ["C1"]})

    def test_long_sync_state_is_saved_and_nothing_syncs_twice(self):
        # a ticket with a dozen customer comments outgrew the old 140-character
        # field, so every sync rolled back and the comments never arrived
        from helpdesk import ticket_puller
        from helpdesk.test_utils import create_customer, make_support_connection

        create_customer("Sync State Trading LLC")
        connection = make_support_connection("Sync State Trading LLC").name
        ticket = make_ticket(subject="Filter not working", description="Sales list.")
        ticket.db_set(
            {"custom_client_ticket": "ST-0001", "custom_qcs_connection": connection}
        )
        comments = [
            {
                "name": f"comment-{i:04d}-abcdef",
                "content": f"Update {i}",
                "owner": "customer@example.com",
            }
            for i in range(12)
        ]

        def call_tool(tool, args):
            rows = (
                comments
                if tool == "get_list" and args.get("doctype") == "Comment"
                else []
            )
            return {"content": [{"type": "text", "text": json.dumps(rows)}]}

        mcp = MagicMock()
        mcp.call_tool.side_effect = call_tool
        with patch.object(ticket_puller, "MCPClient", return_value=mcp), patch.object(
            frappe.db, "commit"
        ), patch.object(frappe, "log_error") as log_error:
            ticket_puller.sync_conversations()
            ticket_puller.sync_conversations()

        log_error.assert_not_called()
        state = json.loads(
            frappe.db.get_value("HD Ticket", ticket.name, "custom_sync_state")
        )
        self.assertEqual(len(state["client"]), 12)
        self.assertEqual(
            frappe.db.count("HD Ticket Comment", {"reference_ticket": ticket.name}),
            12,
        )
