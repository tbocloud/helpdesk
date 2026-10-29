"""Phase 12: a ticket goes only to someone working today, along the chain owner → backup →
the customer's project team → the team's rule, and moves while its assignee is on leave
(helpdesk.ticket_assignment, docs/ticket-owners.md)."""

from unittest.mock import patch

import frappe
from frappe.cache_manager import clear_doctype_map
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk import ticket_assignment
from helpdesk.copilot import thread
from helpdesk.test_utils import (
    age_ticket,
    get_open_assignees,
    get_ticket_chat_notes,
    hold_commits,
    make_agent_status,
    make_assignment,
    make_customer_project,
    make_hd_leave,
    make_owned_customer,
    make_tasky_user,
    make_team,
    make_ticket,
)

OWNER = ("owner@ticket-assignment.example", "Rahul Nair")
BACKUP = ("backup@ticket-assignment.example", "Vishnu Prasad")
DEV_BUSY = ("busy.dev@ticket-assignment.example", "Meera Das")
DEV_FREE = ("free.dev@ticket-assignment.example", "Arjun Menon")
COORDINATOR = ("coordinator@ticket-assignment.example", "Sneha Pillai")
ROTA_AWAY = ("rota.away@ticket-assignment.example", "Kiran Babu")
ROTA_BUSY = ("rota.busy@ticket-assignment.example", "Lekha Raj")
ROTA_FREE = ("rota.free@ticket-assignment.example", "Nikhil Jose")
OUTSIDER = ("outsider@ticket-assignment.example", "Omar Khalid")
MANAGER = ("manager@ticket-assignment.example", "Priya Menon")
CUSTOMER = "Alpha Trading (assignment test)"
NO_PROJECT = "Beta Services (assignment test)"
TEAM = "Assignment Test Rotation"
NOTIFY = "helpdesk.work_reminders.notify_users"


class TicketAssignmentCase(FrappeTestCase):
    def setUp(self):
        self.addCleanup(clear_doctype_map, "Assignment Rule", "HD Ticket")
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        for person in (
            OWNER,
            BACKUP,
            DEV_BUSY,
            DEV_FREE,
            COORDINATOR,
            ROTA_AWAY,
            ROTA_BUSY,
            ROTA_FREE,
            OUTSIDER,
        ):
            make_tasky_user(*person)
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_owned_customer(CUSTOMER, OWNER[0], BACKUP[0])
        make_owned_customer(NO_PROJECT, OWNER[0], BACKUP[0])
        make_customer_project(
            CUSTOMER,
            "Alpha Trading support (assignment test)",
            members=[
                (DEV_BUSY[0], "Developer"),
                (DEV_FREE[0], "Support Engineer"),
                (COORDINATOR[0], "Project Coordinator"),
                (OUTSIDER[0], "Functional Consultant"),
            ],
        )
        make_team(TEAM, [ROTA_AWAY[0], ROTA_BUSY[0], ROTA_FREE[0]])

    def ticket(self, **values) -> str:
        values.setdefault("status", "Open")
        return str(make_ticket(subject="Invoice will not submit", **values).name)

    def away(self, *people, days=2):
        for email, _name in people:
            make_hd_leave(email, nowdate(), add_days(nowdate(), days))


class TestNewTickets(TicketAssignmentCase):
    def test_the_least_busy_on_the_project_team_takes_it_when_owner_and_backup_are_away(
        self,
    ):
        self.away(OWNER, BACKUP)
        # an older ticket keeps the developer busy
        make_assignment("HD Ticket", self.ticket(), DEV_BUSY[0])

        ticket = self.ticket(customer=CUSTOMER)

        self.assertEqual(get_open_assignees(ticket), [DEV_FREE[0]])
        notes = get_ticket_chat_notes(ticket)
        self.assertEqual(len(notes), 1)
        self.assertIn("Arjun Menon, the least busy on", notes[0])
        self.assertIn("Rahul Nair is on leave until", notes[0])
        self.assertTrue(
            frappe.db.exists(
                "HD Ticket Activity",
                {"ticket": ticket, "action": ("like", "%least busy on%project team%")},
            )
        )

    def test_the_chat_says_who_took_it_and_why(self):
        self.away(OWNER)

        ticket = self.ticket(customer=CUSTOMER)

        self.assertEqual(get_open_assignees(ticket), [BACKUP[0]])
        (note,) = get_ticket_chat_notes(ticket)
        self.assertIn("Assigned to Vishnu Prasad", note)
        self.assertIn("backup ticket owner, because Rahul Nair is on leave until", note)

    def test_an_owner_set_to_unavailable_is_passed_over(self):
        status = make_agent_status(
            "Out today (assignment test)", category="Unavailable"
        )
        frappe.db.set_value("HD Agent", OWNER[0], "availability", status.name)

        ticket = self.ticket(customer=CUSTOMER)

        self.assertEqual(get_open_assignees(ticket), [BACKUP[0]])
        self.assertIn(
            "Rahul Nair is set to Unavailable", get_ticket_chat_notes(ticket)[0]
        )

    def test_project_members_in_other_roles_do_not_take_tickets(self):
        self.away(OWNER, BACKUP, DEV_BUSY, DEV_FREE)

        ticket = self.ticket(customer=CUSTOMER)

        self.assertNotIn(OUTSIDER[0], get_open_assignees(ticket))
        self.assertNotIn(COORDINATOR[0], get_open_assignees(ticket))

    def test_the_team_rule_skips_people_on_leave_and_picks_the_least_busy(self):
        self.away(OWNER, BACKUP, ROTA_AWAY)
        make_assignment("HD Ticket", self.ticket(), ROTA_BUSY[0])

        ticket = self.ticket(customer=NO_PROJECT, agent_group=TEAM)

        self.assertEqual(get_open_assignees(ticket), [ROTA_FREE[0]])

    def test_nobody_on_leave_is_picked_when_the_whole_team_is_away(self):
        self.away(OWNER, BACKUP, ROTA_AWAY, ROTA_BUSY, ROTA_FREE)

        ticket = self.ticket(customer=NO_PROJECT, agent_group=TEAM)

        self.assertEqual(get_open_assignees(ticket), [])


class TestNobodyFree(TicketAssignmentCase):
    def test_the_coordinators_are_asked_once(self):
        self.away(OWNER, BACKUP, DEV_BUSY, DEV_FREE)
        ticket = self.ticket(customer=CUSTOMER)
        age_ticket(ticket, minutes=15)

        with patch(NOTIFY) as notify:
            ticket_assignment.ask_for_unassigned()
            ticket_assignment.ask_for_unassigned()

        self.assertEqual(notify.call_count, 1)
        self.assertEqual(notify.call_args.args[0], [COORDINATOR[0]])
        self.assertIn(f"#{ticket}", notify.call_args.args[3])
        self.assertIn(
            "Sneha Pillai asked to assign someone", get_ticket_chat_notes(ticket)[-1]
        )

    def test_the_admins_are_asked_when_the_customer_has_no_coordinator(self):
        self.away(OWNER, BACKUP)
        ticket = self.ticket(customer=NO_PROJECT)
        age_ticket(ticket, minutes=15)

        with patch(NOTIFY) as notify:
            ticket_assignment.ask_for_unassigned()

        self.assertIn(MANAGER[0], notify.call_args.args[0])

    def test_a_brand_new_or_assigned_ticket_is_not_brought_up(self):
        self.away(OWNER, BACKUP, DEV_BUSY, DEV_FREE)
        fresh = self.ticket(customer=CUSTOMER)
        taken = self.ticket(customer=CUSTOMER)
        make_assignment("HD Ticket", taken, OUTSIDER[0])
        age_ticket(taken, minutes=15)

        with patch(NOTIFY) as notify:
            ticket_assignment.ask_for_unassigned()

        asked = [c.args[2] for c in notify.call_args_list]
        self.assertNotIn(fresh, asked)
        self.assertNotIn(taken, asked)


class TestLeave(TicketAssignmentCase):
    def test_a_ticket_moves_from_someone_on_leave_and_says_why(self):
        ticket = self.ticket(customer=CUSTOMER)
        self.assertEqual(get_open_assignees(ticket), [OWNER[0]])
        self.away(OWNER)

        with patch(NOTIFY) as notify:
            moved = ticket_assignment.hand_over_from_leave()

        self.assertIn({"ticket": ticket, "from": [OWNER[0]], "to": BACKUP[0]}, moved)
        self.assertEqual(get_open_assignees(ticket), [BACKUP[0]])
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket, "custom_away_assignee"), OWNER[0]
        )
        self.assertIn(
            "Moved to Vishnu Prasad: Rahul Nair is on leave until",
            get_ticket_chat_notes(ticket)[-1],
        )
        self.assertIn(BACKUP[0], [c.args[0][0] for c in notify.call_args_list])

    def test_a_ticket_someone_working_still_has_stays(self):
        ticket = self.ticket(customer=CUSTOMER)
        make_assignment("HD Ticket", ticket, DEV_FREE[0])
        self.away(OWNER)

        with patch(NOTIFY):
            ticket_assignment.hand_over_from_leave()

        self.assertEqual(get_open_assignees(ticket), sorted([OWNER[0], DEV_FREE[0]]))

    def test_it_goes_back_when_they_return_if_nobody_worked_on_it(self):
        ticket = self.ticket(customer=CUSTOMER)
        self.away(OWNER, days=0)
        with patch(NOTIFY):
            ticket_assignment.hand_over_from_leave()
        self.assertEqual(get_open_assignees(ticket), [BACKUP[0]])

        # the next day the owner works again
        back = ticket_assignment.give_back(day=add_days(nowdate(), 1))

        self.assertIn(ticket, back)
        self.assertEqual(get_open_assignees(ticket), [OWNER[0]])
        self.assertIsNone(
            frappe.db.get_value("HD Ticket", ticket, "custom_away_assignee")
        )
        self.assertIn("Back with Rahul Nair", get_ticket_chat_notes(ticket)[-1])

    def test_it_stays_with_whoever_worked_on_it(self):
        ticket = self.ticket(customer=CUSTOMER)
        self.away(OWNER, days=0)
        with patch(NOTIFY):
            ticket_assignment.hand_over_from_leave()
        frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": ticket,
                "commented_by": BACKUP[0],
                "content": "Looked at the margin settings.",
            }
        ).insert(ignore_permissions=True)

        back = ticket_assignment.give_back(day=add_days(nowdate(), 1))

        self.assertNotIn(ticket, back)
        self.assertEqual(get_open_assignees(ticket), [BACKUP[0]])
        self.assertIsNone(
            frappe.db.get_value("HD Ticket", ticket, "custom_away_assignee")
        )


class TestCopilotDeveloper(TicketAssignmentCase):
    def test_the_developer_is_whoever_takes_the_customers_tickets_today(self):
        self.assertEqual(ticket_assignment.developer_of(CUSTOMER), OWNER[0])
        self.away(OWNER)
        self.assertEqual(ticket_assignment.developer_of(CUSTOMER), BACKUP[0])

    def test_the_old_field_counts_only_without_owners(self):
        make_owned_customer(NO_PROJECT, None, None)
        frappe.db.set_value(
            "HD Customer", NO_PROJECT, "custom_assigned_developer", DEV_FREE[0]
        )
        self.assertEqual(ticket_assignment.developer_of(NO_PROJECT), DEV_FREE[0])
        self.away(DEV_FREE)
        self.assertIsNone(ticket_assignment.developer_of(NO_PROJECT))

    def test_the_patch_makes_the_old_developer_the_owner(self):
        from helpdesk.patches.v16_0_2 import copilot_developer_is_ticket_owner

        make_owned_customer(NO_PROJECT, None, None)
        frappe.db.set_value(
            "HD Customer", NO_PROJECT, "custom_assigned_developer", DEV_FREE[0]
        )

        copilot_developer_is_ticket_owner.execute()

        self.assertEqual(
            frappe.db.get_value("HD Customer", NO_PROJECT, "ticket_owner"), DEV_FREE[0]
        )
        # a customer that has an owner keeps it
        self.assertEqual(
            frappe.db.get_value("HD Customer", CUSTOMER, "ticket_owner"), OWNER[0]
        )


class TestWhoWritesInTheChat(TicketAssignmentCase):
    def test_the_assignee_the_coordinator_and_admins_write_others_read(self):
        ticket = self.ticket(customer=CUSTOMER)

        self.assertTrue(thread.may_write(OWNER[0], ticket))
        self.assertTrue(thread.may_write(COORDINATOR[0], ticket))
        self.assertTrue(thread.may_write(MANAGER[0], ticket))
        self.assertTrue(thread.may_write("Administrator", ticket))
        self.assertFalse(thread.may_write(OUTSIDER[0], ticket))
        self.assertEqual(
            [(p["user"], p["role"]) for p in thread.people(ticket)],
            [(OWNER[0], "developer"), (COORDINATOR[0], "coordinator")],
        )

    def test_a_reader_cannot_write_or_press_but_may_mute(self):
        ticket = self.ticket(customer=CUSTOMER)
        before = frappe.db.count("HDS Copilot Chat Message")

        replies = thread.receive(OUTSIDER[0], ticket, "Please fix it today")
        pressed = thread.press(OUTSIDER[0], ticket, "start", {})
        muted = thread.press(OUTSIDER[0], ticket, "mute", {})

        self.assertIn("Only the developer the ticket is assigned to", str(replies[0]))
        self.assertIn("Only the developer", str(pressed["replies"][0]))
        self.assertNotIn("Only the developer", str(muted["replies"]))
        self.assertTrue(thread.muted(ticket, OUTSIDER[0]))
        self.assertEqual(frappe.db.count("HDS Copilot Chat Message"), before)

    def test_a_reader_sees_no_buttons_but_their_own(self):
        ticket = self.ticket(customer=CUSTOMER)

        state = thread.now(ticket, OUTSIDER[0])

        self.assertFalse(state["can_write"])
        verbs = {a["verb"] for a in state["actions"] + state["more"]}
        self.assertTrue(verbs <= thread.OPEN_VERBS)
