# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Haiku auto-triage engine with loop guards.

Trigger: HD Ticket after_insert → enqueue background job
Model: Claude Haiku 4.5 (~$0.003 per ticket)
"""

import json

import anthropic
import frappe
from frappe import _
from frappe.utils import now_datetime

from helpdesk.ai_engine import call_haiku
from helpdesk.ai_suggestion import queue_suggestion
from helpdesk.api.customization import record_triage_estimate
from helpdesk.automation import automation_user
from helpdesk.session_replay import TIMELINE_HEADING as SESSION_TIMELINE_HEADING
from helpdesk.session_replay import build_triage_context

# Guard constants
MAX_TRIAGE_RETRIES = 2
TRIAGE_COOLDOWN_SECONDS = 30
# thinking models (Kimi) can take minutes on a long ticket; the lock must outlive the job
TRIAGE_JOB_TIMEOUT = 300
TRIAGE_LOCK_TIMEOUT = TRIAGE_JOB_TIMEOUT + 30
# a triage "In Progress" longer than this was killed (timeout, worker restart)
STUCK_TRIAGE_MINUTES = 10
MAX_CONCURRENT_TRIAGES = 10
ERROR_LOGS_FOR_TRIAGE = 10
ERROR_TRACE_CHARS = 600
# tracks that get an automatic investigation on the customer site after triage
AUTO_INVESTIGATE_TRACKS = ("ai_investigate", "dev", "escalate")
# session timeline + diagnostics share of the prompt (~1.5k tokens)
MAX_SESSION_CONTEXT_CHARS = 6000

TRIAGE_SYSTEM_PROMPT = """You are an ERPNext/Frappe support triage AI. Analyze the support ticket and return a JSON object with your assessment.

You must return ONLY valid JSON with these exact fields:
{
  "category": "one of: Account, Billing, Configuration, Data, Integration, Performance, Permissions, Print, Report, Stock, Workflow, Other",
  "priority": "one of: Low, Medium, High, Critical",
  "complexity": "one of: Functional, Configuration, Data, Dev, Infrastructure",
  "summary": "3-6 sentences: what is happening, the most likely cause (cite the matching error log entries when there are any), and the business impact",
  "error_findings": ["one line per relevant error log entry: timestamp, method, and what it means; empty list if none relate to the issue"],
  "recommended_track": "one of: ai_investigate, manual, dev, escalate",
  "request_type": "one of: issue, question, customization",
  "estimate_hours": "only for a customization: developer hours to build, test and deliver it, as a number; null otherwise",
  "estimate_note": "only for a customization: one line on what drives the estimate; empty string otherwise",
  "scope": {
    "period_start": "YYYY-MM-DD or null if not mentioned",
    "period_end": "YYYY-MM-DD or null if not mentioned",
    "specific_entities": ["list of specific doctypes, accounts, or items mentioned"],
    "stated_constraint": "any specific scope the customer mentioned, verbatim"
  },
  "key_doctypes": ["list of ERPNext doctypes likely involved"],
  "investigation_steps": ["3-5 recommended investigation steps"],
  "steps_to_reproduce": ["the customer's steps in order, only when a session timeline is provided; empty list otherwise"],
  "likely_cause": "1-2 sentences, only when a session timeline is provided; empty string otherwise"
}

Rules:
- recommended_track = "ai_investigate" for issues that can be diagnosed by querying data (reports wrong, reconciliation issues, data mismatches)
- recommended_track = "manual" for simple how-to questions or UI guidance
- recommended_track = "dev" for bugs, custom code issues, or feature requests
- recommended_track = "escalate" for critical production-down issues
- request_type = "customization" when the customer asks for something new or changed to be built (a report
  or filter, print format, field, form change, workflow, automation or integration); "issue" when something
  that should work doesn't; "question" for how-to questions. A customization usually has recommended_track "dev"
- estimate_hours: count build, testing and deployment for an experienced ERPNext developer; small report or
  print-format changes are often 2-8 hours. Give one number, not a range
- Extract ALL date references and convert relative dates to absolute (e.g., "last 2 months" → actual date range)
- Extract ALL specific reports, documents, or entities the customer mentions
- If recent error logs from the customer's site are provided, check them for tracebacks that match the
  issue (same doctype, method, report or time window) and use them in the summary; ignore unrelated ones
- If a session timeline of what the customer did before raising the ticket is provided, write
  steps_to_reproduce and likely_cause from that timeline (and its diagnostics) only: the pages opened,
  fields typed in, buttons clicked and the errors or messages shown. Typed values are masked with "•";
  never guess them. If the timeline shows no error, say so in likely_cause instead of inventing one
- Never invent errors, documents or causes that are not in the ticket, the error logs or the session timeline
"""


def auto_triage_ticket(doc, method):
    """after_insert hook for HD Ticket. Enqueues triage with guards."""
    # Guard: check if auto-triage is enabled in Hub Settings
    try:
        from helpdesk.ai_engine import get_hub_settings

        if not get_hub_settings().auto_triage_enabled:
            return
    except Exception:
        return

    # Guard: only triage new tickets
    if doc.docstatus != 0:
        return

    # Guard: skip if already triaged
    if doc.get("custom_triage_status") and doc.custom_triage_status not in (
        "",
        "Pending",
    ):
        return

    # Guard: check concurrent limit
    active_jobs = frappe.cache.get_value("triage_active_count") or 0
    if active_jobs >= MAX_CONCURRENT_TRIAGES:
        frappe.logger().warning(
            f"Triage queue full ({active_jobs}/{MAX_CONCURRENT_TRIAGES}), skipping ticket {doc.name}"
        )
        return

    # Mark as pending
    frappe.db.set_value(
        "HD Ticket", doc.name, "custom_triage_status", "Pending", update_modified=False
    )

    # After commit: the ticket puller attaches the customer's session replay and
    # screenshots in the same transaction, and triage must see them. A job started
    # before the commit would not even find the ticket.
    frappe.enqueue(
        "helpdesk.triage.run_triage",
        ticket_id=doc.name,
        job_id=f"triage-{doc.name}",
        deduplicate=True,
        timeout=TRIAGE_JOB_TIMEOUT,
        queue="short",
        enqueue_after_commit=True,
    )


def retriage_with_session_replay(ticket_id: str):
    """Triage once more when a session replay reaches a ticket after its first triage.

    The customer's files can land on their Support Ticket after the puller has
    already imported it; the replay then arrives through the conversation sync.
    """
    from helpdesk.ai_engine import get_hub_settings

    if not get_hub_settings().auto_triage_enabled:
        return
    status, data = frappe.db.get_value(
        "HD Ticket", ticket_id, ["custom_triage_status", "custom_triage_data"]
    ) or (None, None)
    # a queued or running triage reads the attachments itself
    if status in ("Pending", "In Progress"):
        return
    try:
        triage_data = json.loads(data or "{}")
    except ValueError:
        triage_data = {}
    if triage_data.get("used_session_replay"):
        return

    frappe.enqueue(
        "helpdesk.triage.run_triage",
        ticket_id=ticket_id,
        start_investigation=False,
        job_id=f"triage-{ticket_id}",
        deduplicate=True,
        timeout=TRIAGE_JOB_TIMEOUT,
        queue="short",
        enqueue_after_commit=True,
    )


def run_triage_now(ticket_id: str):
    """Manual trigger with cooldown + retry limit check."""
    ticket = frappe.get_doc("HD Ticket", ticket_id)

    # Guard: cooldown
    if ticket.custom_triage_timestamp:
        elapsed = (now_datetime() - ticket.custom_triage_timestamp).total_seconds()
        if elapsed < TRIAGE_COOLDOWN_SECONDS:
            frappe.throw(
                _("Triage cooldown: wait {0}s").format(
                    int(TRIAGE_COOLDOWN_SECONDS - elapsed)
                )
            )

    # Guard: retry limit
    triage_data = (
        json.loads(ticket.custom_triage_data or "{}")
        if ticket.custom_triage_data
        else {}
    )
    retry_count = triage_data.get("retry_count", 0)
    if retry_count >= MAX_TRIAGE_RETRIES:
        frappe.throw(_("Triage retry limit reached ({0})").format(MAX_TRIAGE_RETRIES))

    frappe.enqueue(
        "helpdesk.triage.run_triage",
        ticket_id=ticket_id,
        is_retry=retry_count > 0,
        job_id=f"triage-{ticket_id}",
        deduplicate=True,
        timeout=TRIAGE_JOB_TIMEOUT,
        queue="short",
    )

    return {"status": "enqueued", "ticket": ticket_id}


def run_triage(
    ticket_id: str, is_retry: bool = False, start_investigation: bool = True
):
    """Background job: run Haiku triage with Redis lock.

    `start_investigation=False` re-triages without starting a second automatic
    investigation on the customer's site.
    """
    lock_key = f"triage_lock:{ticket_id}"

    # Guard: Redis lock (prevent concurrent triage on same ticket)
    # Use raw Redis SET with NX (set if not exists) + EX (expiry)
    # site-prefixed like delete_value() below, so the release actually matches
    lock_acquired = frappe.cache.set(  # key is site-prefixed via make_key; set_value can't do NX - nosemgrep
        frappe.cache.make_key(lock_key), 1, nx=True, ex=TRIAGE_LOCK_TIMEOUT
    )
    if not lock_acquired:
        frappe.logger().warning(f"Triage already running for ticket {ticket_id}")
        return

    # Track concurrent count
    frappe.cache.set_value(
        "triage_active_count", (frappe.cache.get_value("triage_active_count") or 0) + 1
    )

    try:
        # Guard: check ticket still exists and is open
        if not frappe.db.exists("HD Ticket", ticket_id):
            return

        status = frappe.db.get_value("HD Ticket", ticket_id, "status")
        if status == "Closed":
            frappe.db.set_value(
                "HD Ticket",
                ticket_id,
                "custom_triage_status",
                "Skipped",
                update_modified=False,
            )
            return

        # Mark in progress; the timestamp lets fail_stuck_triages spot a killed job
        frappe.db.set_value(
            "HD Ticket",
            ticket_id,
            {
                "custom_triage_status": "In Progress",
                "custom_triage_timestamp": now_datetime(),
            },
            update_modified=False,
        )
        frappe.db.commit()  # background job: persist triage progress and failures as they happen - nosemgrep

        # Build triage input
        ticket = frappe.get_doc("HD Ticket", ticket_id)
        user_message = _build_triage_input(ticket)

        # Guard: insufficient text content (image-only, empty tickets)
        if user_message is None:
            frappe.db.set_value(
                "HD Ticket",
                ticket_id,
                {
                    "custom_triage_status": "Skipped",
                    "custom_triage_summary": "Insufficient text content for auto-triage (possibly image-only ticket)",
                    "custom_triage_recommended_track": "manual",
                    "custom_triage_timestamp": now_datetime(),
                },
                update_modified=False,
            )
            frappe.db.commit()  # background job: persist triage progress and failures as they happen - nosemgrep
            return

        # Call the triage model. Anchor today's date so relative ranges like
        # "last 2 months" resolve to the right year — without this, models
        # guess and get it wrong (found while evaluating providers).
        from frappe.utils import nowdate

        user_message = f"Today's date: {nowdate()}\n\n{user_message}"
        result = call_haiku(TRIAGE_SYSTEM_PROMPT, user_message, ticket_name=ticket_id)
        triage = result["response"]
        if (
            not isinstance(triage, dict)
            or triage.get("parse_error")
            or not triage.get("summary")
        ):
            # an empty or unreadable answer must not be shown as a finished triage
            raise ValueError(
                "AI triage answer was empty or not JSON: "
                + str((triage or {}).get("raw_response", triage))[:1000]
            )

        # Get existing triage data for retry tracking
        existing_data = (
            json.loads(ticket.custom_triage_data or "{}")
            if ticket.custom_triage_data
            else {}
        )
        retry_count = existing_data.get("retry_count", 0) + (1 if is_retry else 0)

        # Store results using db_set to avoid triggering hooks
        triage_data = {
            **triage,
            "used_session_replay": SESSION_TIMELINE_HEADING in user_message,
            "retry_count": retry_count,
            "usage": result["usage"],
            "cost_usd": result["cost"],
        }

        updates = {
            "custom_triage_status": "Completed",
            "custom_triage_category": triage.get("category", ""),
            "custom_triage_priority": triage.get("priority", ""),
            "custom_triage_complexity": triage.get("complexity", ""),
            "custom_triage_summary": triage.get("summary", ""),
            "custom_triage_recommended_track": triage.get("recommended_track", ""),
            "custom_triage_data": json.dumps(triage_data),
            "custom_triage_timestamp": now_datetime(),
        }

        for field, value in updates.items():
            frappe.db.set_value(
                "HD Ticket", ticket_id, field, value, update_modified=False
            )
        record_triage_estimate(ticket_id, triage)

        frappe.db.commit()  # background job: persist triage progress and failures as they happen - nosemgrep

        # Post triage comment (with skip_notifications to prevent cascades)
        investigation = (
            _maybe_start_investigation(ticket, triage) if start_investigation else None
        )
        _post_triage_comment(ticket_id, triage, investigation)
        # a draft reply for the agent to review; it is never sent on its own
        queue_suggestion(ticket_id)

    except anthropic.APIError as e:
        # API rate limit or error - mark failed, no retry
        frappe.db.set_value(
            "HD Ticket",
            ticket_id,
            "custom_triage_status",
            "Failed",
            update_modified=False,
        )
        frappe.db.commit()  # background job: persist triage progress and failures as they happen - nosemgrep
        frappe.log_error(f"Triage API error for ticket {ticket_id}", str(e))

    except Exception as e:
        frappe.db.set_value(
            "HD Ticket",
            ticket_id,
            "custom_triage_status",
            "Failed",
            update_modified=False,
        )
        frappe.db.commit()  # background job: persist triage progress and failures as they happen - nosemgrep
        frappe.log_error(f"Triage error for ticket {ticket_id}", str(e))

    finally:
        # Release lock and decrement counter
        frappe.cache.delete_value(lock_key)
        active = frappe.cache.get_value("triage_active_count") or 1
        frappe.cache.set_value("triage_active_count", max(0, active - 1))


def _build_triage_input(ticket):
    """Build the user message from ticket data.

    Returns None if there's insufficient text content for triage
    (e.g. image-only tickets with no subject or description text).
    """
    subject = (ticket.subject or "").strip()
    desc = ""
    if ticket.description:
        desc = frappe.utils.strip_html_tags(ticket.description).strip()

    session = _session_context(ticket)

    # Check if there's enough text to triage; a session timeline is enough on its own
    total_text = subject + " " + desc
    if len(total_text.strip()) < 10 and not session:
        return None

    parts = []
    if subject:
        parts.append("Subject: %s" % subject)
    if desc:
        parts.append("Description: %s" % desc)
    if ticket.raised_by:
        parts.append("Raised by: %s" % ticket.raised_by)
    if ticket.ticket_type:
        parts.append("Type: %s" % ticket.ticket_type)
    if ticket.priority:
        parts.append("Customer Priority: %s" % ticket.priority)

    error_logs = _recent_error_logs(ticket)
    if error_logs:
        parts.append(
            "\nRecent error logs on the customer's site (newest first):\n" + error_logs
        )

    if session:
        parts.append(
            "\n"
            + session
            + "\n(Use this timeline for steps_to_reproduce and likely_cause; do not go beyond it.)"
        )

    return "\n".join(parts)


def _session_context(ticket) -> str:
    """The customer's recorded session timeline + diagnostics, if the ticket has one."""
    try:
        return build_triage_context(ticket.name, MAX_SESSION_CONTEXT_CHARS)
    except Exception:  # noqa: BLE001 - the replay only enriches triage
        frappe.log_error(
            title=f"Triage could not read the session replay for {ticket.name}",
            message=frappe.get_traceback(),
        )
        return ""


def get_ticket_connection(ticket) -> str | None:
    """The connected customer site for a ticket: the one it came from, else its customer's."""
    from helpdesk.content_sync import get_client_connection

    if ticket.get("custom_qcs_connection") and (
        frappe.db.get_value(
            "HDS Support Connection", ticket.custom_qcs_connection, "connection_status"
        )
        == "Connected"
    ):
        return ticket.custom_qcs_connection
    return get_client_connection(ticket.get("customer"))


def _recent_error_logs(ticket) -> str:
    """Latest Error Log entries from the customer's site, trimmed for the prompt.

    Best effort: triage still runs on the ticket text if the site can't be reached.
    """
    connection = get_ticket_connection(ticket)
    if not connection:
        return ""
    try:
        from helpdesk.mcp_client import MCPClient
        from helpdesk.ticket_puller import _unwrap

        logs = (
            _unwrap(
                MCPClient(connection).call_tool(
                    "get_error_log", {"limit": ERROR_LOGS_FOR_TRIAGE}
                )
            )
            or []
        )
    except Exception:  # noqa: BLE001 - error logs only enrich triage
        frappe.log_error(
            title=f"Triage could not read error logs for {ticket.name}",
            message=frappe.get_traceback(),
        )
        return ""
    lines = []
    for log in logs:
        trace = (log.get("error") or "").strip()
        # the last lines of a traceback carry the exception; keep those
        trace = trace[-ERROR_TRACE_CHARS:]
        lines.append(
            f"- {log.get('creation')} | {log.get('method') or 'unknown'}\n{trace}"
        )
    return "\n".join(lines)


def _maybe_start_investigation(ticket, triage: dict) -> str | None:
    """Start an AI investigation on the customer's site unless it's a simple how-to."""
    from helpdesk.ai_engine import get_hub_settings

    if not get_hub_settings().get("auto_investigate"):
        return None
    if triage.get("recommended_track") not in AUTO_INVESTIGATE_TRACKS:
        return None
    connection = get_ticket_connection(ticket)
    if not connection:
        return None
    try:
        from helpdesk.session_manager import start_investigation

        return start_investigation(
            ticket.name,
            connection,
            agent_notes="Started automatically after triage.",
        )
    except Exception:  # noqa: BLE001 - e.g. session limit reached; triage result still stands
        frappe.log_error(
            title=f"Auto investigation not started for {ticket.name}",
            message=frappe.get_traceback(),
        )
        return None


def _post_triage_comment(
    ticket_id: str, triage: dict, investigation: str | None = None
):
    """Post a summary comment on the ticket."""
    esc = frappe.utils.escape_html
    priority = triage.get("priority", "Unknown")
    category = triage.get("category", "Unknown")
    summary = triage.get("summary", "")
    track = triage.get("recommended_track", "")

    track_labels = {
        "ai_investigate": "AI Investigation",
        "manual": "Manual Support",
        "dev": "Developer Review",
        "escalate": "Escalation",
    }

    def bullet_list(items):
        items = [esc(str(i)) for i in items or [] if i]
        return (
            "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>" if items else ""
        )

    findings = bullet_list(triage.get("error_findings"))
    steps = bullet_list(triage.get("investigation_steps"))
    repro = triage.get("steps_to_reproduce") or []
    repro = [esc(str(i)) for i in repro if i] if isinstance(repro, list) else []
    repro_list = (
        "<ol>" + "".join(f"<li>{i}</li>" for i in repro) + "</ol>" if repro else ""
    )
    likely_cause = triage.get("likely_cause") or ""
    comment_text = f"<b>AI Triage:</b> {esc(priority)} priority | {esc(category)}<br>" f"<b>Summary:</b> {esc(summary)}<br>" + (
        f"<b>Error log findings:</b>{findings}" if findings else ""
    ) + (
        f"<b>Steps to reproduce</b> (from the session replay):{repro_list}"
        if repro_list
        else ""
    ) + (
        f"<b>Likely cause:</b> {esc(str(likely_cause))}<br>" if likely_cause else ""
    ) + (
        f"<b>Next steps:</b>{steps}" if steps else ""
    ) + f"<b>Recommended:</b> {esc(track_labels.get(track, track))}" + (
        f"<br><b>AI investigation started</b> ({esc(investigation)}): it will check the "
        "customer's site and post its diagnosis and any proposed fixes here."
        if investigation
        else ""
    )

    comment = frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": ticket_id,
            "content": comment_text,
            "commented_by": automation_user(),
        }
    )
    comment.flags.skip_notifications = True
    comment.insert(ignore_permissions=True)
    frappe.db.commit()  # background job: persist triage progress and failures as they happen - nosemgrep


def fail_stuck_triages():
    """Hourly: a triage left "In Progress" was killed mid-run; mark it Failed so it can be re-run."""
    from frappe.utils import add_to_date

    cutoff = add_to_date(now_datetime(), minutes=-STUCK_TRIAGE_MINUTES)
    for name in frappe.get_all(
        "HD Ticket",
        filters={
            "custom_triage_status": "In Progress",
            "custom_triage_timestamp": ("<", cutoff),
        },
        pluck="name",
    ):
        frappe.db.set_value(
            "HD Ticket", name, "custom_triage_status", "Failed", update_modified=False
        )
        frappe.log_error(
            title=f"Triage timed out for ticket {name}",
            message=f"Still In Progress after {STUCK_TRIAGE_MINUTES} minutes; marked Failed.",
        )
