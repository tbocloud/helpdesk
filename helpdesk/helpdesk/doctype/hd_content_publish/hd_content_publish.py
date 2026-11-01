# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document

QUEUED = "Queued"
PUBLISHING = "Publishing"
PUBLISHED = "Published"
FAILED = "Failed"


class HDContentPublish(Document):
    pass
