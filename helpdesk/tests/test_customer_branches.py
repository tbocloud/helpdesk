"""Customer branches in the Content Calendar: each branch has its own posts, project
(and so Meta page), monthly plan and approvers."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from helpdesk.api import content_portal, customer_branches
from helpdesk.api.content_board import get_occasions
from helpdesk.content_follow_up import send_client_follow_ups
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    content_project_for,
)
from helpdesk.integrations.meta.publisher import connection_for
from helpdesk.test_utils import (
    create_customer,
    hold_commits,
    make_content_occasion,
    make_content_package,
    make_content_post,
    make_content_project,
    make_customer_branch,
    make_customer_project,
    make_meta_connection,
    make_portal_contact,
    make_tasky_user,
    set_content_settings,
)

CUSTOMER = "Branch Test Jewellers"
OTHER_CUSTOMER = "Branch Test Bakery"
KOCHI_APPROVER = "manager.kochi@branch-test.example"
KINASSERY_APPROVER = "manager.kinassery@branch-test.example"
HEAD_OFFICE = "owner@branch-test.example"
WRITER = ("writer.branch@branch-test.example", "Branch Writer")


class CustomerBranchCase(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        create_customer(CUSTOMER)
        create_customer(OTHER_CUSTOMER)
        make_tasky_user(*WRITER)
        self.customer_project = make_content_project(CUSTOMER)
        self.kochi_project = make_customer_project(CUSTOMER, "Branch Test - Kochi")
        self.kochi = make_customer_branch(
            CUSTOMER, "Kochi", project=self.kochi_project, approvers=[KOCHI_APPROVER]
        )
        self.kinassery = make_customer_branch(
            CUSTOMER, "Kinassery", approvers=[KINASSERY_APPROVER]
        )

    def post(self, title, branch=None, **kwargs):
        return make_content_post(
            title,
            CUSTOMER,
            branch=branch.name if branch else None,
            publish_on=add_days(now_datetime(), 6),
            **kwargs,
        )


class TestBranch(CustomerBranchCase):
    def test_branch_is_named_after_its_customer(self):
        self.assertEqual(self.kochi.name, f"{CUSTOMER} - Kochi")

    def test_branch_project_must_be_the_customers_and_only_its_own(self):
        other = make_customer_project(OTHER_CUSTOMER, "Branch Test Bakery - Main")
        with self.assertRaises(frappe.ValidationError):
            make_customer_branch(CUSTOMER, "Thondayad", project=other)
        with self.assertRaises(frappe.ValidationError):
            make_customer_branch(CUSTOMER, "Thondayad", project=self.kochi_project)

    def test_post_branch_must_belong_to_its_customer(self):
        bakery = make_customer_branch(OTHER_CUSTOMER, "Kochi")
        with self.assertRaises(frappe.ValidationError):
            self.post("Wrong branch", branch=bakery)

    def test_a_disabled_branch_cant_be_picked(self):
        self.kinassery.db_set("enabled", 0)
        with self.assertRaises(frappe.ValidationError):
            self.post("Closed shop", branch=self.kinassery)


class TestBranchProject(CustomerBranchCase):
    def test_branch_posts_go_to_the_branch_project(self):
        self.assertEqual(
            content_project_for(CUSTOMER, self.kochi.name), self.kochi_project
        )
        # a branch without its own project uses the customer's
        self.assertEqual(
            content_project_for(CUSTOMER, self.kinassery.name), self.customer_project
        )

    def test_a_branch_project_is_never_the_customers(self):
        # the Kochi project is the newest, but it is Kochi's, not the customer's
        frappe.db.set_value("Project", self.customer_project, "project_type", None)
        self.assertEqual(content_project_for(CUSTOMER), self.customer_project)

    def test_tasks_of_a_branch_post_join_the_branch_project(self):
        post = self.post("Kochi launch", branch=self.kochi, writer=WRITER[0])
        project = frappe.db.get_value("Task", {"content_post": post.name}, "project")
        self.assertEqual(project, self.kochi_project)
        subject = frappe.db.get_value("Task", {"content_post": post.name}, "subject")
        self.assertIn(self.kochi.name, subject)

    def test_branch_posts_publish_only_to_their_branchs_page(self):
        kochi_page = make_meta_connection(
            self.kochi_project, facebook_page_name="Kochi"
        )
        self.assertEqual(
            connection_for(self.post("Kochi post", branch=self.kochi)).name,
            kochi_page.name,
        )
        # Kinassery has no page of its own: never Kochi's
        kinassery_post = self.post("Kinassery post", branch=self.kinassery)
        self.assertIsNone(connection_for(kinassery_post))


class TestBranchPlans(CustomerBranchCase):
    def package(self, branch=None):
        return make_content_package(
            CUSTOMER,
            [("Instagram", "Post", 4)],
            branch=branch.name if branch else None,
            task_mode="No tasks",
        )

    def test_each_branch_has_its_own_plan(self):
        whole = self.package()
        kochi = self.package(self.kochi)
        self.assertEqual(whole.name, CUSTOMER)
        self.assertEqual(kochi.name, self.kochi.name)
        with self.assertRaises(frappe.ValidationError):
            self.package(self.kochi)

    def test_planned_posts_carry_the_branch(self):
        kochi = self.package(self.kochi)
        kochi.plan("next")
        branches = set(
            frappe.get_all(
                "HD Content Post",
                filters={"content_package": kochi.name},
                pluck="branch",
            )
        )
        self.assertEqual(branches, {self.kochi.name})

    def test_occasions_follow_the_branch_plan(self):
        frappe.db.delete("HD Content Occasion")
        make_content_occasion("Onam", "2026-12-10", region="Kerala")
        make_content_occasion("UAE Day", "2026-12-02", region="UAE")
        make_content_package(
            CUSTOMER,
            [("Instagram", "Post", 4)],
            branch=self.kochi.name,
            include_occasions=1,
            occasions_kerala=1,
        )
        names = [
            o["occasion"]
            for o in get_occasions(
                "2026-12-01", "2026-12-31", CUSTOMER, self.kochi.name
            )
        ]
        self.assertEqual(names, ["Onam"])


class TestBranchApprovers(CustomerBranchCase):
    def setUp(self):
        super().setUp()
        set_content_settings(
            enable_client_portal=1, client_reminder_days=2, client_escalate_days=0
        )
        frappe.clear_document_cache("HD Content Settings", "HD Content Settings")
        make_portal_contact(CUSTOMER, HEAD_OFFICE)
        self.kochi_post = self.post(
            "Kochi offer", branch=self.kochi, status="Client Review"
        )
        self.kinassery_post = self.post(
            "Kinassery offer", branch=self.kinassery, status="Client Review"
        )

    def session(self, email):
        return {
            "email": email,
            "customers": content_portal.customers_for_email(email),
            "branches": content_portal.branches_for_email(email),
        }

    def test_branch_approver_sees_only_their_branch(self):
        session = self.session(KOCHI_APPROVER)
        self.assertEqual(content_portal.session_accounts(session), [self.kochi.name])
        posts = content_portal.get_portal_posts(self.kochi.name, session)
        self.assertEqual([p.name for p in posts], [self.kochi_post.name])

        with patch.object(content_portal, "get_session", return_value=session):
            content_portal.approve(self.kochi_post.name)
            with self.assertRaises(frappe.DoesNotExistError):
                content_portal.approve(self.kinassery_post.name)

    def test_head_office_sees_every_branch(self):
        session = self.session(HEAD_OFFICE)
        posts = content_portal.get_portal_posts(CUSTOMER, session)
        self.assertEqual(
            {p.name for p in posts}, {self.kochi_post.name, self.kinassery_post.name}
        )

    def test_reminders_go_to_each_branchs_approvers(self):
        for post in (self.kochi_post, self.kinassery_post):
            frappe.db.set_value(
                "HD Content Post",
                post.name,
                "client_review_since",
                add_days(now_datetime(), -3),
                update_modified=False,
            )
        with patch.object(frappe, "sendmail") as sendmail:
            send_client_follow_ups()
        sent = {
            tuple(call.kwargs["recipients"]): call.kwargs["message"]
            for call in sendmail.call_args_list
        }
        self.assertEqual(set(sent), {(KOCHI_APPROVER,), (KINASSERY_APPROVER,)})
        self.assertIn("Kochi offer", sent[(KOCHI_APPROVER,)])
        self.assertNotIn("Kinassery offer", sent[(KOCHI_APPROVER,)])

    def test_sharing_the_portal_with_a_new_branch_approver_adds_them(self):
        with patch.object(frappe, "sendmail"):
            content_portal.send_portal_access(
                CUSTOMER, "deputy.kochi@branch-test.example", branch=self.kochi.name
            )
        self.assertIn(
            "deputy.kochi@branch-test.example",
            content_portal.portal_emails(CUSTOMER, self.kochi.name),
        )


class TestBranchesTab(CustomerBranchCase):
    def test_saving_a_branch_sets_its_approvers(self):
        name = customer_branches.save_branch(
            CUSTOMER,
            {"branch_name": " Thondayad ", "approvers": ["Shop@Branch-Test.example"]},
        )
        self.assertEqual(name, f"{CUSTOMER} - Thondayad")

        customer_branches.save_branch(
            CUSTOMER, {"approvers": [], "enabled": 0}, name=name
        )
        row = next(
            b
            for b in customer_branches.get_customer_branches(CUSTOMER)["branches"]
            if b["name"] == name
        )
        self.assertEqual(row["approvers"], [])
        self.assertFalse(row["enabled"])

    def test_a_branch_is_only_edited_under_its_own_customer(self):
        with self.assertRaises(frappe.ValidationError):
            customer_branches.save_branch(
                OTHER_CUSTOMER, {"enabled": 0}, name=self.kochi.name
            )
