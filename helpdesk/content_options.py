"""The platforms and post types a content post can use.

They used to be fixed Select options; they are now records (HD Content Platform,
HD Content Post Type) so the team can add their own from the Add entry dialog.
"""

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Max

# the options every site starts with, in the order they are listed
DEFAULT_PLATFORMS = (
    "Instagram",
    "Facebook",
    "LinkedIn",
    "X",
    "YouTube",
    "Blog",
    "Email",
    "WhatsApp",
)
DEFAULT_POST_TYPES = (
    "Post",
    "Carousel",
    "Reel",
    "Story",
    "Video",
    "Article",
    "Newsletter",
)
PLATFORM = "HD Content Platform"
POST_TYPE = "HD Content Post Type"


class ContentOption(Document):
    """One platform or post type; NAME_FIELD is the field it is named by."""

    NAME_FIELD = ""

    def before_insert(self):
        self.clean_name()
        self.set_sort_order()

    def clean_name(self):
        self.set(self.NAME_FIELD, (self.get(self.NAME_FIELD) or "").strip())

    def set_sort_order(self):
        """A new option goes to the end of the list unless placed explicitly."""
        if self.sort_order:
            return
        table = frappe.qb.DocType(self.doctype)
        highest = frappe.qb.from_(table).select(Max(table.sort_order)).run()
        self.sort_order = (highest[0][0] or 0) + 1


def ensure_default_content_options() -> list[str]:
    """Add the default platforms and post types a site doesn't have yet; returns the ones added."""
    added = []
    for doctype, field, names in (
        (PLATFORM, "platform_name", DEFAULT_PLATFORMS),
        (POST_TYPE, "post_type_name", DEFAULT_POST_TYPES),
    ):
        for name in names:
            if frappe.db.exists(doctype, name):
                continue
            frappe.get_doc({"doctype": doctype, field: name}).insert(
                ignore_permissions=True
            )
            added.append(name)
    return added
