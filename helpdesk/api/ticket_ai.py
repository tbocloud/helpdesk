import html
import re

import frappe
from frappe import _
from frappe.utils import escape_html, strip_html

from helpdesk.ai_engine import call_haiku
from helpdesk.utils import agent_only

# Bounds keep the prompt small (and cheap) however long the thread gets
MAX_MESSAGES = 6
MAX_MESSAGE_CHARS = 1000
MAX_DESCRIPTION_CHARS = 1500
MAX_DRAFT_CHARS = 2000
MAX_PROMPT_CHARS = 13000

SYSTEM_PROMPT = """You are a customer support agent writing an email reply to a customer about their ticket.
Write in clear, warm, professional English. Greet the customer by first name when it is given,
otherwise use a neutral greeting. Answer the customer's latest message using only the facts in the
ticket context. Never invent facts, refunds, credits, discounts, dates, deadlines, order or booking
details, or commitments that are not stated in the context. If something is unknown, say you are
checking and will follow up, or ask the customer for the missing detail. Keep it concise: 2-5 short
paragraphs. Do not include a subject line, a signature block or your name; the agent's signature is
added automatically. Do not quote the earlier messages.
Reply with JSON only: {"reply": "<the email body, using \\n\\n between paragraphs>"}"""


@frappe.whitelist()
@agent_only
def draft_reply(ticket: str, instructions: str = "", current_draft: str = "") -> dict:
    """Draft (or improve) an email reply to the customer on `ticket`."""
    frappe.has_permission("HD Ticket", "read", ticket, throw=True)
    doc = frappe.get_doc("HD Ticket", ticket)

    try:
        result = call_haiku(
            SYSTEM_PROMPT,
            build_prompt(doc, instructions, current_draft),
            ticket_name=ticket,
        )
    except Exception:  # noqa: BLE001 - provider errors vary; show one clear message
        frappe.log_error(
            title="Draft reply with AI failed", message=frappe.get_traceback()
        )
        frappe.throw(
            _(
                "AI drafting is unavailable right now. Check the AI provider in HDS Hub Settings."
            )
        )

    response = result.get("response") or {}
    reply = (response.get("reply") or "").strip() if isinstance(response, dict) else ""
    if not reply:
        frappe.throw(_("The AI didn't return a reply. Try again."))
    # The model is asked for plain text; normalise in case it answers in HTML anyway
    return {"reply": text_to_html(html_to_text(reply))}


def build_prompt(doc, instructions: str, current_draft: str) -> str:
    lines = [f"Ticket subject: {doc.subject}"]
    first_name = get_customer_first_name(doc)
    if first_name:
        lines.append(f"Customer first name: {first_name}")
    if doc.customer:
        lines.append(f"Customer organisation: {doc.customer}")
    messages = get_recent_messages(doc.name)
    # A short thread already starts with the original request as its first email
    if len(messages) >= MAX_MESSAGES or not messages:
        description = truncate(html_to_text(doc.description), MAX_DESCRIPTION_CHARS)
        if description:
            lines.append(f"Original request:\n{description}")
    triage_summary = truncate(
        html_to_text(doc.get("custom_triage_summary")), MAX_MESSAGE_CHARS
    )
    if triage_summary:
        lines.append(
            f"Internal triage summary (for context, do not quote):\n{triage_summary}"
        )

    if messages:
        lines.append(
            "Conversation so far, oldest first (the last one is the latest message):"
        )
        lines.extend(messages)
    if instructions.strip():
        lines.append(
            f"Instructions from the agent: {truncate(instructions.strip(), MAX_MESSAGE_CHARS)}"
        )
    draft = truncate(html_to_text(current_draft), MAX_DRAFT_CHARS)
    if draft:
        lines.append(f"Improve this draft, keeping its facts and intent:\n{draft}")

    prompt = "\n\n".join(lines)
    # Keep the tail: the latest message and the agent's draft matter most
    return prompt if len(prompt) <= MAX_PROMPT_CHARS else prompt[-MAX_PROMPT_CHARS:]


def get_recent_messages(ticket: str) -> list[str]:
    """The last MAX_MESSAGES emails on the ticket, oldest first, as prompt lines."""
    communication = frappe.qb.DocType("Communication")
    rows = (
        frappe.qb.from_(communication)
        .select(
            communication.sender,
            communication.sender_full_name,
            communication.sent_or_received,
            communication.content,
        )
        .where(communication.reference_doctype == "HD Ticket")
        .where(communication.reference_name == ticket)
        .where(communication.communication_type == "Communication")
        .orderby(communication.creation, order=frappe.qb.desc)
        .limit(MAX_MESSAGES)
        .run(as_dict=True)
    )
    lines = []
    for row in reversed(rows):
        role = "Agent" if row.sent_or_received == "Sent" else "Customer"
        who = row.sender_full_name or row.sender or role
        body = truncate(html_to_text(row.content), MAX_MESSAGE_CHARS)
        if body:
            lines.append(f"[{role}: {who}]\n{body}")
    return lines


def get_customer_first_name(doc) -> str:
    if doc.contact:
        first_name = frappe.db.get_value("Contact", doc.contact, "first_name")
        if first_name:
            return first_name
    if doc.raised_by:
        return (
            frappe.db.get_value("Contact", {"email_id": doc.raised_by}, "first_name")
            or ""
        )
    return ""


def html_to_text(content: str | None) -> str:
    if not content:
        return ""
    # Keep paragraph breaks before tags are stripped
    content = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|blockquote)>", "\n", content)
    text = html.unescape(strip_html(content))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def text_to_html(text: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join(
        f"<p>{escape_html(p).replace(chr(10), '<br>')}</p>" for p in paragraphs
    )
