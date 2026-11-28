import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import project_access as access_api
from helpdesk.test_utils import (
    hold_commits,
    make_access_entry,
    make_project,
    make_sales_employee,
    make_tasky_user,
    run_as_user,
)

MANAGER = "access.manager@access.example"
DEVELOPER = "access.dev@access.example"
DESIGNER = "access.designer@access.example"
OUTSIDER = "access.outsider@access.example"
SALES = "access.sales@access.example"
PASSWORD = "Demo-Pass-42!"


class TestProjectAccess(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        for user, name in (
            (MANAGER, "Access Manager"),
            (DEVELOPER, "Access Developer"),
            (DESIGNER, "Access Designer"),
            (OUTSIDER, "Access Outsider"),
        ):
            make_tasky_user(user, name)
        make_sales_employee(SALES, "Access Sales")
        self.project = make_project(
            "Access Project",
            members=[
                (MANAGER, "Project Manager"),
                (DEVELOPER, "Developer"),
                (DESIGNER, "Graphic Designer"),
                (SALES, "Developer"),
            ],
        ).name
        self.entry = make_access_entry(
            self.project,
            label="Demo login",
            kind="Login",
            environment="Demo",
            url="https://demo.client.example",
            username="demo@client.example",
            password=PASSWORD,
            user=DEVELOPER,
        )

    def get(self, user):
        return run_as_user(user, lambda: access_api.get_project_access(self.project))

    def reveal(self, user):
        return run_as_user(
            user,
            lambda: access_api.reveal_access_password(self.project, self.entry["name"]),
        )

    def test_the_team_sees_links_and_usernames_but_never_a_password(self):
        for user in (MANAGER, DEVELOPER, DESIGNER):
            data = self.get(user)
            self.assertNotIn(PASSWORD, frappe.as_json(data))
            entry = data["entries"][0]
            self.assertEqual(
                (entry["url"], entry["username"], entry["has_password"]),
                ("https://demo.client.example", "demo@client.example", True),
            )
            self.assertEqual(entry["added_by"], DEVELOPER)
        self.assertTrue(self.get(DEVELOPER)["can_handle"])
        self.assertFalse(self.get(DESIGNER)["can_handle"])

    def test_outsiders_and_sales_see_nothing_even_when_listed(self):
        for user in (OUTSIDER, SALES):
            with self.assertRaises(frappe.PermissionError):
                self.get(user)

    def test_managers_and_developers_reveal_and_it_is_logged(self):
        self.assertEqual(self.reveal(DEVELOPER)["password"], PASSWORD)
        self.assertEqual(self.reveal(MANAGER)["password"], PASSWORD)
        logged = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Project",
                "reference_name": self.project,
                "content": ("like", "%viewed the password of Demo login%"),
            },
        )
        self.assertEqual(len(logged), 2)

    def test_other_members_may_not_reveal_or_change(self):
        with self.assertRaises(frappe.PermissionError):
            self.reveal(DESIGNER)
        with self.assertRaises(frappe.PermissionError):
            make_access_entry(self.project, user=DESIGNER)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                DESIGNER,
                lambda: access_api.delete_access_entry(
                    self.project, self.entry["name"]
                ),
            )

    def test_an_edit_without_a_password_keeps_it_and_clear_removes_it(self):
        name = self.entry["name"]

        def save(**values):
            entry = {"label": "Demo login", "kind": "Login", **values}
            return run_as_user(
                DEVELOPER,
                lambda: access_api.save_access_entry(self.project, entry, name),
            )

        self.assertTrue(save(notes="Reset monthly")["has_password"])
        self.assertEqual(self.reveal(DEVELOPER)["password"], PASSWORD)
        self.assertFalse(save(clear_password=1)["has_password"])

    def test_an_entry_needs_a_name_and_a_known_kind(self):
        with self.assertRaises(frappe.ValidationError):
            make_access_entry(self.project, label="", user=DEVELOPER)
        with self.assertRaises(frappe.ValidationError):
            make_access_entry(self.project, kind="Spaceship", user=DEVELOPER)

    def test_removing_an_entry_is_written_on_the_timeline(self):
        run_as_user(
            MANAGER,
            lambda: access_api.delete_access_entry(self.project, self.entry["name"]),
        )
        self.assertFalse(self.get(MANAGER)["entries"])
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_name": self.project,
                    "content": ("like", "%removed the access entry Demo login%"),
                },
            )
        )
