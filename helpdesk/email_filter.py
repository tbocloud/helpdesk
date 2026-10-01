"""Which incoming emails must not open a ticket.

A support mailbox also receives social-network notifications, newsletters and
bounces. They are recognised by the sender: automated addresses (noreply@,
notifications@, mailer-daemon@...) and the addresses or domains listed in
HD Settings. Replies on existing tickets are never filtered, since only new
tickets go through this check.
"""

import re

import frappe
from frappe.email.receive import SentEmailInInboxError

AUTOMATED_SENDER = re.compile(
    r"^(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer[-_.]?daemon|postmaster|bounces?|notifications?)([-_.+].*)?$",
    re.IGNORECASE,
)


class UnwantedTicketEmail(SentEmailInInboxError):
    """Raised while a ticket is being created from an unwanted email.

    Frappe's mail receiver rolls back quietly on SentEmailInInboxError; the
    message is already marked read on the server, so it isn't fetched again.
    """


def is_unwanted_sender(sender: str | None) -> bool:
    address = (sender or "").strip().lower()
    if "@" not in address:
        return False
    local, domain = address.rsplit("@", 1)
    settings = frappe.get_cached_doc("HD Settings")
    if settings.ignore_automated_emails and AUTOMATED_SENDER.match(local):
        return True
    return any(
        _matches(entry, address, domain)
        for entry in _blocked_entries(settings.ignored_email_senders)
    )


def _blocked_entries(raw: str | None) -> list[str]:
    entries = re.split(r"[\s,;]+", (raw or "").lower())
    return [e.lstrip("@").strip() for e in entries if e.strip()]


def _matches(entry: str, address: str, domain: str) -> bool:
    if "@" in entry:
        return address == entry
    return domain == entry or domain.endswith("." + entry)
