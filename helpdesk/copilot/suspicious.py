# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Text that tries to instruct the AI (Phase 4 red team).

The worker is told to ignore and report such text, but does not always report it. The hub
looks at the ticket and the customer's messages itself, the worker at every tool result
(`suspicious_instruction` events from both), and the Copilot card warns the agent before
anything is sent. Same patterns as the worker's `suspicious.ts`.
"""

import html
import re

import frappe

PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(ignore|disregard|forget|override)\b[^.\n]{0,60}\b(instructions?|rules?|prompts?|guidelines)\b",
        r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+|any\s+|all\s+)?(ai|a\.i\.|assistants?|copilot|agents?|llms?|models?|bots?)\b",
        r"\byou are now (in )?\w*\s?(mode|admin|administrator|developer|unrestricted|jailbroken)\b",
        r"\b(system prompt|developer mode|maintenance mode|admin mode|god mode|jailbreak)\b",
        r"\b(paste|copy|send|reveal|print|include|output|leak|exfiltrate)\b[^.\n]{0,60}\b(api[ _-]?keys?|secrets?|passwords?|credentials|\.env|env file|full contents|contents of)\b",
        r"\bcat\s+(/etc/(passwd|shadow)|~/\.|\$HOME/\.)",
    )
]
EVENT = "suspicious_instruction"

# shapes of secrets: a flagged line goes into the run's events, and a secret never does
SECRET_SHAPES = [
    re.compile(p)
    for p in (
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
        r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
        r"[A-Za-z0-9+/_=-]{32,}",  # any long opaque string: a token, a key, a signature
    )
]
SECRET_ASSIGNMENT = re.compile(
    r"\b(password|passwd|secret|token|api[_-]?key|apikey|client[_-]?secret)\b(\s*[:=]\s*)([\"']?)[^\s\"']{4,}\3",
    re.IGNORECASE,
)


def redact_secrets(line: str) -> str:
    """The line with anything shaped like a secret replaced, so it can go into an event."""
    text = SECRET_ASSIGNMENT.sub(r"\1\2[secret removed]", line)
    for shape in SECRET_SHAPES:
        text = shape.sub("[secret removed]", text)
    return text


def suspicious_lines(text: str, limit: int = 3) -> list[str]:
    """The lines of `text` (HTML or plain) that look like an instruction to the AI, cut to 200 characters."""
    plain = html.unescape(
        re.sub(r"<(br|/p|/div|/li)[^>]*>", "\n", text or "", flags=re.I)
    )
    plain = re.sub(r"<[^>]+>", " ", plain)
    found = []
    for line in plain.splitlines():
        line = " ".join(line.split())
        # a ticket's description comes back as its first message: each line once
        if line and line[:200] not in found and any(p.search(line) for p in PATTERNS):
            found.append(line[:200])
            if len(found) >= limit:
                break
    return found


def check_ticket(run):
    """Records the ticket's own suspicious lines (subject, description, the customer's messages) once per run."""
    from helpdesk.copilot import runs

    if frappe.db.exists(
        "HDS Copilot Event",
        {"run": run.name, "event_type": EVENT, "actor": runs.SYSTEM},
    ):
        return
    ticket = (
        frappe.db.get_value(
            "HD Ticket", run.ticket, ["subject", "description"], as_dict=True
        )
        or {}
    )
    messages = frappe.get_all(
        "Communication",
        filters={
            "reference_doctype": "HD Ticket",
            "reference_name": run.ticket,
            "sent_or_received": "Received",
        },
        pluck="content",
        order_by="creation asc",
        limit=50,
    )
    text = "\n".join(
        [ticket.get("subject") or "", ticket.get("description") or "", *messages]
    )
    for line in suspicious_lines(text, 5):
        runs.add_event(
            run, EVENT, {"source": "ticket", "text": redact_secrets(line)}, runs.SYSTEM
        )


def seen(run_name: str) -> list[dict]:
    """What the hub and the worker flagged on a run: where it was found and the line."""
    rows = []
    for payload in frappe.get_all(
        "HDS Copilot Event",
        filters={"run": run_name, "event_type": EVENT},
        pluck="payload",
        order_by="creation asc",
        limit=10,
    ):
        data = frappe.parse_json(payload or "{}") or {}
        rows.append(
            {
                "source": data.get("source") or data.get("tool") or "",
                "text": str(data.get("text") or "")[:200],
            }
        )
    return rows
