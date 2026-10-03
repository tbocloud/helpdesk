# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

# "owner/repo" or "owner/*", with GitHub's allowed name characters
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/(\*|[A-Za-z0-9_.-]+)$")


class HDGitHubSettings(Document):
    def validate(self):
        self.normalize_allowed_repos()

    def normalize_allowed_repos(self):
        """One pattern per line, blanks dropped, so matching never sees stray spaces."""
        lines = [line.strip() for line in (self.allowed_repos or "").splitlines()]
        patterns = [line for line in lines if line]
        invalid = [p for p in patterns if not REPO_PATTERN.match(p)]
        if invalid:
            frappe.throw(
                _("Use owner/repo or owner/* for each repository: {0}").format(
                    ", ".join(invalid)
                )
            )
        self.allowed_repos = "\n".join(patterns)

    def allows_repo(self, repo: str | None) -> bool:
        """GitHub treats owner and repository names case-insensitively, so do we."""
        if not repo or "/" not in repo:
            return False
        owner = repo.split("/", 1)[0].lower()
        for pattern in (self.allowed_repos or "").splitlines():
            pattern = pattern.strip().lower()
            if pattern == repo.lower() or pattern == f"{owner}/*":
                return True
        return False
