"""Board actions for the Content Calendar: add entries, postpone, cancel."""

import json

import frappe
from frappe import _
from frappe.core.utils import html2text
from frappe.utils import format_date, format_datetime, get_datetime, now_datetime
from frappe.utils.xlsxutils import make_xlsx

TEAM_FIELDS = ("writer", "designer", "marketer")
# fields the Add entry dialog may set on every post it creates
ENTRY_FIELDS = (
    "title",
    "customer",
    "campaign",
    "format",
    "status",
    "publish_on",
    "caption",
    "hashtags",
    "brief",
    *TEAM_FIELDS,
)


@frappe.whitelist(methods=["POST"])
def add_entries(
    values: str | dict, channels: str | list, separate: bool | int | str = True
) -> list[str]:
    """Create the entry for the chosen platforms, all together or not at all.

    `separate` makes one post per platform (each can be scheduled, approved and
    published on its own); otherwise one post covers every platform.
    """
    frappe.has_permission("HD Content Post", "create", throw=True)
    values = json.loads(values) if isinstance(values, str) else values
    channels = json.loads(channels) if isinstance(channels, str) else channels
    channels = list(dict.fromkeys(c for c in channels or [] if c))
    if not channels:
        frappe.throw(_("Pick at least one platform"))
    separate = frappe.utils.sbool(separate)

    common = {k: values.get(k) for k in ENTRY_FIELDS if values.get(k) not in (None, "")}
    groups = [[c] for c in channels] if separate else [channels]
    names = []
    for platforms in groups:
        post = frappe.get_doc(
            {
                "doctype": "HD Content Post",
                **common,
                "channel": platforms[0],
                "platforms": ", ".join(platforms),
            }
        )
        post.insert()
        names.append(post.name)
    return names


@frappe.whitelist()
def get_team_defaults(customer: str) -> dict:
    """The team on this customer's most recent post, to pre-fill a new entry."""
    latest = frappe.get_list(
        "HD Content Post",
        filters={"customer": customer},
        fields=list(TEAM_FIELDS),
        order_by="creation desc",
        limit=1,
    )
    return latest[0] if latest else dict.fromkeys(TEAM_FIELDS)


@frappe.whitelist(methods=["POST"])
def postpone(post: str, publish_on: str, reason: str):
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    doc.postpone(publish_on, reason)
    return {"publish_on": doc.publish_on, "times_postponed": doc.times_postponed}


@frappe.whitelist(methods=["POST"])
def cancel(post: str, reason: str | None = None):
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    doc.cancel(reason)
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def assign(post: str, role: str, user: str | None = None, hours: float | None = None):
    """Set a post's writer, designer or marketer; their task gets `hours` if given."""
    if role not in TEAM_FIELDS:
        frappe.throw(_("Unknown role {0}").format(role))
    doc = frappe.get_doc("HD Content Post", post)
    doc.check_permission("write")
    doc.set(role, user or None)
    if user and hours:
        doc.flags.task_hours = {role: float(hours)}
    doc.save()
    return {role: doc.get(role)}


@frappe.whitelist()
def get_role_tasks(post: str) -> list[dict]:
    """The open tasks created for this post's team, for the Assign dialog."""
    frappe.has_permission("HD Content Post", "read", post, throw=True)
    if not frappe.get_meta("Task").has_field("content_post"):
        return []
    return frappe.get_all(
        "Task",
        filters={
            "content_post": post,
            "status": ("not in", ("Completed", "Cancelled")),
        },
        fields=["name", "content_role", "expected_time", "status"],
    )


EXPORT_COLUMNS = (
    ("Post", "name", 18),
    ("Publish date", "date", 14),
    ("Time", "time", 10),
    ("Campaign or topic", "title", 40),
    ("Customer", "customer", 26),
    ("Campaign", "campaign", 22),
    ("Platforms", "platforms", 24),
    ("Type", "format", 12),
    ("Status", "status", 16),
    ("Missed", "missed", 9),
    ("Writer", "writer", 28),
    ("Designer", "designer", 28),
    ("Digital marketer", "marketer", 28),
    ("Caption", "caption", 60),
    ("Hashtags", "hashtags", 30),
    ("Brief", "brief", 50),
    ("Times postponed", "times_postponed", 10),
    ("Client feedback", "client_feedback", 40),
    ("Published URL", "published_url", 40),
    ("Published on", "published_on", 18),
)


@frappe.whitelist()
def export_posts(
    start: str,
    end: str,
    customer: str | None = None,
    channel: str | None = None,
    status: str | None = None,
):
    """The Sheet view as an Excel file: same period and filters, same visibility rules."""
    filters = {"publish_on": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]]}
    if customer:
        filters["customer"] = customer
    if channel:
        filters["platforms"] = ["like", f"%{channel}%"]
    if status:
        filters["status"] = status

    fields = [f for _l, f, _w in EXPORT_COLUMNS if f not in ("date", "time", "missed")]
    posts = frappe.get_list(
        "HD Content Post",
        filters=filters,
        fields=["publish_on", "channel", *fields],
        order_by="publish_on asc",
        limit_page_length=0,
    )

    now = now_datetime()
    rows = [[_(label) for label, _f, _w in EXPORT_COLUMNS]]
    for post in posts:
        publish_on = get_datetime(post.publish_on)
        post.date = format_date(publish_on)
        post.time = publish_on.strftime("%I:%M %p").lstrip("0")
        post.platforms = post.platforms or post.channel
        post.missed = (
            _("Yes")
            if publish_on < now and post.status not in ("Published", "Cancelled")
            else ""
        )
        post.caption = html2text(post.caption or "").strip()
        post.published_on = (
            format_datetime(post.published_on) if post.published_on else ""
        )
        rows.append([post.get(field) or "" for _l, field, _w in EXPORT_COLUMNS])

    sheet = f"Content {start} to {end}"
    xlsx = make_xlsx(rows, sheet, column_widths=[w for _l, _f, w in EXPORT_COLUMNS])
    frappe.response.filename = f"content-calendar-{start}-to-{end}.xlsx"
    frappe.response.filecontent = xlsx.getvalue()
    frappe.response.type = "binary"
