"""Post new hub errors to the team's chat channel.

Errors otherwise sit in the Error Log until someone happens to look. Every
DIGEST_MINUTES the new ones are grouped by title and posted once to the
escalation channel in HD Chat Settings. Titles that differ only by a number (a ticket,
a connection) are one group, so a burst of "Status push failed for <ticket>" is one
line with a count. The checkpoint is a hidden field there
(not the cache), so a restart neither repeats nor skips a digest.

Errors about chat delivery itself are left out: they couldn't be posted anyway,
and logging the failed post would bring them back in every digest.
"""

import re
from collections import Counter

import frappe
import requests
from frappe import _
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Count
from frappe.utils import add_to_date, format_datetime, get_datetime, now_datetime

from helpdesk.chat_notifications import ChatError, is_enabled, post_to_channel
from helpdesk.helpdesk.doctype.hds_support_connection.hds_support_connection import (
    OUTAGE_TITLE,
)

DIGEST_MINUTES = 10
MAX_TITLES = 5
UNTITLED = "(no title)"
CHAT_ERROR_TITLES = ("Chat notification not sent", "Chat escalation not posted")
# what the customer-site jobs log (ticket_puller, content_sync, the connection's outage)
SYNC_ERROR_TITLES = (
    OUTAGE_TITLE,
    "Ticket pull failed for ",
    "Ticket import failed for ",
    "Ticket sync failed for ",
    "Status push failed for ",
    "Conversation sync failed for ",
    "File listing failed for ",
    "Media attach failed for ",
    "Listing client images failed for ",
    "Sending image ",
    "Content approval pull failed for ",
    "Content approval push failed for ",
    "Applying content decision failed for ",
)
# "Mark old sync errors as seen" leaves the last day's alone
OLD_SYNC_ERROR_DAYS = 1


def post_error_digest():
    """Scheduled: one channel message for the errors logged since the last run."""
    if not is_enabled() or not frappe.db.get_single_value(
        "HD Chat Settings", "post_error_alerts"
    ):
        return
    now = now_datetime()
    since = _checked_until() or add_to_date(now, minutes=-DIGEST_MINUTES)
    frappe.db.set_single_value(
        "HD Chat Settings", "errors_checked_until", now, update_modified=False
    )
    counts = new_error_counts(since, now)
    if not counts:
        return
    try:
        post_to_channel(
            digest_text(counts, since), frappe.utils.get_url("/app/error-log")
        )
    except (ChatError, requests.RequestException) as e:
        # not log_error: that would be in the next digest, which fails the same way
        frappe.logger("helpdesk").warning(f"Error digest not posted: {e}")


def new_error_counts(since, until) -> list[tuple[str, int]]:
    """(title, count) for errors logged in (since, until], most frequent first,
    without chat errors and the titles the settings ignore."""
    ErrorLog = frappe.qb.DocType("Error Log")
    rows = (
        frappe.qb.from_(ErrorLog)
        .select(ErrorLog.method, Count(ErrorLog.name).as_("count"))
        .where((ErrorLog.creation > since) & (ErrorLog.creation <= until))
        .groupby(ErrorLog.method)
        .run(as_dict=True)
    )
    ignored = _ignored_titles()
    counts = [
        ((row.method or UNTITLED).strip() or UNTITLED, row.count)
        for row in rows
        if (row.method or "") not in CHAT_ERROR_TITLES
    ]
    counts = [
        (title, count)
        for title, count in counts
        if not any(word in title.lower() for word in ignored)
    ]
    return group_similar(counts)


def group_similar(counts: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """One (title, count) per group of titles that differ only by numbers, most frequent
    first. The group shows its most frequent title, and how many others it holds."""
    groups: dict[str, Counter] = {}
    for title, count in counts:
        groups.setdefault(re.sub(r"\d+", "#", title), Counter())[title] += count
    grouped = []
    for titles in groups.values():
        (top, _top_count), *others = titles.most_common()
        label = _("{0} (and {1} similar)").format(top, len(others)) if others else top
        grouped.append((label, sum(titles.values())))
    return sorted(grouped, key=lambda c: (-c[1], c[0]))


def digest_text(counts: list[tuple[str, int]], since) -> str:
    total = sum(count for _title, count in counts)
    lines = [
        _("{0} new error(s) in TBO Support since {1}:").format(
            total, format_datetime(since, "d MMM, HH:mm")
        )
    ]
    lines += [f"• {count} × {title[:150]}" for title, count in counts[:MAX_TITLES]]
    if len(counts) > MAX_TITLES:
        lines.append(_("…and {0} more kind(s).").format(len(counts) - MAX_TITLES))
    return "\n".join(lines)


def _checked_until():
    value = frappe.db.get_single_value("HD Chat Settings", "errors_checked_until")
    return get_datetime(value) if value else None


def _ignored_titles() -> list[str]:
    text = frappe.db.get_single_value("HD Chat Settings", "ignored_error_titles") or ""
    return [line.strip().lower() for line in text.splitlines() if line.strip()]


def mark_old_sync_errors_seen() -> int:
    """Mark the customer-site sync errors older than OLD_SYNC_ERROR_DAYS as seen; returns
    how many. Run by a System Manager from Settings, never on a schedule."""
    ErrorLog = frappe.qb.DocType("Error Log")
    old_sync_errors = (
        (ErrorLog.seen == 0)
        & (ErrorLog.creation < add_to_date(now_datetime(), days=-OLD_SYNC_ERROR_DAYS))
        & Criterion.any([ErrorLog.method.like(f"{t}%") for t in SYNC_ERROR_TITLES])
    )
    count = (
        frappe.qb.from_(ErrorLog)
        .select(Count(ErrorLog.name))
        .where(old_sync_errors)
        .run()[0][0]
    )
    if count:
        frappe.qb.update(ErrorLog).set(ErrorLog.seen, 1).where(old_sync_errors).run()
    return count
