# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import re
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, getdate, now_datetime, nowdate

from helpdesk.api import project_signoff as api
from helpdesk.api import signoff_portal as portal
from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
    CODE_VERIFIED,
    HDProjectSignoff,
    send_signoff_reminders,
)
from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
    DEFAULT_TEMPLATES,
    STAGES,
    ensure_default_signoff_templates,
)
from helpdesk.test_utils import (
    EveryDayWorkCalendar,
    FakeCRM,
    blank_pdf,
    create_customer,
    crm_lead_detail,
    enable_leads,
    fake_pdf_renderer,
    fake_request,
    forget_signoff_lead_access,
    get_reminder_messages,
    hold_commits,
    make_customer_address,
    make_portal_contact,
    make_project,
    make_signoff,
    make_signoff_template,
    make_tasky_user,
    open_signoff_link,
    receive_signoff_reply,
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
COORDINATOR = ("coordinator.signoff@signoff-tests.example", "Sneha Varghese")
TEMPLATE = "Accounts (signoff tests)"
UAT_DETAILS = {"uat_site_url": "https://uat.malabar.example"}
# a mail with the questions page's link, as a template would give it
MAIL = {
    "email_subject": "Training sign-off",
    "email_body": "<p>Please confirm the training here: {{ sign_off_link }}</p>",
}
COMMUNICATION_MAKE = "frappe.core.doctype.communication.email._make"
QUESTIONS = [
    ("Sales", "I can convert a Quotation to a Sales Order and a Sales Invoice."),
    ("Payments", "I can record a Payment Entry against an invoice."),
    ("Reports", "I can read the Accounts Receivable report."),
]


class TestProjectSignoff(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        # the one-time code and the completion letter go by frappe.sendmail; the sign-off's
        # own mails are Communications (TBO's Sign-off requirements, Sending the mail)
        mail = patch("frappe.sendmail")
        self.sendmail = mail.start()
        self.addCleanup(mail.stop)
        self.mail_patcher = patch(COMMUNICATION_MAKE)
        self.mail = self.mail_patcher.start()
        self.addCleanup(self.mail_patcher.stop)

        make_tasky_user(*PM, roles=("Project Manager",))
        for user in (LEAD, TRAINER, OUTSIDER, COORDINATOR):
            make_tasky_user(*user)
        create_customer(CUSTOMER)
        self.contact = make_portal_contact(CUSTOMER, SIGNATORY)
        self.other_contact = make_portal_contact(CUSTOMER, OTHER_CONTACT)
        self.project = make_project(
            "Signoff - Malabar ERP rollout",
            members=[
                (PM[0], "Project Manager"),
                (TRAINER[0], "Functional Consultant"),
                (COORDINATOR[0], "Project Coordinator"),
            ],
            owner=PM[0],
        ).name
        frappe.db.set_value(
            "Project", self.project, {"customer": CUSTOMER, "project_lead": LEAD[0]}
        )
        make_signoff_template(TEMPLATE, QUESTIONS)

    # --- steps of the flow, as the customer or the team takes them ---

    def signoff(self, **values):
        return make_signoff(
            self.project, self.contact, TRAINER[0], TEMPLATE, **{**MAIL, **values}
        )

    def sent(self, **values):
        """A sign-off sent by the project manager; the questions link's token from the mail."""
        doc = self.signoff(**values)
        self.mail.reset_mock()
        run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        doc.reload()
        return doc, self.token_in(self.mail.call_args.kwargs["content"])

    @staticmethod
    def token_in(content: str) -> str:
        return re.search(r"token=([\w-]+)", content).group(1)

    def signed_off(self, doc, **values):
        with fake_pdf_renderer():
            run_as_user(PM[0], lambda: api.mark_signed_off(doc.name, **values))
        return frappe.get_doc(doc.doctype, doc.name)

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
            key, {"otp": "123456", "sent_at": str(now_datetime())}, expires_in_sec=60
        )
        # every try so far used (counted atomically, before the check)
        tries = portal.otp_tries_key(doc.name)
        frappe.cache.set(tries, portal.OTP_MAX_ATTEMPTS)
        self.addCleanup(frappe.cache.delete, tries)
        with patch.object(portal, "start_session") as start:
            self.assertFalse(portal.verify_code(token, "123456")["success"])
            # the locked code is gone: asking again says it expired
            self.assertIn("expired", portal.verify_code(token, "123456")["message"])
            start.assert_not_called()

    def test_a_padded_token_opens_nothing(self):
        # the rate limits count by the raw token: a padded one mustn't open the sign-off
        doc, token = self.sent()
        self.assertEqual(portal.find_signoff(token).name, doc.name)
        for padded in (f"{token} ", f" {token}", f"{token}\n"):
            self.assertIsNone(portal.find_signoff(padded))

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
        for key in ("log", "link_token_hash", "project", "signed"):
            self.assertNotIn(key, view)
        self.assertNotIn("clarification_task", view["items"][0])
        # the customer accepts by replying to the mail: there is nothing to sign on the page
        self.assertFalse(hasattr(portal, "sign"))
        self.assertFalse(view["all_done"])
        doc = self.answer_all_done(doc, _token)
        self.assertTrue(portal.customer_view(doc)["all_done"])
        self.assertEqual(doc.status, "Sent")

    # --- answers and clarification ---

    def test_not_clear_creates_a_task_for_the_trainer_and_notifies(self):
        doc, token = self.sent()
        item = doc.items[1].name
        with self.assertRaises(frappe.ValidationError):
            self.answer(doc, token, item, "Not clear")  # a comment is required

        view = self.answer(doc, token, item, "Not clear", "Allocation of advances?")
        # the answers are progress; the status changes only by our actions
        self.assertEqual(view["status"], "Sent")
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

    def test_without_questions_it_is_accepted_by_reply_alone(self):
        doc = make_signoff(
            self.project, self.contact, TRAINER[0], module_title="HR", **MAIL
        )
        self.assertEqual(len(doc.items), 0)
        # the mail links to a questions page there isn't
        with self.assertRaises(frappe.ValidationError):
            run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        doc.reload()
        doc.email_body = "<p>Please reply to confirm the HR training.</p>"
        doc.save(ignore_permissions=True)
        run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        doc.reload()
        self.assertEqual(doc.status, "Sent")
        self.assertFalse(doc.link_token_hash)
        self.assertNotIn("token=", self.mail.call_args.kwargs["content"])

    def test_a_training_needs_its_module(self):
        with self.assertRaises(frappe.ValidationError):
            make_signoff(self.project, self.contact, TRAINER[0], module_title=" ")

    def test_rewording_a_question_clears_its_answer(self):
        doc, token = self.sent()
        self.answer(doc, token, doc.items[0].name, "Not clear", "Which invoice type?")
        doc.reload()
        # editable again, as after the customer asked for changes
        doc.db_set("status", "Changes Requested")
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

        self.mail.reset_mock()
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
        self.assertEqual(self.mail.call_args.kwargs["recipients"], [SIGNATORY])
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

    # --- sending (TBO's Sign-off requirements, Sending the sign-off mail) ---

    def test_sending_mails_the_contact_with_the_document_and_a_snapshot(self):
        address = make_customer_address(CUSTOMER, "Malabar head office")
        doc, token = self.sent(customer_address=address.name, cc_emails=PM[0])
        self.assertEqual((doc.status, doc.link_sent_by), ("Sent", PM[0]))
        mail = self.mail.call_args.kwargs
        self.assertEqual(
            (mail["doctype"], mail["name"], mail["recipients"], mail["cc"]),
            (doc.doctype, doc.name, [SIGNATORY], [PM[0]]),
        )
        self.assertTrue(mail["send_email"])
        self.assertIn(PM[0], mail["sender"])
        # the sign-off document goes along, kept on the project
        self.assertEqual(mail["attachments"], [doc.sent_pdf])
        self.assertEqual(
            frappe.db.get_value("File", doc.sent_pdf, "attached_to_name"), self.project
        )
        self.assertIn("/project-signoff?token=", mail["content"])
        # what the customer got stays as it was, whatever changes later
        self.assertIn("12 Spice Market Road", doc.address_display)
        frappe.db.set_value("Address", address.name, "address_line1", "Moved")
        doc.reload()
        self.assertIn("12 Spice Market Road", doc.address_display)
        # read-only once sent
        doc.email_subject = "Changed after sending"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_without_attach_no_document_goes(self):
        doc, _token = self.sent(attach_pdf=0)
        self.assertFalse(self.mail.call_args.kwargs["attachments"])
        self.assertFalse(doc.sent_pdf)

    def test_the_mail_history_has_what_was_sent_and_received(self):
        # the real thing this once: a Communication, its mail not handed to a server
        self.mail_patcher.stop()
        communication = "frappe.core.doctype.communication.communication.Communication"
        with patch(f"{communication}.get_outgoing_email_account", return_value=True):
            with patch(f"{communication}.send_email"):
                doc = self.signoff()
                run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        self.mail = self.mail_patcher.start()
        with patch("helpdesk.work_reminders.notify_users") as notify:
            receive_signoff_reply(doc, SIGNATORY)
        mails = run_as_user(PM[0], lambda: api.get_signoff_mails(doc.name))
        self.assertEqual(
            sorted(m.sent_or_received for m in mails), ["Received", "Sent"]
        )
        sent = next(m for m in mails if m.sent_or_received == "Sent")
        self.assertEqual(len(sent.attachments), 1)
        # the reply is written down, and who sent it hears
        doc.reload()
        self.assertEqual(doc.log[-1].event, "Reply received")
        self.assertIn(PM[0], notify.call_args.args[0])

    # --- signed off, changes requested, cancelled ---

    def test_mark_signed_off_saves_the_pdf_on_the_project_and_locks(self):
        doc, token = self.sent()
        with patch("helpdesk.work_reminders.notify_users"):
            reply = receive_signoff_reply(doc, SIGNATORY)
        doc = self.signed_off(doc, acceptance_reference=reply.name)
        self.assertEqual(doc.status, "Signed Off")
        # the reply is the evidence, its date the sign-off's
        self.assertEqual(doc.acceptance_reference, reply.name)
        self.assertEqual(
            (doc.signed_off_by, doc.signer_email), (self.contact, SIGNATORY)
        )
        self.assertFalse(doc.link_token_hash)
        pdf = frappe.get_doc("File", doc.signed_pdf)
        self.assertEqual(
            (pdf.attached_to_doctype, pdf.attached_to_name, pdf.is_private),
            ("Project", self.project, 1),
        )
        self.assertTrue(pdf.file_name.endswith(".pdf"))
        # the signed record to the customer, in the sign-off's thread
        self.assertTrue(self.mail.call_args.kwargs["attachments"][0]["fname"])

        # final: no answers, no edits, no deleting
        # the link stopped when it was signed off
        with self.assertRaises(frappe.PermissionError):
            self.answer(doc, token, doc.items[0].name, "Not clear", "Changed my mind")
        doc.items[0].question = "Edited after signing off"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc(doc.doctype, doc.name, ignore_permissions=True)

    def test_only_a_sent_signoff_is_marked_signed_off(self):
        doc = self.signoff()
        with self.assertRaises(frappe.ValidationError):
            self.signed_off(doc)
        doc, _token = self.sent(module_title="Stock")
        with self.assertRaises(frappe.ValidationError):
            self.signed_off(doc, signed_on=str(add_days(nowdate(), 2)))
        # without a reply in the thread, recorded on the date given
        doc = self.signed_off(doc, signed_on=nowdate())
        self.assertEqual((doc.status, doc.acceptance_reference), ("Signed Off", None))

    def test_changes_requested_needs_remarks_and_opens_it_again(self):
        doc, token = self.sent()
        with self.assertRaises(frappe.ValidationError):
            run_as_user(PM[0], lambda: api.mark_changes_requested(doc.name, " "))
        run_as_user(
            PM[0], lambda: api.mark_changes_requested(doc.name, "Add the GST report")
        )
        doc.reload()
        self.assertEqual(
            (doc.status, doc.remarks), ("Changes Requested", "Add the GST report")
        )
        # the questions link stops until it is sent again
        self.assertIsNone(portal.find_signoff(token))
        items = [{"section": "Reports", "question": "I can file the GST return."}]
        run_as_user(
            PM[0],
            lambda: api.update_signoff(
                doc.name, "Accounts", self.contact, TRAINER[0], items, **MAIL
            ),
        )
        run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        doc.reload()
        self.assertEqual((doc.status, doc.remarks), ("Sent", None))
        self.assertEqual(doc.log[-1].event, "Mail sent again")

    def test_only_a_system_manager_cancels_a_signed_off_signoff(self):
        doc, _token = self.sent()
        doc = self.signed_off(doc)
        self.assertTrue(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(PM[0], lambda: api.cancel_signoff(doc.name, "Wrong module"))
        api.cancel_signoff(doc.name, "Wrong module")
        doc.reload()
        self.assertEqual((doc.status, doc.remarks), ("Cancelled", "Wrong module"))
        self.assertFalse(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )

    def test_completion_letter_once_every_signoff_is_signed_off(self):
        first, _token = self.sent()
        second, _token = self.sent(module_title="Stock")

        self.signed_off(first)
        self.assertFalse(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )
        rollup = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertEqual((rollup["signed"], rollup["total"]), (1, 2))
        self.assertIsNone(rollup["completion_letter"])

        self.signed_off(second)
        letter = frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        self.assertTrue(letter)
        self.assertEqual(
            frappe.db.get_value("File", letter, "attached_to_name"), self.project
        )
        rollup = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertEqual(rollup["completion_letter"]["name"], letter)

    def test_old_statuses_are_mapped(self):
        from helpdesk.patches.v16_0_2.signoff_pdf_statuses import execute

        doc = self.signoff()
        for old, new in (
            ("Signed", "Signed Off"),
            ("Reopened", "Changes Requested"),
            ("Ready to sign", "Sent"),
        ):
            frappe.db.set_value(doc.doctype, doc.name, "status", old)
            execute()
            self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "status"), new)

    def test_deleting_the_last_unsigned_draft_makes_the_completion_letter(self):
        doc, _token = self.sent()
        draft = self.signoff(module_title="Stock")
        self.signed_off(doc)
        self.assertFalse(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )
        run_as_user(PM[0], lambda: api.delete_signoff(draft.name))
        self.assertTrue(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )

    # --- permissions ---

    def test_who_creates_who_sends(self):
        # the trainer (a team member) saves drafts but doesn't send
        member = run_as_user(TRAINER[0], lambda: api.get_project_signoffs(self.project))
        self.assertTrue(member["can_create"])
        draft = run_as_user(
            TRAINER[0],
            lambda: api.create_signoff(
                self.project,
                "HR",
                self.contact,
                TRAINER[0],
                template=TEMPLATE,
                **MAIL,
            ),
        )
        self.assertEqual(draft["status"], "Draft")
        with self.assertRaises(frappe.PermissionError):
            run_as_user(TRAINER[0], lambda: api.send_signoff(draft["name"]))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                TRAINER[0],
                lambda: api.create_signoff(
                    self.project,
                    "Stock",
                    self.contact,
                    TRAINER[0],
                    template=TEMPLATE,
                    send=1,
                    **MAIL,
                ),
            )
        # a coordinator sends, reminds and marks it
        run_as_user(COORDINATOR[0], lambda: api.send_signoff(draft["name"]))
        run_as_user(COORDINATOR[0], lambda: api.send_signoff_reminder(draft["name"]))
        self.assertEqual(
            frappe.db.get_value("HD Project Signoff", draft["name"], "status"), "Sent"
        )
        # outsiders see nothing
        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_project_signoffs(self.project))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(OUTSIDER[0], lambda: api.get_signoff(draft["name"]))

    def test_only_system_managers_edit_templates(self):
        with self.assertRaises(frappe.PermissionError):
            run_as_user(PM[0], api.get_signoff_templates)
        saved = api.save_signoff_template(
            "Projects (signoff tests)",
            [{"section": "Tasks", "question": "I can create a Task."}],
        )
        self.assertEqual(
            len(frappe.get_doc("HD Signoff Template", saved["name"]).items), 1
        )

    # --- UAT: the client's acceptance tests from the plan's SRS ---

    def uat_project(self):
        """The project as made from an implementation plan, with the ERP site faked."""
        frappe.db.set_value(
            "Project",
            self.project,
            {"custom_crm_plan": "PIP-2026-00001", "custom_crm_acting_user": PM[0]},
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
        doc.update(MAIL)
        doc.save(ignore_permissions=True)
        run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        doc.reload()
        token = self.token_in(self.mail.call_args.kwargs["content"])
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
        doc.update(MAIL)
        doc.save(ignore_permissions=True)
        run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        with patch("frappe.enqueue") as enqueue:
            doc = self.signed_off(doc)
        self.assertEqual(
            enqueue.call_args.args[0], "helpdesk.api.project_signoff.record_uat_on_erp"
        )
        # the state as of signing travels with the job
        self.assertEqual(
            (enqueue.call_args.kwargs["status"], enqueue.call_args.kwargs["signed_by"]),
            ("Signed", doc.signer_name),
        )
        api.record_uat_on_erp(
            name, **{k: enqueue.call_args.kwargs[k] for k in ("status", "signed_by")}
        )
        self.assertEqual(
            frappe.db.get_value("HD Project Signoff", name, "crm_recorded"), "Signed"
        )
        (_name, post, params) = crm.lead_calls[-1]
        self.assertTrue(post)
        self.assertEqual(
            (
                params["name"],
                params["status"],
                params["signed_by"],
                params["acting_user"],
            ),
            ("PIP-2026-00001", "Signed", doc.signer_name, PM[0]),
        )
        # the training completion letter isn't the UAT's: cancelling the UAT keeps it
        self.assertFalse(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )
        frappe.db.set_value(
            "Project", self.project, "custom_signoff_letter", "letter.pdf"
        )
        with patch("frappe.enqueue") as enqueue:
            api.cancel_signoff(name, "A test failed after all")
        self.assertEqual(enqueue.call_args.kwargs["status"], "Reopened")
        self.assertEqual(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter"),
            "letter.pdf",
        )

    def test_an_erp_site_out_of_reach_is_retried_then_recorded_by_hand(self):
        from helpdesk.integrations.crm.client import CRMError

        crm = self.uat_project()
        name = run_as_user(
            PM[0],
            lambda: api.create_uat_signoff(self.project, self.contact, TRAINER[0]),
        )["name"]
        crm.lead_error = CRMError("unreachable")
        with patch("time.sleep") as sleep:
            self.assertFalse(api.record_uat_on_erp(name, "Signed", "Fathima Rahman"))
        self.assertEqual(sleep.call_count, 2)
        doc = frappe.get_doc("HD Project Signoff", name)
        self.assertEqual(doc.log[-1].event, "Not recorded on the ERP site")
        self.assertFalse(doc.crm_recorded)
        # only now is Record on the ERP site offered (not while the first try is queued)
        self.assertTrue(run_as_user(PM[0], lambda: api.get_signoff(name))["crm_failed"])
        # once it is back, Record on the ERP site sends the current state
        crm.lead_error = None
        frappe.db.set_value("HD Project Signoff", name, "status", "Signed Off")
        run_as_user(PM[0], lambda: api.record_uat_again(name))
        self.assertEqual(
            frappe.db.get_value("HD Project Signoff", name, "crm_recorded"), "Signed"
        )
        self.assertFalse(
            run_as_user(PM[0], lambda: api.get_signoff(name))["crm_failed"]
        )

    def test_the_plan_link_is_not_changed_by_a_save(self):
        self.uat_project()
        project = frappe.get_doc("Project", self.project)
        project.custom_crm_acting_user = OUTSIDER[0]
        with self.assertRaises(frappe.PermissionError):
            project.save(ignore_permissions=True)

    def test_the_erp_site_is_asked_only_as_the_plans_maker(self):
        self.uat_project()
        frappe.db.set_value("Project", self.project, "custom_crm_acting_user", None)
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0],
                lambda: api.create_uat_signoff(self.project, self.contact, TRAINER[0]),
            )

    def test_a_project_without_a_plan_has_no_uat(self):
        listed = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertFalse(listed["can_create_uat"])
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0],
                lambda: api.create_uat_signoff(self.project, self.contact, TRAINER[0]),
            )

    # --- the mail (docs/project-signoff.md, Mail) ---

    def test_the_mail_fills_in_and_holds_back_what_is_missing(self):
        details = {
            "template": TEMPLATE,
            "signatory_contact": self.contact,
            "module_title": "Accounts",
            "trainer": TRAINER[0],
        }
        preview = run_as_user(
            PM[0], lambda: api.preview_signoff_mail(self.project, **details)
        )
        # the template has no mail of its own: the standard training mail, filled in
        self.assertEqual(preview["missing"], ["Training date"])
        self.assertIn("{{ training_date }}", preview["body"])
        self.assertIn("Meera Joseph", preview["body"])
        self.assertIn("Anjali Pillai", preview["body"])
        self.assertTrue(preview["subject"].startswith("Training Sign-off – Accounts"))
        # a contact without a salutation is "Sir/Madam" (TBO's Sign-off requirements)
        self.assertIn("Dear Sir/Madam", preview["body"])
        with self.assertRaises(frappe.ValidationError) as refused:
            run_as_user(
                PM[0],
                lambda: api.create_signoff(
                    self.project,
                    "Accounts",
                    self.contact,
                    TRAINER[0],
                    template=TEMPLATE,
                    email_subject=preview["subject"],
                    email_body=preview["body"],
                    send=1,
                ),
            )
        self.assertIn("Training date", str(refused.exception))

        filled = run_as_user(
            PM[0],
            lambda: api.preview_signoff_mail(
                self.project, training_date=nowdate(), **details
            ),
        )
        self.assertEqual(filled["missing"], [])
        created = run_as_user(
            PM[0],
            lambda: api.create_signoff(
                self.project,
                "Accounts",
                self.contact,
                TRAINER[0],
                template=TEMPLATE,
                training_date=nowdate(),
                email_subject=filled["subject"],
                email_body=filled["body"],
                cc_emails=f"{PM[0]}; {SIGNATORY}",
                send=1,
            ),
        )
        doc = frappe.get_doc("HD Project Signoff", created["name"])
        # the signatory isn't copied on their own mail
        self.assertEqual((doc.status, doc.cc_emails), ("Sent", PM[0]))
        sent = self.mail.call_args.kwargs
        self.assertEqual(
            (sent["recipients"], sent["cc"], sent["subject"]),
            ([SIGNATORY], [PM[0]], filled["subject"]),
        )
        # from the sender's own account when they have one (their address as sender)
        self.assertIn(PM[0], sent["sender"])
        self.assertIn("/project-signoff?token=", sent["content"])
        self.assertNotIn("{{", sent["content"])
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0],
                lambda: api.create_signoff(
                    self.project,
                    "Accounts",
                    self.contact,
                    TRAINER[0],
                    cc_emails="not-an-email",
                ),
            )

    def test_a_uat_template_carries_only_the_mail(self):
        ensure_default_signoff_templates()
        uat = frappe.get_doc("HD Signoff Template", "UAT Sign-off and Go-Live")
        self.assertEqual(
            (uat.signoff_type, uat.project_type, uat.stage, len(uat.items)),
            ("UAT", "ERP Implementation", "UAT Sign-off and Go-Live", 0),
        )
        # the requirements' Avera mail: accepted by replying
        self.assertIn("by replying to this email", uat.email_body)
        self.assertIn("{{ erpnext_version }}", uat.email_body)
        # picked for an ordinary sign-off, it makes a UAT
        created = run_as_user(
            PM[0],
            lambda: api.create_signoff(
                self.project, "", self.contact, TRAINER[0], template="UAT Sign-off"
            ),
        )
        doc = frappe.get_doc("HD Project Signoff", created["name"])
        self.assertEqual(
            (doc.signoff_type, doc.stage, doc.module_title),
            ("UAT", "UAT Sign-off", "UAT Sign-off"),
        )

    # --- stages (TBO's Sign-off requirements, Template list) ---

    def stage_signoff(self, template: str, **values):
        ensure_default_signoff_templates()
        return make_signoff(
            self.project, self.contact, TRAINER[0], template, module_title="", **values
        )

    def test_the_ten_templates_are_seeded_with_their_stage(self):
        ensure_default_signoff_templates()
        for stage, info in STAGES.items():
            template = frappe.get_doc("HD Signoff Template", stage)
            self.assertEqual(
                (template.stage, template.project_type),
                (stage, info["project_type"]),
            )
            self.assertTrue(template.declaration_text)
            self.assertTrue(template.email_subject)
            # every mail asks the customer to reply (the training's also links its form)
            self.assertIn("reply", template.email_body)

    def test_a_stage_needs_its_details_before_it_is_sent(self):
        doc = self.stage_signoff("UAT Sign-off and Go-Live", **MAIL)
        self.assertEqual(doc.erpnext_version, "V16")
        doc.email_body = "<p>Please reply to confirm.</p>"
        doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError) as refused:
            run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        self.assertIn("Go-live date", str(refused.exception))
        self.assertIn("Modules covered", str(refused.exception))

        doc.reload()
        doc.update(
            {
                "go_live_date": add_days(nowdate(), 7),
                "uat_site_url": "https://uat.malabar.example",
            }
        )
        doc.append("modules", {"module": "Accounts", "status": "Completed"})
        doc.save(ignore_permissions=True)
        run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "status"), "Sent")

    def test_a_training_stage_is_named_after_its_modules(self):
        doc = self.stage_signoff("Accounts")
        self.assertEqual(doc.stage, "Module Training Sign-off")
        # the template's module starts the modules covered, and names the sign-off
        self.assertEqual([r.module for r in doc.modules], ["Accounts"])
        doc.append("modules", {"module": "Stock", "status": "Partially Completed"})
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.module_title, "Accounts, Stock")
        values = doc.mail_values(PM[0])
        self.assertEqual(values["modules"], "Accounts, Stock")

    def test_a_months_deliverables_default_to_last_month(self):
        doc = self.stage_signoff("Monthly Deliverables Sign-off")
        first = getdate(add_months(nowdate(), -1)).replace(day=1)
        self.assertEqual(
            (getdate(doc.period_from), getdate(doc.period_to)),
            (first, getdate(add_days(add_months(first, 1), -1))),
        )
        # ad spend shows only when Paid Ads is one of the services
        self.assertNotIn("ad_spend", doc.shown_sections())
        doc.services = "Social Media, Paid Ads"
        self.assertIn("ad_spend", doc.shown_sections())
        doc.services = "Social Media, Billboards"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_each_kind_gets_its_document(self):
        uat = self.stage_signoff(
            "UAT Sign-off",
            uat_site_url="https://uat.malabar.example",
            srs_version="2.1",
        )
        uat.append(
            "open_items",
            {
                "issue": "GST report rounding",
                "severity": "Medium",
                "agreed_action": "Fix",
            },
        )
        html = uat.render_html(uat.document_context())
        for words in (
            "UAT Sign-off Certificate",
            "Environment",
            "https://uat.malabar.example",
            "Known exceptions accepted by the customer",
            "GST report rounding",
        ):
            self.assertIn(words, html)
        self.assertNotIn("Data migration", html)

        monthly = self.stage_signoff(
            "Monthly Deliverables Sign-off", services="Social Media"
        )
        monthly.append(
            "deliverables",
            {"deliverable_type": "Reel", "planned_qty": 8, "delivered_qty": 7},
        )
        html = monthly.render_html(monthly.document_context())
        for words in ("Engagement", "Deliverables", "Reel", "Social Media"):
            self.assertIn(words, html)
        self.assertNotIn("Ad spend", html)

    def test_go_live_details_fill_the_mail(self):
        doc = self.stage_signoff(
            "Go-Live Confirmation",
            go_live_date="2026-12-01",
            live_site_url="https://erp.malabar.example",
            support_start_date="2026-12-01",
            support_end_date="2027-02-28",
        )
        mail = doc.render_mail(PM[0])
        self.assertEqual(mail["missing"], [])
        self.assertIn("https://erp.malabar.example", mail["body"])
        self.assertTrue(mail["subject"].startswith("Go-Live Confirmation"))

    def test_only_trainings_count_for_the_completion_letter(self):
        training, _token = self.sent()
        srs = self.stage_signoff("SRS / Requirement Sign-off", srs_version="1.0")
        rollup = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
        self.assertEqual(rollup["total"], 1)
        self.signed_off(training)
        self.assertTrue(
            frappe.db.get_value("Project", self.project, "custom_signoff_letter")
        )
        self.assertEqual(frappe.db.get_value(srs.doctype, srs.name, "status"), "Draft")

    def test_a_signed_copy_is_accepted_as_the_evidence(self):
        doc, _token = self.sent()
        copy = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": "signed-sign-off.pdf",
                "content": blank_pdf(),
                "is_private": 1,
            }
        ).insert(ignore_permissions=True)
        doc = self.signed_off(doc, signed_copy=copy.file_url)
        self.assertEqual((doc.status, doc.signed_copy), ("Signed Off", copy.file_url))
        self.assertEqual(
            frappe.db.get_value("File", copy.name, "attached_to_name"), self.project
        )

    def test_sent_reads_viewed_once_the_customer_opens_it(self):
        doc, _token = self.sent()

        def status():
            listed = run_as_user(PM[0], lambda: api.get_project_signoffs(self.project))
            return next(
                s.customer_status for s in listed["signoffs"] if s.name == doc.name
            )

        self.assertEqual(status(), "Sent")
        doc.reload()
        doc.log_event(CODE_VERIFIED, by_email=SIGNATORY)
        doc.flags.signoff_action = True
        doc.save(ignore_permissions=True)
        self.assertEqual(status(), "Viewed")
        self.assertEqual(
            run_as_user(PM[0], lambda: api.get_signoff(doc.name))["customer_status"],
            "Viewed",
        )

    # --- the reminder (docs/project-signoff.md, Reminders) ---

    def test_one_reminder_after_two_working_days(self):
        doc, _token = self.sent()

        def sent_days_ago(days):
            frappe.db.set_value(
                "HD Project Signoff",
                doc.name,
                {
                    "link_sent_on": add_days(now_datetime(), -days),
                    "link_sent_by": PM[0],
                },
            )

        def run():
            with patch("helpdesk.follow_ups.WorkCalendar", EveryDayWorkCalendar):
                with patch("helpdesk.work_reminders.notify_users") as notify:
                    send_signoff_reminders()
            return notify

        self.mail.reset_mock()
        sent_days_ago(1)
        run()
        self.mail.assert_not_called()

        sent_days_ago(3)
        notify = run()
        self.assertEqual(self.mail.call_count, 1)
        mail = self.mail.call_args.kwargs
        self.assertEqual(mail["recipients"], [SIGNATORY])
        self.assertTrue(mail["subject"].startswith("Reminder:"))
        self.assertIn("/project-signoff?token=", mail["content"])
        doc.reload()
        # a reminder leaves it Sent
        self.assertEqual(doc.status, "Sent")
        self.assertTrue(doc.reminder_sent_on)
        # in the name of whoever sent it, who is told
        self.assertEqual(doc.link_sent_by, PM[0])
        self.assertEqual(doc.log[-1].event, "Reminder sent")
        self.assertEqual(notify.call_args.args[0], [PM[0]])

        sent_days_ago(5)
        run()
        self.assertEqual(self.mail.call_count, 1)

        # sent again after changes were asked for: a new wait
        run_as_user(PM[0], lambda: api.mark_changes_requested(doc.name, "New date"))
        run_as_user(PM[0], lambda: api.send_signoff(doc.name))
        self.assertFalse(
            frappe.db.get_value("HD Project Signoff", doc.name, "reminder_sent_on")
        )

    def test_no_reminder_once_the_customer_opened_it(self):
        # its new link would end the session they may be answering in
        doc, _token = self.sent()
        frappe.db.set_value(
            "HD Project Signoff",
            doc.name,
            {"link_sent_on": add_days(now_datetime(), -3), "link_sent_by": PM[0]},
        )
        doc.reload()
        doc.log_event(CODE_VERIFIED, by_email=SIGNATORY)
        doc.flags.signoff_action = True
        doc.save(ignore_permissions=True)
        self.mail.reset_mock()
        with patch("helpdesk.follow_ups.WorkCalendar", EveryDayWorkCalendar):
            with patch("helpdesk.work_reminders.notify_users"):
                send_signoff_reminders()
        self.mail.assert_not_called()
        self.assertFalse(
            frappe.db.get_value("HD Project Signoff", doc.name, "reminder_sent_on")
        )

    # --- after signing off ---

    def test_signing_off_emails_our_owner_and_notes_the_lead(self):
        crm = self.lead_project(owner=OUTSIDER[0])
        doc, _token = self.sent()
        with patch("frappe.enqueue") as enqueue:
            doc = self.signed_off(doc)
        signed_mail = self.mail.call_args.kwargs
        self.assertEqual(signed_mail["recipients"], [SIGNATORY])
        self.assertIn(PM[0], signed_mail["cc"])
        job = next(
            c
            for c in enqueue.call_args_list
            if c.args[0] == "helpdesk.api.project_signoff.note_signed_on_crm_lead"
        )
        note = job.kwargs["note"]
        self.assertEqual(note, f"{TEMPLATE} signed off by {doc.signer_name}")
        with patch("helpdesk.work_reminders.notify_users") as notify:
            api.note_signed_on_crm_lead(doc.name, note)
        (_name, post, params) = next(c for c in crm.lead_calls if c[0] == "add_note")
        self.assertTrue(post)
        self.assertEqual(
            (params["name"], params["note"], params["acting_user"]),
            ("LEAD-SO-1", note, PM[0]),
        )
        # the lead's owner hears too (who sent it and the project lead heard at signing)
        self.assertEqual(notify.call_args.args[0], [OUTSIDER[0]])

    def test_a_link_sent_by_administrator_still_mails(self):
        # Administrator is no email address: left out, or Frappe drops the whole mail
        frappe.db.set_value("Project", self.project, "project_lead", "Administrator")
        doc = self.signoff()
        self.mail.reset_mock()
        api.send_signoff(doc.name)
        doc.reload()
        self.assertEqual(doc.link_sent_by, "Administrator")
        self.assertTrue(self.mail.called)
        self.mail.reset_mock()
        self.signed_off(doc)
        signed = self.mail.call_args.kwargs
        self.assertEqual(signed["recipients"], [SIGNATORY])
        self.assertNotIn("Administrator", signed["cc"] or [])
        self.assertIn(TRAINER[0], signed["cc"])
        letter = self.sendmail.call_args.kwargs
        self.assertEqual(letter["recipients"], sorted([SIGNATORY, TRAINER[0]]))

    # --- the lead page (docs/project-signoff.md, From the lead) ---

    def lead_project(self, owner: str, project: str | None = None):
        """The project made for lead LEAD-SO-1 (owned by `owner`) from a plan, the ERP site
        faked; `project` is what the lead's document chain says its project is."""
        crm = self.uat_project()
        enable_leads()
        forget_signoff_lead_access()
        self.addCleanup(forget_signoff_lead_access)
        frappe.db.set_value("Project", self.project, "custom_crm_lead", "LEAD-SO-1")
        crm.lead_answers["get_lead"] = crm_lead_detail(
            "LEAD-SO-1", project or self.project, owner
        )
        crm.lead_answers["add_note"] = {}
        return crm

    def test_the_lead_owner_sends_the_uat_and_sees_it_signed(self):
        self.lead_project(owner=OUTSIDER[0])

        def lead_status():
            return run_as_user(OUTSIDER[0], lambda: api.get_lead_signoff("LEAD-SO-1"))

        status = lead_status()
        # the lead's owner may send it, though they can't open the project
        self.assertEqual(
            (
                status["project"],
                status["signoff"],
                status["can_send"],
                status["can_open"],
            ),
            (self.project, None, True, False),
        )
        mail = run_as_user(
            OUTSIDER[0],
            lambda: api.preview_signoff_mail(
                self.project,
                "UAT",
                signatory_contact=self.contact,
                trainer=TRAINER[0],
                lead="LEAD-SO-1",
            ),
        )
        # the UAT's own mail needs the site the client tests on (the dialog asks for it)
        self.assertEqual(mail["missing"], ["UAT site URL"])
        mail = run_as_user(
            OUTSIDER[0],
            lambda: api.preview_signoff_mail(
                self.project,
                "UAT",
                signatory_contact=self.contact,
                trainer=TRAINER[0],
                lead="LEAD-SO-1",
                details=UAT_DETAILS,
            ),
        )
        self.assertEqual(mail["missing"], [])
        # a UAT's modules are its tests' sections, from the SRS
        self.assertIn("covering the following modules: Accounts.", mail["body"])
        created = run_as_user(
            OUTSIDER[0],
            lambda: api.create_uat_signoff(
                self.project,
                self.contact,
                TRAINER[0],
                email_subject=mail["subject"],
                email_body=mail["body"],
                cc_emails=PM[0],
                send=1,
                lead="LEAD-SO-1",
                details=UAT_DETAILS,
            ),
        )
        self.assertEqual(created["status"], "Sent")
        self.assertEqual(lead_status()["signoff"]["customer_status"], "Sent")

        doc = frappe.get_doc("HD Project Signoff", created["name"])
        with patch("frappe.enqueue"):
            doc = self.signed_off(doc)
        signed = lead_status()["signoff"]
        self.assertEqual(
            (signed["status"], signed["signer_name"], signed["has_pdf"]),
            ("Signed Off", doc.signer_name, True),
        )
        run_as_user(OUTSIDER[0], lambda: api.download_lead_signoff_pdf("LEAD-SO-1"))
        self.assertTrue(frappe.local.response.filecontent)

    def test_the_lead_page_sends_and_never_keeps_a_draft(self):
        # the lead's owner may not open the project, so a draft there would be stranded
        self.lead_project(owner=OUTSIDER[0])
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                OUTSIDER[0],
                lambda: api.create_uat_signoff(
                    self.project, self.contact, TRAINER[0], lead="LEAD-SO-1", send=0
                ),
            )
        self.assertFalse(
            frappe.db.exists("HD Project Signoff", {"project": self.project})
        )

    def test_others_see_the_lead_status_but_cannot_send(self):
        self.lead_project(owner=PM[0])
        status = run_as_user(OUTSIDER[0], lambda: api.get_lead_signoff("LEAD-SO-1"))
        self.assertEqual((status["can_send"], status["can_open"]), (False, False))
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                OUTSIDER[0],
                lambda: api.create_uat_signoff(
                    self.project, self.contact, TRAINER[0], lead="LEAD-SO-1"
                ),
            )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                OUTSIDER[0],
                lambda: api.get_signoff_form(self.project, lead="LEAD-SO-1"),
            )

    def test_a_project_that_is_not_the_leads_is_refused(self):
        other = make_project(
            "Signoff - another rollout",
            members=[(PM[0], "Project Manager")],
            owner=PM[0],
        ).name
        self.lead_project(owner=OUTSIDER[0], project=other)
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                OUTSIDER[0],
                lambda: api.create_uat_signoff(
                    self.project, self.contact, TRAINER[0], lead="LEAD-SO-1"
                ),
            )
