# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from helpdesk.github_sync import REPO_NAME

# "owner/repo" or "owner/*", with GitHub's allowed name characters
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/(\*|[A-Za-z0-9_.-]+)$")
MERGE_BOT_WORKFLOW = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")
# Singles' JSON defaults only reach new sites, so an existing hub gets them on save
MERGE_BOT_DEFAULTS = {
    "merge_bot_repo": "tbocloud/ai-review",
    "merge_bot_workflow": "merge-bot.yml",
}


class HDGitHubSettings(Document):
    def validate(self):
        self.require_webhook_secret()
        self.normalize_allowed_repos()
        self.validate_merge_bot()

    def require_webhook_secret(self):
        """The webhook refuses everything without it; the form's mandatory_depends_on
        isn't checked on the server."""
        if self.enabled and not self.webhook_secret:
            frappe.throw(_("Webhook Secret: add it before turning the sync on."))

    def normalize_allowed_repos(self):
        """One pattern per line, blanks dropped, so matching never sees stray spaces."""
        lines = [line.strip() for line in (self.allowed_repos or "").splitlines()]
        patterns = [line for line in lines if line]
        invalid = [p for p in patterns if not REPO_PATTERN.match(p)]
        if invalid:
            frappe.throw(
                _("Allowed Repositories: use owner/repo or owner/* on each line, not {0}").format(
                    ", ".join(invalid)
                )
            )
        self.allowed_repos = "\n".join(patterns)

    def validate_merge_bot(self):
        """Both values go into the dispatch URL, so nothing that could change its path."""
        for field, default in MERGE_BOT_DEFAULTS.items():
            self.set(field, (self.get(field) or "").strip() or default)
        if not REPO_NAME.match(self.merge_bot_repo) or ".." in self.merge_bot_repo:
            frappe.throw(_("Merge bot repository: use owner/repo, e.g. tbocloud/ai-review."))
        if not MERGE_BOT_WORKFLOW.match(self.merge_bot_workflow):
            frappe.throw(
                _(
                    "Merge bot workflow: use the workflow's file name, e.g. merge-bot.yml."
                )
            )

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
