"""Asks GitHub to run the org-wide merge bot (tbocloud/ai-review, merge-bot.yml).

GitHub doesn't reliably fire the bot's own schedule, so the hub requests a run
when a PR may have become mergeable (CodeRabbit approved it, or its CI passed)
and every 10 minutes as a fallback. The hub only asks; which PRs merge is
decided by the bot. Requests are debounced: at most one dispatch per
`DEBOUNCE_SECONDS`, however many events arrive. See docs/github-sync.md.
"""

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime

from helpdesk import github_sync

CODERABBIT = "coderabbitai[bot]"
DEBOUNCE_SECONDS = 120
DEBOUNCE_KEY = "helpdesk:merge_bot_dispatch"
CHECK_EVENTS = ("workflow_run", "check_suite")


def on_webhook(settings, event: str, payload: dict):
    """Called after a delivery is recorded; a problem here never fails the webhook."""
    try:
        if settings.trigger_merge_bot and may_be_mergeable(settings, event, payload):
            request_run()
    except Exception:
        frappe.log_error(title=_("Couldn't request a merge bot run"))


def may_be_mergeable(settings, event: str, payload: dict) -> bool:
    if event == "pull_request_review":
        review = payload.get("review") or {}
        return (
            payload.get("action") == "submitted"
            and (review.get("state") or "").lower() == "approved"
            and (review.get("user") or {}).get("login") == CODERABBIT
        )
    if event in CHECK_EVENTS:
        run = payload.get(event) or {}
        repo = (payload.get("repository") or {}).get("full_name") or ""
        return (
            payload.get("action") == "completed"
            and run.get("conclusion") == "success"
            # only runs for a PR: the bot's own runs and pushes to main have none,
            # so a finished bot run never asks for the next one
            and bool(run.get("pull_requests"))
            and repo.lower() != (settings.merge_bot_repo or "").lower()
        )
    return False


def request_run() -> bool:
    """Queue one dispatch unless one was queued in the last DEBOUNCE_SECONDS."""
    if not take_debounce():
        return False
    frappe.enqueue(
        "helpdesk.merge_bot.dispatch",
        queue="short",
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )
    return True


def take_debounce() -> bool:
    """Whether a dispatch may go now; if so, no other may for DEBOUNCE_SECONDS."""
    cache = frappe.cache
    # SET NX is atomic, so concurrent webhooks can't both pass
    return bool(
        cache.set(cache.make_key(DEBOUNCE_KEY), 1, nx=True, ex=DEBOUNCE_SECONDS)
    )


def scheduled_run():
    """Scheduler fallback (every 10 minutes): catches anything the events missed."""
    if frappe.db.get_single_value(github_sync.SETTINGS, "trigger_merge_bot"):
        request_run()


def dispatch() -> bool:
    """Background job: POST the workflow_dispatch and record the outcome on the settings.
    Whether GitHub accepted it, for Settings → GitHub's "Request a run now"."""
    settings = frappe.get_single(github_sync.SETTINGS)
    if not settings.trigger_merge_bot:
        return False
    token = settings.get_password(
        "merge_bot_token", raise_exception=False
    ) or settings.get_password("github_token", raise_exception=False)
    if not token:
        return record(_("Not sent: no merge bot token or GitHub token"), failed=True)
    url = (
        f"{github_sync.GITHUB_API}/repos/{settings.merge_bot_repo}"
        f"/actions/workflows/{settings.merge_bot_workflow}/dispatches"
    )
    try:
        response = requests.post(
            url,
            headers=github_sync.github_headers(token),
            # a string: GitHub reads it as the boolean input, as `gh workflow run -f` sends it;
            # the workflow defaults dry_run to true, so it must be sent
            json={"ref": "main", "inputs": {"dry_run": "false"}},
            timeout=github_sync.REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        return record(_("Failed: {0}").format(type(e).__name__), failed=True)
    if response.ok:
        return record(_("Dispatched (HTTP {0})").format(response.status_code))
    return record(_("Failed (HTTP {0})").format(response.status_code), failed=True)


def record(result: str, failed: bool = False) -> bool:
    """The last outcome on the settings; failures also go to the Error Log. Never the token."""
    frappe.db.set_single_value(
        github_sync.SETTINGS,
        {
            "merge_bot_last_dispatch": now_datetime(),
            "merge_bot_last_result": result,
            # the result is translated; the settings page colours it from this
            "merge_bot_last_outcome": "Failed" if failed else "Dispatched",
        },
        # an admin with the settings open mustn't hit "document has been modified"
        update_modified=False,
    )
    if failed:
        frappe.log_error(title=_("Merge bot dispatch failed"), message=result)
    return not failed
