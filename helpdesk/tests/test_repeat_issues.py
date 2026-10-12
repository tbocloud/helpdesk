from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk import repeat_issues as ri
from helpdesk.content_team import ensure_role
from helpdesk.test_utils import (
    call_repeat_issues,
    create_customer,
    hold_commits,
    make_customer_project,
    make_customer_ticket,
    make_department,
    make_recurring_task,
    make_task_created_on,
    make_tasky_user,
    set_department_heads_as,
    use_support_department,
)

# a week far from the real calendar, so only this test's records fall in the window
TODAY = date(2031, 5, 14)  # a Wednesday; the week is 12 to 18 May
GALOM = "Galom International"
ERNAKULAM = "Ernakulam Traders"
KOCHI = "Kochi Spices"
AGENT = "arun.agent@tbo-repeats.test"
MANAGER = "meera.manager@tbo-repeats.test"
HEAD = "hari.head@tbo-repeats.test"
DM = "sana.dm@tbo-repeats.test"

GSTIN = [
    (
        "GSTIN wrong on sales invoice print",
        "<p>Dear team,</p><p>The GSTIN printed on our sales invoice ACC-SINV-2031-00412 is wrong. Please check.</p><p>Regards,<br>Anil</p>",
        "2031-05-12",
    ),
    (
        "Sales invoice print shows old GSTIN",
        "Hi, our invoice print still shows the old GSTIN 32AABCG1234F1Z5 on the sales invoice. Thanks",
        "2031-04-20",
    ),
    (
        "Wrong GSTIN printed on invoice",
        "Customer copy of invoice dated 03-03-2031 for Rs. 45,000 shows the wrong GSTIN.",
        "2031-03-15",
    ),
    (
        "RE: Invoice print format showing incorrect GSTIN",
        "Hello, the print format of Sales Invoice shows incorrect GSTIN again. Kindly fix.",
        "2031-02-20",
    ),
]
# the title without AI is one of the subjects, without "RE:"
SUBJECTS = {s.removeprefix("RE: ") for s, _d, _day in GSTIN}
UNRELATED = [
    (
        "Salary slip email not sent to employees",
        "Payroll for May ran but salary slips were not emailed to staff.",
        "2031-05-13",
    ),
    (
        "Stock balance mismatch in Kochi warehouse",
        "Stock ledger and stock balance report do not match.",
        "2031-05-12",
    ),
    (
        "Sales invoice print is slow",
        "Printing a sales invoice takes 30 seconds.",
        "2031-05-13",
    ),
]


def ticket(
    customer: str, subject: str, day: str, description: str = "", **values
) -> str:
    return make_customer_ticket(
        customer,
        subject,
        description=description,
        creation=f"{day} 10:00:00",
        **values,
    )


class TestRepeatWords(FrappeTestCase):
    def test_numbers_ids_greetings_and_sign_off_are_left_out(self):
        found = ri.words(
            "Dear team, the GSTIN on ACC-SINV-2031-00412 dated 03-03-2031 for Rs. 45,000 "
            "is wrong. Please check. Regards, Anil"
        )
        self.assertEqual(found, ["gstin", "wrong"])

    def test_word_forms_match(self):
        self.assertEqual(ri.words("Invoices printed"), ri.words("invoice printing"))
        self.assertEqual(ri.words("incorrect GSTIN"), ri.words("wrong GSTIN"))


class TestRepeatIssues(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        ensure_role()
        frappe.cache.delete_keys(ri.CACHE_PREFIX)
        self.addCleanup(frappe.cache.delete_keys, ri.CACHE_PREFIX)
        ai_off = patch("helpdesk.ai_suggestion.is_ai_configured", return_value=False)
        ai_off.start()
        self.addCleanup(ai_off.stop)
        make_department("ERP")
        make_tasky_user(AGENT, "Arun Agent")
        make_tasky_user(MANAGER, "Meera Manager", ("Agent Manager",))
        make_tasky_user(HEAD, "Hari Head")
        make_tasky_user(DM, "Sana Rafeeq", ("DM Employee",))
        for customer in (GALOM, ERNAKULAM, KOCHI):
            create_customer(customer)
        self.project = make_customer_project(GALOM, "Galom ERP support")
        frappe.db.set_value("Project", self.project, "custom_department", "ERP")
        self.gstin = [ticket(GALOM, s, day, d) for s, d, day in GSTIN]
        self.unrelated = [ticket(GALOM, s, day, d) for s, d, day in UNRELATED]
        self.task = make_task_created_on(
            self.project, "Fix GSTIN on the sales invoice print format", "2031-05-13"
        )

    def view(self, user=AGENT, **kwargs):
        return call_repeat_issues(user, TODAY, period="week", **kwargs)

    def galom(self, data) -> dict | None:
        row = next((c for c in data["customers"] if c["customer"] == GALOM), None)
        return row and row["clusters"][0]

    def test_wording_variants_are_one_repeat_issue(self):
        data = self.view()
        found = self.galom(data)
        names = {i["name"] for i in found["items"]}
        self.assertEqual(names, {*self.gstin, self.task})
        self.assertEqual((found["tickets"], found["tasks"]), (4, 1))
        self.assertEqual((found["in_period"], found["total"]), (2, 5))
        self.assertEqual(found["first_seen"], "2031-02-20")
        self.assertEqual(found["last_seen"], "2031-05-13")
        self.assertEqual(found["trend"], "rising")
        self.assertIn(found["title"], SUBJECTS)
        self.assertEqual(found["title_source"], "subjects")
        self.assertIn("ERP", found["departments"])
        # unrelated tickets of the same customer aren't merged in, and alone they
        # aren't repeats
        everything = {
            i["name"]
            for c in data["customers"]
            for cl in c["clusters"]
            for i in cl["items"]
        }
        self.assertFalse(everything & set(self.unrelated))
        self.assertEqual(data["summary"]["issues"], 1)
        self.assertEqual(data["summary"]["tickets_in_period"], 1)
        self.assertEqual(data["summary"]["tasks_in_period"], 1)
        self.assertEqual(data["rules"]["min_occurrences"], 3)

    def test_planned_and_merged_work_is_not_a_repeat(self):
        rule = make_recurring_task(self.project, "Check GSTIN on sales invoice print")
        planned = make_task_created_on(
            self.project,
            "Check GSTIN on sales invoice print",
            "2031-05-12",
            custom_recurring_task=rule.name,
        )
        merged = ticket(
            GALOM,
            "Sales invoice print shows wrong GSTIN",
            "2031-05-13",
            is_merged=1,
            merged_with=self.gstin[0],
        )
        names = {i["name"] for i in self.galom(self.view())["items"]}
        self.assertNotIn(planned, names)
        self.assertNotIn(merged, names)
        self.assertEqual(len(names), 5)

    def test_thresholds(self):
        # three look-alikes, but none in this period
        for subject, day in (
            ("Bank reconciliation statement not matching", "2031-04-01"),
            ("Bank reconciliation does not match the statement", "2031-04-10"),
            ("Bank reconciliation statement mismatch", "2031-04-20"),
        ):
            ticket(KOCHI, subject, day)
        data = self.view()
        self.assertNotIn(KOCHI, [c["customer"] for c in data["customers"]])
        with patch.dict(frappe.conf, {"repeat_issues_min_occurrences": 6}):
            self.assertEqual(self.view()["customers"], [])

    def test_each_customer_has_their_own_repeats(self):
        ernakulam = [
            ticket(ERNAKULAM, subject, day)
            for subject, day in (
                ("GSTIN wrong on sales invoice print", "2031-05-12"),
                ("Old GSTIN on sales invoice print", "2031-04-02"),
                ("Sales invoice print has the wrong GSTIN", "2031-03-02"),
            )
        ]
        data = self.view()
        rows = {c["customer"]: c for c in data["customers"]}
        self.assertEqual(
            {i["name"] for i in rows[ERNAKULAM]["clusters"][0]["items"]}, set(ernakulam)
        )
        self.assertEqual(rows[GALOM]["clusters"][0]["total"], 5)
        # ranked by repeat volume this period
        self.assertEqual(data["customers"][0]["customer"], GALOM)

    def test_dismissal_persists_as_the_cluster_grows(self):
        cluster = self.galom(self.view(MANAGER))
        result = call_repeat_issues(
            MANAGER,
            TODAY,
            "helpdesk.api.repeat_issues.dismiss_repeat_issue",
            period="week",
            cluster=cluster["id"],
        )
        self.assertEqual(
            frappe.db.get_value("HD Repeat Issue", result["issue"], "status"),
            "Dismissed",
        )
        self.assertIsNone(self.galom(self.view()))
        ticket(GALOM, "Our sales invoice print still has the wrong GSTIN", "2031-05-14")
        self.assertIsNone(self.galom(self.view()))

        call_repeat_issues(
            MANAGER,
            TODAY,
            "helpdesk.api.repeat_issues.restore_repeat_issue",
            issue=result["issue"],
        )
        self.assertEqual(self.galom(self.view())["total"], 6)

    def test_only_managers_and_heads_act(self):
        cluster = self.galom(self.view())
        self.assertFalse(self.view()["access"]["can_act"])
        for method, extra in (
            ("dismiss_repeat_issue", {}),
            ("create_root_cause_task", {"project": self.project}),
        ):
            with self.assertRaises(frappe.PermissionError):
                call_repeat_issues(
                    AGENT,
                    TODAY,
                    f"helpdesk.api.repeat_issues.{method}",
                    period="week",
                    cluster=cluster["id"],
                    **extra,
                )
        self.assertFalse(frappe.db.exists("HD Repeat Issue", {"customer": GALOM}))

    def test_root_cause_task(self):
        set_department_heads_as("Administrator", "ERP", [HEAD])
        cluster = self.galom(self.view(HEAD))
        other = make_customer_project(ERNAKULAM, "Ernakulam rollout")
        with self.assertRaises(frappe.ValidationError):
            self.create_root_cause(HEAD, cluster["id"], other)

        result = self.create_root_cause(HEAD, cluster["id"], self.project)
        task = frappe.get_doc("Task", result["task"])
        self.assertEqual((task.project, task.is_key), (self.project, 1))
        self.assertTrue(task.subject.startswith("Root cause: "))
        self.assertIn(f"/helpdesk/tickets/{self.gstin[0]}", task.description)

        found = self.galom(self.view())
        self.assertEqual(found["root_cause"]["task"], task.name)
        # the fix isn't one more occurrence of the issue
        self.assertNotIn(task.name, {i["name"] for i in found["items"]})
        with self.assertRaises(frappe.ValidationError):
            self.create_root_cause(MANAGER, found["id"], self.project)

    def create_root_cause(self, user, cluster_id, project):
        return call_repeat_issues(
            user,
            TODAY,
            "helpdesk.api.repeat_issues.create_root_cause_task",
            period="week",
            cluster=cluster_id,
            project=project,
        )

    def test_ai_titles_with_the_number_guard(self):
        cluster = self.galom(self.view())
        answer = {
            "response": {
                "clusters": [
                    {
                        "id": cluster["id"],
                        "title": "Sales invoice print shows old GSTIN",
                        "cause": "The print format likely reads the GSTIN from 3 old addresses.",
                        "fix": "Point the print format at the company's current address.",
                    }
                ]
            }
        }
        found = ri.detect("week", None, TODAY)["clusters"]
        with patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True), patch(
            "helpdesk.repeat_issues.call_haiku", return_value=answer
        ):
            self.assertEqual(ri.label_clusters(found), 1)
        shown = self.galom(self.view())
        self.assertEqual(shown["title"], "Sales invoice print shows old GSTIN")
        self.assertEqual(shown["title_source"], "ai")
        # "3" isn't in the subjects, so the cause is dropped
        self.assertIsNone(shown["cause"])
        self.assertTrue(shown["fix"])

    def test_ai_failure_keeps_the_subject(self):
        found = ri.detect("week", None, TODAY)["clusters"]
        with patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True), patch(
            "helpdesk.repeat_issues.call_haiku", side_effect=RuntimeError("timeout")
        ), patch("frappe.log_error"):
            self.assertEqual(ri.label_clusters(found), 0)
        shown = self.galom(self.view())
        self.assertEqual(shown["title_source"], "subjects")
        self.assertIn(shown["title"], SUBJECTS)

        invented = {
            "response": {
                "clusters": [{"id": found[0]["id"], "title": "GSTIN wrong 12 times"}]
            }
        }
        frappe.cache.delete_keys(f"{ri.CACHE_PREFIX}_label_retry")
        with patch("helpdesk.ai_suggestion.is_ai_configured", return_value=True), patch(
            "helpdesk.repeat_issues.call_haiku", return_value=invented
        ):
            self.assertEqual(ri.label_clusters(found), 0)

    def test_detection_is_cached(self):
        frappe.cache.delete_keys(f"{ri.CACHE_PREFIX}:")
        first = ri.detect("week", None, TODAY)
        ticket(GALOM, "Sales invoice print still shows the old GSTIN", "2031-05-14")
        self.assertEqual(ri.detect("week", None, TODAY), first)
        frappe.cache.delete_keys(f"{ri.CACHE_PREFIX}:")
        self.assertEqual(ri.detect("week", None, TODAY)["clusters"][0]["total"], 6)

    def test_app_endpoint_shape(self):
        result = call_repeat_issues(
            AGENT, TODAY, "helpdesk.api.mobile.get_repeat_issues", period="week"
        )
        self.assertEqual(result["v"], 1)
        data = result["data"]
        self.assertEqual(
            set(data),
            {"period", "rules", "summary", "customers", "department", "access"},
        )
        cluster = data["customers"][0]["clusters"][0]
        for key in (
            "id",
            "title",
            "tickets",
            "tasks",
            "in_period",
            "total",
            "first_seen",
            "last_seen",
            "trend",
            "people",
            "items",
            "root_cause",
            "article",
        ):
            self.assertIn(key, cluster)

    def test_department_scope_follows_the_scoreboard(self):
        # tickets belong to the support department; without one, ERP has the task only
        with use_support_department(None):
            erp = call_repeat_issues(DM, TODAY, period="week", department="ERP")
        self.assertEqual(erp["department"], "ERP")
        self.assertEqual(erp["customers"], [])
        # the department walls don't apply on the Scoreboard: a DM Employee sees ERP
        with use_support_department("ERP"):
            erp = call_repeat_issues(DM, TODAY, period="week", department="ERP")
        self.assertEqual(self.galom(erp)["total"], 5)
        make_department("Closed Team", is_active=0)
        with self.assertRaises(frappe.ValidationError):
            call_repeat_issues(DM, TODAY, period="week", department="Closed Team")

    def test_a_group_shows_its_departments_only(self):
        make_department("GrowthX", parent_department="ERP")
        make_department("Digital")
        leads = make_customer_project(KOCHI, "Kochi Spices lead funnel")
        frappe.db.set_value("Project", leads, "custom_department", "GrowthX")
        for subject, day in (
            ("Landing page lead form not saving", "2031-05-13"),
            ("Landing page lead form not saving again", "2031-04-10"),
            ("Lead form on the landing page not saving", "2031-03-10"),
        ):
            make_task_created_on(leads, subject, day)

        # the ERP group is ERP and GrowthX; ERP alone leaves GrowthX's repeat out
        expected = (
            ({"group": "ERP"}, {GALOM, KOCHI}),
            ({"department": "ERP"}, {GALOM}),
            ({"department": "Digital"}, set()),
            ({}, {GALOM, KOCHI}),
        )
        with use_support_department("ERP"):
            for scope, customers in expected:
                data = self.view(**scope)
                self.assertEqual(
                    {c["customer"] for c in data["customers"]}, customers, scope
                )
            with self.assertRaises(frappe.ValidationError):
                self.view(group="Digital")

    def test_a_past_period_is_computed_for_its_own_window(self):
        earlier = ticket(GALOM, "Sales invoice print has the wrong GSTIN", "2031-05-08")
        # 7 May is in the week of 5 to 11 May, which has closed by the 14th
        data = self.view(day="2031-05-07")
        self.assertEqual(
            (data["period"]["start"], data["period"]["end"]),
            ("2031-05-05", "2031-05-11"),
        )
        found = self.galom(data)
        # what came after the week isn't in it, and the week's own ticket is
        self.assertEqual(
            {i["name"] for i in found["items"]}, {earlier, *self.gstin[1:]}
        )
        self.assertEqual((found["in_period"], found["total"]), (1, 4))
        self.assertEqual(found["last_seen"], "2031-05-08")
        # the week in progress still counts up to today
        self.assertEqual(self.galom(self.view())["total"], 6)
        with self.assertRaises(frappe.ValidationError):
            self.view(day="2031-05-20")

    def test_detection_is_cached_per_anchor_day(self):
        frappe.cache.delete_keys(f"{ri.CACHE_PREFIX}:")
        past = ri.detect("week", None, TODAY, "2031-05-07")
        current = ri.detect("week", None, TODAY)
        self.assertEqual(past["start"], "2031-05-05")
        self.assertEqual(current["start"], "2031-05-12")
        ticket(GALOM, "Sales invoice print still shows the old GSTIN", "2031-05-14")
        # each anchor keeps its own answer until the cache expires
        self.assertEqual(ri.detect("week", None, TODAY, "2031-05-07"), past)
        self.assertEqual(ri.detect("week", None, TODAY), current)
        keys = frappe.cache.get_keys(f"{ri.CACHE_PREFIX}:week:")
        self.assertTrue(any(":2031-05-07:" in frappe.utils.cstr(k) for k in keys))

    def test_kb_article_already_written(self):
        article = frappe.get_doc(
            {
                "doctype": "HD Article",
                "title": "How do I update the GSTIN on the invoice print?",
                "content": "<p>Steps</p>",
                "status": "Draft",
                "source_ticket": self.gstin[1],
            }
        ).insert(ignore_permissions=True)
        cluster = self.galom(self.view())
        self.assertEqual(cluster["article"]["name"], article.name)
        result = call_repeat_issues(
            AGENT,
            TODAY,
            "helpdesk.api.repeat_issues.draft_kb_article",
            period="week",
            cluster=cluster["id"],
        )
        self.assertEqual((result["name"], result["existing"]), (article.name, True))
