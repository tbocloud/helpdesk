import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, getdate, now_datetime

from helpdesk.content_team import CONTENT_TEAM_ROLE, ensure_role, is_content_only
from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import permission_query
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_content_post,
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


class ContentTaskCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        ensure_role()
        create_customer(CUSTOMER)
        for person in (WRITER, DESIGNER, MARKETER, OTHER):
            make_tasky_user(*person)
        set_content_settings(
            default_task_mode="One task per person",
            writer_days_before=3,
            designer_days_before=1,
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
            status="Drafting",
            publish_on=self.publish,
            writer=WRITER[0],
            designer=DESIGNER[0],
            marketer=MARKETER[0],
            **values,
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
