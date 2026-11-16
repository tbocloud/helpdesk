from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import leads as leads_api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    make_team,
)

BDE = "bde.agent@files.example"
SUPPORT = "support.agent@files.example"
TEAM = "Files Test Sales"
LEAD = "CRM-LEAD-0001"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
FILE = {"name": "f1", "file_name": "requirements.pdf", "can_delete": True}


class TestLeadFiles(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "BDE")
        create_agent(SUPPORT, "Sunil", "Support")
        make_team(TEAM, [BDE])
        enable_leads((TEAM,))
        self.crm = FakeCRM()
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(BDE)

    def serve(self, kind, filename="requirements.pdf"):
        self.crm.lead_answers["get_lead_file"] = (b"bytes", kind)
        leads_api.lead_file(LEAD, "f1", filename=filename)
        return frappe.local.response

    def test_files_are_listed_from_the_erp_site(self):
        self.crm.lead_answers["get_lead_files"] = [FILE]
        self.assertEqual(
            leads_api.get_lead_files(LEAD), {"available": True, "files": [FILE]}
        )
        self.assertEqual(self.crm.lead_calls[0][0], "get_lead_files")
        self.assertEqual(self.crm.lead_calls[0][2]["lead"], LEAD)

    def test_the_card_stays_out_while_the_erp_site_is_older(self):
        self.crm.lead_error = CRMError(
            "no",
            404,
            "Failed to get method for command tbo_smart.api.hub_leads.get_lead_files",
        )
        self.assertEqual(
            leads_api.get_lead_files(LEAD), {"available": False, "files": []}
        )

    def test_a_person_without_leads_gets_nothing(self):
        frappe.set_user(SUPPORT)
        for method, args in (
            (leads_api.get_lead_files, (LEAD,)),
            (leads_api.lead_file, (LEAD, "f1")),
            (leads_api.upload_lead_file, (LEAD, "a.pdf", "aGVsbG8=")),
            (leads_api.delete_lead_file, (LEAD, "f1")),
        ):
            with self.assertRaises(frappe.PermissionError):
                method(*args)
        self.assertEqual(self.crm.lead_calls, [])

    def test_an_upload_is_passed_on(self):
        self.crm.lead_answers["upload_lead_file"] = FILE
        self.assertEqual(
            leads_api.upload_lead_file(LEAD, " requirements.pdf ", "aGVsbG8="), FILE
        )
        method, post, params = self.crm.lead_calls[0]
        self.assertEqual((method, post), ("upload_lead_file", True))
        self.assertEqual(params["filename"], "requirements.pdf")
        self.assertEqual(params["content"], "aGVsbG8=")

    def test_an_empty_or_huge_upload_never_leaves_the_hub(self):
        for content in ("", "A" * (leads_api.MAX_PHOTO_BASE64 + 1)):
            with self.assertRaises(frappe.ValidationError):
                leads_api.upload_lead_file(LEAD, "a.pdf", content)
        self.assertEqual(self.crm.lead_calls, [])

    def test_the_erp_sites_refusal_reaches_the_person(self):
        self.crm.lead_error = CRMError(
            "no",
            417,
            "detail",
            "Attach a PDF, Word, Excel, PowerPoint, CSV, text, image or ZIP file.",
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            leads_api.upload_lead_file(LEAD, "a.exe", "aGVsbG8=")
        self.assertIn("Attach a PDF", str(caught.exception))

    def test_a_file_is_deleted_on_the_erp_site(self):
        self.crm.lead_answers["delete_lead_file"] = {"deleted": "f1"}
        self.assertEqual(leads_api.delete_lead_file(LEAD, "f1"), {"deleted": "f1"})
        self.assertEqual(self.crm.lead_calls[0][:2], ("delete_lead_file", True))

    def test_a_pdf_or_a_picture_opens_in_the_browser(self):
        for kind in ("application/pdf", "image/png", "image/jpeg", "image/webp"):
            response = self.serve(kind)
            self.assertEqual(response.content_type, kind)
            self.assertEqual(response.display_content_as, "inline")
            self.assertEqual(response.filecontent, b"bytes")

    def test_anything_else_is_only_saved(self):
        for kind in (
            "text/html",
            "image/svg+xml",
            "application/vnd.ms-excel",
            "application/octet-stream",
            "",
        ):
            response = self.serve(kind)
            self.assertEqual(response.content_type, "application/octet-stream")
            self.assertEqual(response.display_content_as, "attachment")

    def test_the_saved_name_is_cleaned(self):
        self.assertEqual(
            self.serve("application/pdf", 'a/b\\c:"d".pdf').filename, "abcd.pdf"
        )
        self.assertEqual(self.serve("application/pdf", None).filename, "f1")
