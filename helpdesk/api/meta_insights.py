"""The Reach report: how far each client's Facebook Page and Instagram account reached
(docs/meta-insights.md).

Who sees a client's reach follows the content calendar: the content team's leads see
every client, the rest of the team the clients whose projects they are on. "Sync now"
follows `can_handle_credentials`, like connecting Meta."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, date_diff, formatdate, getdate, today

from helpdesk.content_team import in_content_team
from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    _is_content_lead,
    member_customers,
)
from helpdesk.integrations.meta import connect, insights
from helpdesk.tasky.permissions import can_handle_credentials
from helpdesk.utils import send_report_pdf

PLATFORMS = (insights.FACEBOOK, insights.INSTAGRAM)
# the per-day numbers the chart can show
DAY_FIELDS = ("reach", "views", "engagements")
POST_FIELDS = (
    "name",
    "platform",
    "kind",
    "posted_on",
    "caption",
    "permalink",
    "thumbnail_url",
    "reach",
    "views",
    "reactions",
    "comments",
    "shares",
    "saves",
    "clicks",
    "interactions",
    "content_post",
    "insights_note",
)
TOP_POSTS = 50
# posts listed in the PDF, which goes to the client
PDF_POSTS = 15
# tallest bar of the PDF's daily reach, in pixels
BAR_HEIGHT = 80
# the longest period one report covers
MAX_DAYS = 366


# ----------------------------------------------------------------- who sees it --


def visible_connections(user: str | None = None) -> list[dict]:
    """The Meta connections whose reach `user` may see, without anything secret."""
    user = user or frappe.session.user
    if not in_content_team(user):
        return []
    rows = frappe.get_all(
        connect.CONNECTION,
        filters={"status": ["!=", "Pending"]},
        fields=[
            "name as project",
            "customer",
            "status",
            "facebook_page_name",
            "instagram_username",
            "insights_allowed",
            "insights_synced_on",
            "insights_error",
        ],
        order_by="customer asc, facebook_page_name asc",
    )
    if not _is_content_lead(user):
        mine = member_customers(user)
        rows = [r for r in rows if r.customer in mine]
    for row in rows:
        row.insights_allowed = bool(row.insights_allowed)
        row.insights_synced_on = (
            cstr(row.insights_synced_on) if row.insights_synced_on else None
        )
        row.can_sync = can_handle_credentials(row.project, user)
    return rows


def require_connection(project: str) -> dict:
    row = next((r for r in visible_connections() if r.project == project), None)
    if not row:
        frappe.throw(
            _("You can't see the reach of this project."), frappe.PermissionError
        )
    return row


def clean_period(from_date: str, to_date: str):
    first, last = getdate(from_date), getdate(to_date)
    if last < first:
        frappe.throw(_("The period can't end before it starts."))
    if date_diff(last, first) >= MAX_DAYS:
        frappe.throw(_("Pick a period of a year or less."))
    return first, last


# -------------------------------------------------------------------- endpoints --


@frappe.whitelist()
def get_reach_report(from_date: str, to_date: str, project: str | None = None) -> dict:
    """The connections the viewer can pick from and, for the picked one (or the first),
    the period's reach."""
    first, last = clean_period(from_date, to_date)
    connections = visible_connections()
    selected = next(
        (c for c in connections if c.project == project),
        connections[0] if connections and not project else None,
    )
    if project and not selected:
        frappe.throw(
            _("You can't see the reach of this project."), frappe.PermissionError
        )
    return {
        "enabled": connect.insights_enabled(),
        "connections": connections,
        "selected": selected.project if selected else None,
        "report": build_report(selected, first, last) if selected else None,
    }


@frappe.whitelist(methods=["POST"])
def sync_now(project: str) -> dict:
    """Read the last 90 days again in the background."""
    row = require_connection(project)
    if not row.can_sync:
        frappe.throw(
            _("Only the project's managers can sync its reach."),
            frappe.PermissionError,
        )
    if not row.insights_allowed:
        frappe.throw(_("Connect Meta again and allow the insights permissions first."))
    insights.queue_sync(project)
    return {"queued": True}


@frappe.whitelist()
def export_pdf(project: str, from_date: str, to_date: str):
    """The Reach report as a PDF download, to send to the client."""
    row = require_connection(project)
    first, last = clean_period(from_date, to_date)
    report = build_report(row, first, last)
    send_report_pdf(
        "helpdesk/templates/reach_report_pdf.html",
        {
            "title": _("Reach report"),
            "customer": row.customer or row.facebook_page_name,
            "accounts": account_names(row),
            "period": _("{0} to {1}").format(formatdate(first), formatdate(last)),
            "report": report,
            "bars": [reach_bars(platform, report) for platform in report["series"]],
            "top_posts": [
                {**post, "posted": formatdate(post["posted_on"])}
                for post in report["posts"][:PDF_POSTS]
            ],
        },
        f"reach-{frappe.scrub(row.customer or project)}-{first}-to-{last}",
    )


# ---------------------------------------------------------------------- the report --


def reach_bars(platform: str, report: dict) -> dict:
    """Daily reach as bar heights for the PDF, which can't draw the page's chart. Every
    seventh day carries its date under the bar."""
    values = report["series"][platform]["reach"]
    top = max(values, default=0)
    return {
        "platform": platform,
        "top": top,
        "bars": [
            {
                "label": getdate(day).strftime("%d %b"),
                "value": value,
                "height": round(value * BAR_HEIGHT / top) if top else 0,
                "marked": i % 7 == 0,
            }
            for i, (day, value) in enumerate(zip(report["days"], values))
        ],
    }


def account_names(row) -> str:
    names = [_("Facebook: {0}").format(row.facebook_page_name)]
    if row.instagram_username:
        names.append(_("Instagram: @{0}").format(row.instagram_username))
    return " · ".join(names)


def build_report(row, first, last) -> dict:
    """The period's numbers per platform against the period just before, the days for
    the chart, the posts by reach and how each kind of post did."""
    span = date_diff(last, first) + 1
    previous_first = getdate(add_days(first, -span))
    platforms = [
        p
        for p in PLATFORMS
        if p == insights.FACEBOOK or row.instagram_username or has_rows(row, p)
    ]
    days_rows = frappe.get_all(
        insights.DAILY,
        filters={"project": row.project, "day": ["between", [previous_first, last]]},
        fields=["platform", "day", *DAY_FIELDS, "follows", "unfollows", "followers"],
        order_by="day asc",
    )
    posts = frappe.get_all(
        insights.POSTS,
        filters={
            "project": row.project,
            "posted_on": ["between", [f"{first} 00:00:00", f"{last} 23:59:59"]],
        },
        fields=list(POST_FIELDS),
        order_by="reach desc, posted_on desc",
    )
    # days with numbers end yesterday; later days of the period would only draw zeros
    shown_last = min(last, getdate(add_days(today(), -1)))
    days = [
        getdate(add_days(first, i))
        for i in range(max(date_diff(shown_last, first) + 1, 0))
    ]
    return {
        "platforms": [
            platform_summary(platform, days_rows, posts, first, last, previous_first)
            for platform in platforms
        ],
        "days": [str(d) for d in days],
        "series": {
            platform: daily_series(platform, days_rows, days) for platform in platforms
        },
        "posts": [post_payload(p) for p in posts[:TOP_POSTS]],
        "post_count": len(posts),
        "kinds": kind_summary(posts),
        "engagement_rate": engagement_rate(posts),
    }


def has_rows(row, platform: str) -> bool:
    return bool(
        frappe.db.exists(insights.DAILY, {"project": row.project, "platform": platform})
    )


def platform_summary(platform, days_rows, posts, first, last, previous_first) -> dict:
    current = [r for r in days_rows if r.platform == platform and r.day >= first]
    previous = [
        r
        for r in days_rows
        if r.platform == platform and previous_first <= r.day < first
    ]
    mine = [p for p in posts if p.platform == platform]
    return {
        "platform": platform,
        "current": totals(current),
        "previous": totals(previous) if previous else None,
        "followers": latest_followers(current),
        "followers_before": latest_followers(previous),
        "posts": len(mine),
        "engagement_rate": engagement_rate(mine),
    }


def totals(rows) -> dict:
    values = {field: sum(cint(r[field]) for r in rows) for field in DAY_FIELDS}
    values["net_follows"] = sum(cint(r.follows) - cint(r.unfollows) for r in rows)
    return values


def latest_followers(rows) -> int | None:
    """The last follower total recorded in these days; days filled in later have none."""
    counted = [r for r in rows if cint(r.followers)]
    return cint(counted[-1].followers) if counted else None


def daily_series(platform, days_rows, days) -> dict:
    by_day = {r.day: r for r in days_rows if r.platform == platform}
    return {
        field: [cint((by_day.get(day) or {}).get(field)) for day in days]
        for field in DAY_FIELDS
    }


def engagement_rate(posts) -> float | None:
    """Interactions per person reached, over the period's posts, in percent."""
    reach = sum(cint(p.reach) for p in posts)
    if not reach:
        return None
    return round(sum(cint(p.interactions) for p in posts) * 100 / reach, 1)


def kind_summary(posts) -> list[dict]:
    kinds: dict[str, dict] = {}
    for post in posts:
        kind = kinds.setdefault(
            post.kind or "Other",
            {"kind": post.kind or "Other", "posts": 0, "reach": 0, "interactions": 0},
        )
        kind["posts"] += 1
        kind["reach"] += cint(post.reach)
        kind["interactions"] += cint(post.interactions)
    for kind in kinds.values():
        kind["average_reach"] = round(kind["reach"] / kind["posts"])
    return sorted(kinds.values(), key=lambda k: k["average_reach"], reverse=True)


def post_payload(post) -> dict:
    return {
        **post,
        "posted_on": cstr(post.posted_on) if post.posted_on else None,
    }
