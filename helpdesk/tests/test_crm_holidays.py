from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import crm as crm_api
from helpdesk.api.capacity import _person_row
from helpdesk.integrations.crm import holidays as crm_holidays
from helpdesk.integrations.crm.client import CRMError, CRMPermissionError
from helpdesk.recurrence import working_day_checker
from helpdesk.test_utils import (
    FAKE_COMPANY,
    FAKE_HOLIDAY_LIST,
    FakeCRM,
    create_agent,
    erp_holiday,
    erp_leave_application,
    hold_commits,
    make_hd_leave,
)
from helpdesk.work_calendar import (
    company_holidays,
    leave_fractions,
    leave_today,
    next_holiday,
)

FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
HUB_LIST = "CRM Holiday Sync Test"
SETTINGS = "HD CRM Settings"
# the sync's today: the window is 1 Jan 2026 to 31 Dec 2027
TODAY = "2026-10-10"
DIWALI = date(2026, 10, 20)
CHRISTMAS = date(2026, 12, 25)
INDEPENDENCE_DAY = date(2026, 8, 15)
THIRD_SATURDAY = date(2026, 10, 17)
ANU = "anu.leave@crm-holidays.example"
BIJU = "biju.leave@crm-holidays.example"


class CRMHolidayCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        frappe.db.set_single_value(
            "HD Work Settings", {"weekly_off": "Sunday", "saturdays_off": "2nd and 4th"}
        )
        frappe.clear_document_cache("HD Work Settings", "HD Work Settings")
        frappe.db.set_single_value(
            SETTINGS,
            {
                "enabled": 1,
                "site_url": "https://crm.example",
                "api_key": "test-key",
                "sync_holidays": 1,
                "sync_leave": 1,
                "holiday_lists": "",
                "invoice_company": FAKE_COMPANY,
                "holiday_sync_error": "",
            },
        )
        frappe.clear_document_cache(SETTINGS, SETTINGS)
        self.hub_list = self.make_hub_list()
        # the default SLA reads this list, so the SLA clock and follow-ups use it
        self.sla = frappe.db.get_value(
            "HD Service Level Agreement", {"default_sla": 1, "enabled": 1}
        )
        self.assertTrue(self.sla, "the test site needs a default SLA")
        frappe.db.set_value(
            "HD Service Level Agreement", self.sla, "holiday_list", HUB_LIST
        )
        targets = patch.object(
            crm_holidays, "sla_holiday_lists", return_value=[HUB_LIST]
        )
        targets.start()
        self.addCleanup(targets.stop)
        # saving a holiday list re-saves every open ticket on its SLAs; not under test here
        recalculate = patch(
            "helpdesk.helpdesk.doctype.hd_service_holiday_list."
            "hd_service_holiday_list.HDServiceHolidayList.recalculate_sla"
        )
        recalculate.start()
        self.addCleanup(recalculate.stop)
        clock = patch.object(crm_holidays, "nowdate", return_value=TODAY)
        clock.start()
        self.addCleanup(clock.stop)

        self.crm = FakeCRM()
        self.crm.holiday_rows[FAKE_HOLIDAY_LIST] = [
            erp_holiday(DIWALI, "Diwali"),
            erp_holiday(CHRISTMAS, "<p>Christmas</p>"),
            erp_holiday(INDEPENDENCE_DAY, "Independence Day"),
            # Sunday and the 4th Saturday: Work settings already has them off
            erp_holiday(date(2026, 10, 18), "Sunday", 1),
            erp_holiday(date(2026, 10, 24), "Saturday", 1),
            # the 3rd Saturday is a working day in the hub
            erp_holiday(THIRD_SATURDAY, "Saturday", 1),
            # outside this year and next
            erp_holiday(date(2025, 12, 25), "Christmas 2025"),
        ]

    def make_hub_list(self):
        frappe.delete_doc(
            "HD Service Holiday List", HUB_LIST, force=True, ignore_missing=True
        )
        return frappe.get_doc(
            {
                "doctype": "HD Service Holiday List",
                "holiday_list_name": HUB_LIST,
                "from_date": "2026-01-01",
                "to_date": "2026-12-31",
                "holidays": [
                    # entered by people in the hub
                    {
                        "holiday_date": str(INDEPENDENCE_DAY),
                        "description": "Independence Day (office)",
                    },
                    {"holiday_date": "2026-11-14", "description": "Office day out"},
                ],
            }
        ).insert(ignore_permissions=True)

    def sync(self):
        with patch(FROM_SETTINGS, return_value=self.crm):
            return crm_holidays.sync_holidays_and_leave()

    def rows(self) -> dict:
        """{date: (description, weekly_off, synced)} of the hub list."""
        doc = frappe.get_doc("HD Service Holiday List", HUB_LIST)
        return {
            row.holiday_date: (row.description, row.weekly_off, row.synced_from_crm)
            for row in doc.holidays
        }


class TestHolidaySync(CRMHolidayCase):
    def test_upserts_by_date_and_keeps_manual_holidays(self):
        result = self.sync()

        self.assertTrue(result["ok"], result["problems"])
        rows = self.rows()
        self.assertEqual(rows[DIWALI], ("Diwali", 0, 1))
        self.assertEqual(rows[CHRISTMAS], ("Christmas", 0, 1))
        # people's holidays stay as they are; the same date isn't added twice
        self.assertEqual(rows[INDEPENDENCE_DAY], ("Independence Day (office)", 0, 0))
        self.assertEqual(rows[date(2026, 11, 14)], ("Office day out", 0, 0))
        self.assertNotIn(date(2025, 12, 25), rows)
        self.assertEqual(
            frappe.db.get_single_value(SETTINGS, "holidays_synced_count"), 4
        )
        self.assertTrue(frappe.db.get_single_value(SETTINGS, "holidays_synced_on"))

        # a second run with nothing new changes nothing
        modified = frappe.db.get_value("HD Service Holiday List", HUB_LIST, "modified")
        self.sync()
        self.assertEqual(
            frappe.db.get_value("HD Service Holiday List", HUB_LIST, "modified"),
            modified,
        )

    def test_changed_and_removed_upstream_dates_follow(self):
        self.sync()
        self.crm.holiday_rows[FAKE_HOLIDAY_LIST] = [
            erp_holiday(DIWALI, "Deepavali"),
            erp_holiday(date(2027, 1, 26), "Republic Day"),
        ]

        self.sync()

        rows = self.rows()
        self.assertEqual(rows[DIWALI][0], "Deepavali")
        self.assertNotIn(CHRISTMAS, rows)
        self.assertNotIn(THIRD_SATURDAY, rows)
        # next year's holiday widens the list
        self.assertIn(date(2027, 1, 26), rows)
        self.assertIn(INDEPENDENCE_DAY, rows)
        self.assertIn(date(2026, 11, 14), rows)

    def test_a_picked_list_replaces_the_company_default(self):
        self.crm.holiday_rows["TBO Kerala 2026"] = [
            erp_holiday(date(2026, 9, 4), "Onam")
        ]
        frappe.db.set_single_value(SETTINGS, "holiday_lists", "TBO Kerala 2026")

        self.sync()

        rows = self.rows()
        self.assertIn(date(2026, 9, 4), rows)
        self.assertNotIn(DIWALI, rows)

    def test_synced_holidays_are_days_off_for_sla_and_follow_ups(self):
        self.sync()

        self.assertIn(DIWALI, company_holidays("2026-10-01", "2026-10-31"))
        is_working = working_day_checker(date(2026, 10, 1), date(2026, 10, 31))
        self.assertFalse(is_working(DIWALI))
        self.assertTrue(is_working(date(2026, 10, 21)))
        sla = frappe.get_doc("HD Service Level Agreement", self.sla)
        self.assertIn(DIWALI, sla.get_holidays())
        self.assertEqual(next_holiday("2026-10-12")["description"], "Diwali")


class TestWeeklyOffs(CRMHolidayCase):
    def test_weekly_offs_the_hub_rule_covers_are_not_stored(self):
        result = self.sync()

        rows = self.rows()
        self.assertNotIn(date(2026, 10, 18), rows)
        self.assertNotIn(date(2026, 10, 24), rows)
        self.assertEqual(rows[THIRD_SATURDAY], ("Saturday", 1, 1))
        self.assertEqual((result["covered"], result["uncovered"]), (2, 1))
        self.assertIn(
            "aren't in Work settings",
            frappe.db.get_single_value(SETTINGS, "holiday_sync_result"),
        )

    def test_matching_weekly_offs_say_so(self):
        self.crm.holiday_rows[FAKE_HOLIDAY_LIST] = [
            erp_holiday(date(2026, 10, 18), "Sunday", 1),
            erp_holiday(date(2026, 10, 24), "Saturday", 1),
        ]

        self.sync()

        self.assertIn(
            "match Work settings",
            frappe.db.get_single_value(SETTINGS, "holiday_sync_result"),
        )

    def test_describe_weekly_offs(self):
        sundays = [date(2026, 10, d) for d in (4, 11, 18, 25)]
        saturdays = [date(2026, 10, 10), date(2026, 10, 24)]
        self.assertEqual(
            crm_holidays.describe_weekly_offs(saturdays + sundays),
            "Sunday, 2nd and 4th Saturday",
        )


class TestLeaveSync(CRMHolidayCase):
    def setUp(self):
        super().setUp()
        create_agent(ANU, "Anu", "Varghese")
        create_agent(BIJU, "Biju", "Thomas")
        self.crm.employee_rows = [
            {"name": "HR-EMP-0001", "user_id": ANU.upper()},
            {
                "name": "HR-EMP-0002",
                "user_id": "biju@another-site.example",
                "company_email": BIJU,
            },
            {"name": "HR-EMP-0003", "company_email": "nobody@crm-holidays.example"},
        ]
        self.crm.leave_rows = [
            erp_leave_application(
                "HR-LAP-0001", "HR-EMP-0001", "2026-10-12", "2026-10-14"
            ),
            erp_leave_application(
                "HR-LAP-0002",
                "HR-EMP-0002",
                "2026-10-10",
                "2026-10-10",
                half_day=1,
                half_day_date="2026-10-10",
            ),
            erp_leave_application(
                "HR-LAP-0003", "HR-EMP-0003", "2026-10-12", "2026-10-12"
            ),
        ]

    def test_leave_is_matched_by_user_or_company_email(self):
        result = self.sync()

        self.assertEqual(frappe.db.get_value("HD Leave", "HR-LAP-0001", "user"), ANU)
        self.assertEqual(
            frappe.db.get_value("HD Leave", "HR-LAP-0002", ["user", "half_day"]),
            (BIJU, 1),
        )
        self.assertFalse(frappe.db.exists("HD Leave", "HR-LAP-0003"))
        self.assertEqual((result["leave"], result["unmatched"]), (2, 1))
        self.assertEqual(frappe.db.get_single_value(SETTINGS, "leave_synced_count"), 2)
        self.assertEqual(
            leave_today("2026-10-13")[ANU], {"to_date": "2026-10-14", "half_day": False}
        )

    def test_cancelled_leave_is_removed(self):
        self.sync()
        self.crm.leave_rows = self.crm.leave_rows[1:]

        self.sync()

        self.assertFalse(frappe.db.exists("HD Leave", "HR-LAP-0001"))
        self.assertTrue(frappe.db.exists("HD Leave", "HR-LAP-0002"))

    def test_without_leave_access_holidays_still_sync(self):
        self.crm.leave_error = CRMPermissionError("403")

        with patch.object(frappe, "log_error") as log_error, patch(
            FROM_SETTINGS, return_value=self.crm
        ):
            crm_holidays.sync_holidays_job()

        self.assertIn(DIWALI, self.rows())
        problem = frappe.db.get_single_value(SETTINGS, "holiday_sync_error")
        self.assertIn(
            "Leave sync needs read access to Leave Application and Employee", problem
        )
        # a setting to fix, shown in Settings → CRM, not an error for the error log
        log_error.assert_not_called()

    def test_a_timeout_is_logged_not_raised(self):
        self.crm.holidays_error = CRMError("Couldn't reach the CRM site: timed out")

        with patch.object(frappe, "log_error") as log_error, patch(
            FROM_SETTINGS, return_value=self.crm
        ):
            crm_holidays.sync_holidays_job()

        log_error.assert_called_once()
        self.assertIn(
            "timed out", frappe.db.get_single_value(SETTINGS, "holiday_sync_error")
        )
        # leave doesn't depend on the holidays
        self.assertTrue(frappe.db.exists("HD Leave", "HR-LAP-0001"))

    def test_sync_now_is_for_admins(self):
        frappe.set_user(ANU)
        with self.assertRaises(frappe.PermissionError):
            crm_api.sync_holidays_now()
        frappe.set_user("Administrator")

        with patch(FROM_SETTINGS, return_value=self.crm):
            result = crm_api.sync_holidays_now()
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(result["holidays"], 4)


class TestLeaveInCapacity(FrappeTestCase):
    def test_leave_takes_hours_off_what_is_available(self):
        hold_commits(self)
        create_agent(ANU, "Anu", "Varghese")
        make_hd_leave(ANU, "2026-10-12", "2026-10-12")
        monday, tuesday = date(2026, 10, 12), date(2026, 10, 13)
        leave = leave_fractions([ANU], monday, tuesday)
        self.assertEqual(leave, {ANU: {monday: 1}})

        row = _person_row(
            ANU,
            "Anu Varghese",
            {tuesday: 3},
            [monday, tuesday],
            monday,
            tuesday,
            6,
            leave[ANU],
        )

        self.assertEqual(row["available"], 6)
        self.assertEqual(row["leave_days"], 1)
        self.assertEqual(row["days"][0]["available"], 0)
        self.assertEqual(row["utilisation"], 50)
