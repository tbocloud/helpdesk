import base64
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import proposals as proposals_api
from helpdesk.integrations.crm.client import CRMError
from helpdesk.integrations.crm.leads import LeadsError
from helpdesk.test_utils import (
    FakeCRM,
    create_agent,
    enable_leads,
    hold_commits,
    make_team,
)

BDE = "bde.agent@proposals.example"
SUPPORT = "support.agent@proposals.example"
TEAM = "Proposals Test Sales"
FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
PROPOSALS = "tbo_smart.api.hub_proposals"
LEADS = "tbo_smart.api.hub_leads"


class TestProposals(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        create_agent(BDE, "Bina", "BDE")
        create_agent(SUPPORT, "Sunil", "Support")
        make_team(TEAM, [BDE])
        enable_leads(teams=(TEAM,))
        self.crm = FakeCRM()
        self.crm.lead_answers["get_proposal"] = {"name": "PROP-2026-00001"}
        patcher = patch(FROM_SETTINGS, return_value=self.crm)
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.set_user(BDE)

    def test_only_people_who_use_leads(self):
        frappe.set_user(SUPPORT)
        for call in (
            lambda: proposals_api.get_proposal("PROP-2026-00001"),
            lambda: proposals_api.get_rate_card(),
            lambda: proposals_api.save_template({"template_name": "x"}),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()
        self.assertEqual(self.crm.lead_calls, [])

    def test_reads_and_writes_go_to_the_proposals_api_as_the_person(self):
        self.assertEqual(
            proposals_api.get_proposal("PROP-2026-00001"), {"name": "PROP-2026-00001"}
        )
        proposals_api.create_proposal("CRM-LEAD-1", "ERPNext Implementation", "1")
        proposals_api.save_proposal("PROP-2026-00001", '{"title": "Spice ERP"}')
        proposals_api.save_pricing(
            "PROP-2026-00001", {"items": [{"item_code": "Setup", "qty": 1}]}
        )
        proposals_api.send_proposal(
            "PROP-2026-00001", recipients="  ", message=" Hi ", attach_pdf="1"
        )

        self.assertTrue(all(path.startswith(PROPOSALS) for path in self.crm.lead_paths))
        calls = {name: (post, params) for name, post, params in self.crm.lead_calls}
        self.assertEqual(calls["get_proposal"][0], False)
        self.assertTrue(
            all(calls[name][0] for name in calls if name != "get_proposal"),
            "writes are posted",
        )
        self.assertTrue(
            all(params["acting_user"] == BDE for _post, params in calls.values())
        )
        self.assertEqual(calls["create_proposal"][1]["ai_draft"], 1)
        self.assertEqual(calls["save_proposal"][1]["data"], {"title": "Spice ERP"})
        self.assertEqual(
            calls["send_proposal"][1],
            {
                "name": "PROP-2026-00001",
                "recipients": None,
                "message": "Hi",
                "attach_pdf": 1,
                "acting_user": BDE,
            },
        )

    def test_the_rate_card_is_on_the_leads_api(self):
        proposals_api.get_rate_card()
        proposals_api.save_rate_card('[{"segment": "Premium", "max_discount": 10}]')
        proposals_api.set_segment_rate("Setup", 90000, "Premium")
        self.assertTrue(all(path.startswith(LEADS) for path in self.crm.lead_paths))
        ((_n, _p, card), (_n2, post, rows), (_n3, _p3, rate)) = self.crm.lead_calls
        self.assertTrue(post)
        self.assertEqual(rows["rows"], [{"segment": "Premium", "max_discount": 10}])
        self.assertEqual((rate["segment"], rate["rate"]), ("Premium", 90000))
        with self.assertRaises(frappe.ValidationError):
            proposals_api.save_rate_card('{"segment": "Premium"}')

    def test_request_approval_needs_a_reason(self):
        with self.assertRaises(frappe.ValidationError):
            proposals_api.request_approval("PROP-2026-00001", "  ")
        self.assertEqual(self.crm.lead_calls, [])

    def test_the_erp_sites_reason_reaches_the_page(self):
        self.crm.lead_error = CRMError(
            "417",
            417,
            "ValidationError",
            "The pricing's discount of 12% is above your limit (5%).",
        )
        with self.assertRaises(LeadsError) as caught:
            proposals_api.send_proposal("PROP-2026-00001")
        self.assertIn("above your limit", str(caught.exception))

    def test_an_image_upload_is_checked_then_sent_on(self):
        self.crm.lead_answers["upload_proposal_image"] = {"file": "abc", "url": "u"}
        content = base64.b64encode(b"\x89PNG small").decode()
        self.assertEqual(
            proposals_api.upload_proposal_image("PROP-2026-00001", "a.png", content),
            {"file": "abc", "url": "u"},
        )
        ((name, post, params),) = self.crm.lead_calls
        self.assertEqual((name, post), ("upload_proposal_image", True))
        self.assertEqual((params["content"], params["acting_user"]), (content, BDE))
        too_big = base64.b64encode(b"0" * (proposals_api.MAX_IMAGE_BYTES + 1)).decode()
        for bad in (too_big, "%%%", ""):
            with self.assertRaises(frappe.ValidationError):
                proposals_api.upload_proposal_image("PROP-2026-00001", "a.png", bad)
        self.assertEqual(len(self.crm.lead_calls), 1)
        frappe.set_user(SUPPORT)
        with self.assertRaises(frappe.PermissionError):
            proposals_api.upload_proposal_image("PROP-2026-00001", "a.png", content)

    def test_the_default_letter_head_is_set_on_the_erp_site(self):
        proposals_api.set_default_letter_head("")
        ((name, post, params),) = self.crm.lead_calls
        self.assertEqual(
            (name, post, params["letter_head"]), ("set_default_letter_head", True, None)
        )

    def test_the_letter_heads_html_is_sanitised_for_the_preview(self):
        self.crm.lead_answers["get_proposal"] = {
            "name": "PROP-2026-00001",
            "letter_head_preview": {
                "name": "TBO",
                "header": {"html": '<p onclick="x()">TBO<script>alert(1)</script></p>'},
                "footer": {
                    "image": "https://erp.example/files/f.png",
                    "align": "center",
                },
            },
        }
        head = proposals_api.get_proposal("PROP-2026-00001")["letter_head_preview"]
        self.assertIn("TBO", head["header"]["html"])
        self.assertNotIn("<script", head["header"]["html"])
        self.assertNotIn("onclick", head["header"]["html"])
        self.assertEqual(head["footer"]["align"], "center")

    def test_the_new_proposal_flow_goes_to_the_erp_site(self):
        proposals_api.get_client_profile("CRM-LEAD-1")
        proposals_api.read_client_website("CRM-LEAD-1", " client.example ", "1")
        proposals_api.get_requirements_from_lead("CRM-LEAD-1")
        proposals_api.extract_requirements("CRM-LEAD-1", " HR and Accounts ")
        proposals_api.create_proposal(
            "CRM-LEAD-1",
            "ERPNext Implementation",
            1,
            {"modules": ["Accounts"]},
            " Need HR ",
            {"industry": "Spice export", "pain_points": "Payroll"},
        )
        calls = {name: (post, params) for name, post, params in self.crm.lead_calls}
        self.assertEqual(calls["read_client_website"][1]["url"], "client.example")
        self.assertEqual(calls["read_client_website"][1]["refresh"], 1)
        self.assertEqual(calls["extract_requirements"][1]["text"], "HR and Accounts")
        create = calls["create_proposal"][1]
        self.assertEqual(create["scoping"], {"modules": ["Accounts"]})
        self.assertEqual(create["requirements"], "Need HR")
        self.assertEqual(create["client_profile"]["industry"], "Spice export")
        self.assertFalse(calls["get_client_profile"][0])
        self.assertTrue(
            all(calls[n][0] for n in ("read_client_website", "extract_requirements"))
        )
        with self.assertRaises(frappe.ValidationError):
            proposals_api.extract_requirements("CRM-LEAD-1", "  ")

    def test_regenerate_share_and_libraries_go_to_the_erp_site(self):
        proposals_api.regenerate_section("PROP-2026-00001", "3", "1")
        proposals_api.regenerate_proposal("PROP-2026-00001")
        proposals_api.price_from_modules("PROP-2026-00001")
        proposals_api.share_proposal("PROP-2026-00001")
        proposals_api.use_library_image("PROP-2026-00001", "IMG-1")
        proposals_api.get_proposal_library()
        proposals_api.save_library_record("item", '{"library": "Risk", "title": "x"}')
        proposals_api.delete_library_record("item", "LIB-1")
        proposals_api.draft_library_module("Accounts")
        proposals_api.chat_edit("PROP-2026-00001", "  add Payroll  ")
        calls = {name: (post, params) for name, post, params in self.crm.lead_calls}
        self.assertEqual(
            (
                calls["regenerate_section"][1]["index"],
                calls["regenerate_section"][1]["force"],
            ),
            (3, 1),
        )
        self.assertEqual(calls["regenerate_proposal"][1]["force"], 0)
        self.assertEqual(
            calls["save_library_record"][1]["data"], {"library": "Risk", "title": "x"}
        )
        self.assertFalse(calls["get_proposal_library"][0])
        self.assertEqual(calls["chat_edit"][1]["message"], "add Payroll")
        with self.assertRaises(frappe.ValidationError):
            proposals_api.chat_edit("PROP-2026-00001", " ")
        self.assertTrue(
            all(
                calls[n][0]
                for n in (
                    "regenerate_section",
                    "regenerate_proposal",
                    "price_from_modules",
                    "share_proposal",
                    "use_library_image",
                    "save_library_record",
                    "delete_library_record",
                    "draft_library_module",
                    "chat_edit",
                )
            )
        )
        too_big = base64.b64encode(b"0" * (proposals_api.MAX_IMAGE_BYTES + 1)).decode()
        with self.assertRaises(frappe.ValidationError):
            proposals_api.upload_library_image("a.png", too_big, {"title": "x"})

    def test_documents_after_the_proposal_go_to_the_erp_site(self):
        self.crm.lead_answers["create_document"] = {
            "proposal": {"name": "QUOT-2026-00001"},
            "warnings": [],
        }
        result = proposals_api.create_document("PROP-2026-00001", "Quotation")
        self.assertEqual(result["proposal"]["name"], "QUOT-2026-00001")
        proposals_api.get_document_chain("CRM-LEAD-1")
        with self.assertRaises(frappe.ValidationError):
            proposals_api.create_document("PROP-2026-00001", "Invoice")
        calls = {name: (post, params) for name, post, params in self.crm.lead_calls}
        self.assertEqual(
            calls["create_document"],
            (
                True,
                {
                    "source": "PROP-2026-00001",
                    "document_type": "Quotation",
                    "acting_user": BDE,
                },
            ),
        )
        self.assertEqual(
            calls["get_document_chain"],
            (False, {"lead": "CRM-LEAD-1", "acting_user": BDE}),
        )

    def test_text_that_isnt_a_website_is_refused_here(self):
        for typed in ("build propsol", "not a site", "http://", "client"):
            with self.assertRaises(frappe.ValidationError) as caught:
                proposals_api.read_client_website("CRM-LEAD-1", typed)
            self.assertIn("doesn't look like a website", str(caught.exception))
        self.assertEqual(self.crm.lead_calls, [])
        for typed in ("vasthubuilders.com", "https://www.client.co.in/about"):
            proposals_api.read_client_website("CRM-LEAD-1", typed)
        self.assertEqual(
            [params["url"] for _n, _p, params in self.crm.lead_calls],
            ["vasthubuilders.com", "https://www.client.co.in/about"],
        )
