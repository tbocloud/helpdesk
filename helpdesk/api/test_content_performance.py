# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from helpdesk.api import content_performance
from helpdesk.test_utils import (
    create_customer,
    make_content_post,
    make_employee_with_user,
)

WRITER = ("cp.writer@perf-test.example", "Wanda Writer")
DESIGNER = ("cp.designer@perf-test.example", "Dev Designer")
ACME = "CP Test Acme"
GLOBEX = "CP Test Globex"


class TestContentPerformance(FrappeTestCase):
    def setUp(self):
        self.addCleanup(frappe.db.rollback)
        self.addCleanup(frappe.set_user, "Administrator")
        create_customer(ACME)
        create_customer(GLOBEX)
        self.writer = make_employee_with_user(*WRITER)
        self.designer = make_employee_with_user(*DESIGNER)
        self.start = str(add_days(nowdate(), -6))
        self.end = str(add_days(nowdate(), 6))

        on_time = self.post("On time", ACME, -3, writer=WRITER[0])
        on_time.db_set({"status": "Published", "published_on": add_days(nowdate(), -3)})
        late = self.post("Late", ACME, -4, writer=WRITER[0], designer=DESIGNER[0])
        late.db_set({"status": "Published", "published_on": add_days(nowdate(), -2)})
        self.post("Missed", GLOBEX, -2, designer=DESIGNER[0])
        self.post("Upcoming", GLOBEX, 3, writer=WRITER[0])

    def post(self, title, customer, days, **team):
        return make_content_post(
            title,
            customer,
            status="Drafting",
            publish_on=f"{add_days(nowdate(), days)} 10:00:00",
            **team,
        )

    def test_timing_and_score(self):
        self.assertEqual(content_performance.score("On time", 0), 100)
        self.assertEqual(content_performance.score("Late", 1), 50)
        self.assertEqual(content_performance.score("Missed", 3), 0)
        self.assertIsNone(content_performance.score("Upcoming", 0))

    def test_customers_are_summarised(self):
        report = content_performance.get_customer_performance(
            self.start, self.end, customer=ACME
        )
        rows = {r["customer"]: r for r in report["customers"]}
        self.assertEqual(
            (rows[ACME]["posts"], rows[ACME]["published"], rows[ACME]["on_time"]),
            (2, 2, 1),
        )
        self.assertEqual(rows[ACME]["avg_score"], 80)  # (100 + 60) / 2
        self.assertEqual(rows[ACME]["people"], 2)
        self.assertEqual((rows[GLOBEX]["missed"], rows[GLOBEX]["upcoming"]), (1, 1))

        detail = report["detail"]
        self.assertEqual(detail["customer"], ACME)
        people = {p["employee"]: p for p in detail["people"]}
        self.assertEqual(people[self.writer]["roles"]["writer"], 2)
        self.assertEqual(people[self.writer]["avg_score"], 80)
        self.assertEqual(people[self.designer]["avg_score"], 60)
        self.assertEqual(detail["people"][0]["employee"], self.writer)
        late = next(p for p in detail["posts"] if p["title"] == "Late")
        self.assertEqual(late["team"]["designer"][0]["name"], DESIGNER[1])

    def test_trend_counts_every_post_once(self):
        report = content_performance.get_customer_performance(self.start, self.end)
        trend = report["trend"]
        self.assertEqual(trend["bucket"], "day")
        self.assertEqual(len(trend["dates"]), 13)
        total = sum(sum(v) for v in trend["series"].values())
        self.assertEqual(total, report["summary"]["posts"])

    def test_people_see_only_their_own_customers(self):
        frappe.set_user(DESIGNER[0])
        report = content_performance.get_customer_performance(self.start, self.end)
        rows = {r["customer"]: r for r in report["customers"]}
        self.assertEqual(set(rows), {ACME, GLOBEX})
        # the post nobody they can see is on stays out
        self.assertEqual(rows[GLOBEX]["posts"], 1)

        frappe.set_user(WRITER[0])
        with self.assertRaises(frappe.PermissionError):
            content_performance.get_content_performance(
                self.start, self.end, employee=self.designer
            )

    def test_customer_filter_limits_both_reports(self):
        by_customer = content_performance.get_customer_performance(
            self.start, self.end, for_customer=GLOBEX
        )
        self.assertEqual([r["customer"] for r in by_customer["customers"]], [GLOBEX])
        self.assertEqual(by_customer["detail"]["customer"], GLOBEX)
        self.assertEqual(by_customer["summary"]["posts"], 2)

        by_employee = content_performance.get_content_performance(
            self.start, self.end, for_customer=GLOBEX
        )
        rows = {r["employee"]: r for r in by_employee["team"]}
        # only the Missed post: the designer's Acme post doesn't count here
        self.assertEqual(rows[self.designer]["posts"], 1)
        self.assertEqual(rows[self.designer]["missed"], 1)
        self.assertEqual(rows[self.writer]["posts"], 1)

    def test_a_post_counts_for_everyone_on_a_role(self):
        from helpdesk.api import content_board
        from helpdesk.test_utils import set_content_settings

        # counting is what's tested here, not the role tasks (other apps' Task hooks)
        set_content_settings(create_tasks_on_assign=0)
        late = frappe.get_value("HD Content Post", {"title": "Late"}, "name")
        frappe.db.set_value(
            "HD Content Post", late, "published_url", "https://x.example/1"
        )
        content_board.assign(late, "writer", users=[WRITER[0], DESIGNER[0]])
        report = content_performance.get_content_performance(
            self.start, self.end, employee=self.designer
        )
        late_row = next(p for p in report["detail"]["posts"] if p["title"] == "Late")
        self.assertEqual(sorted(late_row["roles"]), ["designer", "writer"])
        by_customer = content_performance.get_customer_performance(
            self.start, self.end, customer=ACME
        )
        people = {p["employee"]: p for p in by_customer["detail"]["people"]}
        self.assertEqual(people[self.designer]["roles"]["writer"], 1)

    def test_employee_ranking(self):
        report = content_performance.get_content_performance(
            self.start, self.end, employee=self.designer
        )
        ranks = {r["employee"]: r["rank"] for r in report["team"]}
        self.assertLess(ranks[self.writer], ranks[self.designer])
        self.assertEqual(report["detail"]["employee"], self.designer)
        self.assertEqual(
            {p["title"] for p in report["detail"]["posts"]}, {"Late", "Missed"}
        )
        self.assertEqual(getdate(report["from_date"]), getdate(self.start))
