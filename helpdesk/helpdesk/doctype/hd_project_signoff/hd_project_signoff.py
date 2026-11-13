# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A customer's sign-off that training on one module of a project is complete, or (a UAT
sign-off) that they tested the system against its SRS and accept it.

The customer opens a tokenised link, proves they are the named signatory with an
emailed code, answers every question Done / Not clear / Escalate, and signs once
everything is Done. Not clear and Escalate become clarification tasks for the
trainer. Signing saves a PDF on the project; when every sign-off of a project is
signed, a project completion letter is generated. A UAT's items are the SRS's test cases
on the ERP site, answered Pass / Fail / Blocker; a Fail is an open issue (a task to fix it), and
signing is recorded on the ERP site's plan, which starts the warranty. See
docs/project-signoff.md.
"""

import base64
import hashlib
import json
import re
import secrets
import shutil

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    escape_html,
    format_datetime,
    formatdate,
    get_datetime,
    get_fullname,
    get_url,
    getdate,
    now_datetime,
    nowdate,
)

DRAFT = "Draft"
SENT = "Sent"
IN_PROGRESS = "In progress"
NEEDS_CLARIFICATION = "Needs clarification"
READY_TO_SIGN = "Ready to sign"
SIGNED = "Signed"
REOPENED = "Reopened"

PENDING = "Pending"
DONE = "Done"
NOT_CLEAR = "Not clear"
ESCALATED = "Escalated"
CUSTOMER_RESPONSES = (DONE, NOT_CLEAR, ESCALATED)
NEEDS_FOLLOW_UP = (NOT_CLEAR, ESCALATED)

# questions can be added, removed and reordered only while nobody is answering them
EDITABLE_STATUSES = (DRAFT, REOPENED)
LINK_TTL_DAYS = 30
TASK_DONE = ("Completed", "Cancelled")
MAX_TEXT = 1000
MAX_NAME = 140
PORTAL_PATH = "/project-signoff"
TRAINING = "Training"
UAT = "UAT"

# a mail's placeholders, {{ name }}: filled from the sign-off, never run as a template, so a
# template's text can't execute anything (docs/project-signoff.md, Mail)
PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z_]+)\s*}}")
LINK_PLACEHOLDER = "sign_off_link"
# left blank when unknown rather than holding the mail back
OPTIONAL_PLACEHOLDERS = ("contact_salutation", "sender_designation")
REMINDER_AFTER_WORKING_DAYS = 2
EMAIL_SPLIT = re.compile(r"[,;\s]+")


class HDProjectSignoff(Document):
    def before_insert(self):
        self.copy_template_items()
        self.log_event(_("Created"))

    def validate(self):
        self.validate_project()
        self.validate_trainer()
        self.set_signatory()
        self.clean_items()
        self.clean_mail()
        self.prevent_locked_changes()

    # --- validation ---

    def validate_project(self):
        if self.is_new() and not self.customer:
            frappe.throw(
                _(
                    "Set the customer on project {0} first; the signatory must be one of its contacts."
                ).format(self.project_name or self.project)
            )

    def validate_trainer(self):
        from helpdesk.tasky.permissions import get_project_team

        if not self.trainer or not self.has_value_changed("trainer"):
            return
        if self.trainer not in get_project_team(self.project):
            frappe.throw(
                _(
                    "{0} isn't on this project. Pick the trainer from the project team."
                ).format(get_fullname(self.trainer))
            )

    def set_signatory(self):
        """The signatory is a contact of the project's customer; name and email come from it.

        Checked when it is set or changed, so a contact later removed from the customer
        doesn't stop a sign-off already under way.
        """
        if self.signatory_contact and not self.has_value_changed("signatory_contact"):
            return
        if not self.signatory_contact:
            frappe.throw(_("Pick who signs off for the customer."))
        contact = frappe.db.get_value(
            "Contact",
            self.signatory_contact,
            ["full_name", "first_name", "last_name", "email_id"],
            as_dict=True,
        )
        if not contact or not self.is_customer_contact(self.signatory_contact):
            frappe.throw(
                _("{0} isn't a contact of {1}. Add them to the customer first.").format(
                    self.signatory_contact, self.customer
                )
            )
        if not contact.email_id:
            frappe.throw(
                _(
                    "{0} has no email address. Add one to the contact, so they can get the sign-off link."
                ).format(self.signatory_contact)
            )
        self.signatory_email = contact.email_id.strip().lower()
        self.signatory_name = (
            contact.full_name
            or " ".join(n for n in (contact.first_name, contact.last_name) if n)
            or self.signatory_email
        )

    def is_customer_contact(self, contact: str) -> bool:
        return bool(
            frappe.db.exists(
                "HD Customer Member",
                {
                    "parenttype": "HD Customer",
                    "parent": self.customer,
                    "contact_name": contact,
                },
            )
        )

    def clean_items(self):
        rows = []
        for row in self.items:
            row.section = (row.section or "").strip()
            row.question = (row.question or "").strip()
            row.help_text = (row.help_text or "").strip()
            row.response = row.response or PENDING
            if row.question:
                rows.append(row)
        # a draft made without a template starts empty; it needs questions before it is sent
        if not rows and self.status != DRAFT:
            frappe.throw(_("Add at least one question for the customer to answer."))
        self.items = rows

    def prevent_locked_changes(self):
        """A signed sign-off only changes by being reopened; questions only change while editable."""
        before = self.get_doc_before_save()
        if not before or self.flags.signoff_action:
            return
        if before.status == SIGNED:
            frappe.throw(_("This sign-off is signed. Reopen it to change it."))
        if before.status not in EDITABLE_STATUSES and self.question_rows(
            before
        ) != self.question_rows(self):
            frappe.throw(
                _(
                    "The customer is answering these questions, so they can't be changed now. Reopen the sign-off after it is signed, or revoke the link and start a new one."
                )
            )

    @staticmethod
    def question_rows(doc) -> list[tuple]:
        return [(r.section, r.question, r.help_text) for r in doc.items]

    def clean_mail(self):
        """The mail's CC are valid addresses, one each; a subject needs a body and the other way round."""
        self.cc_emails = ", ".join(
            e for e in self.clean_emails(self.cc_emails) if e != self.signatory_email
        )
        self.email_subject = " ".join((self.email_subject or "").split())[:240]
        if bool(self.email_subject) != bool(self.mail_body_text()):
            frappe.throw(_("Give the mail a subject and a message, or neither."))

    @staticmethod
    def clean_emails(text: str | None) -> list[str]:
        """Addresses separated by commas, semicolons or spaces, each checked, without repeats."""
        found = []
        for part in EMAIL_SPLIT.split(text or ""):
            email = part.strip().lower()
            if not email or email in found:
                continue
            if not frappe.utils.validate_email_address(email):
                frappe.throw(_("{0} isn't a valid email address.").format(email))
            found.append(email)
        return found

    def mail_body_text(self) -> str:
        return frappe.utils.strip_html(self.email_body or "").strip()

    # --- template ---

    def copy_template_items(self):
        """Questions are copied, so later edits to the template don't change this sign-off."""
        if self.items or not self.template:
            return
        template = frappe.get_doc("HD Signoff Template", self.template)
        for row in template.items:
            self.append(
                "items",
                {
                    "section": row.section,
                    "question": row.question,
                    "help_text": row.help_text,
                },
            )

    # --- helpers ---

    def get_item(self, item: str):
        for row in self.items:
            if row.name == item:
                return row
        frappe.throw(
            _("That question isn't part of this sign-off."), frappe.DoesNotExistError
        )

    def counts(self) -> dict:
        responses = [row.response or PENDING for row in self.items]
        return {
            "total": len(responses),
            "done": responses.count(DONE),
            "not_clear": responses.count(NOT_CLEAR),
            "escalated": responses.count(ESCALATED),
            "pending": responses.count(PENDING),
        }

    def all_done(self) -> bool:
        return bool(self.items) and all(row.response == DONE for row in self.items)

    def log_event(
        self,
        event: str,
        item: str | None = None,
        detail: str | None = None,
        by_email: str | None = None,
        by_name: str | None = None,
        ip_address: str | None = None,
    ):
        user = frappe.session.user
        if not by_email and user != "Guest":
            by_email = user
            by_name = by_name or get_fullname(user)
        self.append(
            "log",
            {
                "event": event,
                "item": item,
                "detail": (detail or "")[:MAX_TEXT],
                "by_email": by_email,
                "by_name": by_name or by_email,
                "at": now_datetime(),
                "ip_address": ip_address,
            },
        )

    def refresh_status(self):
        """Status follows the answers once the customer has the link; Draft and Signed are set explicitly."""
        if self.status in (DRAFT, SIGNED):
            return
        responses = [row.response or PENDING for row in self.items]
        if any(r in NEEDS_FOLLOW_UP for r in responses):
            self.status = NEEDS_CLARIFICATION
        elif self.all_done():
            self.status = READY_TO_SIGN
        elif any(r != PENDING for r in responses):
            self.status = IN_PROGRESS
        elif self.status != REOPENED:
            self.status = SENT

    def project_lead(self) -> str | None:
        return frappe.db.get_value("Project", self.project, "project_lead")

    def helpdesk_path(self) -> str:
        return f"/projects/{self.project}/signoff/{self.name}"

    # --- customer link ---

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256((token or "").encode()).hexdigest()

    @staticmethod
    def link_url(token: str) -> str:
        return get_url(f"{PORTAL_PATH}?token={token}")

    def issue_link(self) -> str:
        """A new token replaces the old one, so earlier links (and their sessions) stop working.

        Only the hash is stored; the token itself goes out in the email and nowhere else.
        """
        if self.status == SIGNED:
            frappe.throw(
                _("This sign-off is signed. Reopen it to send the link again.")
            )
        if not self.items:
            frappe.throw(
                _("Add at least one question before sending it to the customer.")
            )
        token = secrets.token_urlsafe(32)
        self.link_token_hash = self.hash_token(token)
        self.link_expires_on = add_days(now_datetime(), LINK_TTL_DAYS)
        self.link_sent_on = now_datetime()
        self.link_sent_by = (
            frappe.session.user if frappe.session.user != "Guest" else None
        )
        if self.status == DRAFT:
            self.status = SENT
        self.flags.signoff_action = True
        return token

    def revoke_link(self):
        if not self.link_token_hash:
            frappe.throw(_("There is no open link to revoke."))
        self.link_token_hash = None
        self.link_expires_on = None
        self.flags.signoff_action = True
        self.log_event(_("Link revoked"))

    def link_is_open(self) -> bool:
        return bool(
            self.link_token_hash
            and self.status != DRAFT
            and self.link_expires_on
            and get_datetime(self.link_expires_on) > now_datetime()
        )

    def send_link(self, resend: bool = False):
        """Send (or resend) the link to the signatory; saves the sign-off. The sign-off's own
        mail when it has one (its CC too), else the standard words. A link sent by hand starts
        a new wait for the reminder."""
        self.check_mail_ready()
        token = self.issue_link()
        self.reminder_sent_on = None
        self.log_event(
            _("Link resent") if resend else _("Link sent"),
            detail=_("To {0}").format(self.signatory_email)
            + (_("; CC {0}").format(self.cc_emails) if self.cc_emails else ""),
        )
        self.save(ignore_permissions=True)
        if self.email_subject:
            self.deliver(self.email_subject, self.mail_with_link(token), self.cc_list())
            return
        self.email_customer(
            (
                _("Please test and accept {0}")
                if self.is_uat()
                else _("Please confirm your {0} training")
            ).format(self.module_title),
            (
                _(
                    "{0} has prepared {1} for {2}. Please run each test and tell us, one by one, whether it passes."
                )
                if self.is_uat()
                else _(
                    "{0} has finished your {1} training for {2}. Please go through the checklist and tell us, item by item, whether everything is clear."
                )
            ).format(
                escape_html(
                    get_fullname(self.trainer) if self.trainer else _("Your trainer")
                ),
                escape_html(self.module_title),
                escape_html(self.project_name or self.project),
            ),
            token,
        )

    def email_customer(self, subject: str, intro: str, token: str):
        days = LINK_TTL_DAYS
        message = "".join(
            [
                f"<p>{_('Hello {0},').format(escape_html(self.signatory_name or ''))}</p>",
                f"<p>{intro}</p>",
                f'<p><a href="{self.link_url(token)}">{_("Open the sign-off")}</a></p>',
                "<p>"
                + _(
                    "For your security we will email you a one-time code when you open it. The link works for {0} days and only for {1}."
                ).format(days, escape_html(self.signatory_email))
                + "</p>",
            ]
        )
        frappe.sendmail(
            recipients=[self.signatory_email],
            subject=subject,
            message=message,
            reply_to=self.trainer or None,
            reference_doctype=self.doctype,
            reference_name=self.name,
        )

    # --- the mail (docs/project-signoff.md, Mail) ---

    def deliver(self, subject: str, message: str, cc: list[str] | None = None):
        """The sign-off's own mail to the signatory, in the thread of the sign-off; replies go
        to whoever sent the link."""
        frappe.sendmail(
            recipients=[self.signatory_email],
            cc=cc or None,
            subject=subject,
            message=message,
            reply_to=self.link_sent_by or self.trainer or None,
            reference_doctype=self.doctype,
            reference_name=self.name,
        )

    def cc_list(self) -> list[str]:
        return self.clean_emails(self.cc_emails)

    def check_mail_ready(self):
        """A sign-off's own mail goes out only with every placeholder filled."""
        if not self.email_subject:
            return
        left = {
            name
            for name in PLACEHOLDER.findall(f"{self.email_subject} {self.email_body}")
            if name != LINK_PLACEHOLDER
        }
        if left:
            frappe.throw(
                _("Fill {0}: it is used in the mail.").format(
                    ", ".join(self.placeholder_label(name) for name in sorted(left))
                )
            )

    def mail_with_link(self, token: str, reminder: bool = False) -> str:
        """The mail's body with the customer's link where {{ sign_off_link }} is (or at the
        end), and how the link works."""
        url = self.link_url(token)
        link = f'<a href="{url}">{escape_html(url)}</a>'
        body = self.email_body or ""
        if LINK_PLACEHOLDER in PLACEHOLDER.findall(body):
            body = PLACEHOLDER.sub(
                lambda m: link if m.group(1) == LINK_PLACEHOLDER else m.group(0), body
            )
        else:
            body += f'<p><a href="{url}">{_("Open the sign-off")}</a></p>'
        intro = (
            "<p>"
            + _(
                "A gentle reminder: we haven't heard from you yet. The link below replaces the one we sent before."
            )
            + "</p>"
            if reminder
            else ""
        )
        return intro + body + self.link_note()

    def link_note(self) -> str:
        return (
            '<p style="color:#6b7280">'
            + _(
                "For your security we will email you a one-time code when you open it. The link works for {0} days and only for {1}."
            ).format(LINK_TTL_DAYS, escape_html(self.signatory_email))
            + "</p>"
        )

    def template_mail(self) -> dict:
        """{subject, body, cc} of the sign-off's template, or the standard mail of its kind."""
        from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
            DEFAULT_MAILS,
        )

        template = (
            frappe.db.get_value(
                "HD Signoff Template",
                self.template,
                ["email_subject", "email_body", "default_cc"],
                as_dict=True,
            )
            if self.template
            else None
        )
        if template and template.email_subject:
            return {
                "subject": template.email_subject,
                "body": template.email_body or "",
                "cc": self.clean_emails(template.default_cc),
            }
        mail = DEFAULT_MAILS[UAT if self.is_uat() else TRAINING]
        return {
            "subject": mail["subject"],
            "body": mail["body"],
            "cc": self.clean_emails(template.default_cc) if template else [],
        }

    def render_mail(self, sender: str | None = None) -> dict:
        """The template's mail with what the sign-off knows filled in: {subject, body, cc,
        missing}. A placeholder with nothing to fill it stays as it is, named in `missing`,
        and holds the mail back until it is filled or rewritten."""
        mail = self.template_mail()
        values = self.mail_values(sender or frappe.session.user)
        missing: set[str] = set()
        subject = " ".join(
            self.fill_placeholders(mail["subject"], values, missing, html=False).split()
        )
        body = self.fill_placeholders(mail["body"], values, missing, html=True)
        return {
            "subject": subject,
            "body": body,
            "cc": mail["cc"],
            "missing": [self.placeholder_label(name) for name in sorted(missing)],
        }

    @staticmethod
    def fill_placeholders(text: str, values: dict, missing: set, html: bool) -> str:
        def fill(match):
            name = match.group(1)
            if name == LINK_PLACEHOLDER:
                # filled when the link is made, as the mail goes out
                return "{{ " + LINK_PLACEHOLDER + " }}"
            value = values.get(name)
            if value:
                return escape_html(value) if html else value
            if name in values and name in OPTIONAL_PLACEHOLDERS:
                return ""
            missing.add(name)
            return match.group(0)

        return PLACEHOLDER.sub(fill, text or "")

    def mail_values(self, sender: str) -> dict:
        """What the placeholders say, from the sign-off, its contact and who sends it."""
        from helpdesk.api.config import get_config

        contact = (
            frappe.db.get_value(
                "Contact", self.signatory_contact, ["salutation"], as_dict=True
            )
            if self.signatory_contact
            else None
        )
        designation = None
        if frappe.get_meta("Employee").has_field("designation"):
            designation = frappe.db.get_value(
                "Employee", {"user_id": sender, "status": "Active"}, "designation"
            )
        if self.is_uat():
            # a UAT's modules are its tests' sections, from the SRS
            modules = ", ".join(
                dict.fromkeys(r.section for r in self.items if r.section)
            )
        else:
            modules = self.module_title
        return {
            "contact_salutation": contact.salutation if contact else "",
            "contact_name": self.signatory_name or "",
            "customer_name": self.customer_name() if self.customer else "",
            "project_name": self.project_name
            or frappe.db.get_value("Project", self.project, "project_name")
            or "",
            "modules": modules or "",
            "training_date": formatdate(self.training_date)
            if self.training_date
            else "",
            "trainer_name": get_fullname(self.trainer) if self.trainer else "",
            "sender_name": get_fullname(sender) if sender != "Guest" else "",
            "sender_designation": designation or "",
            "company_name": get_config().brand_name or "TBO",
        }

    @classmethod
    def placeholder_label(cls, name: str) -> str:
        """A placeholder in the words of the form that fills it."""
        return cls.placeholder_labels().get(name, "{{ " + name + " }}")

    @staticmethod
    def placeholder_labels() -> dict:
        return {
            "contact_salutation": _("the contact's salutation"),
            "contact_name": _("Signs off for the customer"),
            "customer_name": _("the project's customer"),
            "project_name": _("the project's name"),
            "modules": _("Module"),
            "training_date": _("Training date"),
            "trainer_name": _("Trainer"),
            "sender_name": _("your name"),
            "sender_designation": _("your designation"),
            "company_name": _("the company's name"),
        }

    def customer_status(self) -> str:
        """The status in the customer's terms: Sent turns Viewed once they opened the link with
        their code (since it was last sent)."""
        if self.status != SENT or not self.link_sent_on:
            return self.status
        sent = get_datetime(self.link_sent_on)
        opened = any(
            row.event == _("Code verified") and get_datetime(row.at) >= sent
            for row in self.log
        )
        return "Viewed" if opened else self.status

    # --- the reminder (docs/project-signoff.md, Reminders) ---

    def reminder_due(self, calendar) -> bool:
        """Sent and still unanswered after two working days, with a link that works, and not
        reminded since that link went out."""
        return bool(
            self.status == SENT
            and not self.reminder_sent_on
            and self.link_is_open()
            and calendar.working_days_since(getdate(self.link_sent_on))
            >= REMINDER_AFTER_WORKING_DAYS
        )

    def send_reminder(self):
        """The one polite reminder: the same mail with a new link (the old one stops working),
        in the name of whoever sent it; they are told."""
        from helpdesk.work_reminders import notify_users

        sender = self.link_sent_by
        token = self.issue_link()
        self.link_sent_by = sender
        self.reminder_sent_on = now_datetime()
        self.log_event(
            _("Reminder sent"), detail=_("To {0}").format(self.signatory_email)
        )
        self.save(ignore_permissions=True)
        if self.email_subject:
            subject = _("Reminder: {0}").format(self.email_subject)
            message = self.mail_with_link(token, reminder=True)
        else:
            subject = _("Reminder: please complete the {0} sign-off").format(
                self.module_title
            )
            message = (
                "<p>"
                + _("Hello {0},").format(escape_html(self.signatory_name or ""))
                + "</p>"
                + self.mail_with_link(token, reminder=True)
            )
        self.deliver(subject, message)
        notify_users(
            [sender],
            self.doctype,
            self.name,
            _(
                "{0} hasn't answered the {1} sign-off in two working days: a reminder went out."
            ).format(self.signatory_name or self.signatory_email, self.module_title),
            link=self.helpdesk_path(),
        )

    # --- customer answers ---

    def ensure_open_for_customer(self):
        if self.status == SIGNED:
            frappe.throw(_("This sign-off is already signed."))
        if self.status == DRAFT:
            frappe.throw(_("This sign-off hasn't been sent yet."))

    def record_response(
        self,
        item: str,
        response: str,
        comment: str,
        email: str,
        ip_address: str | None = None,
    ) -> bool:
        """The customer's answer to one question; True if a clarification is now needed."""
        self.ensure_open_for_customer()
        if response not in CUSTOMER_RESPONSES:
            frappe.throw(
                _("Choose Pass, Fail or Blocker.")
                if self.is_uat()
                else _("Choose Done, Not clear or Escalate.")
            )
        comment = (comment or "").strip()[:MAX_TEXT]
        if response in NEEDS_FOLLOW_UP and not comment:
            frappe.throw(
                _("Say what went wrong, so we can fix it.")
                if self.is_uat()
                else _("Tell your trainer what needs explaining, so they can help.")
            )
        row = self.get_item(item)
        if (row.response, row.customer_comment or "") == (response, comment):
            return False
        changed_response = row.response != response
        row.response = response
        row.customer_comment = comment
        row.responded_on = now_datetime()
        self.flags.signoff_action = True
        self.log_event(
            _("Marked {0}").format(_(response)) if changed_response else _("Comment"),
            item=row.name,
            detail=comment,
            by_email=email,
            by_name=self.signatory_name,
            ip_address=ip_address,
        )
        self.refresh_status()
        return changed_response and response in NEEDS_FOLLOW_UP

    def follow_up(self, item: str):
        """Turn a Not clear / Escalated answer into a task for the trainer and tell the right people.

        Sets the item's task link in memory; the caller saves the sign-off.
        """
        row = self.get_item(item)
        escalate = row.response == ESCALATED
        task = self.open_clarification_task(row)
        if task:
            if escalate:
                self.escalate_task(task)
        else:
            row.clarification_task = self.create_clarification_task(row, escalate).name
        self.notify_follow_up(row, escalate)

    def escalate_task(self, task):
        """An escalated item's open task becomes Urgent and due tomorrow at the latest."""
        tomorrow = add_days(nowdate(), 1)
        changed = task.priority != "Urgent"
        task.priority = "Urgent"
        if not task.exp_end_date or getdate(task.exp_end_date) > getdate(tomorrow):
            task.exp_end_date = tomorrow
            changed = True
        if changed:
            task.save(ignore_permissions=True)

    def open_clarification_task(self, row):
        if not row.clarification_task:
            return None
        task = frappe.get_doc("Task", row.clarification_task)
        return None if task.status in TASK_DONE else task

    def create_clarification_task(self, row, escalate: bool):
        from helpdesk.tasky.api import _assign_user
        from helpdesk.tasky.new_assignments import told_by_caller

        link = get_url(f"/helpdesk{self.helpdesk_path()}")
        description = "".join(
            [
                "<p>"
                + _("{0} marked this item of the {1} sign-off as {2}:").format(
                    escape_html(self.signatory_name or self.signatory_email),
                    escape_html(self.module_title),
                    _(row.response),
                )
                + "</p>",
                f"<blockquote>{escape_html(row.question)}</blockquote>",
                f"<p><strong>{_('Their comment')}:</strong> {escape_html(row.customer_comment or '')}</p>",
                "<p>"
                + _(
                    "Explain it to them (schedule a meeting from this task if a session helps), then mark the item clarified on the sign-off: {0}"
                ).format(f'<a href="{link}">{escape_html(self.module_title)}</a>')
                + "</p>",
            ]
        )
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": (
                    _("Fix: {0}") if self.is_uat() else _("Clarify: {0}")
                ).format(row.question)[:140],
                "project": self.project,
                "status": "Open",
                "priority": "Urgent" if escalate else "High",
                "custom_category": "Functional",
                "exp_end_date": add_days(nowdate(), 1 if escalate else 3),
                "description": description,
            }
        ).insert(ignore_permissions=True)
        # notify_follow_up tells them about the item
        with told_by_caller():
            _assign_user(
                task, self.trainer or self.project_lead(), ignore_permissions=True
            )
        return task

    def notify_follow_up(self, row, escalate: bool):
        from helpdesk.work_reminders import (
            _agent_managers,
            get_project_managers,
            notify_users,
        )

        people = [self.trainer, self.project_lead()]
        if escalate:
            people += get_project_managers(self.project) + _agent_managers()
        who = self.signatory_name or self.signatory_email
        subject = (
            _("{0} escalated an item of the {1} sign-off: {2}")
            if escalate
            else _("{0} needs clarification on the {1} sign-off: {2}")
        ).format(who, self.module_title, row.question[:120])
        notify_users(
            people,
            self.doctype,
            self.name,
            subject,
            escalate=escalate,
            link=self.helpdesk_path(),
        )

    # --- clarification ---

    def mark_clarified(self, item: str, note: str = "", from_task: bool = False):
        """The trainer explained the item: it goes back to Pending for the customer to answer again."""
        if self.status == SIGNED:
            frappe.throw(_("This sign-off is signed."))
        row = self.get_item(item)
        if row.response not in NEEDS_FOLLOW_UP:
            frappe.throw(_("This item isn't waiting for clarification."))
        note = (note or "").strip()[:MAX_TEXT]
        row.response = PENDING
        row.clarified_on = now_datetime()
        row.clarified_by = frappe.session.user
        row.clarification_note = note
        self.flags.signoff_action = True
        self.log_event(
            _("Clarified"),
            item=row.name,
            detail=(
                _("Clarification task {0} completed.").format(row.clarification_task)
                if from_task
                else note
            ),
        )
        if not from_task:
            self.close_clarification_task(row)
        self.refresh_status()

    def close_clarification_task(self, row):
        task = self.open_clarification_task(row)
        if not task:
            return
        task.status = "Completed"
        # the task's own hook would otherwise clarify this item a second time
        task.flags.from_signoff = True
        task.save(ignore_permissions=True)

    def clarify(self, item: str, note: str = "", from_task: bool = False):
        """Mark an item clarified, save, and send the customer a fresh link to answer it again."""
        self.mark_clarified(item, note, from_task=from_task)
        token = self.issue_link() if self.link_token_hash else None
        self.save(ignore_permissions=True)
        if not token:
            return
        pending = sum(
            1 for row in self.items if row.response == PENDING and row.clarified_on
        )
        self.email_customer(
            _("{0} sign-off: ready for you to review again").format(self.module_title),
            (
                _("1 item is ready for you to review again.")
                if pending == 1
                else _("{0} items are ready for you to review again.").format(pending)
            )
            + " "
            + (
                _(
                    "Our team fixed what failed: please test it again. This link replaces the one we sent before."
                )
                if self.is_uat()
                else _(
                    "Your trainer has followed up on what wasn't clear. This link replaces the one we sent before."
                )
            ),
            token,
        )

    # --- signing ---

    def sign(
        self,
        full_name: str,
        designation: str,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ):
        self.ensure_open_for_customer()
        if (email or "").lower() != (self.signatory_email or "").lower():
            frappe.throw(
                _("Only {0} can sign this off.").format(self.signatory_email),
                frappe.PermissionError,
            )
        if not self.all_done():
            frappe.throw(
                _("Every test must pass before signing.")
                if self.is_uat()
                else _("Mark every item Done before signing.")
            )
        full_name = (full_name or "").strip()[:MAX_NAME]
        designation = (designation or "").strip()[:MAX_NAME]
        if not full_name or not designation:
            frappe.throw(_("Enter your full name and designation to sign."))
        self.signed_on = now_datetime()
        self.signer_name = full_name
        self.signer_designation = designation
        self.signer_email = self.signatory_email
        self.signer_ip = ip_address
        self.signer_user_agent = (user_agent or "")[:500]
        self.status = SIGNED
        self.audit_ref = self.compute_audit_ref()
        self.flags.signoff_action = True
        self.log_event(
            _("Signed"),
            detail=_("{0}, {1}").format(full_name, designation),
            by_email=email,
            by_name=full_name,
            ip_address=ip_address,
        )

    def compute_audit_ref(self) -> str:
        payload = {
            "signoff": self.name,
            "project": self.project,
            "module": self.module_title,
            "items": [
                [r.section, r.question, r.response, r.customer_comment or ""]
                for r in self.items
            ],
            "signer": [self.signer_name, self.signer_designation, self.signer_email],
            "signed_on": str(self.signed_on),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def sign_off(
        self,
        full_name: str,
        designation: str,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ):
        """Sign, save the PDF on the project, email it, tell our people and the lead's timeline,
        and complete the project if this was the last one."""
        self.sign(full_name, designation, email, ip_address, user_agent)
        pdf, content = self.make_signed_pdf()
        self.signed_pdf = pdf.name
        self.save(ignore_permissions=True)
        self.email_signed_pdf(pdf.file_name, content)
        self.notify_signed()
        self.complete_project_if_all_signed()
        self.tell_erp_site()
        self.tell_crm_lead()

    def reopen(self, reason: str):
        if self.status != SIGNED:
            frappe.throw(_("Only a signed sign-off can be reopened."))
        reason = (reason or "").strip()[:MAX_TEXT]
        if not reason:
            frappe.throw(
                _(
                    "Say why it is being reopened; the customer's signature is withdrawn."
                )
            )
        self.log_event(
            _("Reopened"),
            detail=_("{0} (was signed by {1} on {2}; PDF {3})").format(
                reason,
                self.signer_name,
                format_datetime(self.signed_on),
                self.signed_pdf or "-",
            ),
        )
        for field in (
            "signed_on",
            "signer_name",
            "signer_designation",
            "signer_email",
            "signer_ip",
            "signer_user_agent",
            "audit_ref",
            "signed_pdf",
        ):
            self.set(field, None)
        self.status = REOPENED
        self.flags.signoff_action = True
        if not self.is_uat():
            # the project's training is no longer fully signed off (a UAT isn't in the letter)
            frappe.db.set_value("Project", self.project, "custom_signoff_letter", None)
        self.tell_erp_site()

    def signed_line(self) -> str:
        """How the signature reads on the lead's timeline and in the notification."""
        who = _("{0}, {1}").format(self.signer_name, self.signer_designation)
        return (
            _("UAT signed by {0}").format(who)
            if self.is_uat()
            else _("{0} training signed off by {1}").format(self.module_title, who)
        )

    def notify_signed(self):
        """Who sent it and the project lead hear at once (the lead's owner from the lead,
        after the commit: helpdesk.api.project_signoff.note_signed_on_crm_lead)."""
        from helpdesk.work_reminders import notify_users

        notify_users(
            [self.link_sent_by, self.project_lead()],
            self.doctype,
            self.name,
            _("{0} ({1})").format(
                self.signed_line(), self.project_name or self.project
            ),
            link=self.helpdesk_path(),
            once=False,
        )

    def tell_crm_lead(self):
        """A project made for a lead: the signature goes on the lead's timeline on the ERP site
        and its owner is told, after the commit, so a slow ERP site never holds up the customer."""
        if frappe.db.get_value("Project", self.project, "custom_crm_lead"):
            frappe.enqueue(
                "helpdesk.api.project_signoff.note_signed_on_crm_lead",
                signoff=self.name,
                note=self.signed_line(),
                enqueue_after_commit=True,
            )

    # --- UAT ---

    def is_uat(self) -> bool:
        return self.signoff_type == UAT

    def tell_erp_site(self):
        """A UAT's state (Signed, Reopened) goes to its plan on the ERP site, after the
        commit, so a slow or failing ERP site never holds up the customer."""
        if self.is_uat() and self.crm_plan:
            # the state as of now: a reopen before the job runs mustn't replace the signature
            frappe.enqueue(
                "helpdesk.api.project_signoff.record_uat_on_erp",
                signoff=self.name,
                status=self.status,
                signed_by=self.signer_name if self.status == SIGNED else None,
                enqueue_after_commit=True,
            )

    # --- documents ---

    def brand(self) -> dict:
        from helpdesk.api.config import get_config

        config = get_config()
        return {
            "name": config.brand_name or "TBO",
            "logo": self.logo_data_uri(config.brand_logo),
        }

    @staticmethod
    def logo_data_uri(file_url: str | None) -> str | None:
        """The logo inline, so the PDF renderer never has to fetch it over the network."""
        if not file_url:
            return None
        name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if not name:
            return None
        try:
            content = frappe.get_doc("File", name).get_content()
        except Exception:
            return None
        if isinstance(content, str):
            content = content.encode()
        ext = file_url.rsplit(".", 1)[-1].lower()
        mime = {"svg": "image/svg+xml", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
            ext, f"image/{ext}"
        )
        return f"data:{mime};base64,{base64.b64encode(content).decode()}"

    def render_document(
        self, template: str, context: dict, title: str
    ) -> tuple[str, bytes]:
        """(file name, content): a PDF, or a print-ready HTML page where wkhtmltopdf isn't installed."""
        html = frappe.render_template(  # the app's own fixed template, not user input - nosemgrep
            template,
            {"brand": self.brand(), "title": title, **context},
        )
        safe_title = re.sub(r'[\\/:*?"<>|]+', "-", title).strip()
        if shutil.which("wkhtmltopdf"):
            from frappe.utils.pdf import get_pdf

            return f"{safe_title}.pdf", get_pdf(html, {"page-size": "A4"})
        return f"{safe_title}.html", html.encode()

    def save_project_file(self, file_name: str, content: bytes):
        """A private File on the project, so it shows in the project's Files tab."""
        return frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "Project",
                "attached_to_name": self.project,
                "is_private": 1,
                "content": content,
            }
        ).insert(ignore_permissions=True)

    def pdf_context(self) -> dict:
        sections: dict[str, list] = {}
        for row in self.items:
            sections.setdefault(row.section or _("General"), []).append(row)
        customer_name = self.customer_name()
        return {
            "doc": self,
            "sections": sections,
            "customer_name": customer_name,
            "trainer_name": get_fullname(self.trainer) if self.trainer else "",
            "training_date": formatdate(self.training_date)
            if self.training_date
            else "",
            "signed_on": format_datetime(self.signed_on),
            # long sentences live here: an HTML formatter would wrap them inside _()
            "lede": (
                _(
                    "{0} confirms that it tested the system as listed below and accepts it."
                )
                if self.is_uat()
                else _(
                    "{0} confirms that the training listed below has been completed."
                )
            ).format(customer_name),
            "confirmation": _(
                "I confirm that we tested the system as listed above and accept it."
            )
            if self.is_uat()
            else _(
                "I confirm that the training listed above has been completed to our satisfaction."
            ),
            "kind_title": _("User acceptance sign-off")
            if self.is_uat()
            else _("Training sign-off"),
            "answers": self.answer_labels(),
        }

    def answer_labels(self) -> dict:
        """How an answer reads: a UAT's Done is Pass, Not clear Fail, Escalated Blocker."""
        if self.is_uat():
            return {DONE: _("Pass"), NOT_CLEAR: _("Fail"), ESCALATED: _("Blocker")}
        return {response: _(response) for response in CUSTOMER_RESPONSES}

    def customer_name(self) -> str:
        return (
            frappe.db.get_value("HD Customer", self.customer, "customer_name")
            or self.customer
        )

    def make_signed_pdf(self):
        file_name, content = self.render_document(
            "helpdesk/templates/signoff/signoff_letter.html",
            self.pdf_context(),
            (
                _("UAT sign-off - {0} - {1}")
                if self.is_uat()
                else _("Training sign-off - {0} - {1}")
            ).format(self.module_title, self.name),
        )
        return self.save_project_file(file_name, content), content

    def email_signed_pdf(self, file_name: str, content: bytes):
        # the signer, and our people: who sent it, the trainer and the project lead
        recipients = {
            self.signatory_email,
            self.link_sent_by,
            self.trainer,
            self.project_lead(),
        }
        frappe.sendmail(
            recipients=sorted(r for r in recipients if r),
            subject=(
                _("{0} signed off") if self.is_uat() else _("{0} training signed off")
            ).format(self.module_title),
            message="<p>"
            + (
                _(
                    "{0} ({1}) accepted {2} for {3} on {4}. The signed record is attached."
                )
                if self.is_uat()
                else _(
                    "{0} ({1}) signed off the {2} training for {3} on {4}. The signed record is attached."
                )
            ).format(
                escape_html(self.signer_name),
                escape_html(self.signer_designation),
                escape_html(self.module_title),
                escape_html(self.project_name or self.project),
                format_datetime(self.signed_on),
            )
            + "</p>",
            attachments=[{"fname": file_name, "fcontent": content}],
            reference_doctype=self.doctype,
            reference_name=self.name,
        )

    # --- project roll-up ---

    def project_signoffs(self) -> list[dict]:
        """The project's training sign-offs (the completion letter's; a UAT isn't one)."""
        return frappe.get_all(
            "HD Project Signoff",
            filters={"project": self.project, "signoff_type": ("!=", UAT)},
            fields=[
                "name",
                "module_title",
                "status",
                "training_date",
                "trainer",
                "signer_name",
                "signer_designation",
                "signatory_email",
                "signed_on",
                "audit_ref",
            ],
            order_by="signed_on asc, creation asc",
            limit_page_length=0,
        )

    def complete_project_if_all_signed(self):
        """Every training sign-off of the project signed: the completion letter goes on the project and out by email."""
        if self.is_uat():
            return
        signoffs = self.project_signoffs()
        if not signoffs or any(s.status != SIGNED for s in signoffs):
            return
        project = frappe.db.get_value(
            "Project", self.project, ["project_name", "project_lead"], as_dict=True
        )
        for s in signoffs:
            s.trainer_name = get_fullname(s.trainer) if s.trainer else ""
            s.training_date = formatdate(s.training_date) if s.training_date else ""
            s.signed_on = format_datetime(s.signed_on)
        file_name, content = self.render_document(
            "helpdesk/templates/signoff/completion_letter.html",
            {
                "project_name": project.project_name or self.project,
                "customer_name": self.customer_name(),
                "signoffs": signoffs,
                # long sentences live here: an HTML formatter would wrap them inside _()
                "lede": _(
                    "Every training module of this project has been signed off by {0}."
                ).format(self.customer_name()),
                "foot": _(
                    "Each module's signed record, with every question and answer, is kept on the project. Generated {0}."
                ).format(format_datetime(now_datetime())),
            },
            _("Project completion - {0}").format(project.project_name or self.project),
        )
        letter = self.save_project_file(file_name, content)
        frappe.db.set_value(
            "Project", self.project, "custom_signoff_letter", letter.name
        )
        recipients = {s.signatory_email for s in signoffs} | {
            s.trainer for s in signoffs if s.trainer
        }
        if project.project_lead:
            recipients.add(project.project_lead)
        frappe.sendmail(
            recipients=sorted(recipients),
            subject=_("{0}: all training signed off").format(
                project.project_name or self.project
            ),
            message="<p>"
            + _(
                "Every module of {0} has been signed off. The project completion letter is attached."
            ).format(escape_html(project.project_name or self.project))
            + "</p>",
            attachments=[{"fname": letter.file_name, "fcontent": content}],
        )


def send_signoff_reminders():
    """Scheduler, daily: on a working day, the one reminder for each sign-off its signatory
    hasn't answered in two working days (docs/project-signoff.md, Reminders). One that fails
    is logged and leaves the others alone."""
    from helpdesk.follow_ups import WorkCalendar

    calendar = WorkCalendar(nowdate())
    if not calendar.is_working_day(calendar.today):
        return
    for name in frappe.get_all(
        "HD Project Signoff",
        filters={
            "status": SENT,
            "reminder_sent_on": ("is", "not set"),
            "link_token_hash": ("is", "set"),
        },
        pluck="name",
    ):
        doc = frappe.get_doc("HD Project Signoff", name)
        if not doc.reminder_due(calendar):
            continue
        frappe.db.savepoint("signoff_reminder")
        try:
            doc.send_reminder()
        except Exception:
            frappe.db.rollback(save_point="signoff_reminder")
            frappe.log_error(title=f"Sign-off reminder failed: {name}")
