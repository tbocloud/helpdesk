import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, get_first_day, getdate, nowdate

from helpdesk.api import support_contracts as api
from helpdesk.support_contracts import (
    contract_periods,
    daily_billable_hours,
    send_support_hours_alerts,
    usage_by_period,
)
from helpdesk.test_utils import (
    create_customer,
    get_reminder_messages,
    hold_commits,
    make_project,
    make_support_contract,
    make_task,
    make_tasky_user,
    make_ticket,
    make_timesheet,
    run_as_user,
)

MANAGER = ("manager@support-hours.example", "Meera Nair")
ACCOUNT_MANAGER = ("accounts@support-hours.example", "Joseph Mathew")
AGENT = ("agent@support-hours.example", "Anil Kumar")
OUTSIDER = ("outsider@support-hours.example", "Sana Iqbal")
CUSTOMER = "Hours Traders LLC"
OTHER_CUSTOMER = "Other Hours Ltd"


def contract_row(**values):
    return frappe._dict(
        {
            "start_date": "2026-01-15",
            "end_date": "2027-01-14",
            "billing_period": "Monthly",
            "hours_per_period": 10,
            "rollover_unused": 0,
            "alert_threshold": 80,
            **values,
        }
    )


class TestSupportPeriods(FrappeTestCase):
    def test_monthly_periods_follow_the_start_date(self):
        periods = contract_periods("2026-01-15", "2026-04-30", "Monthly")
        self.assertEqual(
            [(str(a), str(b)) for a, b in periods],
            [
                ("2026-01-15", "2026-02-14"),
                ("2026-02-15", "2026-03-14"),
                ("2026-03-15", "2026-04-14"),
                # the last period ends with the contract
                ("2026-04-15", "2026-04-30"),
            ],
        )

    def test_quarterly_yearly_and_block_periods(self):
        quarterly = contract_periods("2026-01-01", "2026-12-31", "Quarterly")
        self.assertEqual(
            [str(a) for a, _b in quarterly],
            ["2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01"],
        )
        self.assertEqual(str(quarterly[-1][1]), "2026-12-31")
        yearly = contract_periods("2026-04-01", "2028-03-31", "Yearly")
        self.assertEqual(
            [(str(a), str(b)) for a, b in yearly],
            [("2026-04-01", "2027-03-31"), ("2027-04-01", "2028-03-31")],
        )
        block = contract_periods("2026-02-10", "2026-08-09", "One-off block")
        self.assertEqual(
            [(str(a), str(b)) for a, b in block], [("2026-02-10", "2026-08-09")]
        )

    def test_rollover_carries_unused_hours_forward(self):
        daily = {
            getdate("2026-01-20"): 4,
            getdate("2026-02-20"): 12,
            getdate("2026-03-20"): 3,
        }
        periods = usage_by_period(
            contract_row(rollover_unused=1), daily, today="2026-03-20"
        )
        self.assertEqual([p["carried_in"] for p in periods], [0, 6, 4])
        self.assertEqual([p["allowance"] for p in periods], [10, 16, 14])
        self.assertEqual(periods[-1]["remaining"], 11)
        self.assertTrue(periods[-1]["is_current"])

        without = usage_by_period(contract_row(), daily, today="2026-03-20")
        self.assertEqual([p["allowance"] for p in without], [10, 10, 10])
        # 12 of 10 hours: over, shown as a negative remainder
        self.assertEqual(without[1]["remaining"], -2)
        self.assertEqual(without[1]["stage"], "over")

    def test_stage_follows_the_alert_threshold(self):
        daily = {getdate("2026-01-20"): 8}
        period = usage_by_period(contract_row(), daily, today="2026-01-20")[0]
        self.assertEqual((period["percent"], period["stage"]), (80.0, "warning"))
        period = usage_by_period(
            contract_row(alert_threshold=90), daily, today="2026-01-20"
        )[0]
        self.assertEqual(period["stage"], "ok")

    def test_periods_not_yet_started_are_left_out(self):
        periods = usage_by_period(contract_row(), {}, today="2026-02-20")
        self.assertEqual(len(periods), 2)


class TestSupportContracts(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*MANAGER, roles=("Agent Manager",))
        make_tasky_user(*ACCOUNT_MANAGER)
        make_tasky_user(*AGENT)
        make_tasky_user(*OUTSIDER)
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        self.project = make_project(
            f"{CUSTOMER} - Support", members=[(AGENT[0], "Developer")]
        ).name
        frappe.db.set_value("Project", self.project, "customer", CUSTOMER)
        self.today = getdate(nowdate())
        self.at = f"{self.today} 01:00:00"
        self.contract = make_support_contract(
            CUSTOMER,
            get_first_day(self.today),
            add_days(add_months(get_first_day(self.today), 12), -1),
            account_manager=ACCOUNT_MANAGER[0],
        )

    def used_now(self) -> float:
        hours = daily_billable_hours([CUSTOMER], self.today, self.today)
        return hours.get(CUSTOMER, {}).get(self.today, 0)

    def alerts(self, user=MANAGER[0]) -> list[str]:
        return get_reminder_messages(user, self.contract.name)

    def test_only_billable_time_for_the_customer_counts(self):
        task = make_task(self.project, "Fix the payroll report").name
        make_timesheet(self.project, 3, self.at, task)
        make_timesheet(self.project, 2, self.at, billable=0)
        cancelled = make_timesheet(self.project, 5, self.at)
        cancelled.submit()
        cancelled.cancel()
        # a task raised from the customer's ticket, outside any project
        ticket = make_ticket(subject="Invoice print is blank").name
        frappe.db.set_value("HD Ticket", ticket, "customer", CUSTOMER)
        ticket_task = make_task(None, "Check the print format", hd_ticket=ticket).name
        make_timesheet(None, 1.5, self.at, ticket_task)
        # another customer's project
        other = make_project(f"{OTHER_CUSTOMER} - Rollout").name
        frappe.db.set_value("Project", other, "customer", OTHER_CUSTOMER)
        make_timesheet(other, 7, self.at)

        self.assertEqual(self.used_now(), 4.5)

        result = run_as_user(
            MANAGER[0], lambda: api.get_customer_support_hours(CUSTOMER)
        )
        self.assertEqual(result["contract"].name, self.contract.name)
        self.assertEqual(result["period"]["used"], 4.5)
        self.assertEqual(result["period"]["remaining"], 5.5)
        breakdown = result["breakdown"]
        self.assertEqual(
            {(p["name"], p["hours"]) for p in breakdown["projects"]},
            {(self.project, 3.0), (None, 1.5)},
        )
        self.assertEqual(
            [(t["name"], t["hours"]) for t in breakdown["tickets"]],
            [(str(ticket), 1.5)],
        )

    def test_threshold_alert_is_sent_once_per_period(self):
        make_timesheet(self.project, 8, self.at)

        send_support_hours_alerts()
        send_support_hours_alerts()

        for user in (MANAGER[0], ACCOUNT_MANAGER[0]):
            messages = self.alerts(user)
            self.assertEqual(len(messages), 1, user)
            self.assertIn("80%", messages[0])
        self.contract.reload()
        self.assertEqual(self.contract.alerted_stage, "Threshold")
        self.assertEqual(
            getdate(self.contract.alerted_period_start), get_first_day(self.today)
        )

    def test_overage_alert_follows_the_threshold_alert(self):
        make_timesheet(self.project, 8, self.at)
        send_support_hours_alerts()
        make_timesheet(self.project, 3, self.at)

        send_support_hours_alerts()
        send_support_hours_alerts()

        messages = self.alerts()
        self.assertEqual(len(messages), 2)
        self.assertTrue(any("used all its support hours" in m for m in messages))
        self.assertEqual(
            frappe.db.get_value(
                "HD Support Contract", self.contract.name, "alerted_stage"
            ),
            "Overage",
        )

    def test_no_alert_below_the_threshold(self):
        make_timesheet(self.project, 7.5, self.at)
        send_support_hours_alerts()
        self.assertEqual(self.alerts(), [])

    def test_ended_contracts_expire(self):
        self.contract.db_set("end_date", add_days(self.today, -1))
        send_support_hours_alerts()
        self.assertEqual(
            frappe.db.get_value("HD Support Contract", self.contract.name, "status"),
            "Expired",
        )

    def test_active_contracts_may_not_overlap(self):
        with self.assertRaises(frappe.ValidationError):
            make_support_contract(CUSTOMER, self.today, add_days(self.today, 30))
        # a renewal after the current one ends is fine
        renewal = make_support_contract(
            CUSTOMER,
            add_days(self.contract.end_date, 1),
            add_months(self.contract.end_date, 12),
        )
        self.assertEqual(renewal.status, "Active")

    def test_agents_on_the_customers_projects_see_usage_without_people(self):
        make_timesheet(self.project, 2, self.at)

        result = run_as_user(AGENT[0], lambda: api.get_customer_support_hours(CUSTOMER))

        self.assertFalse(result["can_manage"])
        self.assertEqual(result["period"]["used"], 2)
        self.assertIsNone(result["breakdown"]["people"])
        manager = run_as_user(
            MANAGER[0], lambda: api.get_customer_support_hours(CUSTOMER)
        )
        self.assertTrue(manager["can_manage"])
        self.assertEqual(manager["breakdown"]["people"][0]["hours"], 2)

    def test_other_agents_cant_see_or_manage_contracts(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_customer_support_hours(CUSTOMER))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(AGENT[0], api.get_support_hours)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                AGENT[0],
                lambda: frappe.get_doc(
                    {
                        "doctype": "HD Support Contract",
                        "contract_name": "Sneaky AMC",
                        "customer": OTHER_CUSTOMER,
                        "start_date": self.today,
                        "end_date": add_days(self.today, 30),
                        "hours_per_period": 5,
                    }
                ).insert(),
            )

    def test_support_hours_page_sorts_by_use(self):
        make_support_contract(
            OTHER_CUSTOMER,
            get_first_day(self.today),
            add_days(add_months(get_first_day(self.today), 1), -1),
        )
        other = make_project(f"{OTHER_CUSTOMER} - Rollout").name
        frappe.db.set_value("Project", other, "customer", OTHER_CUSTOMER)
        make_timesheet(other, 9, self.at)
        make_timesheet(self.project, 1, self.at)

        page = run_as_user(MANAGER[0], api.get_support_hours)
        mine = [r for r in page["rows"] if r["customer"] in (CUSTOMER, OTHER_CUSTOMER)]
        self.assertEqual([r["customer"] for r in mine], [OTHER_CUSTOMER, CUSTOMER])
        self.assertEqual(mine[0]["stage"], "warning")

        warning = run_as_user(
            MANAGER[0], lambda: api.get_support_hours(stage="warning")
        )
        self.assertIn(OTHER_CUSTOMER, [r["customer"] for r in warning["rows"]])
        self.assertNotIn(CUSTOMER, [r["customer"] for r in warning["rows"]])
