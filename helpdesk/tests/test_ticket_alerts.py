from unittest.mock import patch

import frappe
from frappe.cache_manager import clear_doctype_map
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.test_utils import (
    call_as_user,
    get_ticket_notices,
    hold_commits,
    make_assignment,
    make_hd_leave,
    make_owned_customer,
    make_tasky_user,
    make_ticket,
    make_ticket_communication,
)

OWNER = ("reshma.ta@ticket-alerts.example", "Reshma Rao")
BACKUP = ("anu.ta@ticket-alerts.example", "Anu Varghese")
AGENT = ("celine.ta@ticket-alerts.example", "Celine Joseph")
CUSTOMER = "Hydrotech (alerts test)"
SUBJECT = "Store not showing"


class TestTicketAlerts(FrappeTestCase):
    """New-ticket and status notices for the customer's ticket owner and backup
    (docs/ticket-owners.md#notification)."""

    def setUp(self):
        self.addCleanup(clear_doctype_map, "Assignment Rule", "HD Ticket")
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        for person in (OWNER, BACKUP, AGENT):
            make_tasky_user(*person)
        make_owned_customer(CUSTOMER, OWNER[0], BACKUP[0])

    def ticket(self, **values) -> str:
        values.setdefault("status", "Open")
        values.setdefault("customer", CUSTOMER)
        return str(make_ticket(subject=SUBJECT, **values).name)

    def set_status(self, ticket: str, status: str, as_user: str = "Administrator"):
        frappe.set_user(as_user)
        doc = frappe.get_doc("HD Ticket", ticket)
        doc.status = status
        doc.save(ignore_permissions=True)
        frappe.set_user("Administrator")

    def updates(self, ticket: str) -> list[tuple[str, str]]:
        return get_ticket_notices(ticket, "Ticket Update")

    # --- a new ticket ------------------------------------------------------------

    def test_owner_and_backup_hear_of_a_new_ticket(self):
        with patch("frappe.publish_realtime") as realtime:
            ticket = self.ticket()

        (backup, owner) = get_ticket_notices(ticket, "New Ticket")  # sorted by user
        self.assertEqual(backup[0], BACKUP[0])
        self.assertEqual(
            backup[1],
            f"New ticket #{ticket} from {CUSTOMER} for Reshma Rao (you're the backup): "
            f"{SUBJECT}",
        )
        self.assertEqual(owner[0], OWNER[0])
        self.assertTrue(owner[1].startswith(f"New ticket #{ticket} from {CUSTOMER}"))

        # only the person taking the ticket gets the chime
        sounds = {
            call.kwargs["user"]: call.args[1]["sound"]
            for call in realtime.call_args_list
            if call.args and call.args[0] == "helpdesk:new-notification"
        }
        self.assertEqual(sounds, {OWNER[0]: True, BACKUP[0]: False})

    def test_the_owner_on_leave_hears_nothing_and_the_backup_takes_it(self):
        make_hd_leave(OWNER[0], nowdate(), add_days(nowdate(), 2))

        ticket = self.ticket()

        ((user, message),) = get_ticket_notices(ticket, "New Ticket")
        self.assertEqual(user, BACKUP[0])
        self.assertIn("You're the backup owner while Reshma Rao is away.", message)

    def test_no_notice_for_a_ticket_you_raised(self):
        ticket = self.ticket(raised_by=OWNER[0])
        self.assertEqual(
            [user for user, _ in get_ticket_notices(ticket, "New Ticket")],
            [BACKUP[0]],
        )

        ticket = self.ticket(raised_by=BACKUP[0])
        self.assertEqual(
            [user for user, _ in get_ticket_notices(ticket, "New Ticket")],
            [OWNER[0]],
        )

    # --- status changes and replies ---------------------------------------------

    def test_resolved_closed_and_reopened_reach_the_owner_once_each(self):
        ticket = self.ticket()

        self.set_status(ticket, "Resolved", as_user=AGENT[0])
        self.set_status(ticket, "Closed", as_user=AGENT[0])
        self.set_status(ticket, "Open", as_user=AGENT[0])

        # the owner is also the assignee: one notice per change, no "Reaction" twin
        self.assertEqual(
            self.updates(ticket),
            sorted(
                [
                    (OWNER[0], f"Celine Joseph marked #{ticket} Resolved: {SUBJECT}"),
                    (OWNER[0], f"Celine Joseph marked #{ticket} Closed: {SUBJECT}"),
                    (OWNER[0], f"Celine Joseph reopened #{ticket}: {SUBJECT}"),
                ]
            ),
        )
        self.assertFalse(
            frappe.db.exists(
                "HD Notification",
                {"reference_ticket": ticket, "notification_type": "Reaction"},
            )
        )

    def test_other_changes_send_nothing(self):
        ticket = self.ticket()
        self.set_status(ticket, "Replied", as_user=AGENT[0])
        self.assertEqual(self.updates(ticket), [])

    def test_whoever_makes_the_change_is_not_told(self):
        ticket = self.ticket()
        make_assignment("HD Ticket", ticket, AGENT[0])

        self.set_status(ticket, "Resolved", as_user=OWNER[0])

        self.assertEqual(
            self.updates(ticket),
            [(AGENT[0], f"Reshma Rao marked #{ticket} Resolved: {SUBJECT}")],
        )

    def test_the_backup_follows_only_while_covering(self):
        ticket = self.ticket()
        self.set_status(ticket, "Resolved", as_user=AGENT[0])
        self.assertNotIn(BACKUP[0], [user for user, _ in self.updates(ticket)])

        make_hd_leave(OWNER[0], nowdate(), add_days(nowdate(), 2))
        self.set_status(ticket, "Open", as_user=AGENT[0])

        reopened = [u for u, m in self.updates(ticket) if "reopened" in m]
        self.assertEqual(sorted(reopened), [BACKUP[0], OWNER[0]])

    def test_a_customer_reply_is_one_notice_per_reply(self):
        ticket = self.ticket()
        self.assertEqual(self.updates(ticket), [])  # the opening message isn't a reply

        reply = make_ticket_communication(ticket, "Still not showing")
        reply.save(ignore_permissions=True)  # saved again, as incoming email is

        self.assertEqual(
            self.updates(ticket),
            [(OWNER[0], f"{CUSTOMER} replied on #{ticket}: {SUBJECT}")],
        )

    def test_a_reply_that_reopens_is_told_once_as_the_reply(self):
        ticket = self.ticket()
        self.set_status(ticket, "Resolved", as_user=AGENT[0])

        make_ticket_communication(ticket, "It broke again")

        self.assertEqual(
            [m for _, m in self.updates(ticket) if "Resolved" not in m],
            [f"{CUSTOMER} replied on #{ticket}: {SUBJECT}"],
        )

    def test_a_portal_reply_is_told_once(self):
        ticket = self.ticket()
        self.set_status(ticket, "Resolved", as_user=AGENT[0])

        frappe.get_doc("HD Ticket", ticket).create_communication_via_contact(
            "Please check again"
        )

        self.assertEqual(
            [m for _, m in self.updates(ticket) if "Resolved" not in m],
            [f"{CUSTOMER} replied on #{ticket}: {SUBJECT}"],
        )

    # --- the sound preference ------------------------------------------------------

    def test_the_sound_is_off_by_default_and_in_the_session(self):
        user = call_as_user(OWNER[0], "helpdesk.api.auth.get_user")
        self.assertFalse(user["new_ticket_sound"])

        frappe.db.set_value("User", OWNER[0], "hd_new_ticket_sound", 1)

        user = call_as_user(OWNER[0], "helpdesk.api.auth.get_user")
        self.assertTrue(user["new_ticket_sound"])
