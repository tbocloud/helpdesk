"""Post new hub errors to the team's chat channel.

Errors otherwise sit in the Error Log until someone happens to look. Every
DIGEST_MINUTES the new ones are grouped by title and posted once to the
escalation channel in HD Chat Settings. The checkpoint is a hidden field there
(not the cache), so a restart neither repeats nor skips a digest.

Errors about chat delivery itself are left out: they couldn't be posted anyway,
and logging the failed post would bring them back in every digest.
"""

import frappe
import requests
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_to_date, format_datetime, get_datetime, now_datetime

from helpdesk.chat_notifications import ChatError, is_enabled, post_to_channel

DIGEST_MINUTES = 10
MAX_TITLES = 5
UNTITLED = "(no title)"
CHAT_ERROR_TITLES = ("Chat notification not sent", "Chat escalation not posted")


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
    return sorted(counts, key=lambda c: (-c[1], c[0]))


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
