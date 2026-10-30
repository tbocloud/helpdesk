from types import SimpleNamespace
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

BDE = "bde.agent@place.example"
SUPPORT = "support.agent@place.example"
TEAM = "Place Test Sales"
LEAD = "CRM-LEAD-0001"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
PHOTO = {"name": "abc123", "file_name": "front.jpg", "caption": "Shop front"}


class TestLeadPlace(FrappeTestCase):
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

    def test_photos_are_listed_from_the_erp_site(self):
        self.crm.lead_answers["get_lead_photos"] = [PHOTO]
        self.assertEqual(
            leads_api.get_lead_photos(LEAD), {"available": True, "photos": [PHOTO]}
        )
        self.assertEqual(self.crm.lead_calls[0][0], "get_lead_photos")
        self.assertEqual(self.crm.lead_calls[0][2]["lead"], LEAD)

    def test_the_card_stays_out_while_the_erp_site_is_older(self):
        self.crm.lead_error = CRMError(
            "no",
            404,
            "Failed to get method for command tbo_smart.api.hub_leads.get_lead_photos",
        )
        self.assertEqual(
            leads_api.get_lead_photos(LEAD), {"available": False, "photos": []}
        )

    def test_a_person_without_leads_gets_nothing(self):
        frappe.set_user(SUPPORT)
        self.crm.lead_answers["get_lead_photos"] = [PHOTO]
        with self.assertRaises(frappe.PermissionError):
            leads_api.get_lead_photos(LEAD)
        with self.assertRaises(frappe.PermissionError):
            leads_api.lead_photo(LEAD, "abc123")
        self.assertEqual(self.crm.lead_calls, [])

    def test_an_upload_is_passed_on_with_a_trimmed_caption(self):
        self.crm.lead_answers["upload_lead_photo"] = PHOTO
        result = leads_api.upload_lead_photo(
            LEAD, "front.jpg", "aGVsbG8=", caption="  Shop front  "
        )
        self.assertEqual(result, PHOTO)
        method, post, params = self.crm.lead_calls[0]
        self.assertEqual((method, post), ("upload_lead_photo", True))
        self.assertEqual(params["caption"], "Shop front")
        self.assertEqual(params["content"], "aGVsbG8=")

    def test_an_empty_or_huge_upload_never_leaves_the_hub(self):
        for content in ("", "A" * (leads_api.MAX_PHOTO_BASE64 + 1)):
            with self.assertRaises(frappe.ValidationError):
                leads_api.upload_lead_photo(LEAD, "x.jpg", content)
        self.assertEqual(self.crm.lead_calls, [])

    def test_the_erp_sites_refusal_reaches_the_person(self):
        self.crm.lead_error = CRMError(
            "no", 417, "detail", "A lead can have 20 photos. Delete one to add another."
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            leads_api.upload_lead_photo(LEAD, "x.jpg", "aGVsbG8=")
        self.assertIn("20 photos", str(caught.exception))

    def test_a_photo_is_deleted_on_the_erp_site(self):
        self.crm.lead_answers["delete_lead_photo"] = {"deleted": "abc123"}
        self.assertEqual(
            leads_api.delete_lead_photo(LEAD, "abc123"), {"deleted": "abc123"}
        )
        self.assertEqual(self.crm.lead_calls[0][:2], ("delete_lead_photo", True))

    def test_the_image_is_streamed_as_the_erp_site_sent_it(self):
        self.crm.lead_answers["get_lead_photo"] = (b"\xff\xd8jpeg", "image/jpeg")
        leads_api.lead_photo(LEAD, "abc123", thumb="1")
        self.assertEqual(frappe.local.response.filecontent, b"\xff\xd8jpeg")
        self.assertEqual(frappe.local.response.content_type, "image/jpeg")
        self.assertEqual(frappe.local.response.display_content_as, "inline")
        self.assertEqual(self.crm.lead_calls[0][2]["thumb"], 1)
        leads_api.lead_photo(LEAD, "abc123")
        self.assertEqual(self.crm.lead_calls[1][2]["thumb"], 0)

    def test_nothing_but_an_image_is_streamed(self):
        for kind in ("text/html", "image/svg+xml", "application/pdf", ""):
            self.crm.lead_answers["get_lead_photo"] = (b"<script>", kind)
            with self.assertRaises(frappe.DoesNotExistError):
                leads_api.lead_photo(LEAD, "abc123")

    def test_a_photo_is_cached_privately_by_the_browser(self):
        def serve(path, status=200):
            response = SimpleNamespace(status_code=status, headers={})
            leads_api.cache_lead_photo(response, SimpleNamespace(path=path))
            return response.headers

        photo = "/api/method/helpdesk.api.leads.lead_photo"
        self.assertEqual(serve(photo), {"Cache-Control": "private, max-age=3600"})
        self.assertEqual(serve(photo, 403), {})
        self.assertEqual(serve("/api/method/helpdesk.api.leads.get_lead"), {})
