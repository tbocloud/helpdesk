"""Ticket intake (docs/ticket-intake.md): mail rules and alert grouping, routing after
triage, customer detection by domain, the client-site import fix and the feedback
request on close."""

from unittest.mock import patch

import frappe
from frappe.cache_manager import clear_doctype_map
from frappe.tests.utils import FrappeTestCase

from helpdesk import intake
from helpdesk.api import home
from helpdesk.automation import automation_user
from helpdesk.consts import (
    ALERT_TICKET_TYPE,
    DEFAULT_TICKET_PRIORITY,
    MONITOR_RESOLVED_STATUS,
)
from helpdesk.email_filter import UnwantedTicketEmail
from helpdesk.helpdesk.doctype.hd_customer.hd_customer import clear_domain_cache
from helpdesk.overrides.email_account import CustomInboundMail
from helpdesk.routing import apply_triage
from helpdesk.test_utils import (
    INTAKE_INBOX,
    FakeCRM,
    call_as_user,
    get_feedback_mails,
    get_intake_logs,
    get_open_assignees,
    get_ticket_comments,
    hold_commits,
    log_activity_as,
    make_domain_customer,
    make_email_account,
    make_intake_mail,
    make_mail_ticket,
    make_owned_customer,
    make_support_connection,
    make_tasky_user,
    make_team,
    make_ticket,
    make_ticket_type,
    set_intake_settings,
    set_ticket_status,
)
from helpdesk.ticket_puller import _create_hd_ticket

GRAFANA = "grafana@stack123.grafana.net"
VENDOR = "support@grafana.com"
UPTIME = "alerts@uptime.example"
FIRING = "[FIRING:1] Site down tbocloud (TBO Team critical tboindia production)"
RESOLVED = "[RESOLVED] Site down tbocloud (TBO Team critical production)"
RULES = [
    {
        "label": "Grafana alerts",
        "sender_pattern": "grafana.net",
        "subject_pattern": r"^\[(FIRING|RESOLVED)",
        "action": "Alert",
    },
    {
        "label": "Grafana account mail",
        "sender_pattern": "grafana.com",
        "action": "Ignore",
    },
    {
        "label": "Energy points",
        "subject_pattern": "^weekly energy points summary",
        "action": "Ignore",
    },
    {
        "label": "Uptime follow-ups",
        "sender_pattern": "uptime.example",
        "action": "Merge into open alert",
    },
]
AGENT = ("asha.intake@intake.example", "Asha Pillai")
OWNER = ("owner.intake@intake.example", "Ravi Menon")
MANAGER = ("manager.intake@intake.example", "Meera Das")
TEAM = "Intake Billing"
CUSTOMER = "Acme Intake"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class IntakeCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Intake Settings", "HD Intake Settings"
        )
        self.addCleanup(frappe.clear_document_cache, "HD Settings", "HD Settings")
        # the domain map would otherwise keep customers the rollback removed
        clear_domain_cache()
        self.addCleanup(clear_domain_cache)
        mail = patch("frappe.sendmail")
        self.sendmail = mail.start()
        self.addCleanup(mail.stop)
        intake.ensure_intake_defaults()
        set_intake_settings(
            rules=RULES,
            routes=[],
            default_team=None,
            apply_triage=1,
            match_customer_by_domain=1,
            public_email_domains="gmail.com\noutlook.com",
            feedback_on_close=1,
            post_alerts_to_channel=0,
        )


class TestMailRules(IntakeCase):
    def test_ignore_rule_logs_the_mail_and_opens_no_ticket(self):
        self.assertTrue(
            intake.handle_new_mail(
                VENDOR, "Please verify your Grafana Cloud account", ""
            )
        )
        self.assertEqual(
            get_intake_logs(VENDOR),
            [{"action": "Ignored", "rule": "Grafana account mail", "ticket": None}],
        )
        with self.assertRaises(UnwantedTicketEmail):
            make_mail_ticket("Your Grafana stack is active!", VENDOR)

    def test_a_subject_rule_matches_any_sender(self):
        sender = "info@life-bridge.example"
        self.assertTrue(
            intake.handle_new_mail(sender, "Weekly energy points summary", "")
        )
        self.assertEqual(get_intake_logs(sender)[0]["rule"], "Energy points")

    def test_alert_rule_opens_an_alert_ticket_without_sla(self):
        self.assertFalse(intake.handle_new_mail(GRAFANA, FIRING, "Site is down"))
        ticket = make_mail_ticket(FIRING, GRAFANA)

        self.assertEqual(ticket.ticket_type, ALERT_TICKET_TYPE)
        self.assertEqual(ticket.alert_key, "site down tbocloud")
        self.assertFalse(ticket.sla)
        self.assertFalse(ticket.agreement_status)
        self.assertFalse(ticket.resolution_by)
        self.assertNotIn(str(ticket.name), [str(t.name) for t in home._open_tickets()])

    def test_home_still_counts_tickets_without_a_type(self):
        untyped = make_ticket(subject="Old ticket", status="Open")
        frappe.db.set_value("HD Ticket", untyped.name, "ticket_type", None)
        self.assertIn(str(untyped.name), [str(t.name) for t in home._open_tickets()])

    def test_a_repeat_is_added_to_the_open_alert(self):
        alert = make_mail_ticket(FIRING, GRAFANA)

        self.assertTrue(intake.handle_new_mail(GRAFANA, FIRING, "Still down"))

        self.assertEqual(frappe.db.get_value("HD Ticket", alert.name, "status"), "Open")
        comments = get_ticket_comments(alert.name)
        self.assertEqual(len(comments), 1)
        self.assertIn("Still down", comments[0])
        self.assertEqual(get_intake_logs(GRAFANA)[-1]["action"], "Grouped")

    def test_partly_resolved_still_fires(self):
        alert = make_mail_ticket(FIRING, GRAFANA)
        intake.handle_new_mail(
            GRAFANA, "[FIRING:1, RESOLVED:1] Site down tbocloud (critical)", ""
        )
        self.assertEqual(frappe.db.get_value("HD Ticket", alert.name, "status"), "Open")

    def test_resolved_comments_then_closes_the_alert(self):
        alert = make_mail_ticket(FIRING, GRAFANA)

        # Grafana's common labels changed between the two mails; the key still matches
        self.assertTrue(intake.handle_new_mail(GRAFANA, RESOLVED, "Back up"))

        self.assertEqual(
            frappe.db.get_value("HD Ticket", alert.name, "status"),
            MONITOR_RESOLVED_STATUS,
        )
        self.assertEqual(len(get_ticket_comments(alert.name)), 1)
        self.assertEqual(
            get_intake_logs(GRAFANA)[-1],
            {"action": "Resolved", "rule": "Grafana alerts", "ticket": str(alert.name)},
        )

    def test_a_resolved_alert_with_nothing_open_opens_nothing(self):
        self.assertTrue(intake.handle_new_mail(GRAFANA, RESOLVED, ""))
        self.assertEqual(get_intake_logs(GRAFANA)[0]["action"], "Ignored")

    def test_merge_rule_only_adds_to_an_open_alert(self):
        subject = "[FIRING:1] Site down tbocloud"
        self.assertTrue(intake.handle_new_mail(UPTIME, subject, ""))
        self.assertEqual(get_intake_logs(UPTIME)[0]["action"], "Ignored")

        alert = make_mail_ticket(FIRING, GRAFANA)
        self.assertTrue(intake.handle_new_mail(UPTIME, subject, "Seen by Uptime"))
        self.assertEqual(len(get_ticket_comments(alert.name)), 1)

    def test_rules_come_before_the_built_in_filter(self):
        frappe.db.set_single_value("HD Settings", "ignore_automated_emails", 1)
        frappe.clear_document_cache("HD Settings", "HD Settings")
        sender = "noreply@monitor.example"
        self.assertTrue(intake.handle_new_mail(sender, FIRING, ""))
        self.assertEqual(get_intake_logs(sender)[0]["rule"], intake.BUILT_IN_FILTER)

        set_intake_settings(
            rules=[
                {
                    "label": "Monitor",
                    "sender_pattern": "monitor.example",
                    "action": "Alert",
                },
                *RULES,
            ]
        )
        self.assertFalse(intake.handle_new_mail(sender, FIRING, ""))

    def test_a_disabled_rule_is_skipped(self):
        set_intake_settings(rules=[{**RULES[1], "enabled": 0}])
        self.assertFalse(intake.handle_new_mail(VENDOR, "A real question", ""))

    def test_parse_alert(self):
        firing = intake.parse_alert(FIRING)
        self.assertFalse(firing.resolved)
        self.assertEqual(firing.key, "site down tbocloud")
        self.assertIn("tboindia", firing.labels)
        self.assertTrue(intake.parse_alert(RESOLVED).resolved)
        self.assertTrue(intake.parse_alert("[OK] Disk full db1").resolved)
        self.assertFalse(intake.parse_alert("[FIRING:2, RESOLVED:1] Disk").resolved)

    def test_a_bad_subject_pattern_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            set_intake_settings(
                rules=[
                    {
                        "label": "Broken",
                        "subject_pattern": "[unclosed",
                        "action": "Ignore",
                    }
                ]
            )


class TestInboundMail(IntakeCase):
    """The whole path: the mailbox's InboundMail goes through the rules first."""

    def receive(self, subject: str, sender: str, body: str = "Alert details"):
        inbox = make_email_account(
            INTAKE_INBOX, enable_outgoing=0, enable_incoming=1, append_to="HD Ticket"
        )
        return CustomInboundMail(
            make_intake_mail(subject, sender, body), inbox, 1
        ).process()

    def test_a_new_alert_opens_an_alert_ticket_and_its_repeat_does_not(self):
        communication = self.receive(FIRING, GRAFANA)
        ticket = frappe.get_doc("HD Ticket", communication.reference_name)
        self.assertEqual(ticket.ticket_type, ALERT_TICKET_TYPE)

        self.assertIsNone(self.receive(FIRING, GRAFANA, "Still down"))
        self.assertIsNone(self.receive(RESOLVED, GRAFANA, "Back up"))

        self.assertEqual(
            frappe.db.count("HD Ticket", {"alert_key": "site down tbocloud"}), 1
        )
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket.name, "status"),
            MONITOR_RESOLVED_STATUS,
        )

    def test_ignored_mail_opens_nothing(self):
        self.assertIsNone(self.receive("Your Grafana stack is active!", VENDOR))
        self.assertFalse(frappe.db.exists("HD Ticket", {"raised_by": VENDOR}))


class TestCleanup(IntakeCase):
    def status(self, ticket) -> str:
        return frappe.db.get_value("HD Ticket", ticket.name, "status")

    def test_preview_then_apply_rules_to_open_tickets(self):
        # tickets that came in before the rules existed
        set_intake_settings(rules=[])
        first = make_mail_ticket(FIRING, GRAFANA)
        repeat = make_mail_ticket(FIRING, GRAFANA)
        resolved = make_mail_ticket(RESOLVED, GRAFANA)
        vendor = make_mail_ticket("New cost optimization tools", VENDOR)
        person = make_mail_ticket("Invoice not printing", "accounts@customer.example")
        set_intake_settings(rules=RULES)

        ours = {str(t.name) for t in (first, repeat, resolved, vendor, person)}
        steps = {
            (s["ticket"], s["action"])
            for s in intake.plan_cleanup()
            if s["ticket"] in ours
        }
        self.assertEqual(
            steps,
            {
                (str(first.name), "mark_alert"),
                (str(repeat.name), "group"),
                (str(resolved.name), "group"),
                (str(first.name), "resolve"),
                (str(vendor.name), "close"),
            },
        )
        # the preview changed nothing
        self.assertEqual(frappe.db.get_value("HD Ticket", first.name, "status"), "Open")

        result = intake.apply_cleanup()

        self.assertEqual(result["failed"], [])
        self.assertEqual(self.status(first), MONITOR_RESOLVED_STATUS)
        self.assertEqual(self.status(repeat), "Closed")
        self.assertEqual(
            frappe.db.get_value("HD Ticket", repeat.name, "merged_with"),
            str(first.name),
        )
        self.assertEqual(self.status(vendor), "Closed")
        self.assertEqual(self.status(person), "Open")
        self.assertEqual(
            frappe.db.get_value("HD Ticket", first.name, "ticket_type"),
            ALERT_TICKET_TYPE,
        )
        self.assertFalse(frappe.db.get_value("HD Ticket", first.name, "sla"))

    def test_only_managers_use_the_settings(self):
        make_tasky_user(*AGENT)
        with self.assertRaises(frappe.PermissionError):
            call_as_user(AGENT[0], "helpdesk.api.intake.preview_cleanup")


class TestRouting(IntakeCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(clear_doctype_map, "Assignment Rule", "HD Ticket")
        for person in (AGENT, OWNER):
            make_tasky_user(*person)
        make_team(TEAM, [AGENT[0]])
        make_ticket_type("Question")
        set_intake_settings(routes=[{"category": "Billing", "team": TEAM}])

    def ticket(self, **values) -> str:
        values.setdefault("status", "Open")
        # the default priority, whatever other tests left in HD Settings or the SLAs
        values.setdefault("priority", DEFAULT_TICKET_PRIORITY)
        return str(make_ticket(subject="Invoice total is wrong", **values).name)

    def test_triage_sets_priority_type_and_team(self):
        ticket = self.ticket()

        changed = apply_triage(
            ticket,
            {"priority": "High", "category": "Billing", "request_type": "question"},
        )

        self.assertEqual(
            changed,
            {"priority": "High", "ticket_type": "Question", "agent_group": TEAM},
        )
        # the team's round robin assigned it
        self.assertEqual(get_open_assignees(ticket), [AGENT[0]])
        self.assertEqual(
            frappe.get_all(
                "HD Ticket Activity",
                filters={"ticket": ticket, "action": "set priority to High"},
                pluck="owner",
            ),
            [automation_user()],
        )

    def test_a_persons_priority_is_kept(self):
        ticket = self.ticket()
        log_activity_as(AGENT[0], ticket, "set priority to Low")
        frappe.db.set_value("HD Ticket", ticket, "priority", "Low")

        changed = apply_triage(ticket, {"priority": "High", "category": "Billing"})

        self.assertNotIn("priority", changed)
        self.assertEqual(frappe.db.get_value("HD Ticket", ticket, "priority"), "Low")

    def test_a_priority_chosen_at_creation_is_kept(self):
        ticket = self.ticket(priority="Urgent")
        self.assertNotIn("priority", apply_triage(ticket, {"priority": "Low"}))

    def test_critical_becomes_urgent(self):
        ticket = self.ticket()
        self.assertEqual(
            apply_triage(ticket, {"priority": "Critical"})["priority"], "Urgent"
        )

    def test_a_category_without_a_route_goes_to_the_default_team(self):
        set_intake_settings(default_team=TEAM)
        ticket = self.ticket()
        self.assertEqual(
            apply_triage(ticket, {"category": "Print"})["agent_group"], TEAM
        )

    def test_a_team_set_by_a_person_is_kept(self):
        make_team("Intake Other Team", [OWNER[0]])
        ticket = self.ticket(agent_group="Intake Other Team")
        self.assertNotIn("agent_group", apply_triage(ticket, {"category": "Billing"}))

    def test_the_ticket_owner_keeps_the_ticket(self):
        make_owned_customer(CUSTOMER, OWNER[0])
        ticket = self.ticket(customer=CUSTOMER)
        self.assertEqual(get_open_assignees(ticket), [OWNER[0]])

        apply_triage(ticket, {"category": "Billing"})

        self.assertEqual(frappe.db.get_value("HD Ticket", ticket, "agent_group"), TEAM)
        # neither the round robin nor the team change takes it from the owner
        self.assertEqual(get_open_assignees(ticket), [OWNER[0]])

    def test_routing_can_be_switched_off(self):
        set_intake_settings(apply_triage=0)
        self.assertEqual(apply_triage(self.ticket(), {"priority": "High"}), {})

    def test_alerts_are_not_routed(self):
        alert = make_mail_ticket(FIRING, GRAFANA)
        self.assertEqual(apply_triage(str(alert.name), {"category": "Billing"}), {})

    def test_settings_show_each_teams_members_and_round_robin(self):
        make_team("Intake Paused Team", [AGENT[0]]).db_set("assignment_rule", None)
        settings = call_as_user("Administrator", "helpdesk.api.intake.get_settings")
        teams = {t["name"]: t for t in settings["teams"]}

        self.assertEqual(teams[TEAM]["members"], 1)
        self.assertTrue(teams[TEAM]["rotation"])
        # the page warns: tickets routed there would stay unassigned
        self.assertFalse(teams["Intake Paused Team"]["rotation"])


class TestCustomerDetection(IntakeCase):
    def test_the_senders_domain_finds_the_customer_and_links_the_contact(self):
        make_domain_customer(CUSTOMER, "https://www.acme-intake.example/")
        ticket = make_ticket(
            subject="Stock report", raised_by="ravi@acme-intake.example"
        )

        self.assertEqual(ticket.customer, CUSTOMER)
        contact = frappe.db.get_value(
            "Contact", {"email_id": "ravi@acme-intake.example"}
        )
        self.assertTrue(
            frappe.db.exists(
                "HD Customer Member", {"parent": CUSTOMER, "contact_name": contact}
            )
        )

    def test_subdomains_and_other_email_domains_match(self):
        make_domain_customer(
            CUSTOMER, "acme-intake.example", "acme-group.example\nacme.co"
        )
        for sender in (
            "a@mail.acme-intake.example",
            "b@acme.co",
            "c@acme-group.example",
        ):
            self.assertEqual(make_ticket(raised_by=sender).customer, CUSTOMER, sender)

    def test_public_mail_domains_never_match(self):
        make_domain_customer(CUSTOMER, "gmail.com")
        self.assertFalse(make_ticket(raised_by="someone@gmail.com").customer)

    def test_a_domain_two_customers_share_matches_neither(self):
        make_domain_customer(CUSTOMER, "shared-intake.example")
        make_domain_customer("Acme Intake Two", "shared-intake.example")
        self.assertFalse(make_ticket(raised_by="x@shared-intake.example").customer)

    def test_matching_can_be_switched_off(self):
        set_intake_settings(match_customer_by_domain=0)
        make_domain_customer(CUSTOMER, "acme-intake.example")
        self.assertFalse(make_ticket(raised_by="ravi@acme-intake.example").customer)

    def test_an_agents_own_ticket_gets_no_customer(self):
        make_tasky_user("agent@acme-intake.example", "Acme Agent")
        make_domain_customer(CUSTOMER, "acme-intake.example")
        ticket = make_ticket(raised_by="agent@acme-intake.example")
        self.assertFalse(ticket.customer)
        self.assertFalse(frappe.db.exists("HD Customer Member", {"parent": CUSTOMER}))

    def test_fill_domains_from_the_crm_website(self):
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_domain_customer(CUSTOMER)
        make_domain_customer("Acme Intake Mail")
        make_domain_customer("Acme Intake Set", "kept-intake.example")
        crm = FakeCRM()
        crm.orgs = [
            {
                "name": CUSTOMER,
                "organization_name": CUSTOMER,
                "website": "https://www.acme-intake.example",
            },
            {
                "name": "Acme Intake Mail",
                "organization_name": "Acme Intake Mail",
                "website": "gmail.com",
            },
            {
                "name": "Acme Intake Set",
                "organization_name": "Acme Intake Set",
                "website": "other-intake.example",
            },
            # a subdomain of another customer's domain: its senders would match both
            {
                "name": "Acme Intake Shop",
                "organization_name": "Acme Intake Shop",
                "website": "shop.kept-intake.example",
            },
        ]
        make_domain_customer("Acme Intake Shop")
        method = "helpdesk.api.crm.fill_customer_domains_now"

        with patch(FROM_SETTINGS, return_value=crm):
            preview = call_as_user(MANAGER[0], method)
            self.assertEqual(
                preview["fill"],
                [{"customer": CUSTOMER, "domain": "acme-intake.example"}],
            )
            self.assertEqual(
                [r["customer"] for r in preview["public"]], ["Acme Intake Mail"]
            )
            self.assertEqual(
                [r["customer"] for r in preview["taken"]], ["Acme Intake Shop"]
            )
            self.assertFalse(frappe.db.get_value("HD Customer", CUSTOMER, "domain"))

            call_as_user(MANAGER[0], method, apply=True)

        self.assertEqual(
            frappe.db.get_value("HD Customer", CUSTOMER, "domain"),
            "acme-intake.example",
        )
        self.assertEqual(
            frappe.db.get_value("HD Customer", "Acme Intake Set", "domain"),
            "kept-intake.example",
        )


class TestClientSiteImport(IntakeCase):
    def test_the_import_that_failed_now_links_the_contact(self):
        """A ping's pull runs as Guest; the sender wasn't a contact of the customer."""
        make_domain_customer("Thaqatal Intake")
        # the ticket links its connection from the start, so it must exist
        connection = make_support_connection("Thaqatal Intake").name
        frappe.set_user("Guest")

        name = _create_hd_ticket(
            connection,
            "Thaqatal Intake",
            {
                "name": "SUP-2026-90001",
                "subject": "Need print option",
                "raised_by": "dripdrop@gmail.com",
            },
        )

        frappe.set_user("Administrator")
        ticket = frappe.get_doc("HD Ticket", name)
        self.assertEqual(ticket.customer, "Thaqatal Intake")
        self.assertEqual(ticket.raised_by, "dripdrop@gmail.com")
        self.assertEqual(ticket.owner, automation_user())
        self.assertTrue(ticket.contact)

    def test_a_user_id_is_no_sender(self):
        customer = make_domain_customer("Adka Intake")
        customer.db_set("email_id", "it@adka-intake.example")
        connection = make_support_connection("Adka Intake").name

        from_owner = _create_hd_ticket(
            connection,
            "Adka Intake",
            {
                "name": "SUP-2026-90002",
                "subject": "Letterhead",
                "raised_by": "Administrator",
                "owner": "maya@adka-intake.example",
            },
        )
        from_customer = _create_hd_ticket(
            connection,
            "Adka Intake",
            {
                "name": "SUP-2026-90003",
                "subject": "Print",
                "raised_by": "Administrator",
                "owner": "Administrator",
            },
        )

        self.assertEqual(
            frappe.db.get_value("HD Ticket", from_owner, "raised_by"),
            "maya@adka-intake.example",
        )
        self.assertEqual(
            frappe.db.get_value("HD Ticket", from_customer, "raised_by"),
            "it@adka-intake.example",
        )

    def test_tbo_support_signed_in_on_the_site_is_no_sender(self):
        customer = make_domain_customer("Hamra Intake")
        customer.db_set("email_id", "it@hamra-intake.example")
        connection = make_support_connection(
            "Hamra Intake", support_user="support@teambackoffice.com"
        ).name

        name = _create_hd_ticket(
            connection,
            "Hamra Intake",
            {
                "name": "SUP-2026-90004",
                "subject": "Report won't load",
                "raised_by": "support@teambackoffice.com",
                "owner": "support@teambackoffice.com",
            },
        )

        self.assertEqual(
            frappe.db.get_value("HD Ticket", name, "raised_by"),
            "it@hamra-intake.example",
        )


class TestFeedbackOnClose(IntakeCase):
    def setUp(self):
        super().setUp()
        frappe.db.set_single_value(
            "HD Settings",
            {
                "enable_email_ticket_feedback": 1,
                "send_email_feedback_on_status": "Resolved",
            },
        )
        frappe.clear_document_cache("HD Settings", "HD Settings")

    def test_closing_without_resolving_asks_once(self):
        ticket = make_ticket(
            subject="Report wrong", raised_by="lina@customer-intake.example"
        )

        self.assertTrue(set_ticket_status(ticket.name, "Closed").feedback_requested_on)
        self.assertEqual(len(get_feedback_mails(self.sendmail)), 1)

        set_ticket_status(ticket.name, "Open")
        set_ticket_status(ticket.name, "Closed")
        self.assertEqual(len(get_feedback_mails(self.sendmail)), 1)

    def test_a_resolved_ticket_is_not_asked_again_on_close(self):
        ticket = make_ticket(
            subject="Report wrong", raised_by="lina@customer-intake.example"
        )
        set_ticket_status(ticket.name, "Resolved")
        set_ticket_status(ticket.name, "Closed")
        self.assertEqual(len(get_feedback_mails(self.sendmail)), 1)

    def test_alerts_and_the_teams_own_tickets_are_never_asked(self):
        make_tasky_user(*AGENT)
        set_ticket_status(make_mail_ticket(FIRING, GRAFANA).name, "Closed")
        set_ticket_status(
            make_ticket(subject="Internal", raised_by=AGENT[0]).name, "Closed"
        )
        self.assertEqual(get_feedback_mails(self.sendmail), [])

    def test_close_path_can_be_switched_off(self):
        set_intake_settings(feedback_on_close=0)
        ticket = make_ticket(
            subject="Report wrong", raised_by="lina@customer-intake.example"
        )
        set_ticket_status(ticket.name, "Closed")
        self.assertEqual(get_feedback_mails(self.sendmail), [])
