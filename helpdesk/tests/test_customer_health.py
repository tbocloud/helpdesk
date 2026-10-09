from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, get_first_day, now_datetime, nowdate

from helpdesk import customer_health as health
from helpdesk.api import directory, home
from helpdesk.api.customer_health import get_customer_health
from helpdesk.test_utils import (
    create_contact,
    create_customer,
    hold_commits,
    make_customer_project,
    make_customer_ticket,
    make_portal_contact,
    make_signoff,
    make_support_connection,
    make_support_contract,
    make_task,
    make_tasky_user,
    make_timesheet,
    run_as_user,
)

AGENT = ("agent@health-tests.example", "Nisha Varghese")
PORTAL_USER = "buyer@health-tests.example"
SICK = "Health Sick Traders"
FINE = "Health Fine Traders"
QUIET = "Health Quiet Traders"


def states(result: dict) -> dict[str, str]:
    return {s["key"]: s["state"] for s in result["signals"]}


class TestHealthRules(FrappeTestCase):
    """Each signal's rule and how the signals add up, without the database."""

    def test_new_tickets_against_the_month_before(self):
        self.assertEqual(health.judge_tickets(0, 0)["state"], health.SKIPPED)
        self.assertEqual(health.judge_tickets(4, 0)["state"], health.OK)
        self.assertEqual(health.judge_tickets(5, 4)["state"], health.OK)
        self.assertEqual(health.judge_tickets(6, 4)["state"], health.WATCH)
        self.assertEqual(health.judge_tickets(10, 6)["state"], health.WATCH)
        self.assertEqual(health.judge_tickets(10, 5)["state"], health.AT_RISK)

    def test_sla_breaches_and_tickets_waiting_on_us(self):
        self.assertEqual(health.judge_sla(0, 0)["state"], health.SKIPPED)
        self.assertEqual(health.judge_sla(0, 4)["state"], health.OK)
        self.assertEqual(health.judge_sla(1, 4)["state"], health.WATCH)
        self.assertEqual(health.judge_sla(3, 4)["state"], health.AT_RISK)
        self.assertEqual(health.judge_waiting(0, 0)["state"], health.SKIPPED)
        self.assertEqual(health.judge_waiting(0, 2)["state"], health.OK)
        self.assertEqual(health.judge_waiting(2, 2)["state"], health.WATCH)
        self.assertEqual(health.judge_waiting(3, 5)["state"], health.AT_RISK)

    def test_rating(self):
        self.assertEqual(health.judge_rating()["state"], health.SKIPPED)
        self.assertEqual(health.judge_rating(3, 4.2)["state"], health.OK)
        self.assertEqual(health.judge_rating(3, 3.5)["state"], health.WATCH)
        self.assertEqual(health.judge_rating(3, 2.8)["state"], health.AT_RISK)

    def test_project_work(self):
        self.assertEqual(health.judge_work()["state"], health.SKIPPED)
        self.assertEqual(health.judge_work(open_tasks=5)["state"], health.OK)
        self.assertEqual(
            health.judge_work(open_tasks=5, key_at_risk=1)["state"], health.WATCH
        )
        self.assertEqual(
            health.judge_work(open_tasks=5, overdue=2)["state"], health.WATCH
        )
        self.assertEqual(
            health.judge_work(open_tasks=5, overdue=3)["state"], health.AT_RISK
        )
        self.assertEqual(
            health.judge_work(open_tasks=5, overdue=1, overdue_key=1)["state"],
            health.AT_RISK,
        )

    def test_support_hours_burning_fast_or_used_up(self):
        period = {"percent": 60, "elapsed": 50, "remaining": 4}
        self.assertEqual(health.judge_contract(None)["state"], health.SKIPPED)
        self.assertEqual(health.judge_contract(period)["state"], health.OK)
        self.assertEqual(
            health.judge_contract({**period, "elapsed": 30})["state"], health.WATCH
        )
        # early in the period a little use isn't burning fast
        self.assertEqual(
            health.judge_contract({**period, "percent": 40, "elapsed": 5})["state"],
            health.OK,
        )
        self.assertEqual(
            health.judge_contract({**period, "percent": 100, "remaining": 0})["state"],
            health.AT_RISK,
        )

    def test_signoffs_and_erp_connection(self):
        self.assertEqual(health.judge_signoff()["state"], health.SKIPPED)
        self.assertEqual(health.judge_signoff(in_progress=2)["state"], health.OK)
        self.assertEqual(
            health.judge_signoff(in_progress=2, needs_clarification=1)["state"],
            health.WATCH,
        )
        self.assertEqual(
            health.judge_signoff(in_progress=2, escalated=1)["state"], health.AT_RISK
        )
        self.assertEqual(health.judge_erp(None)["state"], health.SKIPPED)
        self.assertEqual(health.judge_erp("Connected")["state"], health.OK)
        self.assertEqual(health.judge_erp("Disconnected")["state"], health.WATCH)
        self.assertEqual(health.judge_erp("Error")["state"], health.AT_RISK)

    def test_status_from_points(self):
        # one light signal on watch isn't enough
        light = health.combine([health.judge_tickets(5, 0)])
        self.assertEqual((light["status"], light["points"]), (health.HEALTHY, 1))
        watch = health.combine([health.judge_erp("Error")])
        self.assertEqual((watch["status"], watch["points"]), (health.WATCH, 2))
        at_risk = health.combine([health.judge_sla(3, 3)])
        self.assertEqual((at_risk["status"], at_risk["points"]), (health.AT_RISK, 6))
        two = health.combine([health.judge_rating(2, 2.0), health.judge_waiting(1, 1)])
        self.assertEqual((two["status"], two["points"]), (health.AT_RISK, 6))

    def test_skipped_signals_never_count(self):
        result = health.combine(
            [
                health.judge_sla(0, 0),
                health.judge_rating(),
                health.judge_contract(None),
                health.judge_erp("Connected"),
            ]
        )
        self.assertEqual((result["status"], result["points"]), (health.HEALTHY, 0))
        nothing = health.combine([health.judge_sla(0, 0), health.judge_erp(None)])
        self.assertEqual(nothing["status"], health.NO_DATA)

    def test_reasons_worst_first(self):
        result = health.combine(
            [
                health.judge_erp("Disconnected"),
                health.judge_sla(3, 3),
                health.judge_rating(4, 4.5),
            ]
        )
        self.assertEqual(health.reasons(result), ["SLA breaches", "ERP connection"])
        order = sorted(
            [None, result, health.combine([health.judge_erp("Error")])],
            key=health.sort_key,
        )
        self.assertEqual(
            [o and o["status"] for o in order], [health.AT_RISK, health.WATCH, None]
        )


class TestCustomerHealth(FrappeTestCase):
    """The signals from real records, permissions and the cache."""

    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        mail = patch("frappe.sendmail")
        mail.start()
        self.addCleanup(mail.stop)
        make_tasky_user(*AGENT)
        for name in (SICK, FINE, QUIET):
            create_customer(name)
        health.clear_health_cache()
        self.addCleanup(health.clear_health_cache)

    def sick_tickets(self):
        recent = add_to_date(now_datetime(), days=-5)
        for i in range(3):
            make_customer_ticket(
                SICK,
                f"Late {i}",
                creation=recent,
                sla="Default",
                agreement_status="Failed",
                status_category="Open",
                last_customer_response=recent,
            )
        make_customer_ticket(
            SICK,
            "Rated badly",
            status_category="Resolved",
            resolution_date=now_datetime(),
            feedback_rating=0.4,
        )

    def test_signals_from_tickets(self):
        self.sick_tickets()
        make_customer_ticket(
            FINE, "On time", sla="Default", agreement_status="Fulfilled"
        )

        result = health.compute_all_health()
        sick = states(result[SICK])
        self.assertEqual(sick["sla"], health.AT_RISK)
        self.assertEqual(sick["waiting"], health.AT_RISK)
        self.assertEqual(sick["rating"], health.AT_RISK)
        self.assertEqual(result[SICK]["status"], health.AT_RISK)
        fine = states(result[FINE])
        self.assertEqual(fine["sla"], health.OK)
        self.assertEqual(fine["rating"], health.SKIPPED)
        self.assertEqual(result[FINE]["status"], health.HEALTHY)

    def test_customer_without_data_is_not_penalised(self):
        result = health.compute_all_health()[QUIET]
        self.assertEqual(result["status"], health.NO_DATA)
        self.assertEqual(result["points"], 0)
        self.assertEqual(set(states(result).values()), {health.SKIPPED})

    def test_overdue_key_task_in_an_open_project(self):
        project = make_customer_project(SICK, "Health - Sick rollout")
        make_task(project, "Go-live data import", add_days(nowdate(), -2), is_key=1)
        make_task(project, "Train the stores team", add_days(nowdate(), 10))
        work = health.compute_all_health()[SICK]["signals"]
        signal = next(s for s in work if s["key"] == "work")
        self.assertEqual(signal["state"], health.AT_RISK)
        self.assertEqual(signal["facts"]["overdue_key"], 1)
        self.assertEqual(signal["facts"]["open_tasks"], 2)

    def test_support_hours_used_up(self):
        project = make_customer_project(SICK, "Health - Sick support")
        make_support_contract(SICK, get_first_day(nowdate()), add_days(nowdate(), 300))
        make_timesheet(project, 12, now_datetime())
        signal = next(
            s
            for s in health.compute_all_health()[SICK]["signals"]
            if s["key"] == "contract"
        )
        self.assertEqual(signal["state"], health.AT_RISK)
        self.assertEqual(signal["facts"]["used"], 12)

    def test_escalated_signoff_and_failing_connection(self):
        project = make_customer_project(SICK, "Health - Sick training")
        contact = make_portal_contact(SICK, "accounts@health-sick.example")
        signoff = make_signoff(
            project,
            contact,
            None,
            items=[{"section": "Sales", "question": "I can raise an invoice."}],
        )
        frappe.db.set_value("HD Project Signoff", signoff.name, "status", "Sent")
        frappe.db.set_value(
            "HD Project Signoff Item", signoff.items[0].name, "response", "Escalated"
        )
        make_support_connection(SICK, connection_status="Error")

        result = health.compute_all_health()[SICK]
        self.assertEqual(states(result)["signoff"], health.AT_RISK)
        self.assertEqual(states(result)["erp"], health.AT_RISK)
        signoff_signal = next(s for s in result["signals"] if s["key"] == "signoff")
        self.assertEqual(signoff_signal["facts"]["projects"], [project])
        link = health.present(result, SICK)["signals"]
        self.assertEqual(
            next(s["link"] for s in link if s["key"] == "signoff"),
            {"kind": "signoff", "project": project},
        )

    def test_page_lists_every_signal_with_its_rule_and_link(self):
        self.sick_tickets()
        result = run_as_user(AGENT[0], lambda: get_customer_health(SICK))
        self.assertEqual(result["status"], health.AT_RISK)
        self.assertEqual([s["key"] for s in result["signals"]], list(health.WEIGHTS))
        sla = result["signals"][0]
        self.assertEqual(sla["label"], "SLA breaches")
        self.assertTrue(sla["value"].startswith("3 of "))
        self.assertTrue(sla["rule"])
        self.assertEqual(sla["link"]["kind"], "tickets")
        self.assertIn(["agreement_status", "=", "Failed"], sla["link"]["filters"])
        # skipped signals have nothing to link to
        erp = next(s for s in result["signals"] if s["key"] == "erp")
        self.assertIsNone(erp["link"])

    def test_only_agents_see_health(self):
        create_contact("Buyer", PORTAL_USER)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(PORTAL_USER, lambda: get_customer_health(SICK))

    def test_agents_see_health_only_for_customers_they_can_read(self):
        self.sick_tickets()
        make_support_connection(FINE, connection_status="Error")
        # only this test's customers, whatever else the test site holds
        ours = {
            name: result
            for name, result in health.compute_all_health().items()
            if name in (SICK, FINE, QUIET)
        }
        only_ours = patch("helpdesk.api.home.all_health", return_value=ours)
        only_ours.start()
        self.addCleanup(only_ours.stop)
        # narrow the agent's HD Customer access to SICK only
        with (
            patch(
                "helpdesk.helpdesk.doctype.hd_customer.hd_customer.is_agent",
                return_value=False,
            ),
            patch(
                "helpdesk.helpdesk.doctype.hd_customer.hd_customer.get_customers",
                side_effect=lambda user, get_roles=False: (
                    [{"name": SICK}] if get_roles else [SICK]
                ),
            ),
        ):
            summary = run_as_user(AGENT[0], home._customer_health)
            listed = run_as_user(
                AGENT[0],
                lambda: directory.get_customer_directory(
                    search="Health ", health="attention"
                ),
            )
            with self.assertRaises(frappe.PermissionError):
                run_as_user(AGENT[0], lambda: get_customer_health(FINE))
        self.assertEqual([i["customer"] for i in summary["items"]], [SICK])
        self.assertEqual([r.name for r in listed["rows"]], [SICK])

        # without the narrowing both show, worst first
        summary = run_as_user(AGENT[0], home._customer_health)
        self.assertEqual([i["customer"] for i in summary["items"]], [SICK, FINE])
        self.assertEqual((summary["count"], summary["at_risk"]), (2, 1))

    def test_directory_filters_and_sorts_by_health(self):
        self.sick_tickets()
        make_support_connection(FINE, connection_status="Error")

        def listed(**kwargs):
            result = run_as_user(
                AGENT[0],
                lambda: directory.get_customer_directory(search="Health ", **kwargs),
            )
            return [r.name for r in result["rows"]], result["total"]

        self.assertEqual(listed(health="at_risk"), ([SICK], 1))
        self.assertEqual(listed(health="watch"), ([FINE], 1))
        # a filter alone keeps the chosen sort (name); sort=health puts the worst first
        self.assertEqual(listed(health="attention"), ([FINE, SICK], 2))
        self.assertEqual(listed(health="attention", sort="health"), ([SICK, FINE], 2))
        self.assertEqual(listed(sort="health"), ([SICK, FINE, QUIET], 3))
        # name order (the default) is unchanged, with each row's health
        rows = run_as_user(
            AGENT[0], lambda: directory.get_customer_directory(search="Health ")
        )["rows"]
        self.assertEqual([r.name for r in rows], [FINE, QUIET, SICK])
        self.assertEqual(rows[2]["health"]["status"], health.AT_RISK)
        self.assertIn("SLA breaches", rows[2]["health"]["reasons"])
        with self.assertRaises(frappe.ValidationError):
            directory.get_customer_directory(health="sick")

    def test_cache_is_reused_and_cleared_on_change(self):
        with patch.object(
            health, "compute_all_health", wraps=health.compute_all_health
        ) as compute:
            first = health.all_health()
            self.assertEqual(health.all_health(), first)
        self.assertEqual(compute.call_count, 1)
        self.assertIsNotNone(frappe.cache.get_value(health.CACHE_KEY, expires=True))

        make_support_connection(SICK, connection_status="Error")
        self.assertIsNone(frappe.cache.get_value(health.CACHE_KEY, expires=True))
        self.assertEqual(states(health.all_health()[SICK])["erp"], health.AT_RISK)

        create_customer("Health New Traders")
        self.assertIsNone(frappe.cache.get_value(health.CACHE_KEY, expires=True))
        self.assertIn("Health New Traders", health.all_health())
