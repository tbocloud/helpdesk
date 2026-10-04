from datetime import date

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import work_calendar
from helpdesk.task_estimates import add_working_days
from helpdesk.test_utils import hold_commits

HOLIDAYS = "Saturday Rota Test"


class TestSaturdayRota(FrappeTestCase):
    """Monday to Saturday, with the 2nd and 4th Saturdays off (October 2026)."""

    def setUp(self):
        hold_commits(self)
        self.addCleanup(
            frappe.clear_document_cache, "HD Work Settings", "HD Work Settings"
        )
        frappe.db.set_single_value(
            "HD Work Settings", {"weekly_off": "Sunday", "saturdays_off": "2nd and 4th"}
        )
        frappe.clear_document_cache("HD Work Settings", "HD Work Settings")

    def test_second_and_fourth_saturdays_are_off(self):
        # Saturdays in October 2026: 3rd, 10th, 17th, 24th, 31st
        off = [
            d.day
            for d in work_calendar.saturdays_off_between("2026-10-01", "2026-10-31")
        ]
        self.assertEqual(off, [10, 24])
        self.assertTrue(work_calendar.is_saturday_off("2026-10-10"))
        self.assertFalse(work_calendar.is_saturday_off("2026-10-17"))
        self.assertFalse(work_calendar.is_saturday_off("2026-10-12"))  # a Monday

    def test_working_days_skip_the_saturdays_off(self):
        # Friday 9th + 1 working day: Saturday 10th is off, Sunday too, so Monday 12th
        self.assertEqual(add_working_days("2026-10-09", 2), date(2026, 10, 12))
        # Friday 16th + 1: Saturday 17th is a working day
        self.assertEqual(add_working_days("2026-10-16", 2), date(2026, 10, 17))

    def make_list(self):
        frappe.delete_doc(
            "HD Service Holiday List", HOLIDAYS, force=True, ignore_missing=True
        )
        return frappe.get_doc(
            {
                "doctype": "HD Service Holiday List",
                "holiday_list_name": HOLIDAYS,
                "from_date": "2026-10-01",
                "to_date": "2026-10-31",
                "holidays": [
                    {"holiday_date": "2026-10-02", "description": "Gandhi Jayanti"}
                ],
            }
        ).insert(ignore_permissions=True)

    def test_holiday_list_gets_the_saturdays_and_keeps_other_holidays(self):
        holidays = self.make_list()
        wanted = work_calendar.saturdays_off_between("2026-10-01", "2026-11-30")
        today = date(2026, 10, 1)

        self.assertTrue(work_calendar.sync_holiday_list(holidays.name, wanted, today))
        holidays.reload()
        dates = [str(h.holiday_date) for h in holidays.holidays]
        self.assertEqual(
            dates,
            ["2026-10-02", "2026-10-10", "2026-10-24", "2026-11-14", "2026-11-28"],
        )
        self.assertEqual(str(holidays.to_date), "2026-11-28")  # widened to fit
        self.assertIn("2nd Saturday off", holidays.holidays[1].description)

        # running again changes nothing
        self.assertFalse(work_calendar.sync_holiday_list(holidays.name, wanted, today))

        # a new rule drops the old future Saturdays but never the people's holidays
        new = work_calendar.saturdays_off_between(
            "2026-10-01", "2026-11-30", rule={1, 3}
        )
        work_calendar.sync_holiday_list(holidays.name, new, today)
        holidays.reload()
        dates = [str(h.holiday_date) for h in holidays.holidays]
        self.assertIn("2026-10-02", dates)
        self.assertNotIn("2026-10-10", dates)
        self.assertIn("2026-10-03", dates)
