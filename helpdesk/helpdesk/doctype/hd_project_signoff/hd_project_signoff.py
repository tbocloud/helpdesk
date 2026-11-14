# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""A customer's sign-off for one stage of a project: a module's training, or (a UAT sign-off)
that they tested the system against its SRS and accept it.

The sign-off goes out as a mail from the app (a Communication on the sign-off, so the customer's
reply lands in the same thread), with the sign-off document attached and, when it has questions,
a link to the questions page. The customer accepts by replying; our coordinator then marks it
signed off (or changes requested). Statuses follow TBO's Sign-off requirements: Draft, Sent,
Changes Requested, Signed Off, Cancelled, set only by those actions.

On the questions page the customer answers Done / Not clear / Escalate; Not clear and Escalate
become clarification tasks for the trainer. A UAT's items are the SRS's test cases on the ERP
site (Pass / Fail / Blocker), and its signing off is recorded on the ERP site's plan, which
starts the warranty. Marking signed off saves the signed PDF on the project; when every training
sign-off of a project is signed off, a project completion letter is generated. See
docs/project-signoff.md.
"""

import base64
import hashlib
import re
import secrets
import shutil

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    add_months,
    cint,
    escape_html,
    format_datetime,
    formatdate,
    get_datetime,
    get_formatted_email,
    get_fullname,
    get_url,
    getdate,
    now_datetime,
    nowdate,
)

from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
    DIGITAL_MARKETING,
    ERPNEXT,
    LEGACY_SECTIONS,
    PAID_ADS,
    PLATFORMS,
    SERVICES,
    STAGES,
    TRAINING_STAGE,
)

DRAFT = "Draft"
SENT = "Sent"
CHANGES_REQUESTED = "Changes Requested"
SIGNED_OFF = "Signed Off"
CANCELLED = "Cancelled"
# the log event "Viewed" is read from: stored as is, so the language of the request doesn't matter
CODE_VERIFIED = "Code verified"

PENDING = "Pending"
DONE = "Done"
NOT_CLEAR = "Not clear"
ESCALATED = "Escalated"
CUSTOMER_RESPONSES = (DONE, NOT_CLEAR, ESCALATED)
NEEDS_FOLLOW_UP = (NOT_CLEAR, ESCALATED)

# details, mail and questions change only before the mail goes out, or after the customer
# asked for changes
EDITABLE_STATUSES = (DRAFT, CHANGES_REQUESTED)
CLOSED_STATUSES = (SIGNED_OFF, CANCELLED)
# a stage's details (TBO's Sign-off requirements, Data model): plain fields and child tables
DETAIL_FIELDS = (
    "erpnext_version",
    "uat_site_url",
    "live_site_url",
    "srs_reference",
    "srs_version",
    "srs_date",
    "uat_start_date",
    "uat_end_date",
    "issues_raised",
    "issues_resolved",
    "go_live_date",
    "support_start_date",
    "support_end_date",
    "support_channel",
    "masters_migrated",
    "opening_balances_migrated",
    "migration_remarks",
    "services",
    "platforms",
    "period_from",
    "period_to",
    "pages_delivered",
    "reach",
    "impressions",
    "engagement_rate",
    "followers_gained",
    "website_visits",
    "leads",
    "performance_summary",
    "approved_budget",
    "actual_spend",
    "billed_through",
    "next_period_plan",
    "delivery_report",
)
DETAIL_TABLES = {
    "modules": ("module", "processes_covered", "status", "remarks"),
    "open_items": ("issue", "severity", "agreed_action", "target_date"),
    "attendees": ("attendee_name", "designation"),
    "deliverables": (
        "deliverable_type",
        "planned_qty",
        "delivered_qty",
        "customer_approved",
        "link",
        "remarks",
    ),
    "carry_forward": ("item", "reason", "moved_to"),
}
# what can't change while the customer has the mail (questions are checked on their own)
LOCKED_FIELDS = (
    "module_title",
    "training_date",
    "trainer",
    "signatory_contact",
    "customer_address",
    "cc_emails",
    "email_subject",
    "email_body",
    "attach_pdf",
    "declaration",
    *DETAIL_FIELDS,
)
# the words TBO Smart's record_uat knows for a UAT's state
ERP_STATES = {SIGNED_OFF: "Signed", CANCELLED: "Reopened"}
LINK_TTL_DAYS = 30
TASK_DONE = ("Completed", "Cancelled")
MAX_TEXT = 1000
PORTAL_PATH = "/project-signoff"
TRAINING = "Training"
UAT = "UAT"
# the requirements' two print formats, and the app templates they include
PRINT_FORMATS = {
    ERPNEXT: "Sign-off – ERPNext Implementation",
    DIGITAL_MARKETING: "Sign-off – Digital Marketing",
}
DOCUMENT_TEMPLATES = {
    ERPNEXT: "helpdesk/templates/signoff/signoff_erpnext.html",
    DIGITAL_MARKETING: "helpdesk/templates/signoff/signoff_digital.html",
}

# a mail's placeholders, {{ name }}: filled from the sign-off, never run as a template, so a
# template's text can't execute anything (docs/project-signoff.md, Mail)
PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z_]+)\s*}}")
LINK_PLACEHOLDER = "sign_off_link"
# left blank when unknown rather than holding the mail back (a missing address only warns)
OPTIONAL_PLACEHOLDERS = ("sender_designation", "customer_address")
# what a filled-in detail is called in "Fill …" (the form's labels)
DETAIL_LABELS = {
    "modules": "Modules covered",
    "training_date": "Training date",
    "trainer": "Trainer",
    "erpnext_version": "ERPNext version",
    "uat_site_url": "UAT site URL",
    "live_site_url": "Live site URL",
    "srs_reference": "SRS document",
    "srs_version": "SRS version",
    "srs_date": "SRS date",
    "uat_start_date": "UAT start date",
    "uat_end_date": "UAT end date",
    "go_live_date": "Go-live date",
    "support_start_date": "Support start date",
    "support_end_date": "Support end date",
    "services": "Services",
    "platforms": "Platforms",
    "period_from": "Period from",
    "period_to": "Period to",
}
REMINDER_AFTER_WORKING_DAYS = 2
EMAIL_SPLIT = re.compile(r"[,;\s]+")


class HDProjectSignoff(Document):
    def before_insert(self):
        self.copy_template_items()
        self.copy_template_details()
        self.log_event(_("Created"))

    def validate(self):
        self.validate_project()
        self.set_title()
        self.validate_trainer()
        self.set_signatory()
        self.validate_address()
        self.clean_items()
        self.clean_details()
        self.clean_mail()
        self.prevent_locked_changes()

    def on_trash(self):
        self.prevent_deleting_signed_off()

    # --- validation ---

    def validate_project(self):
        if self.is_new() and not self.customer:
            frappe.throw(
                _(
                    "Set the customer on project {0} first; the signatory must be one of its contacts."
                ).format(self.project_name or self.project)
            )

    def set_title(self):
        """A training's title is its modules; any other sign-off keeps its own, else its stage
        or template's name. Only a training needs its modules, and only when it is sent (TBO's
        Sign-off requirements, Record rules)."""
        modules = self.module_names()
        if self.stage == TRAINING_STAGE and modules:
            self.module_title = ", ".join(modules)[:140]
        self.module_title = (
            (self.module_title or "").strip() or self.stage or self.template or ""
        )
        if not self.module_title:
            frappe.throw(_("Pick a template, or name what the sign-off is for."))

    def module_names(self) -> list[str]:
        return [r.module.strip() for r in self.modules if (r.module or "").strip()]

    def clean_details(self):
        """The stage's details: known services and platforms, periods that run forward,
        counts that aren't negative, and blank table rows dropped."""
        self.services = self.clean_choices(self.services, SERVICES)
        self.platforms = self.clean_choices(self.platforms, PLATFORMS)
        for start, end, label in (
            ("period_from", "period_to", _("The period")),
            ("uat_start_date", "uat_end_date", _("UAT")),
            ("support_start_date", "support_end_date", _("The support period")),
        ):
            if (
                self.get(start)
                and self.get(end)
                and getdate(self.get(start)) > getdate(self.get(end))
            ):
                frappe.throw(_("{0} ends before it starts.").format(label))
        for field in (
            "issues_raised",
            "issues_resolved",
            "reach",
            "impressions",
            "followers_gained",
            "website_visits",
            "leads",
        ):
            if cint(self.get(field)) < 0:
                frappe.throw(
                    _("{0} can't be negative.").format(_(self.meta.get_label(field)))
                )
        if cint(self.issues_resolved) > cint(self.issues_raised) and self.issues_raised:
            frappe.throw(_("More issues are resolved than were raised."))
        for table, fields in DETAIL_TABLES.items():
            first = fields[0]
            self.set(
                table, [r for r in self.get(table) if str(r.get(first) or "").strip()]
            )

    @staticmethod
    def clean_choices(text: str | None, allowed: tuple[str, ...]) -> str:
        """Comma-separated choices from `allowed`, in its order, each once."""
        picked = {p.strip().lower() for p in (text or "").split(",") if p.strip()}
        unknown = picked - {a.lower() for a in allowed}
        if unknown:
            frappe.throw(
                _("{0} isn't one of: {1}.").format(
                    ", ".join(sorted(unknown)), ", ".join(allowed)
                )
            )
        return ", ".join(a for a in allowed if a.lower() in picked)

    def shown_sections(self) -> tuple[str, ...]:
        """The parts of the details and the document this sign-off's stage shows (ad spend
        on a month's deliverables only when Paid Ads is a service)."""
        stage = STAGES.get(self.stage or "")
        if not stage:
            return LEGACY_SECTIONS
        sections = stage["sections"]
        if self.stage == "Monthly Deliverables Sign-off" and PAID_ADS not in (
            self.services or ""
        ):
            sections = tuple(s for s in sections if s != "ad_spend")
        return sections

    def kind(self) -> str:
        """ERP Implementation or Digital Marketing: which document it gets."""
        stage = STAGES.get(self.stage or "")
        return stage["project_type"] if stage else ERPNEXT

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
        contact = self.contact_details(self.signatory_contact)
        if not contact or not self.is_customer_contact(self.signatory_contact):
            frappe.throw(
                _("{0} isn't a contact of {1}. Add them to the customer first.").format(
                    self.signatory_contact, self.customer
                )
            )
        if not contact.email_id:
            frappe.throw(
                _(
                    "{0} has no email address. Add one to the contact, so they can get the sign-off mail."
                ).format(self.signatory_contact)
            )
        self.signatory_email = contact.email_id.strip().lower()
        self.signatory_name = contact.full_name

    @staticmethod
    def contact_details(contact: str) -> frappe._dict | None:
        """A contact's full name, email and designation."""
        row = frappe.db.get_value(
            "Contact",
            contact,
            ["full_name", "first_name", "last_name", "email_id", "designation"],
            as_dict=True,
        )
        if row:
            row.full_name = (
                row.full_name
                or " ".join(n for n in (row.first_name, row.last_name) if n)
                or row.email_id
            )
        return row

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

    def validate_address(self):
        """The address is one of the customer's (linked to it, as Frappe's addresses are)."""
        if not self.customer_address or not self.has_value_changed("customer_address"):
            return
        if not frappe.db.exists(
            "Dynamic Link",
            {
                "parenttype": "Address",
                "parent": self.customer_address,
                "link_doctype": "HD Customer",
                "link_name": self.customer,
            },
        ):
            frappe.throw(
                _("{0} isn't an address of {1}.").format(
                    self.customer_address, self.customer
                )
            )

    def clean_items(self):
        # questions are optional: a sign-off accepted by reply needs none
        rows = []
        for row in self.items:
            row.section = (row.section or "").strip()
            row.question = (row.question or "").strip()
            row.help_text = (row.help_text or "").strip()
            row.response = row.response or PENDING
            if row.question:
                rows.append(row)
        self.items = rows

    def prevent_locked_changes(self):
        """Details, mail and questions change only in Draft or Changes Requested; a signed-off
        or cancelled sign-off doesn't change at all. Actions pass `signoff_action`."""
        before = self.get_doc_before_save()
        if not before or self.flags.signoff_action:
            return
        if before.status in CLOSED_STATUSES:
            frappe.throw(
                _("This sign-off is {0}, so it can't be changed.").format(
                    _(before.status).lower()
                )
            )
        if before.status in EDITABLE_STATUSES:
            return
        if (
            self.question_rows(before) != self.question_rows(self)
            or any(before.get(field) != self.get(field) for field in LOCKED_FIELDS)
            or any(
                self.table_rows(before, table) != self.table_rows(self, table)
                for table in DETAIL_TABLES
            )
        ):
            frappe.throw(
                _(
                    "The mail went out, so this sign-off is read-only. Mark changes requested to edit it again."
                )
            )

    def prevent_deleting_signed_off(self):
        if self.status == SIGNED_OFF:
            frappe.throw(
                _(
                    "A signed-off sign-off can't be deleted. A System Manager can cancel it."
                )
            )

    @staticmethod
    def question_rows(doc) -> list[tuple]:
        return [(r.section, r.question, r.help_text) for r in doc.items]

    @staticmethod
    def table_rows(doc, table: str) -> list[tuple]:
        return [tuple(r.get(f) for f in DETAIL_TABLES[table]) for r in doc.get(table)]

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

    @staticmethod
    def mail_addresses(*users: str | None) -> list[str]:
        """Our people as mail addresses, without repeats. A user that isn't an email
        (Administrator) is left out: one bad address and Frappe drops the whole mail."""
        found = []
        for user in users:
            if user and user not in found and frappe.utils.validate_email_address(user):
                found.append(user)
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

    def copy_template_details(self):
        """The template's kind, stage and declaration, and (a month's deliverables) the
        previous calendar month as the period when none is given."""
        if not self.template:
            return
        template = frappe.db.get_value(
            "HD Signoff Template",
            self.template,
            ["stage", "declaration_text", "module", "signoff_type"],
            as_dict=True,
        )
        # a UAT template makes a UAT (Pass / Fail, recorded on the plan when there is one)
        if template.signoff_type == UAT:
            self.signoff_type = UAT
        self.stage = self.stage or template.stage
        self.declaration = self.declaration or template.declaration_text
        if self.stage == TRAINING_STAGE and not self.modules and template.module:
            self.append("modules", {"module": template.module, "status": "Completed"})
        if self.stage == "Monthly Deliverables Sign-off" and not self.period_from:
            first = getdate(add_months(nowdate(), -1)).replace(day=1)
            self.period_from = first
            self.period_to = add_days(add_months(first, 1), -1)

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

    def project_lead(self) -> str | None:
        return frappe.db.get_value("Project", self.project, "project_lead")

    def helpdesk_path(self) -> str:
        return f"/projects/{self.project}/signoff/{self.name}"

    # --- customer link (the questions page) ---

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
        if self.status in CLOSED_STATUSES:
            frappe.throw(_("This sign-off is closed."))
        token = secrets.token_urlsafe(32)
        self.link_token_hash = self.hash_token(token)
        self.link_expires_on = add_days(now_datetime(), LINK_TTL_DAYS)
        self.flags.signoff_action = True
        return token

    def revoke_link(self, log: bool = True):
        if not self.link_token_hash:
            if log:
                frappe.throw(_("There is no open link to revoke."))
            return
        self.link_token_hash = None
        self.link_expires_on = None
        self.flags.signoff_action = True
        if log:
            self.log_event(_("Link revoked"))

    def link_is_open(self) -> bool:
        return bool(
            self.link_token_hash
            and self.status == SENT
            and self.link_expires_on
            and get_datetime(self.link_expires_on) > now_datetime()
        )

    # --- sending (TBO's Sign-off requirements, Sending the sign-off mail) ---

    def check_ready_to_send(self):
        """Who it goes to, the mail and what the mail uses are complete."""
        if not self.customer:
            frappe.throw(_("This project has no customer."))
        if not self.signatory_email:
            frappe.throw(_("Pick who signs off for the customer."))
        self.clean_emails(self.cc_emails)
        if not self.email_subject or not self.mail_body_text():
            frappe.throw(_("Write the mail's subject and message before sending it."))
        self.check_mail_ready()
        self.check_stage_details()
        uses_link = LINK_PLACEHOLDER in PLACEHOLDER.findall(self.email_body or "")
        if uses_link and not self.items:
            frappe.throw(
                _(
                    "The mail links to the questions page, but there are no questions. Add questions, or take {0} out of the mail."
                ).format("{{ " + LINK_PLACEHOLDER + " }}")
            )

    def check_stage_details(self):
        """What the stage needs is filled (TBO's Sign-off requirements: the go-live date for
        UAT Sign-off and Go-Live, the modules and training date for a training...)."""
        stage = STAGES.get(self.stage or "")
        if not stage:
            return
        missing = [
            _(DETAIL_LABELS.get(field, field))
            for field in stage["required"]
            if not (self.get(field) if field != "modules" else self.module_names())
        ]
        if missing:
            frappe.throw(
                _("Fill {0}: the {1} needs it.").format(
                    ", ".join(missing), _(self.stage)
                )
            )

    def check_mail_ready(self):
        """A mail goes out only with every placeholder filled."""
        left = {
            name
            for name in PLACEHOLDER.findall(
                f"{self.email_subject or ''} {self.email_body or ''}"
            )
            if name != LINK_PLACEHOLDER
        }
        if left:
            frappe.throw(
                _("Fill {0}: it is used in the mail.").format(
                    ", ".join(self.placeholder_label(name) for name in sorted(left))
                )
            )

    def snapshot_customer(self):
        """What the mail and the document say about the customer, kept as it was when sent,
        so a later change to the customer's records doesn't change what they got."""
        contact = self.contact_details(self.signatory_contact)
        self.signatory_name = contact.full_name if contact else self.signatory_name
        self.signatory_designation = (contact.designation if contact else "") or ""
        self.address_display = self.formatted_address()

    def formatted_address(self) -> str:
        if not self.customer_address:
            return ""
        from frappe.contacts.doctype.address.address import render_address

        # validated to be the customer's own; sending needs the project, not Address
        return render_address(self.customer_address, check_permissions=False) or ""

    def send_mail(self, reminder: bool = False):
        """Send the sign-off mail (or, `reminder`, the same mail again with "Reminder:"), save.

        With questions, a new link to the questions page goes in (the old one stops working);
        with Attach sign-off document, the document goes too. A reminder keeps the status
        Sent; a first send (or one after changes were requested) makes it Sent."""
        if self.status in CLOSED_STATUSES:
            frappe.throw(_("This sign-off is closed."))
        if reminder and self.status != SENT:
            frappe.throw(_("Only a sent sign-off gets a reminder."))
        if not reminder and self.status not in EDITABLE_STATUSES:
            frappe.throw(
                _(
                    "The mail already went out. Send a reminder, or mark changes requested to change it."
                )
            )
        self.check_ready_to_send()
        sender = (self.link_sent_by if reminder else None) or frappe.session.user
        if not reminder:
            self.snapshot_customer()
        token = self.issue_link() if self.items else None
        attachments = self.mail_attachments(fresh=not reminder)
        self.record_sending(reminder, sender)
        self.save(ignore_permissions=True)
        subject = (
            _("Reminder: {0}").format(self.email_subject)
            if reminder
            else self.email_subject
        )
        self.deliver(
            subject,
            self.mail_with_link(token, reminder=reminder),
            sender=sender,
            cc=self.cc_list(),
            attachments=attachments,
        )

    def record_sending(self, reminder: bool, sender: str):
        resend = bool(self.link_sent_on)
        self.flags.signoff_action = True
        if reminder:
            self.reminder_sent_on = now_datetime()
            event = _("Reminder sent")
        else:
            self.status = SENT
            self.link_sent_on = now_datetime()
            self.link_sent_by = sender if sender != "Guest" else None
            self.reminder_sent_on = None
            self.remarks = None
            event = _("Mail sent again") if resend else _("Mail sent")
        self.log_event(
            event,
            detail=_("To {0}").format(self.signatory_email)
            + (_("; CC {0}").format(self.cc_emails) if self.cc_emails else ""),
        )

    def mail_attachments(self, fresh: bool) -> list:
        """The sign-off document as a File on the project: made anew for each send, the one
        sent before for a reminder."""
        files = []
        if self.attach_pdf:
            if fresh or not self.sent_pdf:
                file_name, content = self.render_document(self.document_context())
                self.sent_pdf = self.save_project_file(file_name, content).name
            files.append(self.sent_pdf)
        # a month's or a campaign's delivery report goes along (the requirements, Attachments)
        report = (
            frappe.db.get_value("File", {"file_url": self.delivery_report}, "name")
            if self.delivery_report and "attachments" in self.shown_sections()
            else None
        )
        if report:
            files.append(report)
        return files

    def deliver(
        self,
        subject: str,
        message: str,
        sender: str | None = None,
        cc: list[str] | None = None,
        attachments: list | None = None,
    ):
        """A mail to the signatory as a Communication on the sign-off, so it shows in the mail
        history and the customer's reply lands in the same thread. It goes from the sender's
        own email account when they have one, else the site's default."""
        from frappe.core.doctype.communication.email import _make

        sender = sender or self.link_sent_by or frappe.session.user
        _make(
            doctype=self.doctype,
            name=self.name,
            subject=subject,
            content=message,
            sender=get_formatted_email(sender),
            sender_full_name=get_fullname(sender),
            recipients=[self.signatory_email],
            cc=cc or None,
            attachments=attachments or None,
            send_email=True,
        )

    def cc_list(self) -> list[str]:
        return self.clean_emails(self.cc_emails)

    def mail_with_link(self, token: str | None, reminder: bool = False) -> str:
        """The mail's body with the questions page's link where {{ sign_off_link }} is (or at
        the end) and how the link works; without questions, the body as written."""
        body = self.email_body or ""
        note = ""
        if token:
            url = self.link_url(token)
            link = f'<a href="{url}">{escape_html(url)}</a>'
            if LINK_PLACEHOLDER in PLACEHOLDER.findall(body):
                body = PLACEHOLDER.sub(
                    lambda m: link if m.group(1) == LINK_PLACEHOLDER else m.group(0),
                    body,
                )
            else:
                body += f'<p><a href="{url}">{_("Open the sign-off questions")}</a></p>'
            note = self.link_note()
        intro = ""
        if reminder:
            intro = (
                "<p>"
                + _("A gentle reminder: we haven't heard from you yet.")
                + (
                    " " + _("The link below replaces the one we sent before.")
                    if token
                    else ""
                )
                + "</p>"
            )
        return intro + body + note

    def link_note(self) -> str:
        return (
            '<p style="color:#6b7280">'
            + _(
                "For your security we will email you a one-time code when you open it. The link works for {0} days and only for {1}."
            ).format(LINK_TTL_DAYS, escape_html(self.signatory_email))
            + "</p>"
        )

    # --- the mail's words (docs/project-signoff.md, Mail) ---

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
                return escape_html(value).replace("\n", "<br>") if html else value
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
        # the modules covered; a UAT without them, its tests' sections from the SRS
        modules = ", ".join(self.module_names())
        if not modules and self.is_uat():
            modules = ", ".join(
                dict.fromkeys(r.section for r in self.items if r.section)
            )
        elif not modules and not self.stage:
            modules = self.module_title

        def day(field):
            return formatdate(self.get(field)) if self.get(field) else ""

        return {
            # "Dear Sir/Madam Asha Menon" when the salutation isn't known (the requirements)
            "contact_salutation": (contact.salutation if contact else "")
            or _("Sir/Madam"),
            "contact_name": self.signatory_name or "",
            "customer_name": self.customer_name() if self.customer else "",
            "customer_address": self.formatted_address(),
            "project_name": self.project_name
            or frappe.db.get_value("Project", self.project, "project_name")
            or "",
            "modules": modules or "",
            "training_date": day("training_date"),
            "erpnext_version": self.erpnext_version or "",
            "uat_site_url": self.uat_site_url or "",
            "live_site_url": self.live_site_url or "",
            "uat_start_date": day("uat_start_date"),
            "uat_end_date": day("uat_end_date"),
            "go_live_date": day("go_live_date"),
            "support_start_date": day("support_start_date"),
            "support_end_date": day("support_end_date"),
            "srs_version": self.srs_version or "",
            "srs_date": day("srs_date"),
            "services": self.services or "",
            "period_from": day("period_from"),
            "period_to": day("period_to"),
            "trainer_name": get_fullname(self.trainer) if self.trainer else "",
            "sender_name": get_fullname(sender) if sender != "Guest" else "",
            "sender_designation": self.employee_designation(sender),
            "company_name": get_config().brand_name or "TBO",
        }

    @staticmethod
    def employee_designation(user: str | None) -> str:
        if not user or not frappe.get_meta("Employee").has_field("designation"):
            return ""
        return (
            frappe.db.get_value(
                "Employee", {"user_id": user, "status": "Active"}, "designation"
            )
            or ""
        )

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
            "customer_address": _("Address"),
            "project_name": _("the project's name"),
            "modules": _("Modules covered"),
            "training_date": _("Training date"),
            "erpnext_version": _("ERPNext version"),
            "uat_site_url": _("UAT site URL"),
            "live_site_url": _("Live site URL"),
            "uat_start_date": _("UAT start date"),
            "uat_end_date": _("UAT end date"),
            "go_live_date": _("Go-live date"),
            "support_start_date": _("Support start date"),
            "support_end_date": _("Support end date"),
            "srs_version": _("SRS version"),
            "srs_date": _("SRS date"),
            "services": _("Services"),
            "period_from": _("Period from"),
            "period_to": _("Period to"),
            "trainer_name": _("Trainer"),
            "sender_name": _("your name"),
            "sender_designation": _("your designation"),
            "company_name": _("the company's name"),
        }

    def customer_status(self) -> str:
        """The status in the customer's terms: Sent turns Viewed once they opened the
        questions link with their code (since it was last sent)."""
        if self.status != SENT or not self.link_sent_on:
            return self.status
        sent = get_datetime(self.link_sent_on)
        opened = any(
            row.event == CODE_VERIFIED and get_datetime(row.at) >= sent
            for row in self.log
        )
        return "Viewed" if opened else self.status

    # --- the reminder (docs/project-signoff.md, Reminders) ---

    def reminder_due(self, calendar) -> bool:
        """Sent and still unanswered after two working days, and not reminded since. Not once
        the customer opened it (Viewed): the reminder's new link would end the session they may
        be answering in."""
        return bool(
            self.status == SENT
            and self.customer_status() == SENT
            and not self.reminder_sent_on
            and self.link_sent_on
            and calendar.working_days_since(getdate(self.link_sent_on))
            >= REMINDER_AFTER_WORKING_DAYS
        )

    def send_reminder(self, automatic: bool = False):
        """The same mail again with "Reminder:", in the name of whoever sent it; when the
        daily job sends it, they are told."""
        from helpdesk.work_reminders import notify_users

        self.send_mail(reminder=True)
        if automatic:
            notify_users(
                [self.link_sent_by],
                self.doctype,
                self.name,
                _(
                    "{0} hasn't answered the {1} sign-off in two working days: a reminder went out."
                ).format(self.signatory_name or self.signatory_email, self.label()),
                link=self.helpdesk_path(),
            )

    def label(self) -> str:
        """The sign-off in a sentence: its module, or its template's name."""
        return self.module_title or self.template or self.name or _("Sign-off")

    # --- the customer's reply ---

    def note_reply(self, communication):
        """A reply landed in the sign-off's thread: written on the history, and who sent the
        mail and the project lead are told, so they can mark it signed off or changes
        requested."""
        from helpdesk.work_reminders import notify_users

        self.flags.signoff_action = True
        self.log_event(
            _("Reply received"),
            detail=communication.subject,
            by_email=communication.sender,
            by_name=communication.sender_full_name or communication.sender,
        )
        self.save(ignore_permissions=True)
        notify_users(
            [self.link_sent_by, self.project_lead()],
            self.doctype,
            self.name,
            _("{0} replied to the {1} sign-off").format(
                communication.sender_full_name or communication.sender, self.label()
            ),
            link=self.helpdesk_path(),
            once=False,
        )

    # --- customer answers ---

    def ensure_open_for_customer(self):
        if self.status in CLOSED_STATUSES:
            frappe.throw(_("This sign-off is closed."))
        if self.status != SENT:
            frappe.throw(_("This sign-off isn't open for answers right now."))

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
        if self.status in CLOSED_STATUSES:
            frappe.throw(_("This sign-off is closed."))
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
        token = self.issue_link() if self.link_is_open() else None
        self.save(ignore_permissions=True)
        if not token:
            return
        pending = sum(
            1 for row in self.items if row.response == PENDING and row.clarified_on
        )
        intro = (
            _("1 item is ready for you to review again.")
            if pending == 1
            else _("{0} items are ready for you to review again.").format(pending)
        ) + " "
        intro += (
            _(
                "Our team fixed what failed: please test it again. This link replaces the one we sent before."
            )
            if self.is_uat()
            else _(
                "Your trainer has followed up on what wasn't clear. This link replaces the one we sent before."
            )
        )
        url = self.link_url(token)
        self.deliver(
            _("{0} sign-off: ready for you to review again").format(self.label()),
            "".join(
                [
                    f"<p>{_('Hello {0},').format(escape_html(self.signatory_name or ''))}</p>",
                    f"<p>{intro}</p>",
                    f'<p><a href="{url}">{_("Open the sign-off questions")}</a></p>',
                    self.link_note(),
                ]
            ),
        )

    # --- signed off, changes requested, cancelled ---

    def mark_signed_off(
        self,
        acceptance_reference: str | None = None,
        signed_on: str | None = None,
        signed_off_by: str | None = None,
        signed_copy: str | None = None,
    ):
        """The customer accepted (by replying): who for the customer, when, and the reply as
        evidence (the one picked; none when it came to another mailbox). In memory; `sign_off`
        saves and does the rest."""
        if self.status != SENT:
            frappe.throw(_("Only a sent sign-off can be marked signed off."))
        contact_name = signed_off_by or self.signatory_contact
        if contact_name != self.signatory_contact and not self.is_customer_contact(
            contact_name
        ):
            frappe.throw(
                _("{0} isn't a contact of {1}.").format(contact_name, self.customer)
            )
        contact = self.contact_details(contact_name)
        reply = self.check_reply(acceptance_reference)
        when = get_datetime(signed_on) if signed_on else None
        when = when or (get_datetime(reply.communication_date) if reply else None)
        when = when or now_datetime()
        if getdate(when) > getdate(nowdate()):
            frappe.throw(_("The sign-off date can't be in the future."))
        self.signed_off_by = contact_name
        self.signer_name = contact.full_name
        self.signer_designation = contact.designation or ""
        self.signer_email = (contact.email_id or "").strip().lower()
        self.signed_on = when
        self.acceptance_reference = reply.name if reply else None
        self.signed_copy = self.check_signed_copy(signed_copy)
        self.status = SIGNED_OFF
        self.revoke_link(log=False)
        self.flags.signoff_action = True
        self.log_event(
            _("Marked signed off"),
            detail=_("{0}, {1}").format(self.signer_name, self.signer_designation)
            if self.signer_designation
            else self.signer_name,
        )

    def check_signed_copy(self, file_url: str | None) -> str | None:
        """A signed copy uploaded as the acceptance: a file that exists, kept private on the
        project so it stays with the sign-off."""
        if not file_url:
            return None
        name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if not name:
            frappe.throw(_("The signed copy wasn't uploaded. Upload it again."))
        frappe.db.set_value(
            "File",
            name,
            {"attached_to_doctype": "Project", "attached_to_name": self.project},
        )
        return file_url

    def check_reply(self, communication: str | None) -> frappe._dict | None:
        """The customer's reply: a mail received in this sign-off's thread."""
        if not communication:
            return None
        reply = frappe.db.get_value(
            "Communication",
            communication,
            [
                "name",
                "reference_doctype",
                "reference_name",
                "sent_or_received",
                "communication_date",
            ],
            as_dict=True,
        )
        if (
            not reply
            or (reply.reference_doctype, reply.reference_name)
            != (self.doctype, self.name)
            or reply.sent_or_received != "Received"
        ):
            frappe.throw(_("Pick the customer's reply to this sign-off's mail."))
        return reply

    def sign_off(
        self,
        acceptance_reference: str | None = None,
        signed_on: str | None = None,
        signed_off_by: str | None = None,
        signed_copy: str | None = None,
    ):
        """Mark signed off, save the signed PDF on the project, send it, tell our people and the
        lead's timeline, and complete the project if this was the last training sign-off."""
        self.mark_signed_off(
            acceptance_reference, signed_on, signed_off_by, signed_copy
        )
        pdf, content = self.make_signed_pdf()
        self.signed_pdf = pdf.name
        self.save(ignore_permissions=True)
        self.email_signed_pdf(pdf.file_name, content)
        self.notify_signed()
        self.complete_project_if_all_signed()
        self.tell_erp_site()
        self.tell_crm_lead()

    def mark_changes_requested(self, remarks: str):
        """The customer asked for changes: the sign-off can be edited and sent again; the
        questions link stops, so nobody answers what is about to change."""
        if self.status != SENT:
            frappe.throw(_("Only a sent sign-off can be marked changes requested."))
        remarks = (remarks or "").strip()[:MAX_TEXT]
        if not remarks:
            frappe.throw(_("Write what the customer asked to change."))
        self.status = CHANGES_REQUESTED
        self.remarks = remarks
        self.revoke_link(log=False)
        self.flags.signoff_action = True
        self.log_event(_("Changes requested"), detail=remarks)

    def cancel(self, reason: str):
        """Withdrawn (a System Manager, checked by the API): a signed-off training is no
        longer in the project's completion letter, and a UAT's plan on the ERP site hears."""
        if self.status == CANCELLED:
            frappe.throw(_("This sign-off is already cancelled."))
        reason = (reason or "").strip()[:MAX_TEXT]
        if not reason:
            frappe.throw(_("Say why it is being cancelled."))
        was_signed_off = self.status == SIGNED_OFF
        self.status = CANCELLED
        self.remarks = reason
        self.revoke_link(log=False)
        self.flags.signoff_action = True
        self.log_event(_("Cancelled"), detail=reason)
        if was_signed_off and self.is_training():
            frappe.db.set_value("Project", self.project, "custom_signoff_letter", None)
        if was_signed_off:
            self.tell_erp_site()

    def signed_line(self) -> str:
        """How the sign-off reads on the lead's timeline and in the notification."""
        who = (
            _("{0}, {1}").format(self.signer_name, self.signer_designation)
            if self.signer_designation
            else self.signer_name
        )
        return (
            _("UAT signed off by {0}").format(who)
            if self.is_uat()
            else _("{0} signed off by {1}").format(self.label(), who)
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
        """A project made for a lead: the sign-off goes on the lead's timeline on the ERP site
        and its owner is told, after the commit, so a slow ERP site never holds anyone up."""
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

    def erp_state(self) -> str | None:
        """The UAT's state in the ERP site's words (Signed, Reopened), None for the others."""
        return ERP_STATES.get(self.status)

    def tell_erp_site(self):
        """A UAT's state (signed off, cancelled) goes to its plan on the ERP site, after the
        commit, so a slow or failing ERP site never holds anyone up."""
        if self.is_uat() and self.crm_plan and self.erp_state():
            # the state as of now: a cancel before the job runs mustn't replace the signature
            frappe.enqueue(
                "helpdesk.api.project_signoff.record_uat_on_erp",
                signoff=self.name,
                status=self.erp_state(),
                signed_by=self.signer_name if self.status == SIGNED_OFF else None,
                enqueue_after_commit=True,
            )

    # --- documents ---

    def brand(self) -> dict:
        from helpdesk.api.config import get_config

        config = get_config()
        return {
            "name": config.brand_name or "TBO",
            "logo": self.logo_data_uri(config.brand_logo),
            # the site's default Letter Head (the requirements: our letterhead), when set
            "letter_head": frappe.db.get_value(
                "Letter Head", {"is_default": 1, "disabled": 0}, "content"
            ),
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

    def document_source(self) -> str:
        """The sign-off document's Jinja: its template's print format, else the requirements'
        format for its kind (ERP Implementation or Digital Marketing), else the app template
        that format includes."""
        names = [
            frappe.db.get_value("HD Signoff Template", self.template, "print_format")
            if self.template
            else None,
            PRINT_FORMATS[self.kind()],
        ]
        for name in filter(None, names):
            html = frappe.db.get_value(
                "Print Format", {"name": name, "disabled": 0}, "html"
            )
            if html:
                return html
        return '{% include "' + DOCUMENT_TEMPLATES[self.kind()] + '" %}'

    def render_html(self, context: dict, template: str | None = None) -> str:
        """A document of the sign-off as HTML: the sign-off document (what goes out with the
        mail, previewed on the full page, and once signed off the signed record) through its
        print format, or (`template`) the project's completion letter."""
        if template:
            # the app's own fixed template, not user input - nosemgrep
            return frappe.render_template(template, context)
        # a print format is a System Manager's, as anywhere in Frappe - nosemgrep
        return frappe.render_template(
            self.document_source(), {"doc": self, "ctx": context}
        )

    def render_document(
        self, context: dict, template: str | None = None
    ) -> tuple[str, bytes]:
        """(file name, content): a PDF, or a print-ready HTML page where wkhtmltopdf isn't installed."""
        html = self.render_html(context, template)
        safe_title = re.sub(r'[\\/:*?"<>|]+', "-", context["title"]).strip()
        if shutil.which("wkhtmltopdf"):
            from frappe.utils.pdf import get_pdf

            return f"{safe_title}.pdf", get_pdf(html, {"page-size": "A4"})
        return f"{safe_title}.html", html.encode()

    def document_heading(self) -> str:
        """Titled after the template's stage, e.g. "UAT Sign-off Certificate"."""
        if self.stage:
            return _("{0} Certificate").format(_(self.stage))
        return (
            _("User acceptance sign-off") if self.is_uat() else _("Training sign-off")
        )

    def document_context(self, signed_title: bool = False) -> dict:
        """Everything the two print formats show (TBO's Sign-off requirements, Sign-off
        document): header, customer (as sent), project, the stage's sections, the questions
        with their answers, the declaration and both signatures once signed off. A print
        format opened from Frappe's print view computes it itself."""

        def day(value):
            return formatdate(value) if value else ""

        contact = (
            self.contact_details(self.signatory_contact)
            if self.signatory_contact
            else None
        )
        signed = self.status == SIGNED_OFF
        reply_on = (
            frappe.db.get_value(
                "Communication", self.acceptance_reference, "communication_date"
            )
            if self.acceptance_reference
            else None
        )
        tbo_signer = self.link_sent_by or frappe.session.user
        lead = self.project_lead()
        questions: dict[str, list] = {}
        for row in self.items:
            questions.setdefault(row.section or _("General"), []).append(row)
        heading = self.document_heading()
        return {
            "brand": self.brand(),
            "title": (
                _("{0} - {1} - signed off") if signed_title else _("{0} - {1}")
            ).format(heading, self.name or _("New")),
            "heading": heading,
            "date": day(self.link_sent_on or nowdate()),
            "shown": set(self.shown_sections()),
            "customer_name": self.customer_name(),
            "address": self.address_display or self.formatted_address(),
            "contact_name": self.signatory_name
            or (contact.full_name if contact else ""),
            "contact_designation": self.signatory_designation
            or (contact.designation if contact else "")
            or "",
            "contact_email": self.signatory_email or "",
            "project_name": self.project_name or self.project,
            "project_manager": get_fullname(lead) if lead else "",
            "project_coordinator": self.project_coordinator(),
            "trainer_name": get_fullname(self.trainer) if self.trainer else "",
            "training_date": day(self.training_date),
            "dates": {
                field: day(self.get(field))
                for field in (
                    "srs_date",
                    "uat_start_date",
                    "uat_end_date",
                    "go_live_date",
                    "support_start_date",
                    "support_end_date",
                    "period_from",
                    "period_to",
                )
            },
            "open_item_dates": [day(r.target_date) for r in self.open_items],
            "content_calendar": self.content_calendar_link(),
            "delivery_report_name": (
                self.delivery_report.rsplit("/", 1)[-1] if self.delivery_report else ""
            ),
            "questions": questions,
            "answers": self.answer_labels(),
            "declaration": self.declaration or self.default_declaration(),
            "signed": signed,
            "signed_on": day(self.signed_on) if signed else "",
            "acceptance": (
                _("Email reply of {0}").format(format_datetime(reply_on))
                if reply_on
                else _("Signed copy")
                if self.signed_copy
                else ""
            )
            if signed
            else "",
            "tbo_name": get_fullname(tbo_signer) if tbo_signer != "Guest" else "",
            "tbo_designation": self.employee_designation(tbo_signer),
        }

    def default_declaration(self) -> str:
        """The stage's declaration when the template has none (a stage-less sign-off's are
        a training's or a UAT's)."""
        from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
            DECLARATIONS,
        )

        if self.stage in DECLARATIONS:
            return DECLARATIONS[self.stage]
        # long sentences live here: an HTML formatter would wrap them inside _()
        return (
            _("We confirm that we tested the system as listed above and accept it.")
            if self.is_uat()
            else _(
                "We confirm that the training listed above has been completed to our satisfaction."
            )
        )

    def project_coordinator(self) -> str:
        from helpdesk.tasky.permissions import COORDINATOR_PROJECT_ROLE

        user = frappe.db.get_value(
            "Project User",
            {
                "parenttype": "Project",
                "parent": self.project,
                "custom_role": COORDINATOR_PROJECT_ROLE,
            },
            "user",
        )
        return get_fullname(user) if user else ""

    def content_calendar_link(self) -> str:
        """The content calendar, when the customer has posts in the period (Period: "link to
        that period's content calendar if it is in the app")."""
        if not (self.period_from and self.period_to and self.customer):
            return ""
        if not frappe.db.exists(
            "HD Content Post",
            {
                "customer": self.customer,
                "publish_on": ("between", [self.period_from, self.period_to]),
            },
        ):
            return ""
        return get_url(f"/helpdesk/content?date={self.period_from}")

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
            self.document_context(signed_title=True)
        )
        return self.save_project_file(file_name, content), content

    def email_signed_pdf(self, file_name: str, content: bytes):
        """The signed record to the signatory, copied to our people (who sent it, the trainer
        and the project lead), in the sign-off's thread."""
        # one address that isn't an email (Administrator) and Frappe drops the whole mail
        ours = self.mail_addresses(self.link_sent_by, self.trainer, self.project_lead())
        self.deliver(
            (
                _("{0} training signed off")
                if self.is_training()
                else _("{0} signed off")
            ).format(self.label()),
            "<p>"
            + _(
                "{0} ({1}) signed off {2} for {3} on {4}. The signed record is attached."
            ).format(
                escape_html(self.signer_name or ""),
                escape_html(self.signer_designation or "-"),
                escape_html(self.label()),
                escape_html(self.project_name or self.project),
                formatdate(self.signed_on),
            )
            + "</p>",
            cc=sorted(r for r in ours if r and r != self.signatory_email),
            attachments=[{"fname": file_name, "fcontent": content}],
        )

    # --- project roll-up ---

    def project_signoffs(self) -> list[dict]:
        """The project's training sign-offs that count (the completion letter's; a UAT, another
        stage or a cancelled one doesn't), read as committed and locked, so two signing at once
        can't each see the other unsigned and both skip the letter. A stage-less one made before
        stages is a training."""
        signoff = frappe.qb.DocType("HD Project Signoff")
        rows = (
            frappe.qb.from_(signoff)
            .select(
                signoff.name,
                signoff.stage,
                signoff.module_title,
                signoff.status,
                signoff.training_date,
                signoff.trainer,
                signoff.signer_name,
                signoff.signer_designation,
                signoff.signatory_email,
                signoff.signed_on,
                signoff.acceptance_reference,
            )
            .where(signoff.project == self.project)
            .where(signoff.signoff_type != UAT)
            .where(signoff.status != CANCELLED)
            .orderby(signoff.signed_on)
            .orderby(signoff.creation)
            .for_update()
            .run(as_dict=True)
        )
        return [r for r in rows if r.stage in (None, "", TRAINING_STAGE)]

    def is_training(self) -> bool:
        return not self.is_uat() and self.stage in (None, "", TRAINING_STAGE)

    def complete_project_if_all_signed(self):
        """Every training sign-off of the project signed off: the completion letter goes on the project and out by email."""
        if not self.is_training():
            return
        signoffs = self.project_signoffs()
        if not signoffs or any(s.status != SIGNED_OFF for s in signoffs):
            return
        project = frappe.db.get_value(
            "Project", self.project, ["project_name", "project_lead"], as_dict=True
        )
        for s in signoffs:
            s.trainer_name = get_fullname(s.trainer) if s.trainer else ""
            s.training_date = formatdate(s.training_date) if s.training_date else ""
            s.signed_on = formatdate(s.signed_on)
        file_name, content = self.render_document(
            {
                "brand": self.brand(),
                "title": _("Project completion - {0}").format(
                    project.project_name or self.project
                ),
                "project_name": project.project_name or self.project,
                "customer_name": self.customer_name(),
                "signoffs": signoffs,
                # long sentences live here: an HTML formatter would wrap them inside _()
                "lede": _(
                    "Every training module of this project has been signed off by {0}."
                ).format(self.customer_name()),
                "foot": _(
                    "Each module's signed record is kept on the project. Generated {0}."
                ).format(format_datetime(now_datetime())),
            },
            template="helpdesk/templates/signoff/completion_letter.html",
        )
        letter = self.save_project_file(file_name, content)
        frappe.db.set_value(
            "Project", self.project, "custom_signoff_letter", letter.name
        )
        recipients = self.mail_addresses(
            *(s.signatory_email for s in signoffs),
            *(s.trainer for s in signoffs),
            project.project_lead,
        )
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
    """Scheduler, daily: on a working day, the one reminder for each sign-off its customer
    hasn't answered in two working days (docs/project-signoff.md, Reminders). One that fails
    is logged and leaves the others alone."""
    from helpdesk.follow_ups import WorkCalendar

    calendar = WorkCalendar(nowdate())
    if not calendar.is_working_day(calendar.today):
        return
    for name in frappe.get_all(
        "HD Project Signoff",
        filters={"status": SENT, "reminder_sent_on": ("is", "not set")},
        pluck="name",
    ):
        doc = frappe.get_doc("HD Project Signoff", name)
        if not doc.reminder_due(calendar):
            continue
        frappe.db.savepoint("signoff_reminder")
        try:
            doc.send_reminder(automatic=True)
        except Exception:
            frappe.db.rollback(save_point="signoff_reminder")
            frappe.log_error(title=f"Sign-off reminder failed: {name}")


def on_communication_insert(doc, method=None):
    """Communication hook: the customer's reply to a sign-off's mail goes on its history and
    its sender hears (TBO's Sign-off requirements, Sending the sign-off mail, step 7)."""
    if (
        doc.reference_doctype != "HD Project Signoff"
        or doc.sent_or_received != "Received"
    ):
        return
    if frappe.db.exists("HD Project Signoff", doc.reference_name):
        frappe.get_doc("HD Project Signoff", doc.reference_name).note_reply(doc)
