"""Board actions for the Content Calendar: add entries, postpone, cancel."""

import json

import frappe
from frappe import _
from frappe.utils import date_diff

from helpdesk.helpdesk.doctype.hd_content_occasion.hd_content_occasion import (
    occasions_between,
)

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
    "task_mode",
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
    if not values.get("publish_on"):
        frappe.throw(_("Pick the posting date and time"))

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


@frappe.whitelist()
def get_occasions(start: str, end: str, customer: str | None = None) -> list[dict]:
    """Occasions between two dates; for one customer, only its package's regions."""
    frappe.has_permission("HD Content Post", "read", throw=True)
    if date_diff(end, start) > 400:
        frappe.throw(_("Pick a range of at most a year."))
    regions = None
    if customer and frappe.db.exists("HD Content Package", customer):
        regions = frappe.get_cached_doc(
            "HD Content Package", customer
        ).occasion_regions()
    return [
        {
            "date": str(o.date),
            "occasion": o.occasion_name,
            "region": o.region,
            "idea": o.idea,
        }
        for o in occasions_between(start, end, regions)
    ]


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
