import frappe


def execute():
    """Default for the video editor's due date; a Single's field defaults only apply to new sites."""
    Singles = frappe.qb.DocType("Singles")
    saved = (
        frappe.qb.from_(Singles)
        .select(Singles.value)
        .where(Singles.doctype == "HD Content Settings")
        .where(Singles.field == "video_editor_days_before")
        .run()
    )
    # 0 is a real choice (due on the publish date), so only a value never saved is empty
    if not saved or saved[0][0] in (None, ""):
        frappe.db.set_single_value("HD Content Settings", "video_editor_days_before", 1)
