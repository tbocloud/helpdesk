"""The content calendar in the daily stand-up: role parts with their post, posts going
live, content blockers, the team's Content today and the per-department switch.
See docs/standup.md "Content calendar"."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, add_to_date, now_datetime

from helpdesk import standup
from helpdesk.content_team import DM_EMPLOYEE_ROLE, ERP_EMPLOYEE_ROLE, ensure_role
from helpdesk.test_utils import (
    TEST_TEAMS_CHANNEL_URL,
    call_as_user,
    call_mobile_as,
    complete_task_on,
    create_customer,
    enable_chat_notifications,
    get_content_task,
    log_post_move,
    make_content_post_at,
    make_content_project,
    make_content_user,
    make_dm_head,
    make_standup,
    make_tasky_user,
    set_content_settings,
    set_standup_settings,
    standup_calendar,
)
from helpdesk.tests.test_standup import DEPARTMENT, StandupCase

CUSTOMER = "Avera IoT Standup"
WRITER = ("writer.suc@standup.example", "Ajmal Rahman")
DESIGNER = ("designer.suc@standup.example", "Jasir Ali")
CONTENT_HEAD = ("dmhead.suc@standup.example", "Sreeja Nair")
ERP = ("erp.suc@standup.example", "Ajay Kumar")


class ContentStandupCase(StandupCase):
    def setUp(self):
        super().setUp()
        ensure_role()
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        create_customer(CUSTOMER)
        set_content_settings(
            default_task_mode="One task per person",
            writer_days_before=2,
            designer_days_before=1,
            client_reminder_days=2,
        )
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        for user in (WRITER, DESIGNER):
            make_content_user(*user, DM_EMPLOYEE_ROLE)
        make_dm_head(*CONTENT_HEAD)
        make_tasky_user(*ERP, roles=(ERP_EMPLOYEE_ROLE,))
        # the content project is in the stand-up's department, so it has content work
        self.content_project = make_content_project(CUSTOMER)
        frappe.db.set_value(
            "Project", self.content_project, "custom_department", DEPARTMENT
        )
        self.now = now_datetime()
        self.calendar = standup_calendar(self.today)
        self.previous = self.calendar.previous_working_day()
        # going live in two days: the writer's part is due today, the designer's after
        self.handwashing = make_content_post_at(
            "Global Handwashing Day",
            CUSTOMER,
            f"{add_days(self.today, 2)} 10:00:00",
            team={"writer": WRITER[0], "designer": DESIGNER[0]},
        )
        self.writer_task = get_content_task(self.handwashing, "Writer")
        self.designer_task = get_content_task(self.handwashing, "Designer")

    def fill(self, user):
        return standup.autofill(user[0], self.today, self.calendar)

    def rows(self, filled, reference):
        """[(section, row)] for every row about `reference`."""
        return [
            (section, row)
            for section in standup.SECTIONS
            for row in filled[section]
            if row["reference_name"] == reference
        ]

    def content_rows(self, filled):
        return [
            row
            for section in standup.SECTIONS
            for row in filled[section]
            if row.get("content_post")
        ]


class TestContentAutofill(ContentStandupCase):
    def test_the_writer_gets_their_part_once_with_its_post(self):
        rows = self.rows(self.fill(WRITER), self.writer_task)
        # on My Work as a task too, but listed once: as the part
        self.assertEqual(len(rows), 1)
        section, row = rows[0]
        self.assertEqual(section, "today")
        self.assertEqual(row["kind"], "task")
        self.assertEqual(row["title"], f"Writer · Global Handwashing Day ({CUSTOMER})")
        self.assertEqual(row["detail"], "Due today")
        self.assertEqual(row["content_post"], self.handwashing)
        self.assertEqual(row["content_role"], "writer")
        self.assertEqual(row["customer"], CUSTOMER)
        self.assertEqual(row["stage"], "Drafting")

    def test_the_designer_waits_on_the_writer(self):
        rows = self.rows(self.fill(DESIGNER), self.designer_task)
        self.assertEqual([section for section, _row in rows], ["blockers"])
        self.assertEqual(rows[0][1]["detail"], "Waiting on Writer (Ajmal)")
        self.assertEqual(
            rows[0][1]["title"], f"Designer · Global Handwashing Day ({CUSTOMER})"
        )

    def test_yesterday_lists_finished_parts_and_published_posts(self):
        complete_task_on(self.writer_task, self.previous)
        # finishing the part moved the post on: that move isn't listed again
        log_post_move(self.handwashing, WRITER[0], self.previous, "Drafting", "Design")
        diwali = make_content_post_at(
            "Diwali offer",
            CUSTOMER,
            f"{self.previous} 18:30:00",
            team={"marketer": WRITER[0]},
            status="Published",
            published_url="https://instagram.example/p/diwali",
        )
        log_post_move(diwali, WRITER[0], self.previous, "Scheduled", "Published")

        yesterday = self.fill(WRITER)["yesterday"]
        details = {r["title"]: r["detail"] for r in yesterday}
        self.assertEqual(
            details[f"Writer · Global Handwashing Day ({CUSTOMER})"], "Done"
        )
        self.assertEqual(details[f"Diwali offer ({CUSTOMER})"], "Published")
        self.assertEqual(
            [r["reference_doctype"] for r in yesterday if r.get("content_post")],
            ["Task", "HD Content Post"],
        )

    def test_posts_going_live_today_and_tomorrow(self):
        onam = make_content_post_at(
            "Onam greetings",
            CUSTOMER,
            f"{add_days(self.today, 1)} 18:30:00",
            team={"marketer": WRITER[0]},
            status="Scheduled",
        )
        food_day = make_content_post_at(
            "World Food Day",
            CUSTOMER,
            f"{self.today} 23:59:00",
            team={"designer": DESIGNER[0]},
            status="Approved",
        )
        writer = self.fill(WRITER)
        [(section, row)] = self.rows(writer, onam)
        self.assertEqual(section, "today")
        self.assertEqual(row["kind"], "post")
        self.assertEqual(
            row["detail"], "Goes live tomorrow, 18:30 · Instagram · Scheduled"
        )
        # not theirs
        self.assertEqual(self.rows(writer, food_day), [])
        # the Digital Marketing Head hears about every post going live today
        head = self.fill(CONTENT_HEAD)
        self.assertIn(food_day, [r["reference_name"] for r in head["today"]])
        self.assertNotIn(onam, [r["reference_name"] for r in head["today"]])

    def test_blockers_missed_unapproved_changes_and_client(self):
        def post(title, publish_on, status, **values):
            return make_content_post_at(
                title,
                CUSTOMER,
                publish_on,
                team={"designer": DESIGNER[0]},
                status=status,
                **values,
            )

        missed = post("Teachers' Day", f"{add_days(self.today, -1)} 10:00:00", "Design")
        soon = post("Flash sale", add_to_date(self.now, hours=5), "Design")
        changes = post(
            "Product launch",
            f"{add_days(self.today, 6)} 10:00:00",
            "Changes Requested",
            head_feedback="Use the new logo",
        )
        waiting = post(
            "Customer story",
            f"{add_days(self.today, 10)} 10:00:00",
            "Client Review",
            client_review_since=add_days(self.now, -3),
        )
        fresh = post(
            "Team photo",
            f"{add_days(self.today, 10)} 11:00:00",
            "Client Review",
            client_review_since=add_to_date(self.now, hours=-5),
        )

        blockers = {
            r["reference_name"]: r["detail"]
            for r in self.fill(DESIGNER)["blockers"]
            if r["kind"] == "post"
        }
        self.assertTrue(blockers[missed].startswith("Missed · was due "))
        self.assertTrue(blockers[soon].endswith("not approved yet (Design)"))
        self.assertEqual(blockers[changes], "Changes requested: Use the new logo")
        self.assertEqual(
            blockers[waiting], "Waiting on the client's approval for 3 days"
        )
        self.assertNotIn(fresh, blockers)

    def test_the_erp_wall_keeps_content_out(self):
        # an ERP Employee left on a post's team gets no task and no content line
        make_content_post_at(
            "ERP crossover",
            CUSTOMER,
            f"{add_days(self.today, 1)} 10:00:00",
            team={"writer": ERP[0]},
            status="Approved",
        )
        self.assertEqual(self.content_rows(self.fill(ERP)), [])

    def test_the_app_gets_each_lines_post(self):
        data = call_mobile_as(WRITER[0], "get_my_standup")["data"]
        row = next(
            r
            for r in data["standup"]["today"]
            if r["reference_name"] == self.writer_task
        )
        self.assertEqual(
            row["content"],
            {
                "post": self.handwashing,
                "part": "writer",
                "part_label": "Writer",
                "client": CUSTOMER,
                "go_live": f"{add_days(self.today, 2)} 10:00:00",
                "stage": "Drafting",
            },
        )
        self.assertEqual(row["app_route"], f"/task/{self.writer_task}")
        self.assertEqual(row["route"], f"/projects/{self.content_project}")


class TestContentToday(ContentStandupCase):
    def setUp(self):
        super().setUp()
        enable_chat_notifications(teams_channel_webhook=TEST_TEAMS_CHANNEL_URL)
        self.addCleanup(
            frappe.clear_document_cache, "HD Chat Settings", "HD Chat Settings"
        )
        self.missed = make_content_post_at(
            "Teachers' Day",
            CUSTOMER,
            f"{add_days(self.today, -1)} 10:00:00",
            team={"designer": DESIGNER[0]},
            status="Design",
        )
        self.live = make_content_post_at(
            "World Food Day",
            CUSTOMER,
            f"{self.today} 23:59:00",
            team={"marketer": WRITER[0]},
            status="Scheduled",
        )
        part = {
            "kind": "task",
            "title": f"Writer · Global Handwashing Day ({CUSTOMER})",
            "detail": "Due today",
            "reference_doctype": "Task",
            "reference_name": self.writer_task,
            "project": self.content_project,
            "content_post": self.handwashing,
            "content_role": "writer",
            "customer": CUSTOMER,
            "stage": "Drafting",
        }
        make_standup(
            WRITER[0],
            self.today,
            DEPARTMENT,
            today=[part],
            blockers=[{"kind": "note", "title": "Waiting for the brand kit"}],
        )
        make_standup(DESIGNER[0], self.today, DEPARTMENT, status="Submitted")
        post = patch("helpdesk.chat_notifications.requests.post")
        self.post = post.start()
        self.post.return_value = MagicMock(status_code=202)
        self.addCleanup(post.stop)
        for department_head in (CONTENT_HEAD[0], ERP[0]):
            doc = frappe.get_doc("HD Department", DEPARTMENT)
            doc.append("heads", {"user": department_head})
            doc.save(ignore_permissions=True)

    def summary(self) -> list[str]:
        with patch.object(standup, "call_haiku", side_effect=Exception("AI is down")):
            standup.post_summaries(standup.get_settings(), self.today)
        card = self.post.call_args.kwargs["json"]["attachments"][0]["content"]
        return [line for line in card["body"][0]["text"].split("\n") if line]

    def team(self, user):
        return call_as_user(
            user, "helpdesk.api.standup.get_team_standup", team=DEPARTMENT
        )

    def test_the_summary_puts_content_after_the_blockers(self):
        lines = self.summary()
        content = lines.index("**Content today (2)**")
        self.assertLess(lines.index("**Blockers and help needed (1)**"), content)
        self.assertLess(content, lines.index("**Ajmal Rahman (auto)**"))
        # missed first, with names
        self.assertTrue(lines[content + 1].startswith("- Missed: [Teachers' Day]"))
        self.assertIn("Jasir", lines[content + 1])
        self.assertIn("World Food Day", lines[content + 2])
        self.assertIn("Scheduled", lines[content + 2])

    def test_the_team_view_shows_content_today(self):
        view = self.team(CONTENT_HEAD[0])
        self.assertEqual(
            [p["post"] for p in view["content_today"]], [self.missed, self.live]
        )
        missed = view["content_today"][0]
        self.assertEqual(missed["state"], "missed")
        self.assertEqual(missed["client"], CUSTOMER)
        self.assertEqual(missed["channels"], ["Instagram"])
        self.assertEqual(
            missed["people"], [{"user": DESIGNER[0], "full_name": "Jasir Ali"}]
        )
        self.assertEqual(missed["route"], f"/content?post={self.missed}")
        self.assertEqual(view["content_today"][1]["state"], "ready")
        mine = next(p for p in view["people"] if p["user"] == WRITER[0])
        self.assertEqual(mine["today"][0]["content"]["post"], self.handwashing)

        app = call_mobile_as(CONTENT_HEAD[0], "get_team_standup", team=DEPARTMENT)
        self.assertEqual(len(app["data"]["content_today"]), 2)

    def test_the_erp_team_sees_no_content(self):
        view = self.team(ERP[0])
        self.assertIsNone(view["content_today"])
        mine = next(p for p in view["people"] if p["user"] == WRITER[0])
        self.assertEqual(mine["today"], [])
        self.assertEqual(
            [b["title"] for b in view["blockers"]], ["Waiting for the brand kit"]
        )

    def test_switched_off_for_the_department(self):
        set_standup_settings(content_off=[{"department": DEPARTMENT}])
        self.assertIsNone(self.team(CONTENT_HEAD[0])["content_today"])
        self.assertNotIn("**Content today (2)**", self.summary())
        # a fresh draft leaves content out too
        frappe.delete_doc(
            standup.STANDUP,
            standup.standup_name(WRITER[0], self.today),
            ignore_permissions=True,
        )
        mine = call_as_user(WRITER[0], "helpdesk.api.standup.get_my_standup")
        rows = [r for s in standup.SECTIONS for r in mine["standup"][s]]
        self.assertTrue(rows)
        self.assertFalse([r for r in rows if r["content"]])
        switches = call_as_user("Administrator", "helpdesk.api.standup.get_settings")[
            "content"
        ]
        self.assertIn({"department": DEPARTMENT, "include": False}, switches)

    def test_settings_list_departments_with_content(self):
        switches = call_as_user("Administrator", "helpdesk.api.standup.get_settings")[
            "content"
        ]
        self.assertIn({"department": DEPARTMENT, "include": True}, switches)
        call_as_user(
            "Administrator",
            "helpdesk.api.standup.save_settings",
            values={"content_off": [DEPARTMENT]},
        )
        frappe.clear_document_cache(standup.SETTINGS, standup.SETTINGS)
        self.assertFalse(standup.content_on(standup.get_settings(), DEPARTMENT))
