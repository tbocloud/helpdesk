import frappe

from helpdesk.helpdesk.doctype.hd_file_storage_settings.hd_file_storage_settings import (
    DEFAULT_DOCTYPES,
)


def execute():
    """Content calendar attachments are the first to be offered S3 storage (off until set up)."""
    settings = frappe.get_single("HD File Storage Settings")
    if settings.document_types:
        return
    for doctype in DEFAULT_DOCTYPES:
        settings.append("document_types", {"document_type": doctype})
    settings.link_expiry_seconds = settings.link_expiry_seconds or 600
    settings.delete_from_bucket = 1
    settings.flags.ignore_mandatory = True
    settings.save(ignore_permissions=True)
