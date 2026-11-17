"""Phases 22 and 23: who Copilot goes to comes from one roles table, per customer and common, with
main and fallback people (copilot/people.py)."""

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
    make_content_user,
    make_copilot_settings,
    make_hd_leave,
    make_tasky_user,
    make_ticket,
    set_customer_people,
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
SENIOR = ("approver.p22@people.example", "Jaya Senior")
LEAD = ("lead.p23@people.example", "Kavya Leader")
BACKUP = ("backup.p23@people.example", "Lina Backup")
CUSTOMER = "Phase 22 Customer"
BARE = "Phase 22 Bare Customer"


def row(role, user, level="Main", **more):
    return {"role": role, "person": user, "level": level, "active": 1, **more}


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
            SENIOR,
            LEAD,
            BACKUP,
        ):
            make_tasky_user(*person)
        self.settings(new_ticket_notice="Off")
        self.customer(
            CUSTOMER, developers=[FIRST[0], SECOND[0]], coordinators=[COORD[0]]
        )
        self.customer(BARE)

    # --- helpers -------------------------------------------------------------------------

    COMMON_ROWS = (
        row(people.SENIOR, SENIOR[0]),
        row(people.FIX_APPROVER, SENIOR[0]),
        row(people.COORDINATOR, COMMON[0]),
        row(people.RISK, RISK[0]),
        row(people.LEADER, LEAD[0]),
    )

    def settings(self, rows=None, **values):
        values.setdefault("risk_alert_coordinators", 1)
        return make_copilot_settings(
            copilot_people=list(self.COMMON_ROWS if rows is None else rows), **values
        )

    def customer(self, name, developers=(), fixers=(), coordinators=(), **owners):
        if not frappe.db.exists("HD Customer", name):
            frappe.get_doc({"doctype": "HD Customer", "customer_name": name}).insert(
                ignore_permissions=True
            )
        if owners:
            frappe.db.set_value("HD Customer", name, owners)
        return set_customer_people(name, developers, fixers, coordinators)

    def ticket(self, customer=CUSTOMER) -> str:
        return str(
            make_ticket(subject="Invoice total is wrong", customer=customer).name
        )

    # --- the table and its levels --------------------------------------------------------

    def test_the_main_developer_takes_it_while_working(self):
        found = people.for_ticket(CUSTOMER)
        self.assertEqual((found["user"], found["step"]), (FIRST[0], "developer"))
        self.assertFalse(found["no_developer"])

    def test_fallback_1_takes_it_while_the_main_is_on_leave(self):
        make_hd_leave(FIRST[0], nowdate(), add_days(nowdate(), 3))
        found = people.for_ticket(CUSTOMER)
        self.assertEqual((found["user"], found["step"]), (SECOND[0], "developer"))
        self.assertIn("Asha First is on leave until", found["why"])
        self.assertIn("Fallback 1", found["why"])

    def test_several_at_one_level_go_to_the_least_busy(self):
        self.customer(
            CUSTOMER, coordinators=[COORD[0]], developers=[]
        )  # reset, then two at Main
        set_customer_people(
            CUSTOMER,
            rows=[row(people.DEVELOPER, FIRST[0]), row(people.DEVELOPER, SECOND[0])],
        )
        busy = self.ticket(BARE)
        make_assignment("HD Ticket", busy, FIRST[0])
        self.assertEqual(people.for_ticket(CUSTOMER)["user"], SECOND[0])

    def test_a_row_past_until_or_paused_does_not_count(self):
        set_customer_people(
            CUSTOMER,
            rows=[
                row(people.DEVELOPER, FIRST[0], until=add_days(nowdate(), -1)),
                row(people.DEVELOPER, SECOND[0], active=0),
                row(people.DEVELOPER, OTHER[0], "Fallback 1"),
            ],
        )
        self.assertEqual(people.for_ticket(CUSTOMER)["user"], OTHER[0])
        set_customer_people(
            CUSTOMER,
            rows=[
                row(people.DEVELOPER, FIRST[0], until=nowdate()),  # the last day counts
                row(people.DEVELOPER, OTHER[0], "Fallback 1"),
            ],
        )
        self.assertEqual(people.for_ticket(CUSTOMER)["user"], FIRST[0])

    def test_the_customers_coordinator_chooses_when_no_developer_works(self):
        make_hd_leave(FIRST[0], nowdate(), nowdate())
        make_hd_leave(SECOND[0], nowdate(), nowdate())
        found = people.for_ticket(CUSTOMER)
        self.assertEqual((found["user"], found["step"]), (COORD[0], "coordinator"))
        self.assertTrue(found["no_developer"])
        self.assertTrue(found["developer_set"])
        self.assertEqual(found["coordinators"], [COORD[0]])

    def test_a_customer_without_coordinators_uses_the_common_ones(self):
        self.assertEqual(people.coordinators(BARE), [COMMON[0]])
        self.assertEqual(people.coordinators_from(BARE), "common")
        found = people.for_ticket(BARE)
        self.assertEqual(found["user"], COMMON[0])
        self.assertFalse(found["developer_set"])
        self.assertIn("no developer set", found["why"])

    def test_the_customers_coordinators_away_go_on_to_the_common_ones(self):
        make_hd_leave(COORD[0], nowdate(), nowdate())
        self.assertEqual(people.coordinators_today(CUSTOMER), [COMMON[0]])

    def test_no_coordinator_working_a_leader_chooses(self):
        make_hd_leave(FIRST[0], nowdate(), nowdate())
        make_hd_leave(SECOND[0], nowdate(), nowdate())
        make_hd_leave(COORD[0], nowdate(), nowdate())
        make_hd_leave(COMMON[0], nowdate(), nowdate())
        found = people.for_ticket(CUSTOMER)
        self.assertEqual((found["user"], found["step"]), (LEAD[0], "leader"))

    def test_an_empty_developer_follows_the_ticket_owners(self):
        self.customer(BARE, ticket_owner=OTHER[0], backup_ticket_owner=BACKUP[0])
        self.assertEqual(people.developers(BARE), [OTHER[0], BACKUP[0]])
        self.assertEqual(people.for_ticket(BARE)["user"], OTHER[0])
        self.assertIn("ticket owner", people.for_ticket(BARE)["why"])
        # a manager changes the owner: Copilot follows at once (A14)
        frappe.db.set_value("HD Customer", BARE, "ticket_owner", FIXER[0])
        self.assertEqual(people.for_ticket(BARE)["user"], FIXER[0])
        # a Developer row of the customer's own wins over the owners
        self.customer(BARE, developers=[FIRST[0]])
        self.assertEqual(people.developers(BARE), [FIRST[0]])

    def test_only_active_agents_take_work_but_anyone_can_hear_news(self):
        plain = (
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
        self.assertEqual(people.working([plain]), [])  # cannot act in TBO Support (A17)
        self.assertEqual(people.working([plain], acting=False), [plain])
        make_hd_leave(plain, nowdate(), nowdate())
        self.assertEqual(people.working([plain], acting=False), [])
        frappe.db.set_value("HD Agent", OTHER[0], "is_active", 0)
        self.assertEqual(people.working([OTHER[0]]), [])
        set_customer_people(
            CUSTOMER,
            rows=[
                row(people.DEVELOPER, plain),
                row(people.DEVELOPER, FIRST[0], "Fallback 1"),
            ],
        )
        self.assertEqual(people.for_ticket(CUSTOMER)["user"], FIRST[0])

    def test_the_fix_approver_comes_first_for_a_fix_and_leave_moves_it_on(self):
        self.customer(
            CUSTOMER,
            developers=[FIRST[0], SECOND[0]],
            fixers=[FIXER[0]],
            coordinators=[COORD[0]],
        )
        found = people.for_ticket(CUSTOMER, fix=True)
        self.assertEqual((found["user"], found["step"]), (FIXER[0], "fix_approver"))
        self.assertEqual(people.for_ticket(CUSTOMER)["user"], FIRST[0])  # not a fix
        make_hd_leave(FIXER[0], nowdate(), nowdate())
        self.assertEqual(people.for_ticket(CUSTOMER, fix=True)["user"], FIRST[0])

    def test_with_no_leader_set_the_agent_managers_are_the_last_resort(self):
        self.settings(rows=[r for r in self.COMMON_ROWS if r["role"] != people.LEADER])
        self.assertEqual(people.leaders(), people.agent_managers())
        self.assertTrue(any("No Leader" in w for w in people.overview()["warnings"]))

    def test_with_no_senior_the_leaders_act_as_seniors(self):
        self.settings(rows=[r for r in self.COMMON_ROWS if r["role"] != people.SENIOR])
        self.assertEqual(people.seniors(), [LEAD[0]])

    def test_a_customer_holds_only_its_own_roles(self):
        with self.assertRaises(frappe.ValidationError) as caught:
            set_customer_people(CUSTOMER, rows=[row(people.SENIOR, SENIOR[0])])
        self.assertIn("set once for every customer", str(caught.exception))

    def test_the_code_names_nobody_and_picks_nobody_by_a_role(self):
        source = inspect.getsource(people)
        # the only role lookup is the documented last resort: the Agent Managers while no Leader is set
        self.assertEqual(source.count('"Has Role"'), 1)
        self.assertIn("def agent_managers", source)
        for word in ("get_roles(", "COORDINATOR_PROJECT_ROLE", "project_members("):
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
        # the customer's own people first (A13)
        self.assertEqual(offered[:3], [FIRST[0], SECOND[0], COORD[0]])
        self.assertEqual(card["actions"][0]["verb"], people.ASSIGN)
        self.assertIn(
            ("Copilot goes to", "Asha First"), [tuple(f) for f in card["facts"]]
        )
        self.assertFalse(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_waiting")
        )

    def test_assign_to_leaves_out_people_who_do_not_work_tickets(self):
        writer = make_content_user(
            "writer.p23@people.example", "Mona Writer", "DM Employee"
        )
        offered = [value for _title, value in people.choices(CUSTOMER)]
        self.assertNotIn(writer, offered)
        with self.sent():
            ticket = self.ticket()
            refused = self.press(COORD[0], ticket, person=writer)
        self.assertIn("does not work tickets", refused["replies"][0]["lines"][0])

    def test_tbo_support_only_keeps_the_notice_out_of_teams(self):
        self.settings(new_ticket_notice="TBO Support only")
        with self.sent() as send:
            self.ticket()
        self.assertTrue(send.call_args_list)
        self.assertTrue(
            all(c.kwargs.get("channel") == "Web" for c in send.call_args_list)
        )

    def test_off_stops_new_ticket_notices_but_not_the_choice(self):
        with self.sent() as send:
            self.ticket()
        self.assertFalse(send.call_args_list)
        make_hd_leave(FIRST[0], nowdate(), nowdate())
        make_hd_leave(SECOND[0], nowdate(), nowdate())
        with self.sent() as send:
            ticket = self.ticket()
        (call,) = send.call_args_list
        self.assertIn("no developer is working today", call.args[1]["title"])
        self.assertTrue(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_waiting")
        )

    def test_no_developer_set_is_said_so(self):
        self.settings(new_ticket_notice="Teams and TBO Support")
        with self.sent() as send:
            self.ticket(BARE)
        (call,) = [c for c in send.call_args_list if c.args[0] == COMMON[0]]
        self.assertIn("no developer is set", call.args[1]["title"])

    def test_the_notice_goes_only_to_coordinators_actually_set(self):
        # nobody set as coordinator: no new-ticket card to stand-ins or leaders (A11)
        self.settings(
            new_ticket_notice="Teams and TBO Support",
            rows=[r for r in self.COMMON_ROWS if r["role"] != people.COORDINATOR],
        )
        set_customer_people(CUSTOMER, developers=[FIRST[0], SECOND[0]])
        with self.sent() as send:
            self.ticket()
        self.assertFalse(send.call_args_list)

    def test_the_error_watchs_own_tickets_are_left_alone(self):
        self.settings(new_ticket_notice="Teams and TBO Support")
        with patch("frappe.enqueue") as enqueue:
            people.on_ticket_insert(
                frappe._dict(name="X", customer=CUSTOMER, custom_copilot_source="watch")
            )
            people.on_ticket_insert(frappe._dict(name="Y", customer=CUSTOMER))
        (call,) = enqueue.call_args_list  # only the customer's own ticket
        self.assertEqual(call.kwargs["ticket"], "Y")

    def test_a_customer_without_anyone_set_is_left_alone(self):
        self.settings(
            new_ticket_notice="Teams and TBO Support",
            rows=[r for r in self.COMMON_ROWS if r["role"] != people.COORDINATOR],
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
        row_ = frappe.db.get_value(
            "HD Ticket",
            ticket,
            ["custom_copilot_person", "custom_copilot_waiting"],
            as_dict=True,
        )
        self.assertEqual(
            (row_.custom_copilot_person, row_.custom_copilot_waiting), (OTHER[0], 0)
        )
        found = people.for_ticket(CUSTOMER, ticket)
        self.assertEqual((found["user"], found["step"]), (OTHER[0], "chosen"))
        self.assertIn(OTHER[0], people.may_approve(CUSTOMER, ticket))

    def test_a_leader_who_chooses_is_named_so(self):
        with self.sent():
            ticket = self.ticket()
            result = self.press(LEAD[0], ticket, person=OTHER[0])
        self.assertIn("by leader Kavya Leader", result["replies"][0]["lines"][0])

    def test_the_first_choice_stands(self):
        with self.sent():
            ticket = self.ticket()
            sent_at = str(add_to_date(now_datetime(), seconds=-5))
            self.press(COORD[0], ticket, person=OTHER[0], at=sent_at)
            late = self.press(COMMON[0], ticket, person=FIXER[0], at=sent_at)
        self.assertEqual(get_open_assignees(ticket), [OTHER[0]])
        self.assertIn("Ivan Other", late["card"]["lines"][0])

    def test_only_the_coordinators_and_leaders_choose(self):
        with self.sent():
            ticket = self.ticket()
            refused = self.press(OTHER[0], ticket, person=OTHER[0])
            stand_in = self.press(SENIOR[0], ticket, person=OTHER[0])
        self.assertIn(
            "Only this customer's project coordinators",
            refused["replies"][0]["lines"][0],
        )
        self.assertIn(
            "Only this customer's project coordinators",
            stand_in["replies"][0]["lines"][0],
        )  # a fix approver is not asked to choose
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
        self.assertFalse(send.call_args_list)  # the main developer is back
        self.assertFalse(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_waiting")
        )

    def test_a_normal_assignment_ends_the_wait(self):
        make_hd_leave(FIRST[0], nowdate(), add_days(nowdate(), 1))
        make_hd_leave(SECOND[0], nowdate(), add_days(nowdate(), 1))
        with self.sent():
            ticket = self.ticket()
        for holder in get_open_assignees(ticket):
            frappe.db.set_value(
                "ToDo",
                {"reference_name": ticket, "allocated_to": holder},
                "status",
                "Cancelled",
            )
        make_assignment("HD Ticket", ticket, OTHER[0])
        with self.sent() as send:
            people.ask_again()
        self.assertFalse(send.call_args_list)
        self.assertFalse(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_waiting")
        )

    def test_someone_added_beside_the_chosen_person_keeps_the_choice(self):
        with self.sent():
            ticket = self.ticket()
            self.press(COORD[0], ticket, person=OTHER[0])
        people.add_to_ticket(ticket, COORD[0], "The customer asked for a person")
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_person"), OTHER[0]
        )
        # taken away from the chosen person by hand: the choice ends
        frappe.db.set_value(
            "ToDo",
            {"reference_name": ticket, "allocated_to": OTHER[0]},
            "status",
            "Cancelled",
        )
        make_assignment("HD Ticket", ticket, FIXER[0])
        self.assertFalse(
            frappe.db.get_value("HD Ticket", ticket, "custom_copilot_person")
        )

    def test_asked_again_only_people_working_today(self):
        make_hd_leave(FIRST[0], nowdate(), add_days(nowdate(), 1))
        make_hd_leave(SECOND[0], nowdate(), add_days(nowdate(), 1))
        with self.sent():
            self.ticket()
        for person in (COORD[0], COMMON[0], LEAD[0]):
            make_hd_leave(person, nowdate(), nowdate())
        with self.sent() as send:
            people.ask_again()
        self.assertFalse(send.call_args_list)  # a day off: nobody is asked

    # --- talk to a person ----------------------------------------------------------------

    def test_talk_to_a_person_brings_in_the_project_coordinator(self):
        with self.sent():
            ticket = self.ticket()
        with patch("helpdesk.copilot.thread.post") as post:
            thread.on_hand_over(ticket, "I want to talk to someone")
        self.assertIn(COORD[0], get_open_assignees(ticket))
        self.assertIn(COORD[0], post.call_args.kwargs["to"])

    def test_the_coordinators_and_leaders_write_in_the_ticket_chat(self):
        with self.sent():
            ticket = self.ticket()
        self.assertTrue(thread.may_write(COORD[0], ticket))
        self.assertTrue(thread.may_write(LEAD[0], ticket))
        self.assertFalse(thread.may_write(OTHER[0], ticket))

    # --- risk alerts ---------------------------------------------------------------------

    def test_risk_alerts_go_to_the_risk_people_and_the_coordinators(self):
        self.assertEqual(people.risk_recipients(CUSTOMER), [RISK[0], COORD[0]])
        self.settings(risk_alert_coordinators=0)
        self.assertEqual(people.risk_recipients(CUSTOMER), [RISK[0]])
        self.settings(
            risk_alert_coordinators=0,
            rows=[r for r in self.COMMON_ROWS if r["role"] != people.RISK],
        )
        self.assertEqual(people.risk_recipients(CUSTOMER), [LEAD[0]])  # else a Leader

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

    def test_main_developer_first_then_the_fallback(self):
        self.assertEqual(
            approvals.pick_approver(self.fake_run(), sensitive=False), FIRST[0]
        )
        # the main wrote the fix (nobody approves their own): the fallback developer
        self.assertEqual(
            approvals.pick_approver(
                self.fake_run(), sensitive=False, exclude={FIRST[0]}
            ),
            SECOND[0],
        )
        # both wrote it: the project coordinator
        self.assertEqual(
            approvals.pick_approver(
                self.fake_run(), sensitive=False, exclude={FIRST[0], SECOND[0]}
            ),
            COORD[0],
        )
        # the main is on leave: the fallback
        make_hd_leave(FIRST[0], nowdate(), nowdate())
        self.assertEqual(
            approvals.pick_approver(self.fake_run(), sensitive=False), SECOND[0]
        )

    def test_the_fix_approver_comes_before_the_developers(self):
        self.customer(
            CUSTOMER,
            developers=[FIRST[0], SECOND[0]],
            fixers=[FIXER[0]],
            coordinators=[COORD[0]],
        )
        self.assertEqual(
            approvals.pick_approver(self.fake_run(), sensitive=False), FIXER[0]
        )

    def test_the_common_fix_approvers_stand_in_after_the_customers_people(self):
        everyone = {FIRST[0], SECOND[0], COORD[0], COMMON[0]}
        self.assertEqual(
            approvals.pick_approver(self.fake_run(), sensitive=False, exclude=everyone),
            SENIOR[0],
        )

    def test_the_customers_people_deploy_only_an_approved_fix(self):
        # review of Phase 23: a fix merged on GitHub without its approval stays with the
        # seniors, the leaders and the managers
        from helpdesk.copilot import deploy

        approval = frappe.get_doc(
            {
                "doctype": "HDS Copilot Approval",
                "status": "Superseded",
                "repo": "tbocloud/demo",
                "number": 1,
                "head_sha": "a" * 40,
            }
        ).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        run = frappe._dict(
            customer=CUSTOMER,
            ticket=None,
            task=None,
            name="RUN-P23",
            approval=approval.name,
        )
        self.assertFalse(deploy.may_deploy(FIRST[0], run))
        self.assertTrue(deploy.may_deploy(LEAD[0], run))
        approval.db_set("status", "Approved")
        self.assertTrue(deploy.may_deploy(FIRST[0], run))
        self.assertFalse(deploy.may_deploy(OTHER[0], run))

    def test_a_sensitive_fix_still_needs_a_senior(self):
        self.assertEqual(
            approvals.pick_approver(self.fake_run(), sensitive=True), SENIOR[0]
        )

    def test_a_common_coordinator_standing_in_may_decide(self):
        # the customer has no coordinator of its own: the common one gets the fix and may act (A2)
        set_customer_people(CUSTOMER, developers=[FIRST[0], SECOND[0]])
        self.assertIn(COMMON[0], people.may_approve(CUSTOMER))
        self.assertIn(LEAD[0], people.may_approve(CUSTOMER))
        self.assertNotIn(OTHER[0], people.may_approve(CUSTOMER))

    # --- infrastructure ------------------------------------------------------------------

    def test_infrastructure_people_decide_press_and_aws_actions(self):
        self.assertEqual(actions.deciders("normal"), [LEAD[0]])  # none set: a Leader
        self.settings(
            rows=[
                *self.COMMON_ROWS,
                row(people.INFRA, INFRA[0]),
                row(people.INFRA_SENIOR, INFRA_SENIOR[0]),
            ]
        )
        self.assertEqual(actions.deciders("normal"), [INFRA[0]])
        self.assertEqual(actions.deciders("senior"), [INFRA_SENIOR[0]])
        approval = frappe._dict(requested_by=OTHER[0], risk="senior")
        self.assertIn(
            "only Infrastructure Senior people or a Leader",
            actions.may_decide(approval, INFRA[0]),
        )
        self.assertIsNone(actions.may_decide(approval, INFRA_SENIOR[0]))
        self.assertIsNone(actions.may_decide(approval, LEAD[0]))
        self.assertIn(
            "Only the Infrastructure people",
            actions.may_decide(
                frappe._dict(requested_by=OTHER[0], risk="normal"), SENIOR[0]
            ),
        )

    def test_with_no_infrastructure_senior_a_leader_decides_heavy_actions(self):
        self.settings(rows=[*self.COMMON_ROWS, row(people.INFRA, INFRA[0])])
        # A3: a senior action can always be decided by someone
        self.assertEqual(actions.deciders("senior"), [LEAD[0]])
        self.assertIsNone(
            actions.may_decide(
                frappe._dict(requested_by=OTHER[0], risk="senior"), LEAD[0]
            )
        )

    # --- hand over someone's places ------------------------------------------------------

    def test_hand_over_moves_every_row_and_counts_first(self):
        set_customer_people(BARE, developers=[FIRST[0]], coordinators=[COORD[0]])
        counts = people.hand_over_places(COORD[0], OTHER[0], dry_run=1)
        self.assertEqual((counts["rows"], counts["approvals"]), (2, 0))
        self.assertEqual(people.coordinators(CUSTOMER), [COORD[0]])  # nothing moved yet
        people.hand_over_places(COORD[0], OTHER[0], dry_run=0)
        self.assertEqual(people.coordinators(CUSTOMER), [OTHER[0]])
        self.assertEqual(people.coordinators(BARE), [OTHER[0]])

    def test_hand_over_for_one_customer_and_twins_are_merged(self):
        set_customer_people(
            CUSTOMER, developers=[FIRST[0], SECOND[0]], coordinators=[COORD[0]]
        )
        set_customer_people(BARE, coordinators=[COORD[0]])
        counts = people.hand_over_places(
            SECOND[0], FIRST[0], customer=CUSTOMER, dry_run=0
        )
        self.assertEqual(counts["rows"], 1)
        self.assertEqual(
            people.developers(CUSTOMER), [FIRST[0]]
        )  # one row left at each level
        people.hand_over_places(COORD[0], OTHER[0], customer=CUSTOMER, dry_run=0)
        self.assertEqual(
            people.coordinators(BARE), [COORD[0]]
        )  # another customer: untouched

    def test_hand_over_needs_two_different_enabled_people(self):
        with self.assertRaises(frappe.ValidationError):
            people.hand_over_places(COORD[0], COORD[0])

    # --- moving Phase 22's settings ------------------------------------------------------

    def test_phase_22_tables_become_rows(self):
        rows = people.rows_from_old_settings(
            {
                "approvers": [
                    frappe._dict(user="a@x.example", senior=1, active=1),
                    frappe._dict(user="b@x.example", senior=0, active=1),
                    frappe._dict(user="c@x.example", senior=0, active=0),
                ],
                "infrastructure_people": [
                    frappe._dict(user="d@x.example", senior=1, active=1)
                ],
                "deploy_notice_people": [frappe._dict(user="e@x.example", active=1)],
            }
        )
        found = {(r["role"], r["person"]) for r in rows}
        self.assertEqual(
            found,
            {
                (people.SENIOR, "a@x.example"),
                (people.FIX_APPROVER, "a@x.example"),
                (people.FIX_APPROVER, "b@x.example"),
                (people.INFRA_SENIOR, "d@x.example"),
                (people.DEPLOY, "e@x.example"),
            },
        )

    def test_developers_equal_to_the_owners_are_not_copied(self):
        same = frappe._dict(
            ticket_owner="o@x.example",
            backup_ticket_owner="b@x.example",
            custom_first_developer="o@x.example",
            custom_second_developer="b@x.example",
            coordinators=["c@x.example"],
        )
        self.assertEqual(
            [(r["role"], r["person"]) for r in people.rows_from_old_customer(same)],
            [(people.COORDINATOR, "c@x.example")],
        )
        own = frappe._dict(same, custom_first_developer="d@x.example")
        self.assertEqual(
            [
                (r["role"], r["person"], r["level"])
                for r in people.rows_from_old_customer(own)
                if r["role"] == people.DEVELOPER
            ],
            [
                (people.DEVELOPER, "d@x.example", "Main"),
                (people.DEVELOPER, "b@x.example", "Fallback 1"),
            ],
        )

    def test_one_developer_set_keeps_the_owners_in_the_other_place(self):
        only_second = frappe._dict(
            ticket_owner="a@x.example",
            backup_ticket_owner="b@x.example",
            custom_second_developer="c@x.example",
        )
        self.assertEqual(
            [
                (r["person"], r["level"])
                for r in people.rows_from_old_customer(only_second)
            ],
            [("a@x.example", "Main"), ("c@x.example", "Fallback 1")],
        )
        only_first = frappe._dict(
            ticket_owner="a@x.example",
            backup_ticket_owner="b@x.example",
            custom_first_developer="x@x.example",
        )
        self.assertEqual(
            [
                (r["person"], r["level"])
                for r in people.rows_from_old_customer(only_first)
            ],
            [("x@x.example", "Main"), ("b@x.example", "Fallback 1")],
        )

    # --- the cards and the overview ------------------------------------------------------

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

    def test_the_overview_shows_each_role_each_customer_and_the_empty_places(self):
        plain = (
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": "plain2.p23@people.example",
                    "first_name": "Omar",
                    "send_welcome_email": 0,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        set_customer_people(
            BARE,
            rows=[
                row(people.DEVELOPER, plain),
                row(people.COORDINATOR, OTHER[0], until=add_days(nowdate(), -2)),
            ],
        )
        data = people.overview()
        rows = {r["customer"]: r for r in data["customers"]}
        self.assertEqual(rows[CUSTOMER]["today"], "Asha First")
        self.assertIn("Asha First", rows[CUSTOMER]["developers"])
        roles = {r["role"]: r for r in data["common"]}
        self.assertEqual(roles["Leader"]["today"], "Kavya Leader")
        warnings = " ".join(data["warnings"])
        self.assertIn("No Infrastructure people", warnings)
        self.assertIn("Omar", warnings)  # not an active agent
        self.assertIn("cover as Project Coordinator", warnings)
        self.assertNotIn("before Phase 22", warnings)
