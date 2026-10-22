import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.tasky import api as tasky
from helpdesk.test_utils import (
    call_as_user,
    hold_commits,
    log_hours,
    make_project,
    make_sales_employee,
    make_task,
    make_tasky_user,
    run_as_user,
)

LEAD = ("lead.days@timesheet-days.example", "Meera Krishnan")
DEV = ("dev.days@timesheet-days.example", "Arjun Pillai")
OUTSIDER = ("outsider.days@timesheet-days.example", "Sneha Iyer")
SALES = ("sales.days@timesheet-days.example", "Rahul Nair")

MONDAY, TUESDAY = "2026-03-02", "2026-03-03"
DAYS = "helpdesk.tasky.api.get_timesheet_days"


class TestTimesheetDays(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        for user in (LEAD, DEV, OUTSIDER):
            make_tasky_user(*user)
        make_sales_employee(*SALES)
        self.project = make_project(
            "Timesheet Days - Payroll rollout",
            members=[(LEAD[0], "Developer"), (DEV[0], "Developer")],
        ).name
        frappe.db.set_value("Project", self.project, "project_lead", LEAD[0])
        self.other = make_project(
            "Timesheet Days - Warehouse app",
            members=[(DEV[0], "Developer"), (OUTSIDER[0], "Developer")],
        ).name

    def days(self, user, from_date=MONDAY, to_date=TUESDAY, **filters):
        return call_as_user(
            user[0], DAYS, from_date=from_date, to_date=to_date, **filters
        )

    def test_groups_by_person_day_and_task_with_plain_notes(self):
        task = make_task(self.project, "Import opening balances").name
        log_hours(
            DEV[0],
            self.project,
            2,
            MONDAY,
            task=task,
            notes="<p>Imported <b>ledgers</b> &amp; balances</p>",
        )
        log_hours(DEV[0], self.project, 1, MONDAY, "15:00:00", task=task, notes="Done")
        log_hours(DEV[0], self.project, 1.5, MONDAY, "17:00:00")
        log_hours(DEV[0], self.other, 3, TUESDAY, notes="Barcode labels")

        result = self.days(DEV)

        self.assertFalse(result["too_many"])
        self.assertEqual(result["hours"], 7.5)
        [person] = result["people"]
        self.assertEqual(
            (person["user"], person["full_name"], person["hours"]),
            (DEV[0], DEV[1], 7.5),
        )
        monday, tuesday = person["days"]
        self.assertEqual((monday["date"], monday["hours"]), (MONDAY, 4.5))
        self.assertEqual((tuesday["date"], tuesday["hours"]), (TUESDAY, 3))
        on_task, on_project = monday["entries"]
        self.assertEqual(on_task["task"], task)
        self.assertEqual(on_task["task_subject"], "Import opening balances")
        self.assertEqual(on_task["project_name"], "Timesheet Days - Payroll rollout")
        self.assertEqual(on_task["hours"], 3)
        self.assertEqual(on_task["notes"], ["Imported ledgers & balances", "Done"])
        self.assertEqual((on_project["task"], on_project["hours"]), (None, 1.5))
        self.assertEqual(on_project["notes"], [])

    def test_agents_see_their_own_and_leads_their_projects(self):
        log_hours(DEV[0], self.project, 2, MONDAY)
        log_hours(LEAD[0], self.project, 1, MONDAY)
        log_hours(OUTSIDER[0], self.other, 4, MONDAY)

        def people(user, **filters):
            return {p["user"]: p["hours"] for p in self.days(user, **filters)["people"]}

        self.assertEqual(people(DEV), {DEV[0]: 2})
        self.assertEqual(people(LEAD), {LEAD[0]: 1})
        # the lead's team: everyone on the projects they lead, not other projects
        self.assertEqual(people(LEAD, team=1), {DEV[0]: 2, LEAD[0]: 1})
        self.assertEqual(people(LEAD, team=1, agent=DEV[0]), {DEV[0]: 2})
        with self.assertRaises(frappe.PermissionError):
            self.days(DEV, team=1)

    def test_lead_can_open_the_timesheets_on_a_led_project(self):
        sheet = log_hours(DEV[0], self.project, 2, MONDAY)
        other = log_hours(OUTSIDER[0], self.other, 4, MONDAY)

        self.assertTrue(frappe.has_permission("Timesheet", "read", sheet, user=LEAD[0]))
        self.assertFalse(
            frappe.has_permission("Timesheet", "read", other, user=LEAD[0])
        )

    def test_project_filter_applies_to_days_summary_list_and_csv(self):
        on_project = log_hours(DEV[0], self.project, 2, MONDAY)
        log_hours(DEV[0], self.other, 3, MONDAY)

        days = self.days(DEV, project=self.project)
        self.assertEqual(days["hours"], 2)
        summary = run_as_user(
            DEV[0],
            lambda: tasky.get_timesheet_summary(
                from_date=MONDAY, to_date=TUESDAY, project=self.project
            ),
        )
        self.assertEqual(summary["hours"], 2)
        sheets = run_as_user(
            DEV[0],
            lambda: tasky.get_my_timesheets(
                from_date=MONDAY, to_date=TUESDAY, project=self.project
            ),
        )
        self.assertEqual([s["name"] for s in sheets], [on_project])

        frappe.response.clear()
        run_as_user(
            DEV[0],
            lambda: tasky.export_timesheets_csv(
                from_date=MONDAY, to_date=TUESDAY, project=self.project
            ),
        )
        rows = frappe.response.filecontent.strip().splitlines()[1:]
        self.assertEqual(len(rows), 1)
        self.assertIn("Payroll rollout", rows[0])

    def test_sales_employee_sees_only_their_own(self):
        log_hours(SALES[0], None, 1, MONDAY, notes="Client visit")
        log_hours(DEV[0], self.project, 2, MONDAY)

        people = self.days(SALES)["people"]
        self.assertEqual([p["user"] for p in people], [SALES[0]])
        with self.assertRaises(frappe.PermissionError):
            self.days(SALES, team=1)

    def test_cancelled_timesheets_do_not_count(self):
        log_hours(DEV[0], self.project, 2, MONDAY)
        cancelled = frappe.get_doc(
            "Timesheet", log_hours(DEV[0], self.project, 5, MONDAY)
        )
        cancelled.submit()
        cancelled.cancel()

        self.assertEqual(self.days(DEV)["hours"], 2)
        summary = run_as_user(
            DEV[0],
            lambda: tasky.get_timesheet_summary(from_date=MONDAY, to_date=MONDAY),
        )
        self.assertEqual(summary["hours"], 2)

    def test_only_logs_in_the_dates_and_the_range_is_bounded(self):
        log_hours(DEV[0], self.project, 2, MONDAY)
        log_hours(DEV[0], self.project, 3, "2026-03-04")

        self.assertEqual(self.days(DEV, to_date=MONDAY)["hours"], 2)
        self.assertEqual(
            self.days(DEV, from_date="2026-03-05", to_date="2026-03-06")["people"], []
        )
        # 62 days is the most at a time
        self.assertEqual(
            self.days(DEV, from_date="2026-01-01", to_date="2026-03-03")["hours"], 2
        )
        with self.assertRaises(frappe.ValidationError):
            self.days(DEV, from_date="2026-01-01", to_date="2026-03-04")
        with self.assertRaises(frappe.ValidationError):
            self.days(DEV, from_date=TUESDAY, to_date=MONDAY)

    def test_too_many_logs_asks_for_fewer_days(self):
        log_hours(DEV[0], self.project, 1, MONDAY)
        log_hours(DEV[0], self.project, 1, TUESDAY)

        tasky.TIMESHEET_DAYS_MAX_LOGS, limit = 1, tasky.TIMESHEET_DAYS_MAX_LOGS
        self.addCleanup(setattr, tasky, "TIMESHEET_DAYS_MAX_LOGS", limit)

        result = self.days(DEV)
        self.assertTrue(result["too_many"])
        self.assertEqual(result["people"], [])
