"""A ticket as one Markdown brief for an AI coding agent (Claude Code, Cursor...)
or a developer working outside the hub.

It puts together what the hub already knows: the customer's report, their
site and app versions, the steps from the session replay, errors, the AI
triage, the conversation and the attachments, and tells the agent how to
work safely (reproduce off production, fix in the right app, open a PR).
"""

import json

import frappe
from frappe.utils import get_url, nowdate, strip_html_tags

from helpdesk.session_replay import (
    get_timeline,
    load_diagnostics,
    summarize_diagnostics,
)
from helpdesk.triage import get_ticket_connection

MAX_TIMELINE_CHARS = 8000
MAX_MESSAGE_CHARS = 1200
MAX_MESSAGES = 10
CUSTOMER_COMMENT_MARK = "\N{SPEECH BALLOON} Customer"

AGENT_INSTRUCTIONS = """You are fixing a customer issue in a Frappe / ERPNext system. Work like a careful senior developer:

1. **Never change the customer's production site or data.** Reproduce the problem on a development or staging copy.
2. **Find the root cause before changing code.** Use the steps, timeline and errors below; say what you checked.
3. **Fix it in the right place.** Decide whether the cause is in Frappe/ERPNext itself, in one of the customer's custom apps (see the installed apps), in configuration, or in the data. Configuration and data problems get exact steps instead of code.
4. **Keep the change small**, follow the app's conventions (read its AGENTS.md or CLAUDE.md if it has one), and add or update a test that fails without your fix.
5. **Open a pull request** with a clear description; put this ticket's reference (below) in the PR title or description.
6. **If you are not sure, stop and ask.** List what you found and the questions for the support team rather than guessing.

The customer details in this brief are confidential: don't paste them into public places."""


def build_fix_brief(ticket) -> str:
    triage = _triage(ticket)
    sections = [
        f"# Fix brief: ticket #{ticket.name}: {ticket.subject or '(no subject)'}",
        f"_TBO Support · {nowdate()} · {get_url(f'/helpdesk/tickets/{ticket.name}')}_",
        "## Instructions for the AI agent\n\n" + AGENT_INSTRUCTIONS,
        _ticket_section(ticket, triage),
        _site_section(ticket),
        _report_section(ticket),
        _steps_section(triage),
        _timeline_section(ticket),
        _triage_section(triage),
        _conversation_section(ticket),
        _attachments_section(ticket),
        _done_section(ticket),
    ]
    return "\n\n".join(part for part in sections if part).strip() + "\n"


def _triage(ticket) -> dict:
    try:
        data = json.loads(ticket.get("custom_triage_data") or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _ticket_section(ticket, triage: dict) -> str:
    rows = [
        ("Ticket", f"#{ticket.name} (reference: {_reference(ticket)})"),
        ("Customer", ticket.customer),
        ("Raised by", ticket.raised_by),
        ("Status", ticket.status),
        ("Priority", triage.get("priority") or ticket.priority),
        ("Category", triage.get("category")),
        ("Kind of work", triage.get("complexity")),
        ("Opened", str(ticket.creation)[:16] if ticket.creation else None),
        ("Customer's ticket", ticket.get("custom_client_ticket")),
    ]
    return "## Ticket\n\n" + _table(rows)


def _site_section(ticket) -> str:
    rows = []
    connection = get_ticket_connection(ticket)
    if connection:
        site = frappe.db.get_value(
            "HDS Support Connection",
            connection,
            ["site_url", "client_app"],
            as_dict=True,
        )
        if site:
            rows.append(("Site", site.site_url))
            rows.append(("Connected via", site.client_app))
    lines = ["## Customer site", "", _table(rows) if rows else "_No connected site._"]
    diagnostics = summarize_diagnostics(_safe(load_diagnostics, ticket.name))
    if diagnostics:
        lines += [
            "",
            "Browser, versions and errors captured with the ticket:",
            "",
            _code(diagnostics),
        ]
    return "\n".join(lines)


def _report_section(ticket) -> str:
    text = _plain(ticket.description)
    if not text:
        return ""
    return "## What the customer reported\n\n" + _quote(text)


def _steps_section(triage: dict) -> str:
    steps = [s for s in triage.get("steps_to_reproduce") or [] if s]
    if not steps:
        return ""
    numbered = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    return "## Steps to reproduce (from the customer's recorded session)\n\n" + numbered


def _timeline_section(ticket) -> str:
    timeline = _safe(get_timeline, ticket.name)
    if not timeline:
        return ""
    if len(timeline) > MAX_TIMELINE_CHARS:
        timeline = timeline[:MAX_TIMELINE_CHARS] + "\n[timeline shortened]"
    return "## Session timeline (raw)\n\n" + _code(timeline)


def _triage_section(triage: dict) -> str:
    if not triage.get("summary"):
        return ""
    lines = ["## AI triage", "", triage["summary"].strip()]
    if triage.get("likely_cause"):
        lines += ["", f"**Likely cause:** {triage['likely_cause'].strip()}"]
    for title, key in (
        ("Errors that relate", "error_findings"),
        ("Doctypes involved", "key_doctypes"),
        ("Suggested investigation", "investigation_steps"),
    ):
        items = [str(i) for i in triage.get(key) or [] if i]
        if items:
            lines += ["", f"**{title}:**", *[f"- {item}" for item in items]]
    return "\n".join(lines)


def _conversation_section(ticket) -> str:
    messages = frappe.get_all(
        "Communication",
        filters={"reference_doctype": "HD Ticket", "reference_name": ticket.name},
        fields=["creation", "sender", "sent_or_received", "content"],
        order_by="creation desc",
        limit=MAX_MESSAGES,
    )
    comments = frappe.get_all(
        "HD Ticket Comment",
        filters={
            "reference_ticket": ticket.name,
            "content": ("like", f"%{CUSTOMER_COMMENT_MARK}%"),
        },
        fields=["creation", "content"],
        order_by="creation desc",
        limit=MAX_MESSAGES,
    )
    entries = [
        (
            m.creation,
            "Support" if m.sent_or_received == "Sent" else (m.sender or "Customer"),
            m.content,
        )
        for m in messages
    ] + [(c.creation, "Customer (in their ERP)", c.content) for c in comments]
    entries = sorted(entries, key=lambda e: e[0])[-MAX_MESSAGES:]
    if not entries:
        return ""
    blocks = [
        f"**{who}, {str(when)[:16]}:**\n\n{_quote(_plain(content)[:MAX_MESSAGE_CHARS])}"
        for when, who, content in entries
        if _plain(content)
    ]
    return "## Conversation\n\n" + "\n\n".join(blocks) if blocks else ""


def _attachments_section(ticket) -> str:
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "HD Ticket", "attached_to_name": ticket.name},
        fields=["file_name", "file_url"],
        order_by="creation asc",
    )
    if not files:
        return ""
    lines = [f"- [{f.file_name}]({get_url(f.file_url)})" for f in files if f.file_url]
    return "## Attachments\n\nSign in to TBO Support to open them.\n\n" + "\n".join(
        lines
    )


def _done_section(ticket) -> str:
    return (
        "## Done when\n\n"
        "- [ ] The root cause is explained in one or two sentences\n"
        "- [ ] The fix (code, configuration or data steps) is reproduced and verified off production\n"
        "- [ ] A test covers it, where the app has tests\n"
        f"- [ ] The pull request mentions {_reference(ticket)}\n"
        "- [ ] Open questions for the support team are listed"
    )


def _reference(ticket) -> str:
    """How a pull request names this work, as inline code.

    GitHub sync links a pull request to its task by a TASK- reference, and the
    task-reference check refuses a pull request without one, so the brief
    names the ticket's task when it has one.
    """
    task = frappe.db.get_value(
        "Task", {"hd_ticket": ticket.name}, "name", order_by="creation desc"
    )
    if task:
        return "`" + f"Closes {task}" + "`"
    return (
        "`" + f"Refs ticket #{ticket.name}" + "` "
        "(create a task from the ticket first, so the pull request can say `Closes TASK-...`)"
    )


def _table(rows) -> str:
    rows = [(label, value) for label, value in rows if value]
    lines = ["| | |", "| --- | --- |"]
    lines += [f"| {label} | {str(value).replace('|', '/')} |" for label, value in rows]
    return "\n".join(lines)


def _plain(html: str | None) -> str:
    return strip_html_tags(html or "").replace("\xa0", " ").strip()


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.splitlines())


def _code(text: str) -> str:
    return "```\n" + text.replace("```", "'''") + "\n```"


def _safe(fn, *args):
    """Session files only enrich the brief; a missing or broken one is skipped."""
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 - the brief still helps without it
        return None
