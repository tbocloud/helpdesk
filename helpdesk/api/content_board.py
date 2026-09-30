"""Board actions for the Content Calendar: add entries, postpone, cancel."""

import json

import frappe
from frappe import _

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
def add_entries(values: str | dict, channels: str | list) -> list[str]:
    """One post per channel, all with the same content, created together or not at all."""
    frappe.has_permission("HD Content Post", "create", throw=True)
    values = json.loads(values) if isinstance(values, str) else values
    channels = json.loads(channels) if isinstance(channels, str) else channels
    channels = list(dict.fromkeys(c for c in channels or [] if c))
    if not channels:
        frappe.throw(_("Pick at least one platform"))

    common = {k: values.get(k) for k in ENTRY_FIELDS if values.get(k) not in (None, "")}
    names = []
    for channel in channels:
        post = frappe.get_doc(
            {"doctype": "HD Content Post", **common, "channel": channel}
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
