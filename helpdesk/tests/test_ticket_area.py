# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The agent's ticket list (Phase 15): queues that count what they show, the search, the last message per row;
the inbox (Phase 16): the same rows with their newest email, the customer's emails since our reply, Copilot's signal."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk.api import doc as doc_api
from helpdesk.api import ticket_area
from helpdesk.helpdesk.doctype.hd_ticket import api as ticket_api
from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket
from helpdesk.patches.v16_0_2 import ticket_area_status_colours
from helpdesk.test_utils import (
    create_agent,
    hold_commits,
    make_copilot_run,
    make_ticket,
)

AGENT = "queue.agent@example.com"
OPEN = ["status_category", "in", ["Open", "Paused"]]


def at(hours: float):
    return add_to_date(now_datetime(), hours=hours)


class TicketAreaCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(AGENT, "Queue", "Agent")

    def ours(self, filters):
        """The filters, narrowed to this test's tickets (the site may hold others)."""
        return [*filters, ["name", "in", self.names]]

    def listed(self, filters) -> set[str]:
        data = doc_api.get_list_data(
            "HD Ticket", filters=self.ours(filters), page_length=100
        )
        return {str(row["name"]) for row in data["data"]}


class TestTheQueues(TicketAreaCase):
    def setUp(self):
        super().setUp()
        self.fresh = make_ticket(subject="Fresh question")
        self.reply_late = make_ticket(subject="First reply late")
        self.reply_late.db_set(
            {"response_by": at(-2), "first_responded_on": None, "resolution_by": at(20)}
        )
        self.resolve_late = make_ticket(subject="Resolution late")
        self.resolve_late.db_set(
            {
                "response_by": at(-30),
                "first_responded_on": at(-29),
                "resolution_by": at(-1),
            }
        )
        # a new ticket always starts Open: the status moves after
        self.waiting = make_ticket(subject="Waiting on the customer")
        self.waiting.reload()
        self.waiting.status = "Replied"
        self.waiting.save(ignore_permissions=True)
        self.done = make_ticket(subject="Done already")
        self.done.reload()
        self.done.status = "Resolved"
        self.done.save(ignore_permissions=True)
        for t in (self.fresh, self.resolve_late, self.waiting, self.done):
            if t is not self.resolve_late:
                t.db_set({"response_by": at(4), "resolution_by": at(40)})
        frappe.desk.form.assign_to.add(
            {
                "doctype": "HD Ticket",
                "name": self.resolve_late.name,
                "assign_to": [AGENT],
            }
        )
        self.names = [
            str(t.name)
            for t in (
                self.fresh,
                self.reply_late,
                self.resolve_late,
                self.waiting,
                self.done,
            )
        ]

    def test_each_queue_counts_exactly_what_its_list_shows(self):
        queues = {
            "needs reply": (
                [["status_category", "=", "Open"]],
                {self.fresh, self.reply_late, self.resolve_late},
            ),
            "overdue": ([["__overdue", "=", 1]], {self.reply_late, self.resolve_late}),
            "unassigned": (
                [OPEN, ["_assign", "is", "not set"]],
                {self.fresh, self.reply_late, self.waiting},
            ),
            "waiting": ([["status_category", "=", "Paused"]], {self.waiting}),
            "resolved": ([["status_category", "=", "Resolved"]], {self.done}),
        }
        for label, (filters, expected) in queues.items():
            with self.subTest(label):
                expected = {str(t.name) for t in expected}
                self.assertEqual(
                    ticket_area.count(json.dumps(self.ours(filters))), len(expected)
                )
                self.assertEqual(self.listed(filters), expected)

    def test_mine_is_the_open_tickets_assigned_to_the_agent(self):
        mine = [OPEN, ["_assign", "like", "%@me%"]]
        frappe.set_user(AGENT)
        self.assertEqual(ticket_area.count(json.dumps(self.ours(mine))), 1)
        frappe.set_user("Administrator")
        self.assertEqual(ticket_area.count(json.dumps(self.ours(mine))), 0)

    def test_the_assignee_filter_matches_one_person_exactly(self):
        # the quick filter sends `_assign = user`, not a LIKE that reads _ and % as wildcards
        self.assertEqual(
            self.listed([["_assign", "=", AGENT]]), {str(self.resolve_late.name)}
        )


class TestTheSearch(TicketAreaCase):
    def test_words_match_the_number_subject_or_raiser_and_all_must_match(self):
        a = make_ticket(
            subject="Zebrafish export fails", raised_by="omar.zeb@example.com"
        )
        b = make_ticket(subject="Zebrafish import is slow")
        c = make_ticket(subject="Unrelated payroll file")
        self.names = [str(t.name) for t in (a, b, c)]

        self.assertEqual(
            self.listed([["__search", "LIKE", "%zebrafish%"]]),
            {str(a.name), str(b.name)},
        )
        self.assertEqual(
            self.listed([["__search", "LIKE", "%zebrafish export%"]]), {str(a.name)}
        )
        self.assertEqual(
            self.listed([["__search", "LIKE", "%omar.zeb%"]]), {str(a.name)}
        )
        self.assertEqual(
            self.listed([["__search", "LIKE", f"%{c.name}%"]]), {str(c.name)}
        )
        self.assertEqual(
            ticket_area.count(
                json.dumps(self.ours([["__search", "LIKE", "%nothing-like-it%"]]))
            ),
            0,
        )

    def test_the_agents_quick_filters_and_the_portals_own(self):
        agent = [f["name"] for f in doc_api.get_quick_filters("HD Ticket")]
        self.assertEqual(agent, ["__search", "customer", "priority", "_assign"])
        portal = [
            f["name"]
            for f in doc_api.get_quick_filters(
                "HD Ticket", show_customer_portal_fields=True
            )
        ]
        self.assertNotIn("__search", portal)
        self.assertEqual(portal[0], "name")


def email(
    ticket, sent_or_received: str, sender: str, name: str, html: str, hours: float
):
    """An email on the ticket, written straight to the table so no hook moves the ticket."""
    c = frappe.get_doc(
        {
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": "Email",
            "sent_or_received": sent_or_received,
            "sender": sender,
            "sender_full_name": name,
            "content": html,
            "reference_doctype": "HD Ticket",
            "reference_name": ticket,
            "communication_date": at(hours),
        }
    )
    c.set_new_name()
    c.db_insert()
    return c


class TestTheLastMessage(TicketAreaCase):
    def test_each_row_gets_its_newest_email_without_the_quoted_one(self):
        a = make_ticket(subject="Invoice won't submit")
        b = make_ticket(subject="Stock report is empty")
        email(
            a.name,
            "Received",
            "aisha@example.com",
            "Aisha Rahman",
            "<p>It fails on submit.</p>",
            1,
        )
        email(
            a.name,
            "Sent",
            AGENT,
            "Queue Agent",
            "<p>We're checking it now.</p><p>On Mon, 3 Nov, Aisha wrote:</p><p>It fails on submit.</p>",
            2,
        )
        email(
            b.name,
            "Received",
            "omar@example.com",
            "Omar Siddiqui",
            "<p>The report shows nothing since Monday.</p>",
            1,
        )

        got = ticket_area.last_messages(json.dumps([a.name, b.name, "no-such-ticket"]))

        self.assertEqual(set(got), {str(a.name), str(b.name)})
        self.assertEqual(
            (
                got[str(a.name)]["by"],
                got[str(a.name)]["author"],
                got[str(a.name)]["text"],
            ),
            ("team", "Queue", "We're checking it now."),
        )
        self.assertEqual(got[str(b.name)]["by"], "customer")
        self.assertEqual(got[str(b.name)]["author"], "Omar")

    def test_a_long_message_is_cut_to_one_line(self):
        a = make_ticket(subject="Long one")
        email(
            a.name, "Received", "x@example.com", "X", "<p>" + "word " * 100 + "</p>", 1
        )
        text = ticket_area.last_messages(json.dumps([a.name]))[str(a.name)]["text"]
        self.assertLessEqual(len(text), ticket_area.PREVIEW_CHARS)
        self.assertTrue(text.endswith("…"))


class TestTheInbox(TicketAreaCase):
    def rows(self, filters=(), **kwargs) -> dict:
        got = ticket_area.inbox(json.dumps(self.ours(list(filters))), **kwargs)
        return {str(row["name"]): row for row in got["tickets"]}

    def test_a_queues_rows_are_the_ones_it_counts(self):
        fresh = make_ticket(subject="Inbox fresh")
        late = make_ticket(subject="Inbox late")
        late.db_set({"response_by": at(-2), "first_responded_on": None})
        fresh.db_set({"response_by": at(4)})
        self.names = [str(fresh.name), str(late.name)]
        overdue = [["__overdue", "=", 1]]
        rows = self.rows(overdue)
        self.assertEqual(set(rows), {str(late.name)})
        self.assertEqual(ticket_area.count(json.dumps(self.ours(overdue))), len(rows))

    def test_the_newest_email_and_the_customers_emails_since_our_reply(self):
        t = make_ticket(subject="Inbox conversation")
        self.names = [str(t.name)]
        email(
            t.name, "Received", "aisha@example.com", "Aisha Rahman", "<p>Hello</p>", 1
        )
        email(t.name, "Sent", AGENT, "Queue Agent", "<p>Checking</p>", 2)
        email(
            t.name,
            "Received",
            "aisha@example.com",
            "Aisha Rahman",
            "<p>Any news?</p>",
            3,
        )
        email(
            t.name,
            "Received",
            "aisha@example.com",
            "Aisha Rahman",
            "<p>Still stuck</p>",
            4,
        )
        last = self.rows()[str(t.name)]["last"]
        self.assertEqual(
            (last["by"], last["author"], last["text"]),
            ("customer", "Aisha", "Still stuck"),
        )
        self.assertEqual(last["customer_name"], "Aisha Rahman")
        # the two after our reply; the opening email came before it
        self.assertEqual(last["waiting"], 2)

        email(t.name, "Sent", AGENT, "Queue Agent", "<p>Fixed</p>", 5)
        last = self.rows()[str(t.name)]["last"]
        self.assertEqual((last["by"], last["waiting"]), ("team", 0))

    def test_copilot_signals_a_fix_to_approve_or_work_in_progress(self):
        approve = make_ticket(subject="Inbox approve")
        working = make_ticket(subject="Inbox working")
        settled = make_ticket(subject="Inbox settled")
        self.names = [str(t.name) for t in (approve, working, settled)]
        frappe.get_doc(
            {
                "doctype": "HDS Copilot Approval",
                "ticket": approve.name,
                "status": "Pending",
                "kind": "Code Change",
            }
        ).db_insert()
        for ticket, state in ((working, "Investigating"), (settled, "Answered")):
            run = make_copilot_run(ticket.name, state)
            ticket.db_set("custom_copilot_run", run.name)
        rows = self.rows()
        self.assertEqual(rows[str(approve.name)]["copilot"], "approve")
        self.assertEqual(rows[str(working.name)]["copilot"], "working")
        self.assertIsNone(rows[str(settled.name)]["copilot"])
        self.assertNotIn("custom_copilot_run", rows[str(working.name)])

    def test_pages_and_only_agents(self):
        tickets = [make_ticket(subject=f"Inbox page {i}") for i in range(3)]
        self.names = [str(t.name) for t in tickets]
        first = ticket_area.inbox(json.dumps(self.ours([])), page_length=2)
        second = ticket_area.inbox(json.dumps(self.ours([])), start=2, page_length=2)
        self.assertEqual((len(first["tickets"]), first["more"]), (2, True))
        self.assertEqual((len(second["tickets"]), second["more"]), (1, False))
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            ticket_area.inbox("[]")

    def test_copilots_own_emails_and_notes_are_marked_on_the_ticket(self):
        t = make_ticket(subject="Inbox automation")
        bot = "copilot.bot@example.com"
        ours = email(t.name, "Sent", AGENT, "Queue Agent", "<p>Done</p>", 1)
        theirs = email(t.name, "Sent", bot, "TBO AI", "<p>Working on it</p>", 2)
        for c, user in ((ours, AGENT), (theirs, bot)):
            frappe.db.set_value("Communication", c.name, "user", user)
        note = frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": t.name,
                "commented_by": bot,
                "content": "<p>Checked</p>",
            }
        )
        note.db_insert()

        with patch.object(ticket_api, "automation_user", return_value=bot):
            marks = {
                c.name: c.by_automation for c in ticket_api.get_communications(t.name)
            }
            comments = {
                c.name: c.by_automation for c in ticket_api.get_comments(t.name)
            }
        self.assertFalse(marks[ours.name])
        self.assertTrue(marks[theirs.name])
        self.assertTrue(comments[note.name])

        # no automation user set up: Administrator is a person, and nothing is Copilot's
        frappe.db.set_value("Communication", theirs.name, "user", "Administrator")
        with patch.object(ticket_api, "automation_user", return_value="Administrator"):
            self.assertFalse(
                any(c.by_automation for c in ticket_api.get_communications(t.name))
            )

    def test_a_sender_without_an_account_shows_by_their_name(self):
        t = make_ticket(subject="Inbox names")
        email(
            t.name,
            "Received",
            "aisha.noacct@example.com",
            "Aisha Rahman",
            "<p>Hi</p>",
            1,
        )
        names = [c.user["name"] for c in ticket_api.get_communications(t.name)]
        self.assertIn("Aisha Rahman", names)


class TestTheLook(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)

    def test_only_install_colours_move_and_an_admins_choice_stays(self):
        frappe.db.set_value("HD Ticket Status", "Open", "color", "Red")
        frappe.db.set_value(
            "HD Ticket Status", "Replied", "color", "Green"
        )  # an admin chose it
        ticket_area_status_colours.execute()
        self.assertEqual(
            frappe.db.get_value("HD Ticket Status", "Open", "color"), "Blue"
        )
        self.assertEqual(
            frappe.db.get_value("HD Ticket Status", "Replied", "color"), "Green"
        )

    def test_the_default_list_has_one_due_column(self):
        columns = {
            c["key"]: c["label"] for c in HDTicket.default_list_data()["columns"]
        }
        self.assertEqual(columns.get("resolution_by"), "Due")
        self.assertNotIn("response_by", columns)
        self.assertIn("first_responded_on", HDTicket.default_list_data()["rows"])
