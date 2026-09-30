# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, validate_email_address

PLACEHOLDER = re.compile(r"\{(\w+)\}")

DEFAULT_MISSED_POST_SUBJECT = "Missed post: {title} ({customer})"
DEFAULT_MISSED_POST_MESSAGE = """<p><b>{title}</b> for <b>{customer}</b> was due on {channel} at {due_datetime} \
and is still not published ({hours_late} hours overdue).</p>
<p>Publish it, move it to a new date, or cancel it.</p>
<p><a href="{post_link}">Open the post</a></p>"""

DEFAULT_PORTAL_CODE_SUBJECT = "Your content portal sign-in code"
DEFAULT_PORTAL_CODE_MESSAGE = """<p>Hi {customer},</p>
<p>Your one-time code to open your content calendar is:</p>
<p style="font-size:28px;font-weight:700;letter-spacing:4px;">{otp}</p>
<p>It expires in {otp_expiry_minutes} minutes. If you didn't ask for it, you can ignore this email.</p>
<p><a href="{portal_link}">{portal_link}</a></p>"""

# kind -> (subject field, message field, default subject, default message, placeholders)
TEMPLATES = {
    "missed_post": (
        "missed_post_subject",
        "missed_post_message",
        DEFAULT_MISSED_POST_SUBJECT,
        DEFAULT_MISSED_POST_MESSAGE,
        ("title", "customer", "channel", "due_datetime", "hours_late", "post_link"),
    ),
    "portal_code": (
        "portal_code_subject",
        "portal_code_message",
        DEFAULT_PORTAL_CODE_SUBJECT,
        DEFAULT_PORTAL_CODE_MESSAGE,
        ("customer", "otp", "otp_expiry_minutes", "portal_link"),
    ),
}


class HDContentSettings(Document):
    def validate(self):
        self.validate_placeholders()
        self.validate_alert_emails()

    def validate_placeholders(self):
        for subject_field, message_field, *_defaults, allowed in TEMPLATES.values():
            for fieldname in (subject_field, message_field):
                unknown = set(PLACEHOLDER.findall(self.get(fieldname) or "")) - set(
                    allowed
                )
                if unknown:
                    frappe.throw(
                        _("{0} uses unknown placeholders {1}. Use: {2}").format(
                            _(self.meta.get_label(fieldname)),
                            ", ".join(f"{{{p}}}" for p in sorted(unknown)),
                            ", ".join(f"{{{p}}}" for p in allowed),
                        )
                    )

    def validate_alert_emails(self):
        for email in self.get_alert_emails():
            validate_email_address(email, throw=True)

    def get_alert_emails(self) -> list[str]:
        raw = (self.alert_emails or "").replace(",", "\n")
        return [e.strip() for e in raw.splitlines() if e.strip()]

    def get_alert_recipients(self) -> set[str]:
        """Everyone who hears about every missed post, before the post's own team."""
        users = [row.user for row in self.alert_recipients]
        emails = (
            frappe.get_all(
                "User",
                filters={"name": ("in", users), "enabled": 1},
                pluck="email",
            )
            if users
            else []
        )
        return {e for e in emails if e} | set(self.get_alert_emails())

    def render(self, kind: str, values: dict) -> tuple[str, str]:
        """Subject and HTML message for `kind`, falling back to the defaults when blank."""
        subject_field, message_field, default_subject, default_message, _p = TEMPLATES[
            kind
        ]
        subject = self.fill(self.get(subject_field) or default_subject, values)
        message = self.fill(
            self.get(message_field) or default_message,
            {k: escape_html(str(v)) for k, v in values.items()},
        )
        return subject, message

    @staticmethod
    def fill(template: str, values: dict) -> str:
        # Only {known} placeholders are replaced, so stray braces in a template never break it
        return PLACEHOLDER.sub(
            lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0),
            template,
        )


@frappe.whitelist()
def get_template_defaults() -> dict:
    """The built-in templates and their placeholders, shown when a template is left blank."""
    frappe.has_permission("HD Content Settings", "read", throw=True)
    return {
        kind: {
            "subject": default_subject,
            "message": default_message,
            "placeholders": placeholders,
        }
        for kind, (
            _s,
            _m,
            default_subject,
            default_message,
            placeholders,
        ) in TEMPLATES.items()
    }
