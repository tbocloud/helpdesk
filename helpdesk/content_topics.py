"""AI topic ideas for the posts a monthly plan creates as placeholders.

Planning a month creates slots such as "Instagram Post 3/8 · Nov 2026". This background
job asks the AI for one topic and brief per slot, from what the brand does (the plan's
"About the brand"), the platform and format, the month's occasions and recent post titles,
and fills in each post that still has its placeholder title. Occasion posts already have
their topic and are left alone. If the AI fails, the placeholders simply stay.

Content mix and specificity rules adapted from The Agency's Social Media Strategist and
Instagram Curator (github.com/msitarzewski/agency-agents, MIT).
"""

import frappe
from frappe import _

from helpdesk.ai_engine import call_haiku
from helpdesk.helpdesk.doctype.hd_content_occasion.hd_content_occasion import (
    occasions_between,
)

MAX_TITLE_CHARS = 120
MAX_BRIEF_CHARS = 600
RECENT_TITLES = 30

SYSTEM_PROMPT = """You plan social media content for a digital agency's client.
For each numbered slot, suggest one post topic that fits the platform and format, and a 2-3 sentence
brief the writer and designer can work from.
Mix the month: roughly a third about the brand and what it offers, a third useful or educational for
its customers, and a third about its community and customers. Don't repeat a recent topic, and don't
cover the month's occasions; those days already have their own posts.
Be specific to this business. No generic filler such as "Motivation Monday" or "Happy weekend".
Never invent prices, discounts, products, dates or claims that the brand note doesn't give; when
unsure, choose an educational or community topic instead.
Reply with JSON only:
{"ideas": [{"slot": 1, "title": "<under 80 characters>", "brief": "<2-3 sentences>"}]}"""


def suggest_topics(package: str, placeholders: dict):
    """Background job; `placeholders` maps each post to the title planning gave it."""
    try:
        fill_topics(package, placeholders)
    except Exception:  # noqa: BLE001 - the plan stands; the team writes the topics themselves
        frappe.log_error(
            title=f"Content topic ideas failed for {package}",
            message=frappe.get_traceback(),
        )


def fill_topics(package: str, placeholders: dict):
    plan = frappe.get_doc("HD Content Package", package)
    posts = frappe.get_all(
        "HD Content Post",
        filters={"name": ["in", list(placeholders)]},
        fields=["name", "title", "channel", "format", "publish_on"],
        order_by="publish_on asc",
    )
    if not posts:
        return
    result = call_haiku(SYSTEM_PROMPT, build_prompt(plan, posts))
    ideas = parse_ideas(result.get("response") or {})
    for number, row in enumerate(posts, 1):
        idea = ideas.get(number)
        # someone already gave it a topic, or it's no longer an idea
        if not idea or row.title != placeholders.get(row.name):
            continue
        post = frappe.get_doc("HD Content Post", row.name)
        if post.status != "Idea":
            continue
        post.title = idea["title"]
        post.brief = "{0}\n\n{1}".format(
            idea["brief"],
            _("Suggested by AI from the monthly plan; change it freely."),
        )
        # the team already heard about the plan; renaming tasks needs no new notice
        post.flags.quiet_tasks = True
        post.save(ignore_permissions=True)


def build_prompt(plan, posts: list) -> str:
    first, last = posts[0].publish_on, posts[-1].publish_on
    lines = [
        f"Client: {plan.customer}",
        "About the brand: "
        + (
            (plan.about_brand or "").strip()
            or "not given; keep topics to what the client's name suggests, and prefer educational ones"
        ),
        f"Month: {frappe.utils.getdate(first).strftime('%B %Y')}",
    ]
    occasions = occasions_between(first, last, plan.occasion_regions())
    if occasions:
        lines.append(
            "Occasions this month (already planned): "
            + ", ".join(
                f"{o.occasion_name} ({o.date.strftime('%d %b')})" for o in occasions
            )
        )
    recent = recent_titles(plan.customer, {p.name for p in posts})
    if recent:
        lines.append("Recent posts (don't repeat): " + "; ".join(recent))
    lines.append("Slots:")
    lines += [
        f"{number}. {frappe.utils.getdate(p.publish_on).strftime('%a %d %b')}: {p.channel} {p.format}"
        for number, p in enumerate(posts, 1)
    ]
    return "\n".join(lines)


def recent_titles(customer: str, exclude: set) -> list[str]:
    rows = frappe.get_all(
        "HD Content Post",
        filters={"customer": customer, "status": ("!=", "Cancelled")},
        fields=["name", "title"],
        order_by="publish_on desc",
        limit=RECENT_TITLES + len(exclude),
    )
    return [r.title for r in rows if r.name not in exclude][:RECENT_TITLES]


def parse_ideas(response: dict) -> dict[int, dict]:
    """{slot number: {"title", "brief"}} for every complete idea in the AI's answer."""
    ideas = {}
    for idea in response.get("ideas") or []:
        if not isinstance(idea, dict):
            continue
        try:
            number = int(idea.get("slot"))
        except (TypeError, ValueError):
            continue
        title = " ".join(str(idea.get("title") or "").split())[:MAX_TITLE_CHARS]
        brief = str(idea.get("brief") or "").strip()[:MAX_BRIEF_CHARS]
        if title and brief:
            ideas[number] = {"title": title, "brief": brief}
    return ideas
