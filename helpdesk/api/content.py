import frappe
from frappe import _

from helpdesk.ai_engine import call_haiku
from helpdesk.utils import agent_only

# What "good" looks like per channel; the model gets only the line for the chosen channel
CHANNEL_GUIDE = {
    "Instagram": "Hook in the first line (it shows before 'more'). 80-150 words, line breaks for readability, 1-2 emoji at most. 5-10 relevant hashtags.",
    "Facebook": "Conversational, 40-80 words, one clear call to action. 1-3 hashtags.",
    "LinkedIn": "Professional and specific, 80-150 words, short paragraphs, end with a question or call to action. 3-5 hashtags.",
    "X": "One idea, under 250 characters including hashtags. 1-2 hashtags.",
    "YouTube": "A title under 70 characters on the first line, then a 2-3 sentence description. 3-5 hashtags.",
    "Blog": "A headline on the first line, then a 2-3 sentence introduction and a one-line meta description. No hashtags.",
    "Email": "A subject line under 50 characters on the first line, a preview line, then 3-5 short sentences with one call to action. No hashtags.",
    "WhatsApp": "Friendly and short, under 60 words, one call to action. No hashtags.",
}

SYSTEM_PROMPT = """You write social media and marketing copy for a digital agency's clients.
Write in clear, natural English for the client's audience. Never invent facts, prices, dates or
offers that are not in the brief; if the brief lacks a detail, write around it.
Reply with JSON only: {"caption": "<the copy, using \\n for line breaks>", "hashtags": ["#tag", ...]}"""


@frappe.whitelist()
@agent_only
def draft_caption(
    title: str,
    channel: str,
    format: str = "Post",
    customer: str | None = None,
    campaign: str | None = None,
    brief: str = "",
    current_caption: str = "",
) -> dict:
    """Draft (or improve) a caption and hashtags for a content post."""
    if channel not in CHANNEL_GUIDE:
        frappe.throw(_("Unknown channel: {0}").format(channel))

    lines = [
        f"Channel: {channel} ({format})",
        f"Guidelines: {CHANNEL_GUIDE[channel]}",
        f"Post topic: {title}",
    ]
    if customer:
        lines.append(f"Client: {customer}")
    if campaign:
        goal = frappe.db.get_value("HD Content Campaign", campaign, ["campaign_name", "goal"], as_dict=True)
        if goal:
            lines.append(f"Campaign: {goal.campaign_name}" + (f" (goal: {goal.goal})" if goal.goal else ""))
    if brief:
        lines.append(f"Brief from the team: {brief}")
    if current_caption.strip():
        lines.append(f"Improve this draft, keeping its facts and intent:\n{current_caption.strip()}")

    try:
        result = call_haiku(SYSTEM_PROMPT, "\n".join(lines))
    except Exception:  # noqa: BLE001 - provider errors vary; show one clear message
        frappe.log_error(title="Draft with AI failed", message=frappe.get_traceback())
        frappe.throw(_("AI drafting is unavailable right now. Check the AI provider in HDS Hub Settings."))

    response = result.get("response") or {}
    caption = (response.get("caption") or "").strip()
    if not caption:
        frappe.throw(_("The AI didn't return a caption. Try again or add a short brief."))
    return {"caption": caption, "hashtags": normalize_hashtags(response.get("hashtags"))}


def normalize_hashtags(tags) -> str:
    if isinstance(tags, str):
        tags = tags.split()
    cleaned = []
    for tag in tags or []:
        tag = "".join(str(tag).split())
        if not tag:
            continue
        tag = tag if tag.startswith("#") else f"#{tag}"
        if tag.lower() not in {t.lower() for t in cleaned}:
            cleaned.append(tag)
    return " ".join(cleaned)
