"""Join the Malayalam vowel signs that a copy from a PDF split off their letters.

Content posts and tasks saved before `mend_pasted_malayalam` keep text like "പ ോയി" for
"പോയി" (a post's tasks carry its copy in their subject and description). This mends the
same fields the same way, written straight to the table so no save hook runs and
`modified` stays. A second run finds nothing to change.

It replaces `join_pasted_malayalam`, which a test site ran before it covered tasks and
the split plural ending; the new name runs it there again.
"""

import frappe

from helpdesk.helpdesk.doctype.hd_content_post.hd_content_post import (
    PASTED_TEXT_FIELDS as POST_FIELDS,
)
from helpdesk.helpdesk.doctype.task.task import PASTED_TEXT_FIELDS as TASK_FIELDS
from helpdesk.utils import join_malayalam_signs


def execute():
    for doctype, fields in (("HD Content Post", POST_FIELDS), ("Task", TASK_FIELDS)):
        for row in frappe.get_all(
            doctype, fields=["name", *fields], limit_page_length=0
        ):
            mended = {f: join_malayalam_signs(row[f]) for f in fields if row[f]}
            changed = {f: text for f, text in mended.items() if text != row[f]}
            if changed:
                frappe.db.set_value(doctype, row.name, changed, update_modified=False)
