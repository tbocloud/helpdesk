"""Draft knowledge base articles from resolved tickets.

When a ticket is resolved, the AI reads the question and the team's answer and
decides whether other customers are likely to ask the same thing (a how-to, a
setting, a common error). If so, and no published article or earlier draft
already covers it, it writes a Draft HD Article in the General category and the
Agent Managers are asked to review and publish it. Nothing is ever published
automatically, and the draft must not contain the customer's names or data.

A published article then helps TBO AI answer the next customer by itself
(helpdesk.ai_suggestion and the TBO Chat bridge read published articles).
"""

import frappe
from frappe import _
from frappe.utils import md_to_html

from helpdesk.ai_engine import call_haiku
from helpdesk.ai_suggestion import find_related_articles, is_ai_configured
from helpdesk.api.knowledge_base import get_general_category
from helpdesk.api.ticket_ai import build_prompt, html_to_text, truncate
from helpdesk.automation import automation_user
from helpdesk.work_reminders import _agent_managers, notify_users

DRAFT_JOB_TIMEOUT = 300
MAX_TITLE_CHARS = 140
MAX_EARLIER_DRAFTS = 20

DRAFT_SYSTEM_PROMPT = """You maintain the customer knowledge base of TBO, a team that supports ERPNext / Frappe users.

You get a ticket the team has just resolved: the customer's question and the conversation with the answer. Decide whether it should become a knowledge base article.

Write an article only when ALL of these hold:
- other customers are likely to ask the same thing (how to do something, a setting, a common error and its fix);
- the conversation contains a clear, working answer;
- the answer doesn't depend on this one customer's data, and isn't a code bug fixed by a developer.
Don't write one when an existing article or earlier draft listed below already covers it; name that article instead.

The article is for customers: plain, friendly English, short sentences, numbered steps with the exact menu and field names from ERPNext. Never include names, emails, company names, document numbers, amounts or anything else that identifies the customer.

Reply with JSON only:
{"write": true or false,
 "reason": "one line for the support team: why (not)",
 "covered_by": "name of the existing article or draft that already covers it, or empty",
 "title": "a question or task customers would search for, e.g. How do I export a report to Excel?",
 "body": "the article in Markdown: one short intro line, then the steps; empty when write is false"}"""


def on_ticket_update(doc, method=None):
    """HD Ticket on_update: queue a draft when the ticket has just been resolved."""
    if not doc.has_value_changed("status_category"):
        return
    # Closed tickets are in the Resolved category too, so this runs once
    if doc.status_category != "Resolved":
        return
    if not is_enabled():
        return
    frappe.enqueue(
        "helpdesk.kb_drafts.draft_article",
        ticket_id=doc.name,
        job_id=f"kb-draft-{doc.name}",
        deduplicate=True,
        timeout=DRAFT_JOB_TIMEOUT,
        queue="long",
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )


def is_enabled() -> bool:
    return (
        bool(frappe.db.get_single_value("HDS Hub Settings", "draft_kb_articles"))
        and is_ai_configured()
    )


def draft_article(ticket_id: str):
    """Background job; a failure is logged and the ticket is left as it was."""
    try:
        if frappe.db.exists("HD Article", {"source_ticket": ticket_id}):
            return
        doc = frappe.get_doc("HD Ticket", ticket_id)
        if not has_team_answer(ticket_id):
            return
        result = call_haiku(
            DRAFT_SYSTEM_PROMPT, build_draft_prompt(doc), ticket_name=ticket_id
        )
        draft = parse_draft(result.get("response"))
        if draft:
            article = create_draft(doc, draft)
            notify_reviewers(doc, article)
    except Exception:  # noqa: BLE001 - see docstring
        frappe.log_error(
            title=f"KB draft failed for ticket {ticket_id}",
            message=frappe.get_traceback(),
        )


def has_team_answer(ticket_id: str) -> bool:
    """Only an answered ticket has something to teach."""
    return bool(
        frappe.db.exists(
            "Communication",
            {
                "reference_doctype": "HD Ticket",
                "reference_name": ticket_id,
                "sent_or_received": "Sent",
            },
        )
    )


def build_draft_prompt(doc) -> str:
    parts = [build_prompt(doc, "", "")]
    resolution = truncate(html_to_text(doc.get("resolution_details")), 2000)
    if resolution:
        parts.append(f"How the team resolved it:\n{resolution}")
    covered = [
        f"- {a['name']}: {a['title']}\n  {a['excerpt']}"
        for a in find_related_articles(doc)
    ] + [f"- {d.name}: {d.title} (draft)" for d in earlier_drafts()]
    if covered:
        parts.append(
            "Existing articles and drafts that may already cover it:\n"
            + "\n".join(covered)
        )
    return "\n\n".join(parts)


def earlier_drafts() -> list:
    return frappe.get_all(
        "HD Article",
        filters={"status": "Draft", "source_ticket": ("is", "set")},
        fields=["name", "title"],
        order_by="creation desc",
        limit=MAX_EARLIER_DRAFTS,
    )


def parse_draft(response) -> dict | None:
    """Title and Markdown body when the AI chose to write; None otherwise."""
    if not isinstance(response, dict) or response.get("parse_error"):
        return None
    if response.get("write") is not True or response.get("covered_by"):
        return None
    title = " ".join(str(response.get("title") or "").split())
    body = str(response.get("body") or "").strip()
    if not title or not body:
        return None
    return {"title": truncate(title, MAX_TITLE_CHARS), "body": body}


def create_draft(ticket, draft: dict):
    article = frappe.get_doc(
        {
            "doctype": "HD Article",
            "title": draft["title"],
            "content": md_to_html(draft["body"]),
            "category": get_general_category(),
            "status": "Draft",
            "source_ticket": ticket.name,
        }
    ).insert(ignore_permissions=True)
    # before_insert makes the session user (the job's Administrator) the author
    article.db_set("author", automation_user(), update_modified=False)
    return article


def notify_reviewers(ticket, article):
    notify_users(
        _agent_managers(),
        "HD Article",
        article.name,
        _("KB draft to review, from ticket #{0}: {1}").format(
            ticket.name, article.title
        ),
    )
