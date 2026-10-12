# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""What a manager decided about one repeat issue: dismissed ("Not a repeat") or
given a root-cause task. The clusters themselves are computed
(helpdesk.repeat_issues); this record recognises a cluster again by its tickets
and tasks or its keywords. Written through helpdesk.api.repeat_issues.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document

ROOT_CAUSE = "Root-cause task"


class HDRepeatIssue(Document):
    def validate(self):
        self.validate_task()

    def validate_task(self):
        if self.status == ROOT_CAUSE and not self.task:
            frappe.throw(_("A root-cause repeat issue needs its task."))

    def apply_cluster(self, title: str, keywords: list[str], items: list[str]):
        """Takes the cluster's current title and words, and adds its tickets and
        tasks to the ones seen before, so a growing cluster is still recognised."""
        self.title = (title or "")[:140]
        self.keywords = json.dumps(sorted(set(keywords)))
        self.items = json.dumps(sorted(set(self.parse_list(self.items)) | set(items)))

    @staticmethod
    def parse_list(value) -> list[str]:
        """A stored JSON list (keywords, items); empty when it isn't one."""
        try:
            found = json.loads(value or "[]")
        except (TypeError, ValueError):
            return []
        return [str(i) for i in found] if isinstance(found, list) else []
