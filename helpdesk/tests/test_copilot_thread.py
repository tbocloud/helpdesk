# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Every ticket is a chat with Copilot (Phase 11): Copilot narrates each step; an ordinary bug is
fixed by itself and asks once, after; data, settings, sensitive or high-risk work asks first; an
approved fix deploys by itself; people talk to it with the ticket's memory, on the page or in
Teams; Teams hears the ticket's status only."""

import json
from unittest.mock import patch

import frappe

from helpdesk.api import copilot_thread as api
from helpdesk.copilot import assistant, deploy, fixes, router, runs, teams, thread
from helpdesk.test_utils import (
    create_agent,
    fake_investigation,
    make_assignment,
    make_copilot_run,
    make_team,
    make_ticket,
    run_as_user,
)
from helpdesk.tests.test_copilot_fix_flow import FixCase

MESSAGE = assistant.MESSAGE


class ThreadCase(FixCase):
    def setUp(self):
        super().setUp()
        self.settings(shadow_mode=0, ask_before_every_fix=0, deploy_needs_a_press=0)
        self.delivered = (
            []
        )  # (person, card) of every message sent to a person's own chat
        patcher = patch.object(
            assistant,
            "send",
            side_effect=lambda person, reply, **links: self.delivered.append(
                (person, reply)
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.cache.delete_keys("copilot-chat:")

    def chat(self, ticket=None):
        return thread.history((ticket or self.ticket.name))

    def said(self, ticket=None) -> list[str]:
        """Each message of the ticket's chat as one line of text."""
        lines = []
        for m in self.chat(ticket):
            card = m["card"] or {}
            lines.append(
                " ".join(
                    filter(None, [m["text"], card.get("title")] + card.get("lines", []))
                )
            )
        return lines

    def routed(self, category="bug", **extra):
        run = runs.start_run(self.ticket.name)
        run = runs.transition(run, "Investigating", runs.WORKER)
        return router.route(run, fake_investigation(category, 0.9, **extra))


class TestTheNarration(ThreadCase):
    def test_an_ordinary_bug_is_fixed_by_itself_and_the_chat_tells_each_step(self):
        run = self.routed("bug")

        run.reload()
        self.assertEqual(run.fix_status, "Queued")  # nobody pressed anything
        said = self.said()
        self.assertTrue(any(s.startswith("Looking into it.") for s in said))
        found = next(s for s in said if s.startswith("Found it (90% sure)"))
        self.assertIn("I am fixing it now", found)
        # Teams hears the diagnosis (status), not "looking into it"
        heard = [card for person, card in self.delivered if person == self.developer]
        self.assertEqual(len(heard), 1)
        self.assertEqual(heard[0]["title"], f"#{self.ticket.name} · Margin wrong")
        self.assertTrue(heard[0]["lines"][0].startswith("Found it"))
        self.assertIn("mute", [a["verb"] for a in heard[0]["actions"]])

    def test_a_sensitive_bug_asks_first_and_yes_starts_the_fix(self):
        run = self.routed(
            "bug",
            proposal={
                "text": "Fix the margin",
                "files": ["alpha_trading/accounts/margin.py"],
            },
        )

        run.reload()
        self.assertFalse(run.fix_status)
        diagnosis = next(
            m
            for m in self.chat()
            if (m["card"] or {}).get("title", "").startswith("Found it")
        )
        self.assertIn("accounting and tax", " ".join(diagnosis["card"]["lines"]))
        self.assertEqual(
            [a["verb"] for a in diagnosis["card"]["actions"]], ["fix_yes", "not_now"]
        )

        # the people who may write in the chat press its buttons (Phase 12)
        make_assignment("HD Ticket", self.ticket.name, self.approver)
        thread.press(self.approver, self.ticket.name, "fix_yes", {"run": run.name})

        run.reload()
        self.assertEqual(run.fix_status, "Queued")
        self.assertIn("Yes, let Copilot fix it", self.said())

    def test_the_rules_for_asking_first(self):
        def asking(category="bug", **proposal):
            ticket = make_ticket(subject="Rules", customer=self.customer).name
            return fixes.needs_asking(
                make_copilot_run(
                    ticket,
                    "Preparing Fix",
                    root_cause_category=category,
                    proposal=json.dumps(proposal),
                )
            )

        self.assertIsNone(asking(files=["alpha_trading/selling/discounts.py"]))
        self.assertIn("data or settings", asking("wrong_setting"))
        self.assertIn("data or settings", asking("data_damaged_by_bug"))
        self.assertIn("high risk", asking(risk="high"))
        self.assertIn("stock", asking(files=["alpha_trading/stock/stock_entry.py"]))
        self.assertIn("migrations", asking(files=["alpha_trading/patches.txt"]))

    def test_a_failed_fix_is_status_for_the_people_on_the_ticket(self):
        run = self.routed("bug")
        self.delivered.clear()

        fixes.fix_failed(
            frappe.get_doc("HDS Copilot Run", run.name), "the bug did not show"
        )

        self.assertTrue(
            any(
                "Copilot could not fix it: the bug did not show" in s
                for s in self.said()
            )
        )
        self.assertTrue(
            any(
                "Copilot could not fix it" in " ".join(card["lines"])
                for person, card in self.delivered
                if person == self.developer
            )
        )


class TestDeployingByItself(ThreadCase):
    def approval(self, risk="low", sensitive=0):
        return frappe._dict(
            risk_level=risk, sensitive=sensitive, decided_by=self.approver, name="APR-x"
        )

    def test_an_approved_fix_deploys_by_itself_low_risk_now_the_rest_tonight(self):
        run = frappe._dict(name="RUN-x", ticket=self.ticket.name, kind="investigate")
        with patch.object(deploy.press, "configured", return_value=True), patch.object(
            deploy, "request_deploy"
        ) as requested:
            deploy.auto_request(run, self.approval("low"))
            deploy.auto_request(run, self.approval("high"))
            deploy.auto_request(run, self.approval("low", sensitive=1))
        self.assertEqual(
            [c.args[1] for c in requested.call_args_list], ["now", "tonight", "tonight"]
        )
        self.assertTrue(all(c.kwargs["auto"] for c in requested.call_args_list))

    def test_with_deploy_needs_a_press_a_person_deploys(self):
        self.settings(shadow_mode=0, deploy_needs_a_press=1, auto_deploy_categories="")
        run = frappe._dict(name="RUN-x", ticket=self.ticket.name, kind="investigate")
        with patch.object(deploy.press, "configured", return_value=True), patch.object(
            deploy, "request_deploy"
        ) as requested:
            deploy.auto_request(run, self.approval("low"))
        requested.assert_not_called()


class TestTalkingToIt(ThreadCase):
    def setUp(self):
        super().setUp()
        self.prompts = []
        self.intents = {}
        patcher = patch("helpdesk.ai_engine.call_haiku", side_effect=self.fake_ai)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_ai(self, system_prompt, user_message, ticket_name=None, job=None):
        self.prompts.append((system_prompt, user_message))
        if system_prompt == assistant.ANSWER_PROMPT:
            return {
                "response": {"answer": "Because the tier comes from the price list."},
                "cost": 0.0001,
            }
        if system_prompt == thread.SUMMARY_PROMPT:
            return {
                "response": {"summary": "The margin check failed; Copilot fixed it."},
                "cost": 0.0001,
            }
        text = user_message.rsplit("<<<\n", 1)[-1].rsplit("\n>>>", 1)[0]
        return {
            "response": self.intents.get(text, {"intent": "unclear"}),
            "cost": 0.0002,
        }

    def test_a_question_is_answered_with_the_tickets_memory(self):
        run = self.routed("bug")
        self.intents["use the price list rate instead"] = {
            "intent": "change_request",
            "reason": "use the price list rate instead",
        }
        thread.receive(
            self.developer, self.ticket.name, "use the price list rate instead"
        )
        self.intents["why this way?"] = {
            "intent": "question",
            "question": "why this way?",
        }

        replies = thread.receive(
            self.developer, self.ticket.name, "why this way?", via="Teams"
        )

        self.assertIn("price list", " ".join(replies[0]["lines"]))
        answer_prompt = next(p for s, p in self.prompts if s == assistant.ANSWER_PROMPT)
        self.assertIn(
            "use the price list rate instead", answer_prompt
        )  # the instruction
        self.assertIn("Found it", answer_prompt)  # the chat so far
        mine = [m for m in self.chat() if m["direction"] == "In"]
        self.assertEqual(
            [(m["text"], m["via"]) for m in mine][-2:],
            [("use the price list rate instead", "Web"), ("why this way?", "Teams")],
        )
        # the worker reads people's instructions when it works on the ticket again
        context = runs.run_context(frappe.get_doc("HDS Copilot Run", run.name))
        self.assertIn(
            "use the price list rate instead",
            " ".join(context["ticket_chat"]["instructions"]),
        )

    def test_the_summary_keeps_the_older_messages(self):
        self.routed("bug")
        thread.summarise(self.ticket.name)
        self.assertIn("Copilot fixed it", thread.memory_for(self.ticket.name))

    def test_in_teams_a_reply_without_a_number_goes_to_the_current_ticket(self):
        self.routed("bug")
        assistant.chat_for(self.developer, "Teams")
        thread.set_current(self.developer, self.ticket.name)
        self.intents["did it work?"] = {
            "intent": "question",
            "question": "did it work?",
        }

        replies = assistant.receive(self.developer, "Teams", "did it work?")

        self.assertIn(f"About ticket {self.ticket.name}", replies[0]["lines"][0])
        self.assertIn("did it work?", self.said())  # copied into the ticket's chat

    def test_a_drafted_reply_is_sent_by_the_person(self):
        run = self.routed("question")
        draft = next(
            m
            for m in self.chat()
            if (m["card"] or {}).get("title") == "Reply for the customer (draft)"
        )
        with patch(
            "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.HDTicket.reply_via_agent"
        ) as sent:
            thread.press(
                self.developer,
                self.ticket.name,
                "send_reply",
                draft["card"]["actions"][0]["data"],
            )
            again = thread.press(
                self.developer,
                self.ticket.name,
                "send_reply",
                draft["card"]["actions"][0]["data"],
            )
        self.assertEqual(sent.call_count, 1)
        self.assertTrue(sent.call_args.kwargs["message"].startswith("<p>"))
        self.assertIn("sent already", again["replies"][0]["lines"][0])
        self.assertTrue(run.name)


class TestTeamsAndThePanel(ThreadCase):
    def test_a_reply_to_a_tickets_message_in_teams_goes_to_that_ticket(self):
        chat = assistant.chat_for(self.developer, "Teams")
        assistant.record(
            chat,
            "Out",
            "status",
            {"title": "x"},
            ticket=self.ticket.name,
            teams_activity="1698000000001",
        )
        quoted = {
            "attachments": [
                {
                    "contentType": "text/html",
                    "content": '<blockquote itemscope="" itemtype="http://schema.skype.com/Reply" itemid="1698000000001">x</blockquote><p>why?</p>',
                }
            ]
        }
        self.assertEqual(teams.quoted_ticket(quoted), self.ticket.name)
        self.assertEqual(
            teams.quoted_ticket({"replyToId": "1698000000001"}), self.ticket.name
        )
        self.assertIsNone(teams.quoted_ticket({"replyToId": "unknown"}))

    def test_a_muted_ticket_stays_quiet_in_teams(self):
        thread.set_muted(self.ticket.name, self.developer, True)
        self.routed("bug")
        self.assertFalse([p for p, card in self.delivered if p == self.developer])
        self.assertTrue(thread.muted(self.ticket.name, self.developer))

    def test_the_panel_shows_the_teams_chat_too(self):
        teams_chat = assistant.chat_for(self.developer, "Teams")
        web_chat = assistant.chat_for(self.developer, "Web")
        assistant.record(teams_chat, "In", "said in Teams")
        assistant.record(web_chat, "In", "said on the web")

        shown = assistant.history(self.developer, "Web")
        teams_only = assistant.history(self.developer, "Teams")

        self.assertEqual(
            [(m["text"], m["via"]) for m in shown],
            [("said in Teams", "Teams"), ("said on the web", "Web")],
        )
        self.assertEqual([m["text"] for m in teams_only], ["said in Teams"])

    def test_what_you_can_do_now(self):
        fresh = make_ticket(subject="Fresh", customer=self.customer).name
        self.assertEqual(
            [a["verb"] for a in thread.now(fresh, self.developer)["actions"]], ["start"]
        )
        self.settings(shadow_mode=0, ask_before_every_fix=1)
        self.routed("bug")
        # someone who only reads the chat keeps just the buttons anyone may press (Phase 12)
        self.assertNotIn(
            "fix",
            [a["verb"] for a in thread.now(self.ticket.name, self.approver)["actions"]],
        )
        make_assignment("HD Ticket", self.ticket.name, self.approver)
        now = thread.now(self.ticket.name, self.approver)
        self.assertIn("fix", [a["verb"] for a in now["actions"]])
        self.assertIn("mute", [a["verb"] for a in now["more"]])

    def test_only_people_who_may_read_the_ticket_see_its_chat(self):
        outsider = create_agent("thread.outsider@example.com").name
        team = make_team("Thread Restricted Team", members=[self.approver])
        frappe.db.set_value("HD Ticket", self.ticket.name, "agent_group", team.name)
        frappe.db.set_single_value(
            "HD Settings",
            {
                "restrict_tickets_by_agent_group": 1,
                "do_not_restrict_tickets_without_an_agent_group": 0,
            },
        )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(outsider, lambda: api.history(self.ticket.name))
        with self.assertRaises(frappe.PermissionError):
            thread.receive(outsider, self.ticket.name, "hello")
        frappe.db.set_single_value("HD Settings", "restrict_tickets_by_agent_group", 0)
