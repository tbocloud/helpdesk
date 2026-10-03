import html

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.chat_notifications import helpdesk_url


class HDNotification(Document):
    def format_message(self):
        user_from = self.get_from()
        if self.notification_type == "Mention":
            if self.reference_comment:
                return f"{user_from} mentioned you in a comment"
            return f"{user_from} mentioned you"
        return ""

    def get_from(self):
        return frappe.db.get_value(
            "User", {"name": self.user_from}, fieldname="full_name"
        )

    def get_button_label(self):
        if self.reference_comment:
            return "See Comment"
        return "Visit"

    def get_url(self):
        res = "/helpdesk"
        if self.reference_ticket:
            res += "/tickets/" + str(self.reference_ticket)
        if self.reference_comment:
            res += "#" + self.reference_comment
        return frappe.utils.get_url(res)

    def parse_html(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(self.message, "html.parser")
        if soup.find("img"):
            img = soup.find("img")
            img["src"] = ("").join([frappe.utils.get_url(), img["src"]])
            return str(soup)
        return str(soup)

    def get_args(self):
        if self.notification_type == "Mention":
            return {
                "title": self.format_message(),
                "button_label": self.get_button_label(),
                "callback_url": self.get_url(),
                "comment": self.parse_html(),
            }

    def after_insert(self):
        self.deliver()

    def deliver(self):
        """Chat instead of email when HD Chat Settings is on (sent after commit, in the background)."""
        from helpdesk.chat_notifications import is_enabled

        if self.notification_type not in ("Mention", "Reminder"):
            return
        if not is_enabled():
            self.send_email()
            return
        frappe.enqueue(
            "helpdesk.chat_notifications.deliver_notification",
            notification=self.name,
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )

    def send_email(self):
        self.send_mention_email()
        self.send_reminder_email()

    def chat_text(self) -> str:
        if self.notification_type == "Mention":
            text = _("{0} mentioned you in ticket #{1}").format(
                self.get_from() or self.user_from, self.reference_ticket
            )
            comment = frappe.utils.strip_html(self.message or "").strip()
            return f"{text}: {comment[:300]}" if comment else text
        return frappe.utils.strip_html(self.message or "")

    def chat_path(self) -> str:
        if self.link:
            return self.link
        if self.reference_ticket:
            anchor = (
                f"#comment-{self.reference_comment}" if self.reference_comment else ""
            )
            return f"/tickets/{self.reference_ticket}{anchor}"
        return "/my-work"

    def send_mention_email(self):
        if self.notification_type != "Mention":
            return
        if frappe.db.get_single_value("HD Settings", "skip_email_workflow"):
            return
        frappe.sendmail(
            recipients=self.user_to,
            subject="New notification",
            message=self.format_message(),
            template="notification",
            args=self.get_args(),
        )

    def send_reminder_email(self):
        """Deadline reminders also go by email, unless the person turned email notifications off."""
        from frappe.desk.doctype.notification_settings.notification_settings import (
            is_email_notifications_enabled,
        )

        if self.notification_type != "Reminder":
            return
        if not is_email_notifications_enabled(self.user_to):
            return
        text = html.unescape(frappe.utils.strip_html(self.message or ""))
        try:
            frappe.sendmail(
                recipients=self.user_to,
                # multi-line reminders (the morning brief) use their first line as subject
                subject=text.split("\n", 1)[0],
                template="new_notification",
                args={
                    "body_content": frappe.utils.escape_html(text).replace(
                        "\n", "<br>"
                    ),
                    "doc_link": helpdesk_url(self.chat_path()),
                },
                header=[_("Reminder"), "orange"],
            )
        except frappe.OutgoingEmailError:
            # no outgoing email account yet; the in-app reminder is still there
            self.log_error("Reminder email not sent")
