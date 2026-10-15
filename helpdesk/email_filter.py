"""Which incoming emails must not open a ticket.

A support mailbox also receives social-network notifications, newsletters and
bounces. They are recognised by the sender: automated addresses (noreply@,
notifications@, mailer-daemon@...) and the addresses or domains listed in
HD Settings. Replies on existing tickets are never filtered, since only new
tickets go through this check. The intake rules (helpdesk/intake.py) run before
these built-in checks and match senders the same way (`sender_matches`).
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
    settings = frappe.get_cached_doc("HD Settings")
    if settings.ignore_automated_emails and AUTOMATED_SENDER.match(
        address.rsplit("@", 1)[0]
    ):
        return True
    return sender_matches(settings.ignored_email_senders, address)


def sender_matches(entries: str | None, sender: str | None) -> bool:
    """Whether `sender` is one of `entries`: addresses, or domains that also match
    their subdomains, separated by commas, semicolons, spaces or new lines."""
    address = (sender or "").strip().lower()
    if "@" not in address:
        return False
    domain = address.rsplit("@", 1)[1]
    return any(_matches(entry, address, domain) for entry in _entries(entries))


def _entries(raw: str | None) -> list[str]:
    entries = re.split(r"[\s,;]+", (raw or "").lower())
    return [e.lstrip("@").strip() for e in entries if e.strip()]


def _matches(entry: str, address: str, domain: str) -> bool:
    if "@" in entry:
        return address == entry
    return domain == entry or domain.endswith("." + entry)
