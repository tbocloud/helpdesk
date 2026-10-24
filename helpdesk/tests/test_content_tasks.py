from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, getdate, now_datetime

from helpdesk.api.content_board import get_content_project
from helpdesk.content_team import (
    CONTENT_TEAM_ROLE,
    DM_EMPLOYEE_ROLE,
    ensure_role,
    is_content_only,
)
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import TASK_ROLES
from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import permission_query
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_content_post,
    make_customer_project,
    make_project,
    make_tasky_user,
    make_ticket,
    set_content_settings,
)

CUSTOMER = "Content Tasks Traders"
WRITER = ("writer.ct@content-tasks.example", "Faris Writer")
DESIGNER = ("designer.ct@content-tasks.example", "Jasir Designer")
MARKETER = ("marketer.ct@content-tasks.example", "Mufliha Marketer")
OTHER = ("other.ct@content-tasks.example", "Nisha Other")
EDITOR = ("editor.ct@content-tasks.example", "Vivek Editor")


class ContentTaskCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        ensure_role()
        create_customer(CUSTOMER)
        for person in (WRITER, DESIGNER, MARKETER, OTHER, EDITOR):
            make_tasky_user(*person)
        set_content_settings(
            default_task_mode="One task per person",
            writer_days_before=3,
            designer_days_before=1,
            video_editor_days_before=2,
        )
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        self.project = make_project(f"{CUSTOMER} - Social media").name
        frappe.db.set_value(
            "Project",
            self.project,
            {"customer": CUSTOMER, "project_type": "Content Calendar"},
        )
        self.publish = add_days(now_datetime(), 10).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

    def post(self, **values):
        return make_content_post(
            "Diwali offer",
            CUSTOMER,
            **{
                "status": "Drafting",
                "publish_on": self.publish,
                "writer": WRITER[0],
                "designer": DESIGNER[0],
                "marketer": MARKETER[0],
                **values,
            },
        )

    def tasks(self, post, open_only=True):
        filters = {"content_post": post.name}
        if open_only:
            filters["status"] = ("not in", ["Completed", "Cancelled"])
        rows = frappe.get_all(
            "Task",
            filters=filters,
            fields=[
                "name",
                "content_role",
                "status",
                "exp_end_date",
                "project",
                "_assign",
            ],
        )
        return {r.content_role: r for r in rows}

    def assignees(self, task):
        return frappe.get_doc("Task", task.name).assignees()


class TestTasksFromPosts(ContentTaskCase):
    def test_one_task_per_person_due_before_publishing(self):
        post = self.post()

        tasks = self.tasks(post)
        self.assertEqual(set(tasks), {"Writer", "Designer", "Marketer"})
        day = getdate(self.publish)
        self.assertEqual(getdate(tasks["Writer"].exp_end_date), add_days(day, -3))
        self.assertEqual(getdate(tasks["Designer"].exp_end_date), add_days(day, -1))
        self.assertEqual(getdate(tasks["Marketer"].exp_end_date), day)
        self.assertEqual(tasks["Writer"].project, self.project)
        self.assertEqual(self.assignees(tasks["Designer"]), [DESIGNER[0]])
        # each person hears about their task
        self.assertTrue(
            frappe.db.exists(
                "HD Notification",
                {"user_to": WRITER[0], "message": ("like", "New content task:%")},
            )
        )

    def test_one_task_for_the_post_is_shared(self):
        post = self.post(task_mode="One task for the post")

        tasks = self.tasks(post)
        self.assertEqual(set(tasks), {"All"})
        self.assertEqual(
            set(self.assignees(tasks["All"])), {WRITER[0], DESIGNER[0], MARKETER[0]}
        )

    def test_a_post_without_copy_is_named_by_its_post_type(self):
        post = make_content_post(
            "",
            CUSTOMER,
            format="Carousel",
            status="Drafting",
            publish_on=self.publish,
            writer=WRITER[0],
        )

        self.assertEqual(post.title, "")
        subject = frappe.db.get_value(
            "Task", self.tasks(post)["Writer"].name, "subject"
        )
        self.assertTrue(subject.startswith("Writer: Carousel (Instagram)"), subject)

    def test_the_task_carries_the_copy_sub_copy_and_description(self):
        post = self.post(
            caption="<p>Busy day? Your car wash doesn't have to wait.</p>",
            brief="Make car care easy to fit in",
        )
        task = self.tasks(post)["Writer"].name
        text = frappe.utils.strip_html(frappe.db.get_value("Task", task, "description"))
        for part in ("Diwali offer", "Busy day?", "Make car care easy to fit in"):
            self.assertIn(part, text)

        # a new copy reaches the task
        post.reload()
        post.title = "Time-saving"
        post.save()
        text = frappe.utils.strip_html(frappe.db.get_value("Task", task, "description"))
        self.assertIn("Time-saving", text)

        # a link added by hand, with the same words, counts as written by hand
        linked = frappe.db.get_value("Task", task, "description").replace(
            "Time-saving", '<a href="https://example.com/brand">Time-saving</a>'
        )
        frappe.db.set_value("Task", task, "description", linked)
        post.reload()
        post.caption = "<p>Wash in ten minutes.</p>"
        post.save()
        self.assertEqual(frappe.db.get_value("Task", task, "description"), linked)

        # a description written by hand stays
        frappe.db.set_value("Task", task, "description", "<p>Use the blue logo</p>")
        post.reload()
        post.brief = "Something else"
        post.save()
        self.assertEqual(
            frappe.db.get_value("Task", task, "description"), "<p>Use the blue logo</p>"
        )

    def test_no_tasks(self):
        post = self.post(task_mode="No tasks")
        self.assertEqual(self.tasks(post), {})

    def test_reassigning_and_postponing_follow_the_post(self):
        post = self.post()

        post.designer = OTHER[0]
        post.publish_on = add_to_date(self.publish, days=2)
        post.save(ignore_permissions=True)

        tasks = self.tasks(post)
        self.assertEqual(self.assignees(tasks["Designer"]), [OTHER[0]])
        self.assertEqual(
            getdate(tasks["Marketer"].exp_end_date), add_days(getdate(self.publish), 2)
        )

    def at(self, days):
        return add_days(now_datetime(), days).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

    def test_a_lead_time_already_passed_is_due_today(self):
        # publishing tomorrow: the writer's 3 days and the designer's 1 day are used up
        post = self.post(publish_on=self.at(1))

        tasks = self.tasks(post)
        today = getdate()
        self.assertEqual(getdate(tasks["Writer"].exp_end_date), today)
        self.assertEqual(getdate(tasks["Designer"].exp_end_date), today)
        self.assertEqual(getdate(tasks["Marketer"].exp_end_date), add_days(today, 1))

    def test_a_missed_post_keeps_its_publish_date(self):
        post = self.post(publish_on=self.at(-1))

        yesterday = add_days(getdate(), -1)
        self.assertEqual(
            {getdate(t.exp_end_date) for t in self.tasks(post).values()}, {yesterday}
        )

    def test_saving_the_post_does_not_move_a_late_tasks_date(self):
        post = self.post()
        writer = self.tasks(post)["Writer"].name
        late = add_days(getdate(), -2)
        frappe.db.set_value("Task", writer, "exp_end_date", late)

        post.reload()
        post.caption = "Lights, sweets and 20% off"
        post.save()

        self.assertEqual(
            getdate(frappe.db.get_value("Task", writer, "exp_end_date")), late
        )

    def test_rescheduling_closer_makes_used_up_lead_times_due_today(self):
        post = self.post()

        post.reload()
        post.postpone(self.at(1), "Client moved the launch")

        tasks = self.tasks(post)
        self.assertEqual(getdate(tasks["Writer"].exp_end_date), getdate())
        self.assertEqual(
            getdate(tasks["Marketer"].exp_end_date), add_days(getdate(), 1)
        )

    def late_writer(self, post):
        writer = self.tasks(post)["Writer"].name
        late = add_days(getdate(), -2)
        frappe.db.set_value("Task", writer, "exp_end_date", late)
        return writer, late

    def test_a_new_time_on_the_same_day_leaves_a_late_task_alone(self):
        post = self.post()
        writer, late = self.late_writer(post)

        post.reload()
        post.postpone(post.publish_on.replace(hour=16), "Client wants the afternoon")

        self.assertEqual(
            getdate(frappe.db.get_value("Task", writer, "exp_end_date")), late
        )
        self.assertFalse(frappe.db.get_value("Task", writer, "slip_count"))

    def test_bringing_a_post_earlier_leaves_a_late_task_late(self):
        post = self.post()
        writer, late = self.late_writer(post)

        post.reload()
        post.postpone(self.at(1), "Client moved the launch forward")

        self.assertEqual(
            getdate(frappe.db.get_value("Task", writer, "exp_end_date")), late
        )

    def test_postponing_later_moves_a_late_task_too(self):
        post = self.post()
        writer, late = self.late_writer(post)

        post.reload()
        post.postpone(self.at(20), "Client asked for later")

        self.assertEqual(
            getdate(frappe.db.get_value("Task", writer, "exp_end_date")),
            add_days(getdate(self.at(20)), -3),
        )

    def test_a_cancelled_part_is_not_recreated(self):
        post = self.post()
        designer_task = frappe.get_doc("Task", self.tasks(post)["Designer"].name)
        designer_task.status = "Cancelled"
        designer_task.save(ignore_permissions=True)

        post.reload()
        post.publish_on = add_to_date(self.publish, days=1)
        post.save(ignore_permissions=True)

        self.assertNotIn("Designer", self.tasks(post))
        self.assertEqual(
            frappe.db.count(
                "Task", {"content_post": post.name, "content_role": "Designer"}
            ),
            1,
        )

    def test_finishing_the_writing_moves_the_post_to_design(self):
        post = self.post()
        writer_task = frappe.get_doc("Task", self.tasks(post)["Writer"].name)

        writer_task.status = "Completed"
        writer_task.save(ignore_permissions=True)

        post.reload()
        self.assertEqual(post.status, "Design")
        # the designer is told it's their turn
        self.assertTrue(
            frappe.db.exists(
                "HD Notification",
                {"user_to": DESIGNER[0], "message": ("like", "%is now Design%")},
            )
        )

    def test_publishing_completes_and_cancelling_cancels(self):
        published = self.post()
        published.status = "Published"
        published.published_url = "https://instagram.example/p/1"
        published.save(ignore_permissions=True)
        statuses = {t.status for t in self.tasks(published, open_only=False).values()}
        self.assertEqual(statuses, {"Completed"})

        cancelled = self.post()
        cancelled.status = "Cancelled"
        cancelled.save(ignore_permissions=True)
        statuses = {t.status for t in self.tasks(cancelled, open_only=False).values()}
        self.assertEqual(statuses, {"Cancelled"})


class TestEstimatedHours(ContentTaskCase):
    def hours(self, post):
        return {
            role: frappe.db.get_value("Task", t.name, "custom_estimated_hours")
            for role, t in self.tasks(post).items()
        }

    def test_each_role_task_gets_its_hours(self):
        post = self.post(writer_hours=2, designer_hours=3.5)

        hours = self.hours(post)
        self.assertEqual(hours["Writer"], 2)
        self.assertEqual(hours["Designer"], 3.5)

    def test_changing_the_hours_updates_the_task(self):
        post = self.post(writer_hours=2)

        post.writer_hours = 4
        post.save(ignore_permissions=True)

        self.assertEqual(self.hours(post)["Writer"], 4)

    def test_no_hours_keeps_the_tasks_own_estimate(self):
        post = self.post()
        task = self.tasks(post)["Writer"].name
        frappe.db.set_value("Task", task, "custom_estimated_hours", 1.5)

        post.publish_on = add_to_date(self.publish, days=1)
        post.save(ignore_permissions=True)

        self.assertEqual(
            frappe.db.get_value("Task", task, "custom_estimated_hours"), 1.5
        )

    def test_assigning_can_set_the_roles_hours(self):
        from helpdesk.api import content_board

        post = self.post(writer_hours=2)

        content_board.assign(post.name, "writer", [WRITER[0]], hours=3)
        self.assertEqual(self.hours(post)["Writer"], 3)

        # no hours given leaves the estimate as it was
        content_board.assign(post.name, "writer", [WRITER[0], OTHER[0]])
        post.reload()
        self.assertEqual(post.writer_hours, 3)

    def test_assigning_can_set_the_tasks_due_date(self):
        from helpdesk.api import content_board

        post = self.post()
        day = getdate(self.publish)
        # the dialog starts at the date the task already has
        self.assertEqual(
            content_board.get_role_due(post.name, "writer"), str(add_days(day, -3))
        )

        content_board.assign(
            post.name, "writer", [WRITER[0]], due=str(add_days(day, -5))
        )
        task = self.tasks(post)["Writer"]
        self.assertEqual(getdate(task.exp_end_date), add_days(day, -5))
        self.assertEqual(
            content_board.get_role_due(post.name, "writer"), str(add_days(day, -5))
        )

        # never after the post goes live, nor a new date in the past
        for bad in (add_days(day, 1), add_days(getdate(), -1)):
            with self.assertRaises(frappe.ValidationError, msg=str(bad)):
                content_board.assign(post.name, "writer", [WRITER[0]], due=str(bad))

    def test_a_finished_task_keeps_its_due_date(self):
        from helpdesk.api import content_board

        post = self.post()
        day = getdate(self.publish)
        task = self.tasks(post)["Writer"].name
        frappe.db.set_value("Task", task, "status", "Completed")

        # the dialog offers the usual date, and saving leaves the finished task alone
        self.assertEqual(
            content_board.get_role_due(post.name, "writer"), str(add_days(day, -3))
        )
        content_board.assign(
            post.name, "writer", [WRITER[0]], due=str(add_days(day, -5))
        )
        self.assertEqual(
            getdate(frappe.db.get_value("Task", task, "exp_end_date")),
            add_days(day, -3),
        )

    def test_a_role_without_a_task_offers_its_usual_due_date(self):
        from helpdesk.api import content_board

        post = self.post(designer=None)
        self.assertEqual(
            content_board.get_role_due(post.name, "designer"),
            str(add_days(getdate(self.publish), -1)),
        )

    def test_clearing_the_hours_clears_the_tasks_estimate(self):
        post = self.post(writer_hours=3)

        post.writer_hours = 0
        post.save(ignore_permissions=True)

        self.assertEqual(self.hours(post)["Writer"], 0)

    def test_shared_task_adds_up_every_role(self):
        post = self.post(
            task_mode="One task for the post",
            writer_hours=2,
            designer_hours=3,
            marketer_hours=0.5,
        )

        self.assertEqual(self.hours(post), {"All": 5.5})


class TestSeveralPeopleAndVideoEditor(ContentTaskCase):
    def test_several_people_on_a_role_share_its_task(self):
        post = self.post()
        post.set_people("designer", [DESIGNER[0], OTHER[0], DESIGNER[0]])
        post.save(ignore_permissions=True)

        self.assertEqual(post.designer, DESIGNER[0])
        self.assertEqual(post.people("designer"), [DESIGNER[0], OTHER[0]])
        tasks = self.tasks(post)
        # still one task per role, now with both designers on it
        self.assertEqual(set(tasks), {"Writer", "Designer", "Marketer"})
        self.assertEqual(
            set(self.assignees(tasks["Designer"])), {DESIGNER[0], OTHER[0]}
        )

        # taking the main designer off: the other becomes main and keeps the task
        post.set_people("designer", [OTHER[0]])
        post.save(ignore_permissions=True)
        self.assertEqual((post.designer, post.extra_team), (OTHER[0], []))
        self.assertEqual(self.assignees(self.tasks(post)["Designer"]), [OTHER[0]])

    def test_video_editor_gets_a_task_and_design_waits_for_both(self):
        post = self.post(video_editor=EDITOR[0])
        tasks = self.tasks(post)
        self.assertEqual(set(tasks), {"Writer", "Designer", "Video Editor", "Marketer"})
        self.assertEqual(
            getdate(tasks["Video Editor"].exp_end_date),
            add_days(getdate(self.publish), -2),
        )
        self.assertEqual(self.assignees(tasks["Video Editor"]), [EDITOR[0]])

        post.db_set("status", "Design")
        designer_task = frappe.get_doc("Task", tasks["Designer"].name)
        designer_task.status = "Completed"
        designer_task.save(ignore_permissions=True)
        post.reload()
        # the video isn't done yet, so the post stays in Design
        self.assertEqual(post.status, "Design")

        editor_task = frappe.get_doc("Task", tasks["Video Editor"].name)
        editor_task.status = "Completed"
        editor_task.save(ignore_permissions=True)
        post.reload()
        self.assertEqual(post.status, "Internal Review")

    def in_design_with_the_designer_done(self):
        post = self.post(video_editor=EDITOR[0])
        tasks = self.tasks(post)
        post.db_set("status", "Design")
        designer_task = frappe.get_doc("Task", tasks["Designer"].name)
        designer_task.status = "Completed"
        designer_task.save(ignore_permissions=True)
        post.reload()
        self.assertEqual(post.status, "Design")
        return post, tasks

    def test_cancelling_the_last_open_design_part_ends_design(self):
        post, tasks = self.in_design_with_the_designer_done()

        editor_task = frappe.get_doc("Task", tasks["Video Editor"].name)
        editor_task.status = "Cancelled"
        editor_task.save(ignore_permissions=True)

        post.reload()
        self.assertEqual(post.status, "Internal Review")

    def test_taking_the_video_editor_off_ends_design(self):
        post, tasks = self.in_design_with_the_designer_done()

        post.set_people("video_editor", [])
        post.save(ignore_permissions=True)

        self.assertEqual(
            frappe.db.get_value("Task", tasks["Video Editor"].name, "status"),
            "Cancelled",
        )
        post.reload()
        self.assertEqual(post.status, "Internal Review")

    def test_cancelling_a_design_part_never_skips_drafting(self):
        post = self.post(video_editor=EDITOR[0])
        tasks = self.tasks(post)
        post.db_set("status", "Drafting")
        designer_task = frappe.get_doc("Task", tasks["Designer"].name)
        designer_task.status = "Completed"
        designer_task.save(ignore_permissions=True)

        editor_task = frappe.get_doc("Task", tasks["Video Editor"].name)
        editor_task.status = "Cancelled"
        editor_task.save(ignore_permissions=True)

        post.reload()
        self.assertEqual(post.status, "Drafting")

    def test_design_nobody_did_does_not_end_design(self):
        post = self.post(video_editor=EDITOR[0])
        tasks = self.tasks(post)
        post.db_set("status", "Design")
        for role in ("Designer", "Video Editor"):
            task = frappe.get_doc("Task", tasks[role].name)
            task.status = "Cancelled"
            task.save(ignore_permissions=True)

        post.reload()
        self.assertEqual(post.status, "Design")

    def test_person_filter_lists_each_post_once(self):
        from frappe.client import get_list

        post = self.post()
        post.set_people("writer", [WRITER[0], OTHER[0]])
        post.set_people("designer", [DESIGNER[0], OTHER[0]])
        post.save(ignore_permissions=True)

        # the same query the calendar's person filter and "My posts" send
        or_filters = [
            *([role, "=", OTHER[0]] for role in TASK_ROLES),
            ["HD Content Post Member", "user", "=", OTHER[0]],
        ]
        names = get_list(
            "HD Content Post",
            fields=["name", "title", "publish_on"],
            filters={"customer": CUSTOMER},
            or_filters=or_filters,
            group_by="`tabHD Content Post`.`name`",
            order_by="publish_on asc",
            limit_page_length=1000,
        )
        self.assertEqual([p["name"] for p in names], [post.name])

    def test_board_follows_the_task_mode(self):
        from helpdesk.api import content_board

        post = self.post()
        post.task_mode = "One task for the post"
        post.save(ignore_permissions=True)

        shared = self.tasks(post)["All"].name
        status = content_board.get_team_task_status([post.name])[post.name]
        # the per-role tasks the switch cancelled no longer stand for the role
        self.assertEqual(status["designer"][0]["task"], shared)
        self.assertEqual(status["designer"][0]["status"], "Open")

    def test_one_task_for_the_post_includes_everyone(self):
        post = self.post(task_mode="One task for the post", video_editor=EDITOR[0])
        post.set_people("writer", [WRITER[0], OTHER[0]])
        post.save(ignore_permissions=True)
        self.assertEqual(
            set(self.assignees(self.tasks(post)["All"])),
            {WRITER[0], OTHER[0], DESIGNER[0], MARKETER[0], EDITOR[0]},
        )

    def test_board_shows_each_person_with_their_task(self):
        from helpdesk.api import content_board

        post = self.post()
        content_board.assign(post.name, "writer", [WRITER[0], OTHER[0]])
        status = content_board.get_team_task_status([post.name])[post.name]
        self.assertEqual([p["user"] for p in status["writer"]], [WRITER[0], OTHER[0]])
        self.assertEqual(status["writer"][0]["full_name"], WRITER[1])
        # both writers share the writer's task
        self.assertEqual(status["writer"][0]["task"], status["writer"][1]["task"])
        self.assertEqual(status["writer"][0]["status"], "Open")
        self.assertEqual(status["video_editor"], [])

    def test_extra_people_can_see_the_post(self):
        from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
            has_permission,
        )

        # only the content team sees posts at all
        frappe.get_doc("User", OTHER[0]).add_roles(DM_EMPLOYEE_ROLE)
        post = self.post()
        self.assertFalse(has_permission(post, "read", OTHER[0]))
        post.set_people("marketer", [MARKETER[0], OTHER[0]])
        post.save(ignore_permissions=True)
        self.assertIsNone(has_permission(post, "read", OTHER[0]))
        frappe.set_user(OTHER[0])
        self.assertIn(post.name, frappe.get_list("HD Content Post", pluck="name"))


class TestContentProject(ContentTaskCase):
    def without_project_customer(self):
        frappe.db.set_value("Project", self.project, "customer", None)

    def without_task_projects(self, post):
        # tasks made before the customer's project had the customer (older posts)
        for task in self.tasks(post).values():
            frappe.db.set_value("Task", task.name, "project", None)

    def test_tasks_join_the_project_once_it_has_the_customer(self):
        post = self.post()
        self.without_task_projects(post)
        self.without_project_customer()

        project = frappe.get_doc("Project", self.project)
        project.customer = CUSTOMER
        project.save()

        self.assertEqual({t.project for t in self.tasks(post).values()}, {self.project})

    def test_saving_the_post_fills_in_a_missing_project(self):
        post = self.post()
        self.without_task_projects(post)

        post.reload()
        post.caption = "Lights, sweets and 20% off"
        post.save()

        self.assertEqual({t.project for t in self.tasks(post).values()}, {self.project})

    def test_no_content_project_blocks_creating_tasks(self):
        self.without_project_customer()
        with self.assertRaisesRegex(frappe.ValidationError, "has no open project"):
            self.post(with_project=False)
        self.assertFalse(
            frappe.db.exists(
                "HD Content Post", {"customer": CUSTOMER, "title": "Diwali offer"}
            )
        )

    def test_a_post_without_people_needs_no_project(self):
        self.without_project_customer()
        post = make_content_post(
            "Diwali offer", CUSTOMER, with_project=False, publish_on=self.publish
        )
        self.assertEqual(self.tasks(post), {})

    def test_editing_a_post_that_has_its_tasks_is_not_blocked(self):
        post = self.post()
        self.without_project_customer()

        post.reload()
        post.caption = "Lights, sweets and 20% off"
        post.save()

        self.assertEqual(set(self.tasks(post)), {"Writer", "Designer", "Marketer"})

    def test_adding_a_person_without_a_project_is_blocked(self):
        post = make_content_post(
            "Diwali offer",
            CUSTOMER,
            status="Drafting",
            publish_on=self.publish,
            writer=WRITER[0],
        )
        self.without_project_customer()

        post.reload()
        post.designer = DESIGNER[0]
        with self.assertRaisesRegex(frappe.ValidationError, "has no open project"):
            post.save()

    def test_a_project_picked_by_hand_stays(self):
        post = self.post()
        other = make_project("Content Tasks hand-picked").name
        writer = self.tasks(post)["Writer"].name
        frappe.db.set_value("Task", writer, "project", other)

        post.reload()
        post.caption = "Lights, sweets and 20% off"
        post.save()

        self.assertEqual(frappe.db.get_value("Task", writer, "project"), other)

    def test_a_new_customer_moves_the_tasks_to_their_project(self):
        post = self.post()
        create_customer("Content Tasks Movers")
        theirs = make_project("Content Tasks Movers - Social media").name
        frappe.db.set_value(
            "Project",
            theirs,
            {"customer": "Content Tasks Movers", "project_type": "Content Calendar"},
        )

        post.reload()
        post.customer = "Content Tasks Movers"
        post.save()

        self.assertEqual({t.project for t in self.tasks(post).values()}, {theirs})

    def test_the_dialog_is_told_which_project_tasks_go_to(self):
        self.assertEqual(get_content_project(CUSTOMER)["name"], self.project)
        self.without_project_customer()
        missing = get_content_project(CUSTOMER)
        self.assertIsNone(missing["name"])
        self.assertIn("has no open project", missing["missing"])

    def test_the_dialog_hides_a_project_the_viewer_cant_open(self):
        real = frappe.has_permission
        with patch(
            "helpdesk.api.content_board.frappe.has_permission",
            side_effect=lambda doctype, *a, **k: doctype != "Project"
            and real(doctype, *a, **k),
        ):
            self.assertEqual(
                get_content_project(CUSTOMER), {"name": None, "hidden": True}
            )

    def test_a_project_of_any_type_takes_the_tasks(self):
        frappe.db.set_value("Project", self.project, "project_type", "Website")
        post = self.post(with_project=False)
        self.assertEqual({t.project for t in self.tasks(post).values()}, {self.project})

    def test_a_content_calendar_project_is_preferred(self):
        frappe.db.set_value("Project", self.project, "project_type", "Website")
        content = make_customer_project(CUSTOMER, "Content Tasks - Content calendar")
        frappe.db.set_value("Project", content, "project_type", "Content Calendar")
        # the other project changed last, but the content one still wins
        frappe.db.set_value("Project", self.project, "project_name", "Website rebuild")

        post = self.post(with_project=False)

        self.assertEqual({t.project for t in self.tasks(post).values()}, {content})

    def test_a_save_that_adds_nobody_is_not_blocked(self):
        # a role left without a task (say it was deleted) doesn't block finishing,
        # approving or other saves that add no one
        post = self.post()
        frappe.delete_doc("Task", self.tasks(post)["Designer"].name, force=True)
        self.without_project_customer()

        post.reload()
        post.caption = "Lights, sweets and 20% off"
        post.save()

    def test_moving_a_post_to_a_customer_without_a_project_is_blocked(self):
        post = self.post()
        create_customer("Content Tasks Projectless")

        post.reload()
        post.customer = "Content Tasks Projectless"
        with self.assertRaisesRegex(frappe.ValidationError, "has no open project"):
            post.save()

    def test_cancelling_while_changing_the_customer_is_not_blocked(self):
        post = self.post()
        create_customer("Content Tasks Projectless")

        post.reload()
        post.customer = "Content Tasks Projectless"
        post.status = "Cancelled"
        post.save()

        self.assertEqual(self.tasks(post), {})

    def test_one_task_for_the_post_needs_a_project_too(self):
        self.without_project_customer()
        with self.assertRaisesRegex(frappe.ValidationError, "has no open project"):
            self.post(task_mode="One task for the post", with_project=False)

    def test_background_posts_are_made_and_join_the_project_later(self):
        self.without_project_customer()
        post = frappe.get_doc(
            {
                "doctype": "HD Content Post",
                "title": "Planned post",
                "customer": CUSTOMER,
                "channel": "Instagram",
                "status": "Idea",
                "publish_on": self.publish,
                "writer": WRITER[0],
            }
        )
        post.flags.tasks_join_project_later = True
        post.insert(ignore_permissions=True)
        self.assertEqual(self.tasks(post)["Writer"].project, None)

        frappe.get_doc("Project", self.project).update({"customer": CUSTOMER}).save()

        self.assertEqual(self.tasks(post)["Writer"].project, self.project)

    def test_only_the_project_tasks_go_to_takes_them(self):
        post = self.post()
        self.without_task_projects(post)
        other = make_customer_project(CUSTOMER, "Content Tasks - Website")

        # the Content Calendar project is the one tasks go to, so saving another
        # project of the customer takes nothing
        frappe.get_doc("Project", other).save()

        self.assertEqual({t.project for t in self.tasks(post).values()}, {None})

    def test_the_project_is_found_through_any_customer_field(self):
        # on ERPNext sites the HD Customer is in Project.hd_customer; stand in another
        # field for it, since this site's Project has no hd_customer
        frappe.db.set_value(
            "Project", self.project, {"customer": None, "project_name": CUSTOMER}
        )
        with patch(
            "helpdesk.helpdesk.doctype.hd_content_post.hd_content_post.project_customer_fields",
            return_value=["customer", "project_name"],
        ):
            self.assertEqual(get_content_project(CUSTOMER)["name"], self.project)


class TestContentTeamRole(ContentTaskCase):
    def test_content_team_sees_no_tickets_unless_they_manage(self):
        frappe.get_doc("User", WRITER[0]).add_roles(CONTENT_TEAM_ROLE)
        self.assertTrue(is_content_only(WRITER[0]))
        make_ticket(subject="Someone else's ticket")

        condition = permission_query(WRITER[0])
        self.assertIn("raised_by", condition)
        frappe.set_user(WRITER[0])
        self.assertEqual(
            frappe.get_list(
                "HD Ticket", filters={"subject": "Someone else's ticket"}, pluck="name"
            ),
            [],
        )
        frappe.set_user("Administrator")

        # a ticket they raised themselves stays theirs to list and open
        own = make_ticket(subject="My own ticket", raised_by=WRITER[0])
        frappe.set_user(WRITER[0])
        self.assertEqual(
            frappe.get_list(
                "HD Ticket", filters={"subject": "My own ticket"}, pluck="name"
            ),
            [own.name],
        )
        self.assertTrue(frappe.get_doc("HD Ticket", own.name).has_permission("read"))
        frappe.set_user("Administrator")

        frappe.get_doc("User", WRITER[0]).add_roles("Project Manager")
        self.assertFalse(is_content_only(WRITER[0]))
        frappe.db.set_single_value("HD Settings", "restrict_tickets_by_agent_group", 0)
        frappe.set_user(WRITER[0])
        self.assertEqual(
            len(
                frappe.get_list(
                    "HD Ticket",
                    filters={"subject": "Someone else's ticket"},
                    pluck="name",
                )
            ),
            1,
        )
