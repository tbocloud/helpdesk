import frappe
from frappe import _

from helpdesk.ai_engine import call_haiku
from helpdesk.utils import agent_only

# What "good" looks like per channel and format; the model gets only the lines for the
# chosen ones. Hook, call-to-action and hashtag rules adapted from The Agency's
# Instagram Curator and LinkedIn Content Creator (github.com/msitarzewski/agency-agents, MIT).
CHANNEL_GUIDE = {
    "Instagram": "Hook in the first line (it shows before 'more'). 80-150 words, line breaks for readability, 1-2 emoji at most. End with a call to action (comment, save, visit, DM). 5-10 hashtags mixing broad, niche and the brand's own.",
    "Facebook": "Conversational, 40-80 words, one clear call to action. 1-3 hashtags.",
    "LinkedIn": "Professional and specific, 80-150 words. The first line must earn the 'see more' click: a concrete fact, number or short story, not a slogan. One idea per paragraph, 1-2 lines each. Have a clear point of view. No links in the body (say 'link in the comments'). End with a question that invites a reply. 3-5 specific hashtags.",
    "X": "One idea, under 250 characters including hashtags. 1-2 hashtags.",
    "YouTube": "A title under 70 characters on the first line, then a 2-3 sentence description. 3-5 hashtags.",
    "Blog": "A headline on the first line, then a 2-3 sentence introduction and a one-line meta description. No hashtags.",
    "Email": "A subject line under 50 characters on the first line, a preview line, then 3-5 short sentences with one call to action. No hashtags.",
    "WhatsApp": "Friendly and short, under 60 words, one call to action. No hashtags.",
}

FORMAT_GUIDE = {
    "Carousel": "The caption teases what the slides teach and asks people to swipe and save; don't repeat every slide.",
    "Reel": "The first line matches the reel's opening hook; keep the caption short and point to the video.",
    "Story": "Very short: one line and one action (reply, tap the link, vote).",
    "Video": "Say what the viewer will learn or see in the first line.",
    "Article": "Lead with the article's most useful takeaway, then invite people to read it.",
    "Newsletter": "Lead with what this issue gives the reader, then one reason to subscribe or read.",
}

SYSTEM_PROMPT = """You write social media and marketing copy for a digital agency's clients.
Write in clear, natural English for the client's audience. Never invent facts, prices, dates or
offers that are not in the brief; if the brief lacks a detail, write around it.
Open with a hook that would stop someone scrolling. Be specific, not generic: a concrete detail
beats a slogan. Avoid stock phrases such as "Excited to share", "In today's fast-paced world" or
"Look no further". Close with one clear call to action. Hashtags must be specific to the topic and
the audience, not generic ones like #business or #love.
Reply with JSON only: {"caption": "<the copy, using \\n for line breaks>", "hashtags": ["#tag", ...]}"""


@frappe.whitelist()
@agent_only
def draft_caption(
    title: str = "",
    channel: str = "Instagram",
    format: str = "Post",
    customer: str | None = None,
    campaign: str | None = None,
    brief: str = "",
    current_caption: str = "",
) -> dict:
    """Draft (or improve) a caption and hashtags for a content post."""
    if not frappe.db.exists("HD Content Platform", channel):
        frappe.throw(_("Unknown channel: {0}").format(channel))
    if not (title.strip() or brief.strip() or current_caption.strip()):
        frappe.throw(
            _("Add the copy or a short brief so the AI knows what to write about.")
        )

    lines = [
        f"Channel: {channel} ({format})",
        # platforms the team added have no guide; the AI writes for the channel by name
        *(
            [f"Guidelines: {CHANNEL_GUIDE[channel]}"]
            if channel in CHANNEL_GUIDE
            else []
        ),
        *([f"Format: {FORMAT_GUIDE[format]}"] if format in FORMAT_GUIDE else []),
        f"Post topic: {title.strip() or 'see the brief below'}",
    ]
    if customer:
        lines.append(f"Client: {customer}")
    if campaign and campaign.strip():
        lines.append(f"Campaign: {campaign.strip()}")
    if brief:
        lines.append(f"Brief from the team: {brief}")
    if current_caption.strip():
        lines.append(
            f"Improve this draft, keeping its facts and intent:\n{current_caption.strip()}"
        )

    try:
        result = call_haiku(SYSTEM_PROMPT, "\n".join(lines))
    except Exception:  # noqa: BLE001 - provider errors vary; show one clear message
        frappe.log_error(title="Draft with AI failed", message=frappe.get_traceback())
        frappe.throw(
            _(
                "AI drafting is unavailable right now. Check the AI provider in HDS Hub Settings."
            )
        )

    response = result.get("response") or {}
    caption = (response.get("caption") or "").strip()
    if not caption:
        frappe.throw(
            _("The AI didn't return a caption. Try again or add a short brief.")
        )
    return {
        "caption": caption,
        "hashtags": normalize_hashtags(response.get("hashtags")),
    }


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
