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

    def test_a_step_out_of_order_is_made_from_the_lead(self):
        self.crm.lead_answers["create_document"] = {
            "proposal": {"name": "SRS-2026-00001"},
            "warnings": [],
        }
        proposals_api.create_document(document_type="SRS", lead="CRM-LEAD-1")
        # neither a source nor a lead: nothing to make it for
        with self.assertRaises(frappe.ValidationError):
            proposals_api.create_document(document_type="SRS")
        calls = [c for c in self.crm.lead_calls if c[0] == "create_document"]
        self.assertEqual(
            calls,
            [
                (
                    "create_document",
                    True,
                    {"document_type": "SRS", "lead": "CRM-LEAD-1", "acting_user": BDE},
                )
            ],
        )

    def test_skipping_and_bringing_back_go_to_the_erp_site(self):
        chain = {"steps": [], "next": None}
        self.crm.lead_answers["skip_steps"] = chain
        self.crm.lead_answers["bring_back_step"] = chain
        self.assertEqual(
            proposals_api.skip_steps(
                "CRM-LEAD-1", '["Proposal", "BRD"]', "  Repeat client  "
            ),
            chain,
        )
        proposals_api.skip_steps("CRM-LEAD-1", ["SRS"], "Plan only", "Not used")
        proposals_api.bring_back_step("CRM-LEAD-1", "BRD")
        # refused here before anything is sent: no reason, no step, a reason too long,
        # a status that isn't one
        for bad in (
            lambda: proposals_api.skip_steps("CRM-LEAD-1", ["BRD"], "   "),
            lambda: proposals_api.skip_steps("CRM-LEAD-1", [], "Not needed"),
            lambda: proposals_api.skip_steps("CRM-LEAD-1", ["BRD"], "x" * 501),
            lambda: proposals_api.skip_steps("CRM-LEAD-1", ["BRD"], "x", "Done"),
            lambda: proposals_api.skip_steps("CRM-LEAD-1", "BRD", "Not needed"),
        ):
            with self.assertRaises(frappe.ValidationError):
                bad()
        calls = [c for c in self.crm.lead_calls if c[0] != "get_proposal_options"]
        self.assertEqual(
            calls,
            [
                (
                    "skip_steps",
                    True,
                    {
                        "lead": "CRM-LEAD-1",
                        "document_types": '["Proposal","BRD"]',
                        "reason": "Repeat client",
                        "status": "Skipped",
                        "acting_user": BDE,
                    },
                ),
                (
                    "skip_steps",
                    True,
                    {
                        "lead": "CRM-LEAD-1",
                        "document_types": '["SRS"]',
                        "reason": "Plan only",
                        "status": "Not used",
                        "acting_user": BDE,
                    },
                ),
                (
                    "bring_back_step",
                    True,
                    {"lead": "CRM-LEAD-1", "document_type": "BRD", "acting_user": BDE},
                ),
            ],
        )

    def test_the_erp_sites_reason_for_a_refused_skip_reaches_the_page(self):
        self.crm.lead_answers["skip_steps"] = LeadsError(
            "BRD is Sent. It can't be skipped, only revised."
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            proposals_api.skip_steps("CRM-LEAD-1", ["BRD"], "Not needed")
        self.assertIn("only revised", str(caught.exception))

    def test_the_project_straight_from_the_lead(self):
        self.crm.lead_answers["get_lead"] = {
            "lead": {
                "name": "CRM-LEAD-9",
                "company_name": "Malabar Spices",
                "lead_owner": "Administrator",
                "tbo_lead_type": "ERP / Software",
            }
        }
        self.crm.lead_answers["link_project"] = {"steps": [], "next": None}
        frappe.set_user("Administrator")
        result = proposals_api.create_project_from_lead("CRM-LEAD-9")
        project = frappe.get_doc("Project", result["project"])
        self.assertEqual(
            (project.project_name, project.custom_crm_lead, project.custom_crm_plan),
            ("Malabar Spices - ERP / Software", "CRM-LEAD-9", None),
        )
        link = next(c[2] for c in self.crm.lead_calls if c[0] == "link_project")
        self.assertEqual(
            (link["lead"], link["project"], "plan" in link, "proposal" in link),
            ("CRM-LEAD-9", project.name, False, False),
        )
        # again: the same project
        self.assertEqual(
            proposals_api.create_project_from_lead("CRM-LEAD-9")["project"],
            project.name,
        )
        self.assertEqual(
            frappe.db.count("Project", {"custom_crm_lead": "CRM-LEAD-9"}), 1
        )

    def test_a_project_the_erp_site_refuses_is_not_left_behind(self):
        self.crm.lead_answers["get_lead"] = {
            "lead": {
                "name": "CRM-LEAD-8",
                "lead_name": "Asha",
                "lead_owner": "Administrator",
            }
        }
        self.crm.lead_answers["link_project"] = LeadsError(
            "This lead's project is made from its implementation plan."
        )
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.ValidationError):
            proposals_api.create_project_from_lead("CRM-LEAD-8")
        self.assertFalse(frappe.db.exists("Project", {"custom_crm_lead": "CRM-LEAD-8"}))

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

    def test_mark_ready_and_the_chat_answer_go_to_the_erp_site(self):
        proposals_api.finalise_proposal("PROP-2026-00001", "1")
        proposals_api.finalise_proposal("PROP-2026-00001", 0)
        proposals_api.read_chat_answer(
            "CRM-LEAD-1", "What's the client's website?", "  payroll venam  "
        )
        calls = [(name, post, params) for name, post, params in self.crm.lead_calls]
        ready = [
            params["ready"]
            for name, _post, params in calls
            if name == "finalise_proposal"
        ]
        self.assertEqual(ready, [1, 0])
        read = next(
            params for name, _post, params in calls if name == "read_chat_answer"
        )
        self.assertEqual(read["text"], "payroll venam")
        self.assertEqual(read["question"], "What's the client's website?")
        self.assertTrue(all(post for _name, post, _params in calls))
        with self.assertRaises(frappe.ValidationError):
            proposals_api.read_chat_answer("CRM-LEAD-1", "Q", " ")

    def test_the_brd_questionnaire_goes_to_the_erp_site(self):
        proposals_api.save_questions(
            "BRD-2026-00001", '[{"section_type": "Integrations", "question": "Bank?"}]'
        )
        proposals_api.share_questionnaire("BRD-2026-00001")
        proposals_api.send_questionnaire("BRD-2026-00001", " ", " Hello ")
        proposals_api.apply_answers("BRD-2026-00001")
        with self.assertRaises(frappe.ValidationError):
            proposals_api.save_questions("BRD-2026-00001", '{"question": "Bank?"}')
        calls = {name: (post, params) for name, post, params in self.crm.lead_calls}
        self.assertTrue(all(post for post, _params in calls.values()))
        self.assertEqual(
            calls["save_questions"][1]["questions"],
            [{"section_type": "Integrations", "question": "Bank?"}],
        )
        self.assertEqual(
            (
                calls["send_questionnaire"][1]["recipients"],
                calls["send_questionnaire"][1]["message"],
            ),
            (None, "Hello"),
        )
        self.assertEqual(calls["apply_answers"][1]["name"], "BRD-2026-00001")

    def test_the_plans_project_is_made_here_once(self):
        self.crm.lead_answers["get_project_plan"] = {
            "plan": "PIP-2026-00001",
            "lead": "CRM-LEAD-1",
            "client": "Malabar Spices",
            "project_name": "Malabar Spices - ERPNext Implementation",
            "solution_type": "ERPNext Implementation",
            "start": "2026-11-02",
            "end": "2027-01-30",
            "hub_project": None,
            "phases": [
                {
                    "phase": "Analysis",
                    "start": "2026-11-02",
                    "end": "2026-11-11",
                    "tasks": [
                        {
                            "subject": "Accounts: study of the chart of accounts",
                            "start": "2026-11-02",
                            "end": "2026-11-11",
                            "milestone": 0,
                        },
                        {
                            "subject": "Analysis complete",
                            "start": "2026-11-11",
                            "end": "2026-11-11",
                            "milestone": 1,
                        },
                    ],
                }
            ],
        }
        self.crm.lead_answers["link_project"] = {"steps": [], "next": None}
        frappe.set_user("Administrator")
        result = proposals_api.create_project_from_plan("PIP-2026-00001")
        project = frappe.get_doc("Project", result["project"])
        self.assertEqual(
            (
                project.project_type,
                str(project.expected_start_date),
                project.custom_crm_plan,
                project.custom_crm_acting_user,
            ),
            ("ERP Implementation", "2026-11-02", "PIP-2026-00001", "Administrator"),
        )
        tasks = frappe.get_all(
            "Task",
            filters={"project": project.name},
            fields=["subject", "custom_phase", "is_milestone"],
            order_by="creation asc",
        )
        self.assertEqual(
            [(t.custom_phase, t.is_milestone) for t in tasks],
            [("Analysis", 0), ("Analysis", 1)],
        )
        calls = {name: params for name, _post, params in self.crm.lead_calls}
        self.assertEqual(calls["link_project"]["project"], project.name)
        # the ERP's link_project takes the lead and the plan (tbo_smart#56)
        self.assertEqual(calls["link_project"]["plan"], "PIP-2026-00001")
        self.assertNotIn("name", calls["link_project"])
        # again: the same project, no second set of tasks; a missing maker is filled in
        frappe.db.set_value("Project", project.name, "custom_crm_acting_user", None)
        again = proposals_api.create_project_from_plan("PIP-2026-00001")
        self.assertEqual(again["project"], project.name)
        self.assertEqual(frappe.db.count("Task", {"project": project.name}), 2)
        self.assertEqual(
            frappe.db.get_value("Project", project.name, "custom_crm_acting_user"),
            "Administrator",
        )
