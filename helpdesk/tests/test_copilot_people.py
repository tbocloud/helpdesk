"""Phase 22: who Copilot goes to comes from settings, per customer and common (copilot/people.py)."""

import inspect
import re
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from helpdesk.copilot import actions, approvals, people, teams, thread
from helpdesk.test_utils import (
    get_open_assignees,
    hold_commits,
    make_assignment,
    make_copilot_settings,
    make_hd_leave,
    make_tasky_user,
    make_ticket,
)

FIRST = ("first.p22@people.example", "Asha First")
SECOND = ("second.p22@people.example", "Bilal Second")
FIXER = ("fixer.p22@people.example", "Chitra Fixer")
COORD = ("coord.p22@people.example", "Deepa Coordinator")
COMMON = ("common.p22@people.example", "Eldho Common")
RISK = ("risk.p22@people.example", "Farah Risk")
INFRA = ("infra.p22@people.example", "Gopal Infra")
INFRA_SENIOR = ("infrasenior.p22@people.example", "Hana Senior")
OTHER = ("other.p22@people.example", "Ivan Other")
APPROVER = ("approver.p22@people.example", "Jaya Approver")
CUSTOMER = "Phase 22 Customer"
BARE = "Phase 22 Bare Customer"


class TestCopilotPeople(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        for person in (
            FIRST,
            SECOND,
            FIXER,
            COORD,
            COMMON,
            RISK,
            INFRA,
            INFRA_SENIOR,
            OTHER,
            APPROVER,
        ):
            make_tasky_user(*person)
        self.settings(new_ticket_notice="Off")
        self.customer(
            CUSTOMER, first=FIRST[0], second=SECOND[0], coordinators=[COORD[0]]
        )
        self.customer(BARE)

    # --- helpers -------------------------------------------------------------------------

    def settings(self, **values):
        values.setdefault(
            "approvers", [{"user": APPROVER[0], "senior": 1, "active": 1}]
        )
        values.setdefault("project_coordinators", [{"user": COMMON[0]}])
        values.setdefault("risk_alert_people", [{"user": RISK[0]}])
        values.setdefault("risk_alert_coordinators", 1)
        return make_copilot_settings(**values)

    def customer(self, name, first=None, second=None, fixer=None, coordinators=()):
        if frappe.db.exists("HD Customer", name):
            doc = frappe.get_doc("HD Customer", name)
        else:
            doc = frappe.get_doc({"doctype": "HD Customer", "customer_name": name})
        doc.custom_first_developer = first
        doc.custom_second_developer = second
        doc.custom_fix_approver = fixer
        doc.set("custom_copilot_coordinators", [{"user": u} for u in coordinators])
        doc.save(ignore_permissions=True)
        return doc

    def ticket(self, customer=CUSTOMER) -> str:
        return str(
            make_ticket(subject="Invoice total is wrong", customer=customer).name
        )

    # --- the chain -----------------------------------------------------------------------

    def test_the_first_developer_takes_it_while_working(self):
        found = people.for_ticket(CUSTOMER)
        self.assertEqual((found["user"], found["step"]), (FIRST[0], "first"))
        self.assertFalse(found["no_developer"])

    def test_the_second_developer_takes_it_while_the_first_is_on_leave(self):
        make_hd_leave(FIRST[0], nowdate(), add_days(nowdate(), 3))
        found = people.for_ticket(CUSTOMER)
        self.assertEqual((found["user"], found["step"]), (SECOND[0], "second"))
        self.assertIn("Asha First is on leave until", found["why"])

    def test_the_customers_coordinator_takes_it_when_both_are_away(self):
        make_hd_leave(FIRST[0], nowdate(), nowdate())
        make_hd_leave(SECOND[0], nowdate(), nowdate())
        found = people.for_ticket(CUSTOMER)
        self.assertEqual((found["user"], found["step"]), (COORD[0], "coordinator"))
        self.assertTrue(found["no_developer"])
        self.assertEqual(found["coordinators"], [COORD[0]])

    def test_a_customer_without_coordinators_uses_the_common_ones(self):
        self.assertEqual(people.of_customer(BARE)["coordinators"], [COMMON[0]])
        self.assertEqual(people.of_customer(BARE)["coordinators_from"], "common")
        found = people.for_ticket(BARE)
        self.assertEqual(found["user"], COMMON[0])
        self.assertIn("no developer set", found["why"])

    def test_an_empty_developer_is_the_customers_ticket_owner(self):
        doc = self.customer(BARE)
        doc.ticket_owner, doc.backup_ticket_owner = OTHER[0], FIXER[0]
        doc.save(ignore_permissions=True)
        found = people.of_customer(BARE)
        self.assertEqual((found["first"], found["second"]), (OTHER[0], FIXER[0]))
        self.customer(BARE, first=FIRST[0])
        self.assertEqual(
            people.of_customer(BARE)["first"], FIRST[0]
        )  # Copilot's own field wins

    def test_someone_set_who_is_not_an_agent_counts_unless_on_leave(self):
        developer = (
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": "plain.p22@people.example",
                    "first_name": "Kiran",
                    "send_welcome_email": 0,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.assertEqual(people.working([developer]), [developer])
        make_hd_leave(developer, nowdate(), nowdate())
        self.assertEqual(people.working([developer]), [])
        frappe.db.set_value("HD Agent", OTHER[0], "is_active", 0)
        self.assertEqual(people.working([OTHER[0]]), [])  # an inactive agent is away

    def test_the_customers_own_coordinators_win_over_the_common_ones(self):
        self.assertEqual(people.of_customer(CUSTOMER)["coordinators"], [COORD[0]])

    def test_the_fix_approver_comes_first_for_a_fix_and_leave_moves_it_on(self):
        self.customer(
            CUSTOMER,
            first=FIRST[0],
            second=SECOND[0],
            fixer=FIXER[0],
            coordinators=[COORD[0]],
        )
        self.assertEqual(people.for_ticket(CUSTOMER, fix=True)["user"], FIXER[0])
        self.assertEqual(people.for_ticket(CUSTOMER)["user"], FIRST[0])  # not a fix
        make_hd_leave(FIXER[0], nowdate(), nowdate())
        self.assertEqual(people.for_ticket(CUSTOMER, fix=True)["user"], FIRST[0])

    def test_the_code_names_nobody_and_picks_nobody_by_a_role(self):
        source = inspect.getsource(people)
        # no role lookups and no role names to look up (the overview's warning may say who stands in)
        for word in (
            "get_roles",
            "Has Role",
            "managers(",
            "COORDINATOR_PROJECT_ROLE",
            '"Project Coordinator"',
            '"Agent Manager"',
        ):
            self.assertNotIn(word, source)
        self.assertFalse(
            re.search(r"[\w.-]+@[\w-]+\.[\w.]+", source)
        )  # no email address

    # --- every new ticket, and the coordinator's choice -------------------------------------

    def sent(self):
        return patch("helpdesk.copilot.assistant.send", return_value="Web")

    def test_every_new_ticket_is_told_to_the_coordinators_with_assign_to(self):
        self.settings(new_ticket_notice="Teams and TBO Support")
        with self.sent() as send:
            ticket = self.ticket()
        (call,) = [c for c in send.call_args_list if c.args[0] == COORD[0]]
        card = call.args[1]
        self.assertIn(f"New ticket #{ticket}", card["title"])
        self.assertEqual(card["inputs"][0]["type"], "choice")
        offered = [value for _title, value in card["inputs"][0]["choices"]]
        self.assertIn(OTHER[0], offered)
        self.assertEqual(card["actions"][0]["verb"], people.ASSIGN)
        self.assertIn(
            ("Copilot goes to", "Asha First"), [tuple(f) for f in card["facts"]]
        )
        self.assertFalse(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_waiting")
        )

    def test_tbo_support_only_keeps_the_notice_out_of_teams(self):
        self.settings(new_ticket_notice="TBO Support only")
        with self.sent() as send:
            self.ticket()
        self.assertTrue(send.call_args_list)
        self.assertTrue(
            all(c.kwargs.get("channel") == "Web" for c in send.call_args_list)
        )

    def test_off_stops_new_ticket_notices_but_not_the_choice_when_both_are_away(self):
        with self.sent() as send:
            self.ticket()
        self.assertFalse(send.call_args_list)
        make_hd_leave(FIRST[0], nowdate(), nowdate())
        make_hd_leave(SECOND[0], nowdate(), nowdate())
        with self.sent() as send:
            ticket = self.ticket()
        (call,) = send.call_args_list
        self.assertIn("both developers are away", call.args[1]["title"])
        self.assertTrue(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_waiting")
        )

    def test_a_customer_without_copilot_people_is_left_alone(self):
        self.settings(
            new_ticket_notice="Teams and TBO Support", project_coordinators=[]
        )
        with self.sent() as send:
            self.ticket(BARE)
        self.assertFalse(send.call_args_list)

    def press(self, user, ticket, verb=people.ASSIGN, person=None, at=None):
        return people.press(
            user,
            "Web",
            verb,
            {
                "ticket": ticket,
                "at": at or str(add_to_date(now_datetime(), seconds=-5)),
            },
            {"person": person} if person else {},
        )

    def test_the_coordinator_assigns_someone_and_copilot_follows(self):
        make_hd_leave(FIRST[0], nowdate(), nowdate())
        make_hd_leave(SECOND[0], nowdate(), nowdate())
        with self.sent():
            ticket = self.ticket()
            result = self.press(COORD[0], ticket, person=OTHER[0])
        self.assertIn(
            "Assigned to Ivan Other by project coordinator Deepa Coordinator",
            result["replies"][0]["lines"][0],
        )
        self.assertEqual(get_open_assignees(ticket), [OTHER[0]])
        row = frappe.db.get_value(
            "HD Ticket",
            ticket,
            ["custom_copilot_person", "custom_copilot_waiting"],
            as_dict=True,
        )
        self.assertEqual(
            (row.custom_copilot_person, row.custom_copilot_waiting), (OTHER[0], 0)
        )
        found = people.for_ticket(CUSTOMER, ticket)
        self.assertEqual((found["user"], found["step"]), (OTHER[0], "chosen"))
        self.assertIn(OTHER[0], people.may_approve(CUSTOMER, ticket))

    def test_the_first_choice_stands(self):
        with self.sent():
            ticket = self.ticket()
            sent_at = str(add_to_date(now_datetime(), seconds=-5))
            self.press(COORD[0], ticket, person=OTHER[0], at=sent_at)
            late = self.press(APPROVER[0], ticket, person=FIXER[0], at=sent_at)
        self.assertEqual(get_open_assignees(ticket), [OTHER[0]])
        self.assertIn("Ivan Other", late["card"]["lines"][0])

    def test_only_the_coordinators_and_approvers_choose(self):
        with self.sent():
            ticket = self.ticket()
            refused = self.press(OTHER[0], ticket, person=OTHER[0])
        self.assertIn(
            "Only this customer's project coordinators",
            refused["replies"][0]["lines"][0],
        )
        self.assertFalse(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_person")
        )

    def test_keep_leaves_the_ticket_where_it_is(self):
        with self.sent():
            ticket = self.ticket()
            if not get_open_assignees(ticket):
                make_assignment("HD Ticket", ticket, FIRST[0])
            holders = get_open_assignees(ticket)
            result = self.press(COORD[0], ticket, verb=people.KEEP)
        self.assertEqual(get_open_assignees(ticket), holders)
        self.assertIn("Kept with", result["replies"][0]["lines"][0])

    def test_coordinators_are_asked_again_each_morning_until_one_chooses(self):
        make_hd_leave(FIRST[0], nowdate(), add_days(nowdate(), 1))
        make_hd_leave(SECOND[0], nowdate(), add_days(nowdate(), 1))
        with self.sent():
            ticket = self.ticket()
        with self.sent() as send:
            people.ask_again()
        self.assertTrue(send.call_args_list)
        frappe.db.delete("HD Leave", {"user": FIRST[0]})
        with self.sent() as send:
            people.ask_again()
        self.assertFalse(send.call_args_list)  # the first developer is back
        self.assertFalse(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_waiting")
        )

    # --- talk to a person ----------------------------------------------------------------

    def test_talk_to_a_person_brings_in_the_project_coordinator(self):
        with self.sent():
            ticket = self.ticket()
        with patch("helpdesk.copilot.thread.post") as post:
            thread.on_hand_over(ticket, "I want to talk to someone")
        self.assertIn(COORD[0], get_open_assignees(ticket))
        self.assertIn(COORD[0], post.call_args.kwargs["to"])

    def test_the_settings_coordinators_write_in_the_ticket_chat(self):
        with self.sent():
            ticket = self.ticket()
        self.assertTrue(thread.may_write(COORD[0], ticket))
        self.assertFalse(thread.may_write(OTHER[0], ticket))

    # --- risk alerts ---------------------------------------------------------------------

    def test_risk_alerts_go_to_the_risk_people_and_the_coordinators(self):
        self.assertEqual(people.risk_recipients(CUSTOMER), [RISK[0], COORD[0]])
        self.settings(risk_alert_coordinators=0)
        self.assertEqual(people.risk_recipients(CUSTOMER), [RISK[0]])

    def test_a_risk_alert_reaches_them_and_skips_the_approver(self):
        with self.sent() as send:
            people.alert_risk(
                "A senior Press action",
                ["Asked by someone."],
                customer=CUSTOMER,
                skip=(COORD[0],),
            )
        told = [c.args[0] for c in send.call_args_list]
        self.assertEqual(told, [RISK[0]])
        self.assertIn(
            "who approves does not change", send.call_args.args[1]["lines"][-1]
        )

    # --- fix approvals -------------------------------------------------------------------

    def fake_run(self, ticket=None, customer=CUSTOMER):
        return frappe._dict(customer=customer, ticket=ticket, task=None, name="RUN-P22")

    def test_a_fix_goes_to_the_customers_developer_even_when_not_an_approver(self):
        self.assertEqual(
            approvals.pick_approver(self.fake_run(), sensitive=False), FIRST[0]
        )

    def test_a_sensitive_fix_still_needs_a_senior(self):
        self.assertEqual(
            approvals.pick_approver(self.fake_run(), sensitive=True), APPROVER[0]
        )

    # --- infrastructure people -----------------------------------------------------------

    def test_infrastructure_people_decide_press_and_aws_actions(self):
        self.assertEqual(
            actions.deciders("normal"), [APPROVER[0]]
        )  # none set: the approvers
        self.settings(
            infrastructure_people=[
                {"user": INFRA[0], "senior": 0, "active": 1},
                {"user": INFRA_SENIOR[0], "senior": 1, "active": 1},
            ]
        )
        self.assertEqual(actions.deciders("normal"), [INFRA[0], INFRA_SENIOR[0]])
        self.assertEqual(actions.deciders("senior"), [INFRA_SENIOR[0]])
        approval = frappe._dict(requested_by=OTHER[0], risk="senior")
        self.assertIn(
            "senior among the infrastructure people",
            actions.may_decide(approval, INFRA[0]),
        )
        self.assertIsNone(actions.may_decide(approval, INFRA_SENIOR[0]))
        self.assertIn(
            "Only the infrastructure people",
            actions.may_decide(
                frappe._dict(requested_by=OTHER[0], risk="normal"), APPROVER[0]
            ),
        )

    # --- the cards -----------------------------------------------------------------------

    def test_teams_draws_assign_to_as_a_list(self):
        card = teams.adaptive(
            {
                "title": "t",
                "inputs": [
                    {
                        "id": "person",
                        "type": "choice",
                        "label": "Assign to",
                        "choices": [["Ivan Other (0 open)", OTHER[0]]],
                    }
                ],
                "actions": [{"label": "Assign", "verb": people.ASSIGN, "data": {}}],
            }
        )
        (choice,) = [b for b in card["body"] if b["type"] == "Input.ChoiceSet"]
        self.assertEqual(
            choice["choices"], [{"title": "Ivan Other (0 open)", "value": OTHER[0]}]
        )
        self.assertIn("person", teams.CARD_INPUTS)

    def test_the_overview_shows_each_customer_and_the_empty_places(self):
        data = people.overview()
        rows = {r["customer"]: r for r in data["customers"]}
        self.assertEqual(rows[CUSTOMER]["today"], "Asha First")
        self.assertEqual(rows[BARE]["coordinators_from"], "common")
        self.assertIn("first developer", rows[BARE]["empty"])
        self.assertTrue(any("infrastructure" in w for w in data["warnings"]))
