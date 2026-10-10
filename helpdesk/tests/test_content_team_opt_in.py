"""Only the content team sees the content calendar; everyone else sees only the content
tasks that are their own. See docs/content-calendar.md "Who sees the content calendar"."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from helpdesk.content_team import (
    CONTENT_TEAM_ROLE,
    DM_COORDINATOR_ROLE,
    DM_EMPLOYEE_ROLE,
    ERP_EMPLOYEE_ROLE,
    in_content_team,
)
from helpdesk.test_utils import (
    call_as_user,
    create_customer,
    get_content_task,
    get_visible_content_posts,
    get_visible_tasks,
    hold_commits,
    make_assignment,
    make_content_post,
    make_content_user,
    make_dm_head,
    make_project,
    make_task,
    make_tasky_user,
    set_content_settings,
    set_department_wall_as,
)

CUSTOMER = "Malabar Spices Export"
# an ERP consultant with no roles at all: the owner's example
CONSULTANT = ("gayathri.s@content-opt-in.example", "Gayathri S")
DEVELOPER = ("vishnu.b@content-opt-in.example", "Vishnu B")
WRITER = ("riya.t@content-opt-in.example", "Riya T")


class TestContentTeamOptIn(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(
            frappe.clear_document_cache, "HD Content Settings", "HD Content Settings"
        )
        create_customer(CUSTOMER)
        set_content_settings(default_task_mode="One task per person")
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        self.consultant = make_tasky_user(*CONSULTANT)
        self.developer = make_tasky_user(*DEVELOPER)
        self.writer = make_content_user(*WRITER, DM_EMPLOYEE_ROLE)
        project = make_project(
            f"{CUSTOMER} - Social media",
            members=[(self.consultant, "Functional Consultant")],
        )
        # the developer leads it, so only the content team rule keeps tasks from them
        project.db_set(
            {
                "customer": CUSTOMER,
                "project_type": "Content Calendar",
                "project_lead": self.developer,
            }
        )
        self.project = project.name
        self.post = make_content_post(
            "Onam offer",
            CUSTOMER,
            status="Drafting",
            publish_on=add_days(now_datetime(), 10),
            writer=self.writer,
        )
        self.writer_task = get_content_task(self.post.name, "Writer")

    def flag(self, user: str) -> bool:
        return call_as_user(user, "helpdesk.api.auth.get_user")["in_content_team"]

    def test_a_plain_agent_sees_no_content_calendar(self):
        self.assertFalse(in_content_team(self.consultant))
        self.assertFalse(self.flag(self.consultant))
        # a member of the client's project used to see the client's posts
        self.assertEqual(get_visible_content_posts(self.consultant), set())
        self.assertFalse(
            frappe.has_permission(
                "HD Content Post", "read", self.post.name, user=self.consultant
            )
        )

    def test_someone_outside_the_team_sees_only_their_own_content_task(self):
        banner = make_task(
            self.project, "Onam offer: website banner", content_post=self.post.name
        ).name
        make_assignment("Task", banner, self.developer)
        other = make_task(self.project, "Set up the client's ERP").name

        visible = get_visible_tasks(self.developer, self.project)
        self.assertIn(banner, visible)
        self.assertIn(other, visible)
        self.assertNotIn(self.writer_task, visible)
        self.assertTrue(
            frappe.has_permission("Task", "read", doc=banner, user=self.developer)
        )
        self.assertFalse(
            frappe.has_permission(
                "Task", "read", doc=self.writer_task, user=self.developer
            )
        )
        # the task, never the calendar
        self.assertFalse(self.flag(self.developer))
        self.assertEqual(get_visible_content_posts(self.developer), set())

    def test_the_content_roles_and_the_admins_are_in(self):
        people = [
            self.writer,
            make_content_user(
                "dm.coordinator@content-opt-in.example",
                "Shabna R",
                DM_COORDINATOR_ROLE,
            ),
            make_dm_head("dm.head@content-opt-in.example", "Arun H"),
            make_content_user(
                "designer@content-opt-in.example", "Jasir D", CONTENT_TEAM_ROLE
            ),
            make_tasky_user(
                "agent.manager@content-opt-in.example",
                "Faris M",
                roles=("Agent Manager",),
            ),
            make_tasky_user(
                "system.manager@content-opt-in.example",
                "Sammish T",
                roles=("System Manager",),
            ),
        ]
        for user in people:
            self.assertTrue(in_content_team(user), user)
            self.assertTrue(self.flag(user), user)
        self.assertTrue(in_content_team("Administrator"))
        # the writer sees the post they're on; the leads see every post
        for user in (self.writer, *people[1:3], *people[4:]):
            self.assertIn(self.post.name, get_visible_content_posts(user), user)
        self.assertIn(self.writer_task, get_visible_tasks(self.writer))

    def test_the_erp_employee_wall_is_unchanged(self):
        erp = make_content_user(
            "ajay.k@content-opt-in.example", "Ajay K", ERP_EMPLOYEE_ROLE
        )
        # even with a content role, an ERP Employee stays out unless they edit content
        frappe.get_doc("User", erp).add_roles(DM_EMPLOYEE_ROLE)
        self.assertFalse(in_content_team(erp))
        self.assertFalse(self.flag(erp))
        self.assertTrue(call_as_user(erp, "helpdesk.api.auth.get_user")["is_erp_only"])
        task = make_task(
            self.project, "Onam offer: caption", content_post=self.post.name
        ).name
        with self.assertRaises(frappe.ValidationError):
            make_assignment("Task", task, erp)

        frappe.get_doc("User", erp).add_roles(DM_COORDINATOR_ROLE)
        self.assertTrue(in_content_team(erp))

    def test_settings_shows_and_sets_who_is_in_the_content_team(self):
        manager = make_tasky_user(
            "sreeja.p@content-opt-in.example", "Sreeja P", roles=("Agent Manager",)
        )
        users = [self.consultant, self.writer, manager]

        def members():
            return call_as_user(
                manager, "helpdesk.api.departments.get_content_team", users=users
            )

        self.assertEqual(members(), [self.writer, manager])
        # the Digital team wall is the DM Employee role, which adds them
        set_department_wall_as(manager, self.consultant, DM_EMPLOYEE_ROLE)
        self.assertEqual(members(), users)
        set_department_wall_as(manager, self.consultant, "")
        self.assertEqual(members(), [self.writer, manager])

        with self.assertRaises(frappe.PermissionError):
            call_as_user(
                self.consultant,
                "helpdesk.api.departments.get_content_team",
                users=users,
            )
