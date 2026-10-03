"""Spot tickets that are probably the same request raised twice.

A customer often reports one problem twice: an email and a ticket from their
ERP, a reminder sent as a new email, or two colleagues raising it. Open tickets
of the same customer (or, without one, the same sender) from the last
LOOKBACK_DAYS count as possible duplicates when their subjects match or they
share enough meaningful words. The agent decides and merges; nothing is merged
automatically. A plain word match, so it costs no AI call and works offline.
"""

import re

import frappe
from frappe.utils import add_days, get_datetime, now_datetime

from helpdesk.ai_suggestion import get_keywords

LOOKBACK_DAYS = 14
MAX_CANDIDATES = 50
MAX_DUPLICATES = 3
MIN_SHARED_WORDS = 3
MIN_OVERLAP = 0.5
OPEN_CATEGORIES = ["Open", "Paused"]
REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|tr)\s*:\s*)+", re.IGNORECASE)


def find_duplicates(ticket) -> list[dict]:
    """Up to MAX_DUPLICATES open tickets that look like the same request, best first."""
    if ticket.status_category not in OPEN_CATEGORIES or ticket.get("is_merged"):
        return []
    same_requester = _same_requester(ticket)
    if not same_requester:
        return []
    candidates = frappe.get_list(
        "HD Ticket",
        filters={
            **same_requester,
            "name": ("!=", ticket.name),
            "status_category": ("in", OPEN_CATEGORIES),
            "is_merged": 0,
            "creation": (">=", add_days(now_datetime(), -LOOKBACK_DAYS)),
        },
        fields=["name", "subject", "description", "status", "creation", "raised_by"],
        order_by="creation desc",
        limit=MAX_CANDIDATES,
    )
    subject = normalized_subject(ticket.subject)
    words = set(get_keywords(ticket))
    matches = []
    for other in candidates:
        same_subject = bool(subject) and subject == normalized_subject(other.subject)
        other_words = set(get_keywords(other))
        shared = words & other_words
        overlap = len(shared) / (min(len(words), len(other_words)) or 1)
        if not same_subject and (
            len(shared) < MIN_SHARED_WORDS or overlap < MIN_OVERLAP
        ):
            continue
        matches.append((same_subject, overlap, len(shared), other))
    matches.sort(key=lambda m: m[:3], reverse=True)
    return [
        {
            "name": str(other.name),
            "subject": other.subject,
            "status": other.status,
            "creation": str(other.creation),
            "raised_by": other.raised_by,
            "same_subject": same_subject,
            "shared_words": shared_count,
            # the older ticket is the original; the newer one is merged into it
            "is_older": get_datetime(other.creation) < get_datetime(ticket.creation),
        }
        for same_subject, _overlap, shared_count, other in matches[:MAX_DUPLICATES]
    ]


def normalized_subject(subject: str | None) -> str:
    return " ".join(REPLY_PREFIX.sub("", subject or "").lower().split())


def _same_requester(ticket) -> dict:
    if ticket.customer:
        return {"customer": ticket.customer}
    if ticket.raised_by:
        return {"raised_by": ticket.raised_by}
    return {}
