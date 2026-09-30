# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""AI suggested reply: a draft answer waiting on the ticket for an agent.

After triage (and again when an investigation of the customer's site finishes)
the AI drafts a reply from everything known about the ticket. It is only stored
on the ticket: an agent inserts it into the composer, edits it and sends it.
Nothing here ever emails the customer.
"""

import json
import re

import frappe
from frappe.query_builder import Criterion
from frappe.utils import escape_html, get_url, now_datetime
from frappe.utils.password import get_decrypted_password

from helpdesk.ai_engine import call_haiku
from helpdesk.api.ticket_ai import build_prompt, html_to_text, text_to_html, truncate
from helpdesk.search import STOPWORDS
from helpdesk.session_replay import build_triage_context
from helpdesk.utils import get_doc_room, publish_event

# room for a thinking model's second, larger attempt (see call_haiku)
SUGGESTION_JOB_TIMEOUT = 240
REALTIME_EVENT = "helpdesk:ai-suggestion"
CLOSED_STATUSES = ("Closed", "Resolved")
CONFIDENCE_LEVELS = ("high", "medium", "low")

# Each context block is bounded so the prompt stays cheap however much we know
MAX_TRIAGE_CHARS = 1500
MAX_SESSION_CHARS = 3000
MAX_INVESTIGATION_CHARS = 3000
MAX_NOTE_CHARS = 300
MAX_INSTRUCTIONS_CHARS = 1000

MAX_ARTICLES = 3
MAX_ARTICLE_CANDIDATES = 50
MAX_ARTICLE_EXCERPT_CHARS = 500
MAX_KEYWORDS = 10
# a title match scores 3, a body match 1: one body-only hit is too weak to suggest
MIN_ARTICLE_SCORE = 2
# words every support email has, which would match every article
GREETING_WORDS = {
    "able",
    "also",
    "any",
    "can",
    "cannot",
    "could",
    "dear",
    "facing",
    "from",
    "getting",
    "have",
    "hello",
    "help",
    "issue",
    "our",
    "please",
    "problem",
    "regards",
    "team",
    "thank",
    "thanks",
    "this",
    "unable",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "you",
    "your",
}

SUGGESTION_SYSTEM_PROMPT = """You are a customer support agent drafting a reply to a customer's ticket.
A human agent reviews and edits your draft before anything is sent.

Write in the language of the customer's latest message (English if unsure), in a clear, warm,
professional tone. Greet the customer by first name when it is given, otherwise use a neutral greeting.
Keep it short: 2-5 short paragraphs. Give concrete steps the customer can follow when the context
supports them. If the fix needs work from our team (a bug fix, a data correction or a change on their
site), say plainly what happens next instead of promising a date.

Use only the facts in the ticket, the conversation and the internal context. Never invent errors,
causes, documents, refunds, credits, discounts, dates, deadlines or commitments. If the cause is not
clear yet, say you are checking and ask for the one detail you need. Never mention the triage, the
session recording, the investigation or that you are an AI.

When a knowledge base article listed in the context answers part of the question, you may point the
customer to it by writing its URL exactly as given. Never write any other URL. Do not include a subject
line, a signature block or your name; the agent's signature is added automatically. Do not quote the
earlier messages.

Reply with JSON only:
{"reply": "<the email body, using \\n\\n between paragraphs>",
 "confidence": "high, medium or low: how sure you are that this reply resolves the ticket",
 "note": "one line for the agent, not the customer: why that confidence and what to check before sending"}"""


def queue_suggestion(ticket_id: str, instructions: str = "") -> bool:
    """Queue a fresh suggested reply for `ticket_id`; False when AI or the ticket rules it out.

    Never raises: it runs at the end of triage and investigations, whose own
    results must stand whatever happens here.
    """
    try:
        if not is_ai_configured() or not is_open_ticket(ticket_id):
            return False
        set_suggestion_status(ticket_id, "Pending")
        # after commit, so the job sees the triage or investigation that queued it
        frappe.enqueue(
            "helpdesk.ai_suggestion.generate_suggestion",
            ticket_id=ticket_id,
            instructions=instructions,
            job_id=f"ai-suggestion-{ticket_id}",
            deduplicate=True,
            timeout=SUGGESTION_JOB_TIMEOUT,
            queue="short",
            enqueue_after_commit=True,
        )
        return True
    except Exception:  # noqa: BLE001 - see docstring
        frappe.log_error(
            title=f"AI suggested reply not queued for {ticket_id}",
            message=frappe.get_traceback(),
        )
        return False


def generate_suggestion(ticket_id: str, instructions: str = ""):
    """Background job: draft a reply for the agent and store it on the ticket.

    Failures only mark the suggestion Failed: the agent can still reply by hand.
    """
    try:
        if not is_open_ticket(ticket_id):
            # a ticket closed while the job waited has nothing left to draft
            if (
                frappe.db.get_value(
                    "HD Ticket", ticket_id, "custom_ai_suggestion_status"
                )
                == "Pending"
            ):
                set_suggestion_status(ticket_id, "")
            return

        doc = frappe.get_doc("HD Ticket", ticket_id)
        context = gather_context(doc)
        result = call_haiku(
            SUGGESTION_SYSTEM_PROMPT,
            build_suggestion_prompt(doc, instructions, context),
            ticket_name=ticket_id,
        )
        suggestion = parse_suggestion(result.get("response"), context["articles"])
        if not suggestion:
            # an empty answer must not replace a reply the agent could still use
            raise ValueError(
                "AI suggested reply was empty or not JSON: "
                + str(result.get("response"))[:1000]
            )
        store_suggestion(ticket_id, suggestion, context["sources"])
    except Exception:  # noqa: BLE001 - see docstring
        set_suggestion_status(ticket_id, "Failed")
        frappe.log_error(
            title=f"AI suggested reply failed for {ticket_id}",
            message=frappe.get_traceback(),
        )


def get_suggestion_info(ticket_id: str) -> dict:
    """The stored suggestion on `ticket_id`, shaped for the agent UI."""
    row = frappe.db.get_value(
        "HD Ticket",
        ticket_id,
        [
            "custom_ai_suggestion_status",
            "custom_ai_suggested_reply",
            "custom_ai_suggestion_note",
            "custom_ai_suggestion_at",
            "custom_ai_suggestion_sources",
        ],
        as_dict=True,
    )
    if not row:
        return {
            "status": "",
            "reply": "",
            "note": "",
            "generated_at": "",
            "sources": [],
        }
    try:
        sources = json.loads(row.custom_ai_suggestion_sources or "[]")
    except ValueError:
        sources = []
    return {
        "status": row.custom_ai_suggestion_status or "",
        "reply": row.custom_ai_suggested_reply or "",
        "note": row.custom_ai_suggestion_note or "",
        "generated_at": str(row.custom_ai_suggestion_at or ""),
        "sources": sources if isinstance(sources, list) else [],
    }


def is_ai_configured() -> bool:
    """Whether the hub has an AI key, checked without frappe.throw's user-facing message."""
    return bool(
        get_decrypted_password(
            "HDS Hub Settings",
            "HDS Hub Settings",
            "anthropic_api_key",
            raise_exception=False,
        )
        or frappe.conf.get("anthropic_api_key")
    )


def is_open_ticket(ticket_id: str) -> bool:
    row = frappe.db.get_value(
        "HD Ticket", ticket_id, ["status", "status_category"], as_dict=True
    )
    return (
        bool(row)
        and row.status not in CLOSED_STATUSES
        and row.status_category != "Resolved"
    )


def set_suggestion_status(ticket_id: str, status: str):
    frappe.db.set_value(
        "HD Ticket",
        ticket_id,
        "custom_ai_suggestion_status",
        status,
        update_modified=False,
    )
    notify_agents(ticket_id)


def store_suggestion(ticket_id: str, suggestion: dict, sources: list[dict]):
    frappe.db.set_value(
        "HD Ticket",
        ticket_id,
        {
            "custom_ai_suggestion_status": "Ready",
            "custom_ai_suggested_reply": suggestion["reply"],
            "custom_ai_suggestion_note": suggestion["note"],
            "custom_ai_suggestion_at": now_datetime(),
            "custom_ai_suggestion_sources": json.dumps(sources),
        },
        update_modified=False,
    )
    notify_agents(ticket_id)


def notify_agents(ticket_id: str):
    """Tell open ticket views to reload the card instead of waiting for their next poll."""
    publish_event(
        REALTIME_EVENT,
        room=get_doc_room("HD Ticket", ticket_id),
        data={"ticket_id": ticket_id},
    )


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def gather_context(doc) -> dict:
    """Every input the reply can draw on, plus which of them were there (the card's source chips)."""
    blocks, sources = [], []

    if is_triaged(doc):
        triage = get_triage_context(doc)
        if triage:
            blocks.append(f"Triage of this ticket:\n{triage}")
        # build_prompt carries the triage summary even when there is nothing more
        sources.append({"kind": "triage"})

    session = get_session_context(doc.name)
    if session:
        blocks.append(session)
        sources.append({"kind": "replay"})

    investigation_name, findings = get_investigation_context(doc.name)
    if findings:
        blocks.append(
            f"Findings of an investigation of the customer's ERP site:\n{findings}"
        )
        sources.append({"kind": "investigation", "name": investigation_name})

    articles = find_related_articles(doc)
    sources.extend(
        {"kind": "article", "name": a["name"], "title": a["title"], "url": a["url"]}
        for a in articles
    )
    return {"blocks": blocks, "articles": articles, "sources": sources}


def is_triaged(doc) -> bool:
    return doc.get("custom_triage_status") == "Completed" and bool(
        doc.get("custom_triage_summary")
    )


def get_triage_context(doc) -> str:
    """Likely cause and steps to reproduce from the triage (build_prompt already has its summary)."""
    try:
        data = json.loads(doc.get("custom_triage_data") or "{}")
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        return ""

    lines = []
    for label, key in (("Category", "category"), ("Likely cause", "likely_cause")):
        value = str(data.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    for label, key in (
        ("Steps to reproduce", "steps_to_reproduce"),
        ("Error log findings", "error_findings"),
    ):
        items = data.get(key)
        items = (
            [str(i).strip() for i in items if str(i).strip()]
            if isinstance(items, list)
            else []
        )
        if items:
            lines.append(f"{label}:\n" + "\n".join(f"- {i}" for i in items))
    return truncate("\n".join(lines), MAX_TRIAGE_CHARS)


def get_session_context(ticket_id: str) -> str:
    """The customer's recorded session before the ticket, if there is one."""
    try:
        return build_triage_context(ticket_id, MAX_SESSION_CHARS)
    except Exception:  # noqa: BLE001 - the replay only enriches the reply
        frappe.log_error(
            title=f"AI suggested reply could not read the session replay for {ticket_id}",
            message=frappe.get_traceback(),
        )
        return ""


def get_investigation_context(ticket_id: str) -> tuple[str | None, str]:
    """The latest completed investigation of the customer's site: (session name, findings)."""
    session = frappe.qb.DocType("HDS AI Support Session")
    rows = (
        frappe.qb.from_(session)
        .select(session.name, session.diagnosis, session.resolution)
        .where(session.ticket == ticket_id)
        .where(session.status == "Completed")
        .orderby(session.modified, order=frappe.qb.desc)
        .limit(1)
        .run(as_dict=True)
    )
    if not rows:
        return None, ""
    row = rows[0]
    findings = "\n\n".join(
        text
        for text in (html_to_text(row.diagnosis), html_to_text(row.resolution))
        if text
    )
    if len(findings) > MAX_INVESTIGATION_CHARS:
        # a resumed investigation appends its conclusion, so keep the end
        findings = "…" + findings[-MAX_INVESTIGATION_CHARS:]
    return (row.name, findings) if findings else (None, "")


def find_related_articles(doc) -> list[dict]:
    """Up to MAX_ARTICLES published knowledge base articles sharing the most words with the ticket.

    A plain keyword match rather than helpdesk.search: that needs RediSearch,
    which a site may not have, and a background job should not depend on it.
    """
    keywords = get_keywords(doc)
    if not keywords:
        return []
    article = frappe.qb.DocType("HD Article")
    rows = (
        frappe.qb.from_(article)
        .select(article.name, article.title, article.content)
        .where(article.status == "Published")
        .where(
            Criterion.any(
                [
                    article.title.like(f"%{word}%") | article.content.like(f"%{word}%")
                    for word in keywords
                ]
            )
        )
        .orderby(article.modified, order=frappe.qb.desc)
        .limit(MAX_ARTICLE_CANDIDATES)
        .run(as_dict=True)
    )

    scored = []
    for row in rows:
        title = (row.title or "").lower()
        body = html_to_text(row.content)
        lowered = body.lower()
        score = sum(3 * (word in title) + (word in lowered) for word in keywords)
        if score >= MIN_ARTICLE_SCORE:
            scored.append((score, row, body))
    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "name": row.name,
            "title": row.title,
            "url": get_url(f"/helpdesk/kb-public/articles/{row.name}"),
            "excerpt": truncate(body, MAX_ARTICLE_EXCERPT_CHARS),
        }
        for _score, row, body in scored[:MAX_ARTICLES]
    ]


def get_keywords(doc) -> list[str]:
    """Distinct meaningful words of the subject, then the description."""
    stopwords = set(STOPWORDS) | GREETING_WORDS
    text = f"{doc.subject or ''} {html_to_text(doc.description)[:500]}".lower()
    keywords = []
    for word in re.findall(r"[a-z][a-z0-9]{2,}", text):
        if word not in stopwords and word not in keywords:
            keywords.append(word)
    return keywords[:MAX_KEYWORDS]


# ---------------------------------------------------------------------------
# Prompt and answer
# ---------------------------------------------------------------------------


def build_suggestion_prompt(doc, instructions: str, context: dict) -> str:
    """draft_reply's ticket + conversation prompt, followed by the internal context and articles."""
    parts = [
        build_prompt(doc, truncate(instructions.strip(), MAX_INSTRUCTIONS_CHARS), "")
    ]
    if context["blocks"]:
        parts.append(
            "Internal context (for getting the facts right; never quote it or say where it came from):\n\n"
            + "\n\n".join(context["blocks"])
        )
    if context["articles"]:
        parts.append(
            "Knowledge base articles you may point the customer to:\n"
            + "\n".join(
                f"- {a['title']}\n  URL: {a['url']}\n  Excerpt: {a['excerpt']}"
                for a in context["articles"]
            )
        )
    return "\n\n".join(parts)


def parse_suggestion(response, articles: list[dict]) -> dict | None:
    """The reply as HTML and the one-line note for the agent; None for an empty or unreadable answer."""
    if not isinstance(response, dict) or response.get("parse_error"):
        return None
    # asked for plain text; normalise in case it answers in HTML anyway
    reply = html_to_text(str(response.get("reply") or ""))
    if not reply:
        return None

    confidence = str(response.get("confidence") or "").strip().lower()
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "low"
    why = " ".join(str(response.get("note") or "").split())
    note = f"Confidence: {confidence}" + (f" — {why}" if why else "")
    return {
        "reply": link_articles(text_to_html(reply), articles),
        "note": truncate(note, MAX_NOTE_CHARS),
    }


def link_articles(reply_html: str, articles: list[dict]) -> str:
    """Make the article URLs we gave the model clickable; any other URL stays plain text."""
    for article in articles:
        url = escape_html(article["url"])
        anchor = f'<a href="{url}">{url}</a>'
        reply_html = re.sub(
            re.escape(url) + r"(?![\w/-])", lambda _match: anchor, reply_html
        )
    return reply_html
