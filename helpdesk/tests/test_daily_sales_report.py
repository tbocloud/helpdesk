from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import leads as leads_api
from helpdesk.daily_sales_report import person_text, team_text
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    daily_report,
    daily_report_person,
    enable_leads,
    hold_commits,
    make_sales_manager,
)

BDE = "daily.bde@report.example"
MANAGER = "daily.manager@report.example"
SECOND_MANAGER = "daily.manager2@report.example"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
MONDAY, WEDNESDAY, SUNDAY = "2026-10-26", "2026-10-28", "2026-10-25"
OLDER = CRMError("x", 417, "Failed to get method for command tbo_smart.api.hub_leads.x")


def shahana(**fields):
    return daily_report_person(
        "shahana@tbo.example",
        "Shahana V K",
        calls_total=32,
        calls_connected=20,
        fresh_leads=8,
        follow_up_leads=14,
        positive_leads=[{"name": "L-1", "lead_name": "A"}] * 3,
        new_quotations={"count": 2, "value": 90000, "items": []},
        new_leads=[
            {"name": "L-2", "lead_name": "Asha Traders"},
            {"name": "L-3", "lead_name": None, "company_name": "Bright Co"},
        ],
        **fields,
    )


class TestDailySalesReport(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "BDE")
        make_sales_manager(MANAGER, "Maya")
        make_sales_manager(SECOND_MANAGER, "Mohan")
        enable_leads()
        for field, value in (
            ("daily_lead_target", 10),
            ("weekly_meeting_target", 10),
            ("weekly_proposal_target", 5),
            ("weekly_follow_up_target", 40),
            ("send_daily_sales_report", 1),
        ):
            frappe.db.set_single_value("HD CRM Settings", field, value)
        self.crm = FakeCRM()
        self.crm.lead_answers["get_daily_report"] = daily_report([shahana()])
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Monday to Saturday, with no other days off, whatever the site's settings say
        for target, value in (
            ("helpdesk.work_calendar.saturday_rule", set()),
            ("helpdesk.work_calendar.company_holidays", set()),
        ):
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def read(self, date=MONDAY, **kwargs):
        frappe.set_user(BDE)
        return leads_api.get_daily_report(date=date, **kwargs)

    def test_the_report_is_proxied_as_the_signed_in_person(self):
        report = self.read(owner=BDE)
        self.assertTrue(report["available"])
        self.assertEqual(report["people"][0]["full_name"], "Shahana V K")
        ((method, post, params),) = self.crm.lead_calls
        self.assertEqual(method, "get_daily_report")
        self.assertFalse(post)
        self.assertEqual(
            (params["date"], params["owner"], params["acting_user"]),
            (MONDAY, BDE, BDE),
        )

    def test_the_week_is_measured_against_the_targets_pro_rated_by_working_days(self):
        self.crm.lead_answers["get_daily_report"] = daily_report(
            [
                shahana(
                    week_to_date={
                        "leads": 20,
                        "meetings": 1,
                        "proposals": 2,
                        "follow_ups": 30,
                    }
                )
            ],
            date=WEDNESDAY,
        )
        report = self.read(date=WEDNESDAY)
        # Mon, Tue, Wed of six working days (Mon to Sat) have passed
        self.assertEqual(report["working_days"], {"elapsed": 3, "total": 6})
        self.assertEqual(
            report["targets"],
            {"leads": 10, "meetings": 10, "proposals": 5, "follow_ups": 40},
        )
        person = report["people"][0]
        pace = person["pace"]
        # the day's lead target times the week's six days is 60, 30 of it by Wednesday
        self.assertEqual(
            (
                pace["leads"]["target"],
                pace["leads"]["expected"],
                pace["leads"]["behind"],
            ),
            (60, 30.0, 10),
        )
        self.assertEqual(
            (pace["meetings"]["expected"], pace["meetings"]["behind"]), (5.0, 4)
        )
        self.assertEqual(pace["proposals"]["behind"], 1)  # 2.5 expected, 2 done
        self.assertEqual(pace["follow_ups"]["behind"], 0)  # 20 expected, 30 done
        self.assertFalse(person["on_track"])
        self.assertEqual(
            {(b["metric"], b["by"]) for b in person["behind"]},
            {("leads", 10), ("meetings", 4), ("proposals", 1)},
        )

    def test_someone_at_pace_is_on_track_and_a_zero_target_is_left_out(self):
        frappe.db.set_single_value("HD CRM Settings", "weekly_proposal_target", 0)
        self.crm.lead_answers["get_daily_report"] = daily_report(
            [
                shahana(
                    week_to_date={
                        "leads": 30,
                        "meetings": 5,
                        "proposals": 0,
                        "follow_ups": 20,
                    }
                )
            ],
            date=WEDNESDAY,
        )
        person = self.read(date=WEDNESDAY)["people"][0]
        self.assertTrue(person["on_track"])
        self.assertEqual(person["behind"], [])
        self.assertNotIn("proposals", person["pace"])

    def test_the_whatsapp_text_follows_the_template_exactly(self):
        person = self.read()["people"][0]
        self.assertEqual(
            person["text"],
            "\n".join(
                [
                    "📊 DAILY SALES PERFORMANCE REPORT",
                    "📅 Date: 26 Oct 2026",
                    "👤 Employee Name: Shahana V K",
                    "",
                    "📞 1. Daily Call Performance",
                    "• Total Calls Made: 32",
                    "• Fresh Leads: 8",
                    "• Follow-up Leads: 14",
                    "• Positive Leads: 3",
                    "• New Quotations: 2",
                    "",
                    "🎯 2. New Leads Generated",
                    "• Total New Leads: 2",
                    "• Lead Names:",
                    "1. Asha Traders",
                    "2. Bright Co",
                ]
            ),
        )

    def test_an_empty_list_reads_as_a_dash_and_the_team_text_has_a_block_each(self):
        quiet = daily_report_person("q@tbo.example", "Quiet Q")
        self.assertTrue(person_text(quiet, MONDAY).endswith("• Lead Names:\n—"))
        text = team_text([shahana(), quiet], MONDAY)
        self.assertEqual(text.count("📊 DAILY SALES PERFORMANCE REPORT"), 2)
        self.assertIn("──────────", text)
        self.crm.lead_answers["get_daily_report"] = daily_report([shahana(), quiet])
        self.assertEqual(self.read(fresh=1)["team_text"], text)

    def test_a_read_is_kept_for_the_person_until_fresh_or_a_call_is_logged(self):
        self.read()
        self.read()
        self.assertEqual(len(self.crm.lead_calls), 1)
        self.read(fresh=1)
        self.assertEqual(len(self.crm.lead_calls), 2)
        # another day is another read
        self.read(date=WEDNESDAY)
        self.assertEqual(len(self.crm.lead_calls), 3)

        self.crm.lead_answers["log_call"] = {
            "name": "CALL-1",
            "status": "Answered",
            "outcomes": [],
        }
        leads_api.log_call("L-1", "Connected")
        self.read()
        self.assertEqual(len(self.crm.lead_calls), 5)  # log_call, then the read again

    def test_an_erp_site_without_the_report_says_unavailable_quietly(self):
        self.crm.lead_answers["get_daily_report"] = OLDER
        frappe.clear_messages()
        self.assertEqual(self.read(), {"available": False})
        self.assertEqual(frappe.message_log, [])
        # not remembered: a deploy shows at once
        self.crm.lead_answers["get_daily_report"] = daily_report([shahana()])
        self.assertTrue(self.read()["available"])

    def test_other_errors_still_show(self):
        self.crm.lead_answers["get_daily_report"] = CRMError("x", 502, "")
        with self.assertRaises(frappe.ValidationError):
            self.read()

    def test_log_call_is_posted_as_the_signed_in_person(self):
        self.crm.lead_answers["log_call"] = {"name": "CALL-1", "status": "Answered"}
        frappe.set_user(BDE)
        result = leads_api.log_call("CRM-LEAD-0001", "No answer", note=" rang twice ")
        self.assertEqual(result["name"], "CALL-1")
        ((method, post, params),) = self.crm.lead_calls
        self.assertEqual((method, post), ("log_call", True))
        self.assertEqual(
            (params["lead"], params["outcome"], params["note"], params["acting_user"]),
            ("CRM-LEAD-0001", "No answer", "rang twice", BDE),
        )
        with self.assertRaises(frappe.ValidationError):
            leads_api.log_call("CRM-LEAD-0001", "Hung up")

    def test_log_call_without_the_erp_method_says_so(self):
        self.crm.lead_answers["log_call"] = OLDER
        frappe.set_user(BDE)
        with self.assertRaises(frappe.ValidationError):
            leads_api.log_call("CRM-LEAD-0001", "Busy")

    def test_the_options_say_whether_a_call_can_be_logged(self):
        self.crm.lead_answers["get_options"] = {"stages": []}
        frappe.set_user(BDE)
        self.assertTrue(leads_api.get_options()["can_log_call"])
        self.crm.lead_answers["get_daily_report"] = OLDER
        frappe.cache.delete_keys("hd_leads:")
        frappe.clear_messages()
        self.assertFalse(leads_api.get_options()["can_log_call"])
        self.assertEqual(frappe.message_log, [])

    # --- the 6 pm message ---

    def run_job(self, day=MONDAY):
        from helpdesk import daily_sales_report as job

        with patch.object(job, "today", return_value=day), patch(
            "helpdesk.follow_ups.deliver_digest"
        ) as deliver:
            job.run()
        return deliver

    def test_each_manager_gets_one_message_with_the_teams_day(self):
        deliver = self.run_job()
        users = [c.args[0] for c in deliver.call_args_list]
        sent = {c.args[0]: c.args for c in deliver.call_args_list}
        # one message each (the site's own System Managers get theirs too)
        self.assertEqual(len(users), len(set(users)))
        self.assertTrue({MANAGER, SECOND_MANAGER} <= set(sent))
        self.assertNotIn(BDE, sent)
        _user, subject, sections = sent[MANAGER]
        self.assertIn("26 Oct 2026", subject)
        ((heading, rows),) = sections
        self.assertIn("Shahana V K", heading)
        lines = [text for text, _path in rows]
        self.assertIn("• Total Calls Made: 32", lines)
        self.assertIn("1. Asha Traders", lines)
        # asked as each manager, with the day
        acting = {p["acting_user"] for m, _post, p in self.crm.lead_calls}
        self.assertTrue({MANAGER, SECOND_MANAGER} <= acting)
        self.assertNotIn(BDE, acting)

    def test_nothing_goes_out_on_a_day_off(self):
        self.assertEqual(self.run_job(SUNDAY).call_count, 0)
        self.assertEqual(self.crm.lead_calls, [])

    def test_nothing_goes_out_when_the_setting_is_off(self):
        frappe.db.set_single_value("HD CRM Settings", "send_daily_sales_report", 0)
        self.assertEqual(self.run_job().call_count, 0)
        self.assertEqual(self.crm.lead_calls, [])

    def test_an_erp_site_without_the_report_is_skipped_silently(self):
        self.crm.lead_answers["get_daily_report"] = OLDER
        frappe.clear_messages()
        self.assertEqual(self.run_job().call_count, 0)
        self.assertEqual(frappe.message_log, [])

    def test_a_manager_without_a_sales_account_does_not_stop_the_rest(self):
        refused = CRMError("x", 403, "no sales role")
        answers = iter([refused, daily_report([shahana()])])
        self.crm.call = lambda method, post=False, **params: next(answers)
        self.assertEqual(self.run_job().call_count, 1)
