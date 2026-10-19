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
