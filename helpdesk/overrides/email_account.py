import re
from email import message_from_string

import frappe
from frappe import _
from frappe.core.doctype.communication.communication import Communication
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.email.doctype.email_queue.email_queue import EmailQueue
from frappe.email.receive import InboundMail


class CustomInboundMail(InboundMail):
    """
    Extend InboundMail with robust thread stitching for forwarded emails.
       1. Run the standard Frappe parent_communication lookups first (In-Reply-To → Communication, EmailQueue, communication-name fallback)
       2. If still no parent, use the References header from emails, which may contain multiple message IDs in a thread
    """

    def _find_communication_by_message_id(self, msg_id: str):
        """Return a Communication for msg_id, checking both Communication and EmailQueue."""
        # Direct hit: incoming email stored its message_id on Communication
        comm = Communication.find_one_by_filters(
            message_id=msg_id, order_by="creation DESC"
        )
        if comm:
            return comm

        # Outgoing email: message_id lives in EmailQueue, not on Communication
        eq = EmailQueue.find_one_by_filters(message_id=msg_id)
        if eq and eq.communication:
            return Communication.find(eq.communication, ignore_error=True) or None

        return None

    def parent_communication(self):
        # Respect cached result from any prior call on this instance
        if self._parent_communication is not None:
            return self._parent_communication

        # Run the standard Frappe lookup method first. Checks for finding in reply to in Communication then if not found it looks in EmailQueue
        result = super().parent_communication()
        if result:
            return result

        # fallback: use the References header from emails
        references_raw = self.mail.get("References") or ""
        ref_ids = re.findall(r"<([^>]+)>", references_raw)

        for ref_id in reversed(ref_ids):
            communication = self._find_communication_by_message_id(ref_id)
            if communication:
                self._parent_communication = communication
                return self._parent_communication

        self._parent_communication = ""
        return self._parent_communication

    def process(self):
        """New support mail goes through the intake rules first (helpdesk/intake.py): an
        ignored mail or a repeat of an open alert is handled there and opens nothing.

        A mail Frappe threads onto an existing ticket by its subject keeps doing so,
        except a monitor's: its alerts group by their own key, so a new alert never
        lands on an old, closed alert ticket that had the same subject."""
        from helpdesk.intake import IGNORE, decide, handle_mail

        if not self.is_new_ticket_mail():
            return super().process()
        decision = decide(self.from_email, self.subject)
        monitor = bool(decision) and decision.action != IGNORE
        if monitor or not self.reference_document():
            if handle_mail(decision, self.from_email, self.subject, self.content):
                return None
            if monitor:
                self._reference_document = ""
        return super().process()

    def is_new_ticket_mail(self) -> bool:
        """A mail that would open an HD Ticket: not a reply, not already received."""
        append_to = (
            self.append_to
            if self.email_account.use_imap
            else self.email_account.append_to
        )
        return (
            append_to == "HD Ticket"
            and not self.parent_communication()
            and not self.is_sender_same_as_receiver()
            and not self.is_exist_in_system()
        )


class CustomEmailAccount(EmailAccount):
    def get_inbound_mails(self) -> list[InboundMail]:
        """retrive and return inbound mails."""
        mails = []

        def process_mail(messages, append_to=None):
            for index, message in enumerate(messages.get("latest_messages", [])):
                try:
                    _msg = message_from_string(
                        message.decode("utf-8", errors="replace")
                    )

                    # Important: If the email is auto-generated, we do not create a ticket
                    if _msg.get("X-Auto-Generated"):
                        continue

                    uid = (
                        messages["uid_list"][index]
                        if messages.get("uid_list")
                        else None
                    )
                    seen_status = messages.get("seen_status", {}).get(uid)
                    if self.email_sync_option != "UNSEEN" or seen_status != "SEEN":
                        _inbound_mail = CustomInboundMail(
                            message,
                            self,
                            frappe.safe_decode(uid),
                            seen_status,
                            append_to,
                        )
                        mails.append(_inbound_mail)
                except Exception as e:
                    # Log the error but continue processing other emails
                    frappe.log_error(
                        title=_(
                            "Error processing email at index {0}, message: {1}"
                        ).format(index, e),
                        message=frappe.get_traceback(),
                    )
                    self.handle_bad_emails(index, message, frappe.get_traceback())
                    continue

        if not self.enable_incoming:
            return []

        try:
            if self.service == "Frappe Mail":
                frappe_mail_client = self.get_frappe_mail_client()
                messages = frappe_mail_client.pull_raw(
                    last_received_at=self.last_synced_at
                )
                process_mail(messages)
                self.db_set(
                    "last_synced_at",
                    messages["last_received_at"],
                    update_modified=False,
                )
            else:
                email_sync_rule = self.build_email_sync_rule()
                email_server = self.get_incoming_server(
                    in_receive=True, email_sync_rule=email_sync_rule
                )
                if self.use_imap:
                    # process all given imap folder
                    for folder in self.imap_folder:
                        if email_server.select_imap_folder(folder.folder_name):
                            email_server.settings["uid_validity"] = folder.uidvalidity
                            messages = (
                                email_server.get_messages(
                                    folder=f'"{folder.folder_name}"'
                                )
                                or {}
                            )
                            process_mail(messages, folder.append_to)
                else:
                    # process the pop3 account
                    messages = email_server.get_messages() or {}
                    process_mail(messages)

                # close connection to mailserver
                email_server.logout()
        except Exception:
            self.log_error(
                title=_("Error while connecting to email account {0}").format(self.name)
            )
            return []

        return mails
