# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime, nowdate

from helpdesk.api import project_signoff as api
from helpdesk.api import signoff_portal as portal
from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
    HDProjectSignoff,
)
from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
    DEFAULT_TEMPLATES,
    ensure_default_signoff_templates,
)
from helpdesk.test_utils import (
    FakeCRM,
    create_customer,
    fake_pdf_renderer,
    fake_request,
    get_reminder_messages,
    hold_commits,
    make_portal_contact,
    make_project,
    make_signoff,
    make_signoff_template,
    make_tasky_user,
    open_signoff_link,
    run_as_user,
    signoff_session,
)

CUSTOMER = "Malabar Spices Trading"
SIGNATORY = "accounts.head@malabar-spices.example"
OTHER_CONTACT = "store.keeper@malabar-spices.example"
PM = ("pm.signoff@signoff-tests.example", "Anjali Pillai")
LEAD = ("lead.signoff@signoff-tests.example", "Rahul Nair")
TRAINER = ("trainer.signoff@signoff-tests.example", "Meera Joseph")
OUTSIDER = ("outsider.signoff@signoff-tests.example", "Vivek Kumar")
TEMPLATE = "Accounts (signoff tests)"
QUESTIONS = [
    ("Sales", "I can convert a Quotation to a Sales Order and a Sales Invoice."),
    ("Payments", "I can record a Payment Entry against an invoice."),
    ("Reports", "I can read the Accounts Receivable report."),
]


class TestProjectSignoff(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        mail = patch("frappe.sendmail")
        self.sendmail = mail.start()
        self.addCleanup(mail.stop)

        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (LEAD, TRAINER, OUTSIDER):
            make_tasky_user(*user)
        create_customer(CUSTOMER)
        self.contact = make_portal_contact(CUSTOMER, SIGNATORY)
        self.other_contact = make_portal_contact(CUSTOMER, OTHER_CONTACT)
        self.project = make_project(
            "Signoff - Malabar ERP rollout",
            members=[(PM[0], "Project Manager"), (TRAINER[0], "Functional Consultant")],
            owner=PM[0],
        ).name
        frappe.db.set_value(
            "Project", self.project, {"customer": CUSTOMER, "project_lead": LEAD[0]}
        )
        make_signoff_template(TEMPLATE, QUESTIONS)

    # --- steps of the flow, as the customer or the team takes them ---

    def signoff(self, **values):
        return make_signoff(self.project, self.contact, TRAINER[0], TEMPLATE, **values)

    def sent(self, **values):
        doc = self.signoff(**values)
        token = open_signoff_link(doc)
        return doc, token

    def answer(self, doc, token, item, response, comment=""):
        with signoff_session(doc):
            return run_as_user(
                "Guest",
                lambda: portal.save_response(token, item, response, comment),
            )

    def answer_all_done(self, doc, token):
        for row in frappe.get_doc(doc.doctype, doc.name).items:
            self.answer(doc, token, row.name, "Done")
        return frappe.get_doc(doc.doctype, doc.name)

    def sign(self, doc, token, email=None):
        with signoff_session(doc, email):
            with fake_pdf_renderer():
                return run_as_user(
                    "Guest",
                    lambda: portal.sign(token, "Fathima Rahman", "Finance Manager", 1),
                )

    # --- templates ---

    def test_template_questions_are_copied_not_shared(self):
        doc = self.signoff()
        self.assertEqual(
            [(r.section, r.question, r.response) for r in doc.items],
            [(s, q, "Pending") for s, q in QUESTIONS],
        )
        self.assertEqual(doc.status, "Draft")
        self.assertEqual(doc.signatory_email, SIGNATORY)

        template = frappe.get_doc("HD Signoff Template", TEMPLATE)
        template.items[0].question = "Changed later"
        template.save()
        self.assertEqual(
            frappe.get_doc(doc.doctype, doc.name).items[0].question, QUESTIONS[0][1]
        )

    def test_default_templates_are_seeded_once(self):
        ensure_default_signoff_templates()
        for template in DEFAULT_TEMPLATES:
            self.assertTrue(
                frappe.db.exists("HD Signoff Template", template["template_name"])
            )
        self.assertEqual(ensure_default_signoff_templates(), [])
        accounts = frappe.get_doc("HD Signoff Template", "Accounts")
        self.assertEqual(
            sorted({r.section for r in accounts.items}),
            ["Payments", "Purchase", "Reports", "Sales"],
        )

    def test_signatory_must_be_a_contact_of_the_customer(self):
        stranger = make_portal_contact(
            create_customer("Other Co").name, "x@other.example"
        )
        with self.assertRaises(frappe.ValidationError):
            make_signoff(self.project, stranger, TRAINER[0], TEMPLATE)

    # --- link and code ---

    def test_link_token_is_stored_hashed_and_replaced_by_a_new_link(self):
        doc, token = self.sent()
        self.assertEqual(doc.link_token_hash, HDProjectSignoff.hash_token(token))
        self.assertNotIn(token, frappe.as_json(doc.as_dict()))
        self.assertEqual(portal.find_signoff(token).name, doc.name)

        new_token = open_signoff_link(doc)
        self.assertIsNone(portal.find_signoff(token))
        self.assertEqual(portal.link_state(portal.find_signoff(new_token)), "open")

    def test_code_goes_to_the_signatory_and_works_once(self):
        doc, token = self.sent()
        frappe.cache.delete_value(portal.otp_key(doc.name))
        self.addCleanup(frappe.cache.delete_value, portal.otp_key(doc.name))

        sent = run_as_user("Guest", lambda: portal.request_code(token))
        self.assertTrue(sent["success"])
        self.assertEqual(self.sendmail.call_args.kwargs["recipients"], [SIGNATORY])
        code = frappe.cache.get_value(portal.otp_key(doc.name))["otp"]
        wrong = "000000" if code != "000000" else "111111"

        with patch.object(portal, "start_session") as start:
            self.assertFalse(portal.verify_code(token, wrong)["success"])
            self.assertTrue(portal.verify_code(token, code)["success"])
            start.assert_called_once()
            self.assertFalse(portal.verify_code(token, code)["success"])

    def test_code_locks_after_too_many_wrong_tries_and_expires(self):
        doc, token = self.sent()
        key = portal.otp_key(doc.name)
        self.addCleanup(frappe.cache.delete_value, key)
        frappe.cache.set_value(
            key,
            {
                "otp": "123456",
                "sent_at": str(now_datetime()),
                "attempts": portal.OTP_MAX_ATTEMPTS,
            },
            expires_in_sec=60,
        )
        with patch.object(portal, "start_session") as start:
            self.assertFalse(portal.verify_code(token, "123456")["success"])
            # the locked code is gone: asking again says it expired
            self.assertIn("expired", portal.verify_code(token, "123456")["message"])
            start.assert_not_called()

    def test_expired_or_revoked_link_is_refused(self):
        doc, token = self.sent()
        doc.db_set("link_expires_on", add_days(now_datetime(), -1))
        with self.assertRaises(frappe.PermissionError):
            portal.request_code(token)
        self.assertEqual(portal.page_data(token)["state"], "expired")

        doc, token = self.sent(module_title="Stock")
        doc.revoke_link()
        doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            portal.request_code(token)
        self.assertEqual(portal.page_data(token)["state"], "invalid")

    def test_session_is_bound_to_its_signoff_token_and_signatory(self):
        doc, token = self.sent()
        other, other_token = self.sent(module_title="Stock")
        sid = "test-session-id"
        fake_request(self, {portal.SESSION_COOKIE: sid})
        self.addCleanup(frappe.cache.delete_value, portal.session_key(sid))
        frappe.cache.set_value(
            portal.session_key(sid),
            {
                "signoff": doc.name,
                "token_hash": doc.link_token_hash,
                "email": SIGNATORY,
            },
            expires_in_sec=60,
        )

        self.assertTrue(portal.get_session(doc))
        self.assertEqual(portal.page_data(token)["state"], "open")
        # the same browser can't use that session for another sign-off
        self.assertIsNone(portal.get_session(other))
        self.assertEqual(portal.page_data(other_token)["state"], "code")
        with self.assertRaises(frappe.AuthenticationError):
            portal.require_session(other_token)

        # a new link ends sessions opened with the old one
        doc.link_token_hash = HDProjectSignoff.hash_token("a-newer-token-" * 3)
        self.assertIsNone(portal.get_session(doc))

    def test_customer_view_has_no_internal_details(self):
        doc, _token = self.sent()
        view = portal.customer_view(doc)
        self.assertEqual(len(view["items"]), 3)
        for key in ("log", "audit_ref", "signer_ip", "link_token_hash", "project"):
            self.assertNotIn(key, view)
        self.assertNotIn("clarification_task", view["items"][0])

    # --- answers and clarification ---

    def test_not_clear_creates_a_task_for_the_trainer_and_notifies(self):
        doc, token = self.sent()
        item = doc.items[1].name
        with self.assertRaises(frappe.ValidationError):
            self.answer(doc, token, item, "Not clear")  # a comment is required

        view = self.answer(doc, token, item, "Not clear", "Allocation of advances?")
        self.assertEqual(view["status"], "Needs clarification")
        doc.reload()
        task = frappe.get_doc("Task", doc.items[1].clarification_task)
        self.assertEqual(task.project, self.project)
        self.assertTrue(task.subject.startswith("Clarify: I can record a Payment"))
        self.assertIn(
            TRAINER[0],
            frappe.parse_json(frappe.db.get_value("Task", task.name, "_assign")),
        )
        self.assertTrue(get_reminder_messages(TRAINER[0], doc.name))
        self.assertTrue(get_reminder_messages(LEAD[0], doc.name))
        self.assertFalse(get_reminder_messages(PM[0], doc.name))

    def test_escalate_is_urgent_and_reaches_project_managers(self):
        doc, token = self.sent()
        self.answer(doc, token, doc.items[0].name, "Escalated", "Invoice prints wrong")
        doc.reload()
        task = frappe.get_doc("Task", doc.items[0].clarification_task)
        self.assertEqual(task.priority, "Urgent")
        self.assertTrue(get_reminder_messages(PM[0], doc.name))

    def test_escalating_an_open_task_makes_it_urgent_and_due_tomorrow(self):
        doc, token = self.sent()
        item = doc.items[0].name
        self.answer(doc, token, item, "Not clear", "Which invoice type?")
        doc.reload()
        task = doc.items[0].clarification_task
        self.assertEqual(frappe.db.get_value("Task", task, "priority"), "High")

        self.answer(doc, token, item, "Escalated", "Still unclear after the call")
        doc.reload()
        self.assertEqual(doc.items[0].clarification_task, task)
        self.assertEqual(
            frappe.db.get_value("Task", task, ["priority", "exp_end_date"]),
            ("Urgent", getdate(add_days(nowdate(), 1))),
        )

    def test_a_draft_without_questions_saves_but_cannot_be_sent(self):
        doc = make_signoff(self.project, self.contact, TRAINER[0], module_title="HR")
        self.assertEqual(len(doc.items), 0)
        with self.assertRaises(frappe.ValidationError):
            open_signoff_link(doc)

    def test_rewording_a_question_clears_its_answer(self):
        doc, token = self.sent()
        self.answer(doc, token, doc.items[0].name, "Not clear", "Which invoice type?")
        doc.reload()
        # editable again, as after a reopen
        doc.db_set("status", "Reopened")
        items = [
            {"name": r.name, "section": r.section, "question": r.question}
            for r in doc.items
        ]
        items[0]["question"] = "I can make a Sales Invoice with a discount."
        run_as_user(
            PM[0],
            lambda: api.update_signoff(
                doc.name, "Accounts", self.contact, TRAINER[0], items
            ),
        )
        row = frappe.get_doc(doc.doctype, doc.name).items[0]
        self.assertEqual(
            (row.response, row.customer_comment, row.clarification_task),
            ("Pending", None, None),
        )

    def test_marking_clarified_returns_the_item_and_emails_a_new_link(self):
        doc, token = self.sent()
        item = doc.items[1].name
        self.answer(doc, token, item, "Not clear", "Allocation of advances?")
        doc.reload()
        task = doc.items[1].clarification_task

        self.sendmail.reset_mock()
        run_as_user(
            TRAINER[0],
            lambda: api.mark_item_clarified(
                doc.name, item, "We went through it on a call."
            ),
        )
        doc.reload()
        self.assertEqual(doc.items[1].response, "Pending")
        self.assertEqual(doc.items[1].clarified_by, TRAINER[0])
        self.assertEqual(doc.status, "Sent")
        self.assertIn(
            frappe.db.get_value("Task", task, "status"), ("Completed", "Pending Review")
        )
        self.assertEqual(self.sendmail.call_args.kwargs["recipients"], [SIGNATORY])
        # the email carries a new link; the old one no longer opens the sign-off
        self.assertIsNone(portal.find_signoff(token))
        self.assertIn("Clarified", [row.event for row in doc.log])

    def test_completing_the_task_clarifies_the_item(self):
        doc, token = self.sent()
        self.answer(doc, token, doc.items[0].name, "Not clear", "Which invoice type?")
        doc.reload()
        task = frappe.get_doc("Task", doc.items[0].clarification_task)
        task.status = "Completed"
        task.save(ignore_permissions=True)
        doc.reload()
        self.assertEqual(doc.items[0].response, "Pending")
        self.assertTrue(doc.items[0].clarified_on)

    # --- signing ---

    def test_signing_needs_every_item_done_and_the_signatory(self):
        doc, token = self.sent()
        self.answer(doc, token, doc.items[0].name, "Done")
        with self.assertRaises(frappe.ValidationError):
            self.sign(doc, token)

        doc = self.answer_all_done(doc, token)
        self.assertEqual(doc.status, "Ready to sign")
        with self.assertRaises(frappe.PermissionError):
            self.sign(doc, token, email=OTHER_CONTACT)

    def test_signing_saves_the_pdf_on_the_project_and_locks(self):
        doc, token = self.sent()
        doc = self.answer_all_done(doc, token)
        view = self.sign(doc, token)
        self.assertEqual(view["status"], "Signed")

        doc.reload()
        self.assertEqual(
            (doc.signer_name, doc.signer_designation, doc.signer_email),
            ("Fathima Rahman", "Finance Manager", SIGNATORY),
        )
        self.assertEqual(len(doc.audit_ref), 64)
        pdf = frappe.get_doc("File", doc.signed_pdf)
        self.assertEqual(
            (pdf.attached_to_doctype, pdf.attached_to_name, pdf.is_private),
            ("Project", self.project, 1),
        )
        self.assertTrue(pdf.file_name.endswith(".pdf"))

        with self.assertRaises(frappe.ValidationError):
            self.answer(doc, token, doc.items[0].name, "Not clear", "Changed my mind")
        doc.items[0].question = "Edited after signing"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_reopen_needs_a_reason_and_is_logged(self):
        doc, token = self.sent()
        self.sign(self.answer_all_done(doc, token), token)
        doc.reload()
        with self.assertRaises(frappe.ValidationError):
            run_as_user(PM[0], lambda: api.reopen_signoff(doc.name, " "))

        run_as_user(PM[0], lambda: api.reopen_signoff(doc.name, "Add the GST report"))
        doc.reload()
        self.assertEqual(doc.status, "Reopened")
        self.assertIsNone(doc.signed_on)
        reopened = [row for row in doc.log if row.event == "Reopened"]
        self.assertIn("Add the GST report", reopened[0].detail)
        self.assertEqual(reopened[0].by_email, PM[0])

    def test_completion_letter_once_every_signoff_is_signed(self):
        first, first_token = self.sent()
        second, second_token = self.sent(module_title="Stock")

        self.sign(self.answer_all_done(first, first_token), first_token)
        self.assertFalse(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )
        rollup = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertEqual((rollup["signed"], rollup["total"]), (1, 2))
        self.assertIsNone(rollup["completion_letter"])

        self.sign(self.answer_all_done(second, second_token), second_token)
        letter = frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        self.assertTrue(letter)
        self.assertEqual(
            frappe.db.get_value("File", letter, "attached_to_name"), self.project
        )
        rollup = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertEqual(rollup["completion_letter"]["name"], letter)

    # --- permissions ---

    def test_members_view_and_only_managers_or_the_trainer_act(self):
        doc = self.signoff()
        member = run_as_user(TRAINER[0], lambda: api.get_project_signoffs(self.project))
        self.assertEqual([s["name"] for s in member["signoffs"]], [doc.name])
        self.assertFalse(member["can_create"])

        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_project_signoffs(self.project))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_signoff(doc.name))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                TRAINER[0],
                lambda: api.create_signoff(
                    self.project, "HR", self.contact, TRAINER[0]
                ),
            )

        # the trainer runs their own sign-off; the lead and the manager may too
        run_as_user(TRAINER[0], lambda: api.send_signoff_link(doc.name))
        self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "status"), "Sent")
        created = run_as_user(
            LEAD[0],
            lambda: api.create_signoff(self.project, "HR", self.contact, TRAINER[0]),
        )
        self.assertTrue(frappe.db.exists(doc.doctype, created["name"]))

    def test_only_project_managers_edit_templates(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(TRAINER[0], api.get_signoff_templates)
        saved = run_as_user(
            PM[0],
            lambda: api.save_signoff_template(
                "Projects (signoff tests)",
                [{"section": "Tasks", "question": "I can create a Task."}],
            ),
        )
        self.assertEqual(
            len(frappe.get_doc("HD Signoff Template", saved["name"]).items), 1
        )

    # --- UAT: the client's acceptance tests from the plan's SRS ---

    def uat_project(self):
        """The project as made from an implementation plan, with the ERP site faked."""
        frappe.db.set_value(
            "Project", self.project, "custom_crm_plan", "PIP-2026-00001"
        )
        crm = FakeCRM()
        crm.lead_answers["get_uat_cases"] = {
            "srs": "SRS-2026-00001",
            "cases": [
                {
                    "fr": "FR-ACC-01",
                    "module": "Accounts",
                    "title": "FR-ACC-01: Raise sales invoices with GST",
                    "steps": "1. Sign in.\n2. Raise a sales invoice.",
                    "expected": "The invoice shows CGST and SGST.",
                },
                {
                    "fr": "FR-ACC-02",
                    "module": "Accounts",
                    "title": "FR-ACC-02: Reconcile the bank",
                    "steps": "1. Sign in.\n2. Reconcile.",
                    "expected": "The payment matches the statement line.",
                },
            ],
        }
        crm.lead_answers["record_uat"] = {"steps": [], "next": None}
        patcher = patch(
            "helpdesk.integrations.crm.client.CRMClient.from_settings", return_value=crm
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return crm

    def test_a_uat_is_made_from_the_srs_and_answered_pass_or_fail(self):
        crm = self.uat_project()
        listed = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertTrue(listed["can_create_uat"])
        name = run_as_user(
            PM[0],
            lambda: api.create_uat_signoff(self.project, self.contact, TRAINER[0]),
        )["name"]
        doc = frappe.get_doc("HD Project Signoff", name)
        self.assertEqual((doc.signoff_type, doc.crm_plan), ("UAT", "PIP-2026-00001"))
        self.assertEqual(
            [(row.section, row.question) for row in doc.items],
            [
                ("Accounts", "FR-ACC-01: Raise sales invoices with GST"),
                ("Accounts", "FR-ACC-02: Reconcile the bank"),
            ],
        )
        self.assertIn(
            "Expected: The invoice shows CGST and SGST.", doc.items[0].help_text
        )
        # read on behalf of the project's maker, the person the ERP site knows
        (_name, _post, params) = crm.lead_calls[0]
        self.assertEqual(params["acting_user"], PM[0])
        token = open_signoff_link(doc)
        self.assertEqual(portal.page_data(token)["words"]["done"], "Pass")
        # a Fail is an open issue: a task to fix it
        self.answer(
            doc, token, doc.items[1].name, "Not clear", "The payment didn't match."
        )
        doc.reload()
        task = frappe.get_doc("Task", doc.items[1].clarification_task)
        self.assertTrue(task.subject.startswith("Fix: FR-ACC-02"))
        with self.assertRaises(frappe.ValidationError):
            self.answer(doc, token, doc.items[0].name, "Not clear", "")

    def test_signing_a_uat_is_recorded_on_the_erp_site(self):
        crm = self.uat_project()
        name = run_as_user(
            PM[0],
            lambda: api.create_uat_signoff(self.project, self.contact, TRAINER[0]),
        )["name"]
        doc = frappe.get_doc("HD Project Signoff", name)
        token = open_signoff_link(doc)
        for row in doc.items:
            self.answer(doc, token, row.name, "Done")
        with patch("frappe.enqueue") as enqueue:
            self.sign(frappe.get_doc("HD Project Signoff", name), token)
        self.assertEqual(
            enqueue.call_args.args[0], "helpdesk.api.project_signoff.record_uat_on_erp"
        )
        api.record_uat_on_erp(name)
        (_name, post, params) = crm.lead_calls[-1]
        self.assertTrue(post)
        self.assertEqual(
            (
                params["name"],
                params["status"],
                params["signed_by"],
                params["acting_user"],
            ),
            ("PIP-2026-00001", "Signed", "Fathima Rahman", PM[0]),
        )
        # the training completion letter isn't the UAT's
        self.assertFalse(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )

    def test_a_project_without_a_plan_has_no_uat(self):
        listed = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertFalse(listed["can_create_uat"])
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0],
                lambda: api.create_uat_signoff(self.project, self.contact, TRAINER[0]),
            )
