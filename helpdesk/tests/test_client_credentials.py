from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import client_credentials as credentials_api
from helpdesk.api import proposals as proposals_api
from helpdesk.test_utils import (
    FakeCRM,
    enable_leads,
    hold_commits,
    make_accepted_proposal,
    make_credentials,
    make_department,
    make_dm_head,
    make_project,
    make_sales_employee,
    make_tasky_user,
    run_as_user,
)

MANAGER = "cred.manager@credentials.example"
MEMBER = "cred.member@credentials.example"
SALES = "cred.sales@credentials.example"
HEAD = "cred.head@credentials.example"
PASSWORD = "s3cret-Pass!"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"


class TestClientCredentials(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(MANAGER, "Cred Manager")
        make_tasky_user(MEMBER, "Cred Member")
        make_sales_employee(SALES, "Cred Sales")
        make_dm_head(HEAD, "Cred Head")
        digital = make_department("Digital")
        self.project = make_project(
            "Credentials Project",
            members=[(MANAGER, "Project Manager"), (MEMBER, "Developer")],
        ).name
        frappe.db.set_value("Project", self.project, "custom_department", digital.name)
        self.handover = make_credentials(self.project)

    def test_managers_and_heads_may_open_nobody_else(self):
        for user in (MANAGER, HEAD, "Administrator"):
            data = run_as_user(
                user, lambda: credentials_api.get_credentials(self.project)
            )
            self.assertEqual(len(data["handovers"]), 1)
        for user in (MEMBER, SALES):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(user, lambda: credentials_api.get_credentials(self.project))
            with self.assertRaises(frappe.PermissionError):
                make_credentials(self.project, user=user)

    def test_a_password_is_never_in_a_list(self):
        data = run_as_user(
            MANAGER, lambda: credentials_api.get_credentials(self.project)
        )
        self.assertNotIn(PASSWORD, frappe.as_json(data))
        item = data["handovers"][0]["items"][0]
        self.assertTrue(item["has_password"])
        self.assertNotIn("password", item)

    def test_revealing_one_password_is_logged_on_the_project(self):
        item = self.handover["items"][0]["name"]
        revealed = run_as_user(
            MANAGER,
            lambda: credentials_api.reveal_password(
                self.project, self.handover["name"], item
            ),
        )
        self.assertEqual(revealed["password"], PASSWORD)
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Project", "reference_name": self.project},
            pluck="content",
        )
        self.assertTrue(any("viewed the Facebook password" in c for c in comments))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                MEMBER,
                lambda: credentials_api.reveal_password(
                    self.project, self.handover["name"], item
                ),
            )

    def test_editing_without_a_password_keeps_the_old_one(self):
        item = self.handover["items"][0]
        credentials_api.save_handover(
            self.project,
            handed_over_by="Client Owner",
            name=self.handover["name"],
            items=[{"name": item["name"], "platform": "Facebook", "username": "new"}],
        )
        revealed = credentials_api.reveal_password(
            self.project, self.handover["name"], item["name"]
        )
        self.assertEqual(revealed["password"], PASSWORD)

    def test_handing_back_closes_the_project_and_keeps_passwords_by_reference(self):
        result = run_as_user(
            MANAGER,
            lambda: credentials_api.hand_back_and_close(
                self.project, "Client Owner", frappe.utils.today(), "Budget cut"
            ),
        )
        returned = result["handover"]
        self.assertEqual(returned["direction"], "Returned to client")
        self.assertEqual(len(returned["items"]), 1)
        self.assertTrue(returned["items"][0]["returned_from"])
        row = frappe.get_all(
            "HD Client Credential",
            filters={"parent": returned["name"]},
            fields=["name", "password"],
        )[0]
        self.assertNotIn(PASSWORD, frappe.as_json(row))
        self.assertEqual(
            frappe.db.get_value("Project", self.project, "status"), "Cancelled"
        )
        with self.assertRaises(frappe.ValidationError):
            credentials_api.hand_back_and_close(
                self.project, "Client Owner", frappe.utils.today(), "Again"
            )


class TestProjectFromProposal(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_department("Digital")
        enable_leads()
        self.crm = FakeCRM()
        self.crm.lead_answers["get_accepted_proposal"] = make_accepted_proposal()
        self.crm.lead_answers["link_project"] = {"steps": [], "next": None}
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_project_is_made_once_in_digital_and_linked_back(self):
        result = proposals_api.create_project_from_proposal("PROP-2026-00042")
        project = frappe.get_doc("Project", result["project"])
        self.assertEqual(
            (
                project.custom_department,
                project.project_type,
                str(project.expected_start_date),
                project.custom_crm_proposal,
                project.custom_crm_lead,
            ),
            (
                "Digital",
                "Content Calendar",
                "2026-11-02",
                "PROP-2026-00042",
                "CRM-LEAD-42",
            ),
        )
        link = next(p for m, _post, p in self.crm.lead_calls if m == "link_project")
        self.assertEqual(
            (link["project"], link["proposal"], link["lead"]),
            (project.name, "PROP-2026-00042", "CRM-LEAD-42"),
        )
        again = proposals_api.create_project_from_proposal("PROP-2026-00042")
        self.assertEqual(again["project"], project.name)

    def test_an_older_erp_site_is_told_plainly(self):
        self.crm.lead_answers["get_accepted_proposal"] = None
        with patch.object(proposals_api, "call_if_deployed", return_value=None):
            with self.assertRaises(frappe.ValidationError):
                proposals_api.create_project_from_proposal("PROP-2026-00042")
