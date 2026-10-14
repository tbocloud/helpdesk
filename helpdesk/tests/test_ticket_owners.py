from unittest.mock import patch

import frappe
from frappe.cache_manager import clear_doctype_map
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from helpdesk.api.directory import get_customer_directory
from helpdesk.automation import automation_user
from helpdesk.test_utils import (
    FakeCRM,
    call_as_user,
    call_mobile_as,
    get_open_assignees,
    get_ticket_owner_activity,
    hold_commits,
    make_assignment,
    make_department,
    make_hd_leave,
    make_owned_customer,
    make_tasky_user,
    make_team,
    make_ticket,
)
from helpdesk.utils import remove_assignment

OWNER = ("reshma.to@ticket-owners.example", "Reshma Rao")
BACKUP = ("anu.to@ticket-owners.example", "Anu Varghese")
ROTATION = ("biju.to@ticket-owners.example", "Biju Thomas")
OTHER = ("celine.to@ticket-owners.example", "Celine Joseph")
PM = ("pm.to@ticket-owners.example", "Dileep Nair")
HEAD = ("head.to@ticket-owners.example", "Elsa Mathew")
MANAGER = ("manager.to@ticket-owners.example", "Faisal Rahman")
CUSTOMER = "Hydrotech (owner test)"
SECOND = "Adka (owner test)"
TEAM = "Ticket Owner Rotation"
NOTIFY = "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.notify_users"
SET_OWNER = "helpdesk.api.ticket_owner.set_ticket_owner"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class TestTicketOwners(FrappeTestCase):
    def setUp(self):
        # runs after the rollback: forget the team's rolled-back assignment rule
        self.addCleanup(clear_doctype_map, "Assignment Rule", "HD Ticket")
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        for person in (OWNER, BACKUP, ROTATION, OTHER, HEAD):
            make_tasky_user(*person)
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_team(TEAM, [ROTATION[0]])
        make_owned_customer(CUSTOMER, OWNER[0], BACKUP[0])

    def ticket(self, **values) -> str:
        values.setdefault("status", "Open")
        return str(make_ticket(subject="Store not showing", **values).name)

    # --- who gets a new ticket ---------------------------------------------------

    def test_owner_is_assigned_on_insert(self):
        ticket = self.ticket(customer=CUSTOMER)

        self.assertEqual(get_open_assignees(ticket), [OWNER[0]])
        self.assertEqual(
            get_ticket_owner_activity(ticket),
            [f"assigned Reshma Rao, ticket owner of {CUSTOMER}"],
        )
        # credited to the hub's automation user, not whoever's session raised it
        self.assertEqual(
            frappe.get_value(
                "HD Ticket Activity",
                {"ticket": ticket, "action": ("like", "%ticket owner of%")},
                "owner",
            ),
            automation_user(),
        )

    def test_backup_takes_it_while_the_owner_is_on_leave(self):
        make_hd_leave(OWNER[0], nowdate(), add_days(nowdate(), 2))

        ticket = self.ticket(customer=CUSTOMER)

        self.assertEqual(get_open_assignees(ticket), [BACKUP[0]])
        (activity,) = get_ticket_owner_activity(ticket)
        self.assertIn("assigned Anu Varghese, backup ticket owner of", activity)
        self.assertIn("Reshma Rao is on leave until", activity)

    def test_a_half_day_of_leave_still_counts_as_working(self):
        make_hd_leave(OWNER[0], nowdate(), nowdate(), half_day=1)
        self.assertEqual(get_open_assignees(self.ticket(customer=CUSTOMER)), [OWNER[0]])

    def test_backup_takes_it_while_the_owner_is_inactive(self):
        frappe.db.set_value("HD Agent", OWNER[0], "is_active", 0)

        ticket = self.ticket(customer=CUSTOMER)

        self.assertEqual(get_open_assignees(ticket), [BACKUP[0]])
        self.assertIn("Reshma Rao is inactive", get_ticket_owner_activity(ticket)[0])

    def test_the_assignment_rule_decides_when_neither_can_take_it(self):
        make_hd_leave(OWNER[0], nowdate(), nowdate())
        frappe.db.set_value("User", BACKUP[0], "enabled", 0)

        ticket = self.ticket(customer=CUSTOMER, agent_group=TEAM)

        self.assertEqual(get_open_assignees(ticket), [ROTATION[0]])
        self.assertEqual(get_ticket_owner_activity(ticket), [])

    def test_owner_wins_over_the_team_rotation_with_one_todo(self):
        # the owner isn't in the team, and still gets it
        ticket = self.ticket(customer=CUSTOMER, agent_group=TEAM)

        self.assertEqual(get_open_assignees(ticket), [OWNER[0]])

    def test_a_rule_assignment_that_got_in_first_is_replaced(self):
        ticket = frappe.get_doc("HD Ticket", self.ticket(agent_group=TEAM))
        self.assertEqual(get_open_assignees(ticket.name), [ROTATION[0]])

        ticket.customer = CUSTOMER
        ticket.assign_customer_owner()

        self.assertEqual(get_open_assignees(ticket.name), [OWNER[0]])

    def test_a_ticket_without_customer_is_left_alone(self):
        ticket = self.ticket()

        self.assertNotIn(OWNER[0], get_open_assignees(ticket))
        self.assertEqual(get_ticket_owner_activity(ticket), [])

    def test_a_reassignment_is_never_overridden(self):
        make_owned_customer(SECOND, OTHER[0])
        name = self.ticket(customer=CUSTOMER)
        remove_assignment("HD Ticket", name, OWNER[0], ignore_permissions=True)
        make_assignment("HD Ticket", name, ROTATION[0])

        ticket = frappe.get_doc("HD Ticket", name)
        ticket.customer = SECOND
        ticket.save()

        self.assertEqual(get_open_assignees(name), [ROTATION[0]])

    def test_a_customer_set_later_assigns_the_owner_once(self):
        make_owned_customer(SECOND, OTHER[0])
        name = self.ticket()
        for user in get_open_assignees(name):
            remove_assignment("HD Ticket", name, user, ignore_permissions=True)

        ticket = frappe.get_doc("HD Ticket", name)
        ticket.customer = CUSTOMER
        ticket.save()
        self.assertEqual(get_open_assignees(name), [OWNER[0]])

        # unassigned again and moved to another customer: not applied a second time
        remove_assignment("HD Ticket", name, OWNER[0], ignore_permissions=True)
        ticket.reload()
        ticket.customer = SECOND
        ticket.save()
        self.assertNotIn(OTHER[0], get_open_assignees(name))
        self.assertEqual(len(get_ticket_owner_activity(name)), 1)

    # --- the owner's notice ------------------------------------------------------

    def test_the_owner_is_notified_once(self):
        with patch(NOTIFY) as notify:
            ticket = self.ticket(customer=CUSTOMER, priority="Urgent")

        notify.assert_called_once()
        users, doctype, name, message = notify.call_args.args
        self.assertEqual((users, doctype, str(name)), ([OWNER[0]], "HD Ticket", ticket))
        self.assertTrue(
            message.startswith(
                f"New ticket #{ticket} from {CUSTOMER} assigned to you: Store not showing"
            )
        )
        self.assertIn("Priority: Urgent", message)

    def test_no_notice_when_the_rule_decides(self):
        make_hd_leave(OWNER[0], nowdate(), nowdate())
        make_owned_customer(CUSTOMER, OWNER[0])
        with patch(NOTIFY) as notify:
            self.ticket(customer=CUSTOMER)
        notify.assert_not_called()

    # --- setting owners ----------------------------------------------------------

    def test_only_managers_pms_and_heads_set_owners(self):
        make_department("Ticket Owner Dept", heads=[{"user": HEAD[0]}])
        make_owned_customer(SECOND)

        with self.assertRaises(frappe.PermissionError):
            call_as_user(OTHER[0], SET_OWNER, customers=[SECOND], ticket_owner=OWNER[0])
        self.assertIsNone(frappe.db.get_value("HD Customer", SECOND, "ticket_owner"))

        for person in (PM, HEAD, MANAGER):
            call_as_user(
                person[0], SET_OWNER, customers=[SECOND], ticket_owner=person[0]
            )
            self.assertEqual(
                frappe.db.get_value("HD Customer", SECOND, "ticket_owner"), person[0]
            )

    def test_an_agent_cannot_change_owners_through_the_customer(self):
        doc = frappe.get_doc("HD Customer", CUSTOMER)
        doc.ticket_owner = OTHER[0]
        frappe.set_user(OTHER[0])
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_owners_must_be_active_agents_and_different(self):
        doc = frappe.get_doc("HD Customer", CUSTOMER)
        doc.backup_ticket_owner = OWNER[0]
        self.assertRaises(frappe.ValidationError, doc.save)

        frappe.db.set_value("HD Agent", OTHER[0], "is_active", 0)
        doc.reload()
        doc.ticket_owner = OTHER[0]
        self.assertRaises(frappe.ValidationError, doc.save)

        doc.reload()
        doc.ticket_owner = None
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_bulk_set_keeps_backups_unless_they_become_the_owner(self):
        make_owned_customer(SECOND, OTHER[0], ROTATION[0])

        call_as_user(
            MANAGER[0],
            SET_OWNER,
            customers=[CUSTOMER, SECOND],
            ticket_owner=BACKUP[0],
        )

        owners = {
            c: frappe.db.get_value(
                "HD Customer", c, ["ticket_owner", "backup_ticket_owner"]
            )
            for c in (CUSTOMER, SECOND)
        }
        # Hydrotech's backup was Anu, now its owner, so the backup is cleared
        self.assertEqual(owners[CUSTOMER], (BACKUP[0], None))
        self.assertEqual(owners[SECOND], (BACKUP[0], ROTATION[0]))

    def test_clearing_the_owner_clears_the_backup(self):
        call_as_user(MANAGER[0], SET_OWNER, customers=[CUSTOMER], ticket_owner="")
        self.assertEqual(
            frappe.db.get_value(
                "HD Customer", CUSTOMER, ["ticket_owner", "backup_ticket_owner"]
            ),
            (None, None),
        )

    # --- where owners show ---------------------------------------------------------

    def test_customers_list_filters_customers_without_owner(self):
        make_owned_customer(SECOND)

        everyone = get_customer_directory(search="(owner test)")["rows"]
        unowned = get_customer_directory(search="(owner test)", owner="none")["rows"]

        owned = next(r for r in everyone if r.name == CUSTOMER)
        self.assertEqual(owned.ticket_owner, OWNER[0])
        self.assertEqual(owned.ticket_owner_name, "Reshma Rao")
        self.assertEqual([r.name for r in unowned], [SECOND])

    def test_mobile_ticket_names_the_customer_owner(self):
        ticket = self.ticket(customer=CUSTOMER)
        data = call_mobile_as(OWNER[0], "get_ticket", ticket=ticket)["data"]
        self.assertEqual(
            data["customer_owner"], {"user": OWNER[0], "full_name": "Reshma Rao"}
        )

    def test_crm_account_managers_fill_only_empty_owners(self):
        make_owned_customer(SECOND)
        crm = FakeCRM()
        crm.account_managers = {
            CUSTOMER: OTHER[0],
            SECOND: PM[0].upper(),
        }

        with patch(FROM_SETTINGS, return_value=crm):
            result = call_as_user(MANAGER[0], "helpdesk.api.crm.fill_ticket_owners_now")

        self.assertTrue(result["ok"])
        self.assertEqual(result["filled"], [SECOND])
        self.assertEqual(
            frappe.db.get_value("HD Customer", SECOND, "ticket_owner"), PM[0]
        )
        self.assertEqual(
            frappe.db.get_value("HD Customer", CUSTOMER, "ticket_owner"), OWNER[0]
        )
