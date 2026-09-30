"""GitHub pull requests move TBO Support tasks.

A PR names its task (TASK-2026-00012) in its title, description or branch;
"Closes TASK-..." means merging it finishes the task, any other mention only
refers to it. Each PR-task pair is an HD Pull Request row. Webhook deliveries
are verified and logged by `receive_webhook`, then processed in the background
by `process_delivery`:

- opened / reopened: the task moves Open -> Working.
- ready for review / review requested: the task goes to Pending Review and the
  project lead hears about it.
- review approved: the assignees hear about it; changes requested: the task goes
  back to Working with the reviewer's note.
- CI failing: the assignees hear about it.
- merged: a closing PR completes the task (or sends it for review when the
  project wants that), and a linked ticket hears the fix is in.
- closed without merging: the task goes On Hold for the lead to decide. Tasks
  are never cancelled automatically.

Every change is compared with the stored row first, so processing the same
event twice adds no second comment or notification.
"""

import hashlib
import hmac
import html
import json
import re
from urllib.parse import parse_qs

import frappe
import requests
from frappe import _
from frappe.utils import (
    convert_utc_to_system_timezone,
    escape_html,
    get_datetime,
    md_to_html,
    now_datetime,
    strip_html,
)

from helpdesk.work_reminders import notify_users

SETTINGS = "HD GitHub Settings"
DELIVERY = "HD GitHub Delivery"
PULL_REQUEST = "HD Pull Request"
HANDLED_EVENTS = ("pull_request", "pull_request_review", "workflow_run")
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 10

# not inside a longer word or number, so "task-2026-00012_login" in a branch still counts
TASK_REF = re.compile(r"(?<![A-Za-z0-9])TASK-\d{4}-\d{5}(?!\d)", re.IGNORECASE)
CLOSING_REF = re.compile(
    r"(?<![A-Za-z0-9])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+(TASK-\d{4}-\d{5})(?!\d)",
    re.IGNORECASE,
)
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

OPEN_STATES = ("Open", "Draft")
DONE = ("Completed", "Cancelled")
ON_HOLD = "On Hold"
PENDING_REVIEW = "Pending Review"
ADMIN_ROLES = ("System Manager", "Agent Manager")
CI_RESULTS = {
    "success": "Passing",
    "failure": "Failing",
    "timed_out": "Failing",
    "startup_failure": "Failing",
}
NOTE_LIMIT = 300


# --- receiving ---


def receive_webhook(raw: bytes, headers) -> dict:
    """Verify, deduplicate and log one delivery, then process it in the background."""
    settings = frappe.get_single(SETTINGS)
    check_signature(settings, raw, headers.get("X-Hub-Signature-256"))

    event = (headers.get("X-GitHub-Event") or "").strip()
    if event == "ping":
        return {"ok": True, "pong": True}

    delivery_id = (headers.get("X-GitHub-Delivery") or "").strip()
    if not delivery_id:
        frappe.throw(_("The X-GitHub-Delivery header is missing."))
    if frappe.db.exists(DELIVERY, delivery_id):
        return {"ok": True, "duplicate": True}

    payload = parse_payload(raw, headers.get("Content-Type"))
    repo = (payload.get("repository") or {}).get("full_name") or ""
    note = ignore_reason(settings, event, repo)
    try:
        delivery = frappe.get_doc(
            {
                "doctype": DELIVERY,
                "delivery_id": delivery_id,
                "event": event,
                "action": str(payload.get("action") or ""),
                "repo": repo,
                "status": "Ignored" if note else "Queued",
                "error": note,
                # only kept for deliveries we act on; the job reads it from here
                "payload": None if note else json.dumps(payload),
            }
        ).insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        # GitHub retried while the first attempt was still being recorded
        return {"ok": True, "duplicate": True}

    if note:
        return {"ok": True, "ignored": note}
    frappe.enqueue(
        "helpdesk.github_sync.process_delivery",
        queue="short",
        delivery=delivery.name,
        enqueue_after_commit=True,
        now=frappe.flags.in_test,
    )
    return {"ok": True, "queued": delivery.name}


def check_signature(settings, raw: bytes, signature: str | None):
    """Refuse anything not signed with our secret, and everything while the sync is off."""
    secret = (
        settings.get_password("webhook_secret", raise_exception=False)
        if settings.enabled
        else None
    )
    if not secret or not signature:
        frappe.throw(_("This webhook isn't accepted."), frappe.AuthenticationError)
    expected = (
        "sha256=" + hmac.new(secret.encode(), raw or b"", hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(expected, signature.strip()):
        frappe.throw(_("This webhook isn't accepted."), frappe.AuthenticationError)


def parse_payload(raw: bytes, content_type: str | None) -> dict:
    """GitHub sends JSON, or the same JSON in a `payload` form field."""
    text = (raw or b"").decode("utf-8")
    if "application/x-www-form-urlencoded" in (content_type or ""):
        text = (parse_qs(text).get("payload") or ["{}"])[0]
    try:
        payload = json.loads(text or "{}")
    except ValueError:
        frappe.throw(_("The webhook body isn't valid JSON."))
    if not isinstance(payload, dict):
        frappe.throw(_("The webhook body isn't a JSON object."))
    return payload


def ignore_reason(settings, event: str, repo: str) -> str | None:
    if event not in HANDLED_EVENTS:
        return _("Event {0} isn't used.").format(event or "-")
    if not settings.allows_repo(repo):
        return _("Repository {0} isn't in the allowed list.").format(repo or "-")
    return None


# --- processing ---


def process_delivery(delivery: str):
    """Background job: apply one logged delivery; a failure is recorded, never retried blindly."""
    doc = frappe.get_doc(DELIVERY, delivery)
    if doc.status != "Queued":
        return
    previous_user = frappe.session.user
    frappe.set_user("Administrator")  # the job inherits Guest from the webhook; task rules and history need a real user - nosemgrep
    frappe.db.savepoint("github_delivery")
    try:
        handled = handle_event(doc.event, frappe.parse_json(doc.payload or "{}"), doc)
        status, error = ("Processed", None) if handled else ("Ignored", None)
    except Exception:
        frappe.db.rollback(save_point="github_delivery")
        status, error = "Failed", frappe.get_traceback()
        frappe.log_error(
            title=_("GitHub delivery {0} failed").format(doc.name),
            reference_doctype=DELIVERY,
            reference_name=doc.name,
        )
    finally:
        frappe.set_user(previous_user)  # back to whoever enqueued it (Guest, or the test user) - nosemgrep
    doc.db_set({"status": status, "error": error})


def handle_event(event: str, payload: dict, delivery) -> bool:
    """Returns whether the delivery changed anything we track."""
    repo = (payload.get("repository") or {}).get("full_name") or ""
    action = payload.get("action") or ""
    if event == "workflow_run":
        return handle_workflow_run(repo, action, payload.get("workflow_run") or {})
    pr = payload.get("pull_request")
    if not pr or not repo:
        return False
    sync = PullRequestSync(repo, pr, payload.get("sender"))
    if event == "pull_request":
        return sync.on_pull_request(action, delivery)
    if event == "pull_request_review" and action == "submitted":
        return sync.on_review(payload.get("review") or {})
    return False


def handle_workflow_run(repo: str, action: str, run: dict) -> bool:
    """A finished workflow marks the PRs it ran for as passing or failing."""
    result = CI_RESULTS.get(run.get("conclusion") or "")
    if action != "completed" or not result:
        return False
    numbers = [p.get("number") for p in run.get("pull_requests") or [] if p]
    if numbers:
        filters = {"repo": repo, "number": ("in", numbers)}
    elif run.get("head_branch"):
        # runs for PRs from forks come without pull_requests; the branch still matches
        filters = {
            "repo": repo,
            "head_branch": run["head_branch"],
            "state": ("in", OPEN_STATES),
        }
    else:
        return False
    rows = frappe.qb.get_query(PULL_REQUEST, fields=["name"], filters=filters).run(
        pluck="name"
    )
    for name in rows:
        link = PullRequestLink(frappe.get_doc(PULL_REQUEST, name))
        link.record_ci(result, run.get("head_sha") or "", run.get("name") or "")
        link.save()
    return bool(rows)


class PullRequestLink:
    """One HD Pull Request row, what its state was before this event, and its task."""

    def __init__(self, row, is_new: bool = False):
        self.row = row
        self.is_new = is_new
        self.before_state = None if is_new else row.state
        self._task = None

    @property
    def task(self):
        if self._task is None:
            self._task = frappe.get_doc("Task", self.row.task)
        return self._task

    @property
    def label(self) -> str:
        return _("PR #{0}").format(self.row.number)

    def save(self):
        self.row.last_event_at = now_datetime()
        self.row.save(ignore_permissions=True)

    # --- task history and people ---

    def comment(self, text: str):
        """Info comment on the task, with the PR label linking to GitHub."""
        label = escape_html(self.label)
        url = self.row.url or ""
        if url.startswith("https://github.com/"):
            label = f'<a href="{escape_html(url)}">{label}</a>'
        self.task.add_comment("Info", f"{label} {escape_html(text)}")

    def notify_assignees(self, subject: str):
        notify_users(self.task.assignees(), "Task", self.task.name, subject)

    def notify_leads(self, subject: str):
        notify_users(self.task.leads_or_managers(), "Task", self.task.name, subject)

    def move_task(self, status: str, **values) -> bool:
        """Through the Task controller, so dependency, hold and review rules apply.

        A rule that refuses the move (e.g. an unfinished dependency) is noted on
        the task instead of failing the whole delivery.
        """
        task = self.task
        frappe.db.savepoint("github_task_move")
        try:
            task.status = status
            task.update(values)
            task.save(ignore_permissions=True)
            return True
        except frappe.ValidationError as e:
            frappe.db.rollback(save_point="github_task_move")
            frappe.clear_last_message()
            task.reload()
            self.comment(
                _("couldn't move the task to {0}: {1}").format(
                    _(status), strip_html(str(e))
                )
            )
            return False

    def stop_timer(self):
        """A running timer is folded into the actual hours before the task leaves Working."""
        task = self.task
        start = task.get("custom_timer_start")
        if not start:
            return
        hours = round(
            (now_datetime() - get_datetime(start)).total_seconds() / 3600, 2
        )
        task.custom_actual_hours = (task.get("custom_actual_hours") or 0) + hours
        task.custom_timer_elapsed = (task.get("custom_timer_elapsed") or 0) + hours
        task.custom_timer_start = None

    # --- events ---

    def record_ci(self, result: str, sha: str, workflow: str):
        row = self.row
        before = row.ci_state
        # another workflow already failed on this commit; one passing doesn't fix it
        if result == "Passing" and before == "Failing" and sha == row.ci_head_sha:
            return
        row.ci_state = result
        row.ci_head_sha = sha
        if result == "Failing" and before != "Failing":
            self.comment(_("CI failing ({0}).").format(workflow or "CI"))
            self.notify_assignees(
                _("CI failing on {0}: {1}").format(self.label, row.title)
            )
        elif result == "Passing" and before == "Failing":
            self.comment(_("CI passing again."))


class PullRequestSync:
    """One pull request from a webhook payload and the tasks it's linked to."""

    def __init__(self, repo: str, pr: dict, sender: dict | None = None):
        self.repo = repo
        self.pr = pr
        self.number = int(pr.get("number") or 0)
        self.login = (sender or {}).get("login") or (pr.get("user") or {}).get(
            "login"
        )
        self.settings = frappe.get_single(SETTINGS)

    @property
    def state(self) -> str:
        if self.pr.get("merged") or self.pr.get("merged_at"):
            return "Merged"
        if self.pr.get("state") == "closed":
            return "Closed"
        return "Draft" if self.pr.get("draft") else "Open"

    @property
    def title(self) -> str:
        return (self.pr.get("title") or "").strip()

    # --- linking ---

    def task_refs(self) -> dict[str, str]:
        """Task name -> "Closes" or "Refs"; only tasks that exist."""
        text = f"{self.pr.get('title') or ''}\n{self.pr.get('body') or ''}"
        branch = (self.pr.get("head") or {}).get("ref") or ""
        refs = {
            m.upper(): "Refs" for m in TASK_REF.findall(f"{text}\n{branch}")
        }
        for m in CLOSING_REF.findall(text):
            refs[m.upper()] = "Closes"
        if not refs:
            return {}
        existing = set(
            frappe.qb.get_query(
                "Task", fields=["name"], filters={"name": ("in", list(refs))}
            ).run(pluck="name")
        )
        return {task: kind for task, kind in refs.items() if task in existing}

    def link_rows(self, extra: dict[str, str] | None = None) -> list[PullRequestLink]:
        """Rows for every task the PR names, plus tasks it was linked to earlier.

        Earlier links stay even if the description changes, so a task created for
        an unlinked PR keeps following it. Rows are updated in memory; the
        caller saves each one once.
        """
        refs = {**self.task_refs(), **(extra or {})}
        names = frappe.qb.get_query(
            PULL_REQUEST,
            fields=["name"],
            filters={"repo": self.repo, "number": self.number},
        ).run(pluck="name")
        links = []
        for name in names:
            row = frappe.get_doc(PULL_REQUEST, name)
            links.append(PullRequestLink(row))
            if row.task in refs:
                row.link_kind = refs.pop(row.task)
        for task, kind in refs.items():
            row = frappe.new_doc(PULL_REQUEST)
            row.update({"repo": self.repo, "number": self.number, "task": task})
            row.link_kind = kind
            links.append(PullRequestLink(row, is_new=True))
        for link in links:
            self.refresh_row(link.row)
        return links

    def refresh_row(self, row):
        row.update(
            {
                "title": self.title[:255],
                "url": self.pr.get("html_url"),
                "author": (self.pr.get("user") or {}).get("login"),
                "head_branch": (self.pr.get("head") or {}).get("ref"),
                "state": self.state,
            }
        )
        if self.pr.get("merged_at"):
            row.merged_at = github_time(self.pr["merged_at"])
        if self.pr.get("closed_at"):
            row.closed_at = github_time(self.pr["closed_at"])

    # --- pull_request ---

    def on_pull_request(self, action: str, delivery) -> bool:
        links = self.link_rows()
        if not links:
            if action != "opened":
                return False
            links = self.handle_unlinked(delivery)
            if not links:
                return True
        for link in links:
            self.apply_pull_request(action, link)
            link.save()
        return True

    def apply_pull_request(self, action: str, link: PullRequestLink):
        if link.is_new or (
            link.before_state not in OPEN_STATES and self.state in OPEN_STATES
        ):
            self.on_linked(action, link)
        elif action == "converted_to_draft" and link.before_state == "Open":
            link.comment(_("moved back to draft by @{0}.").format(self.login))

        if action in ("ready_for_review", "review_requested"):
            self.on_review_requested(link)
        elif action == "closed" and link.before_state != self.state:
            if self.state == "Merged":
                self.on_merged(link)
            else:
                self.on_closed_unmerged(link)

    def on_linked(self, action: str, link: PullRequestLink):
        """First time we see the PR for this task, or it was reopened."""
        if action == "reopened" and not link.is_new:
            link.comment(_("reopened by @{0}.").format(self.login))
            self.resume_our_hold(link)
        elif action == "opened" and self.state == "Draft":
            link.comment(
                _("opened as a draft by @{0}: {1}").format(self.login, self.title)
            )
        elif action == "opened":
            link.comment(_("opened by @{0}: {1}").format(self.login, self.title))
        else:
            link.comment(_("linked by @{0}: {1}").format(self.login, self.title))

        if self.state == "Open" and link.task.status == "Open":
            link.move_task("Working")

    def resume_our_hold(self, link: PullRequestLink):
        """Undo the hold we put on the task when this PR was closed."""
        task = link.task
        if task.status == ON_HOLD and (task.hold_note or "").startswith(
            self.hold_prefix(link)
        ):
            link.move_task(task.hold_previous_status or "Open")

    def on_review_requested(self, link: PullRequestLink):
        row = link.row
        if row.review_state == "Review requested" or self.state != "Open":
            return
        row.review_state = "Review requested"
        link.comment(_("ready for review."))
        task = link.task
        review_flagged = False
        if task.status in ("Open", "Working"):
            link.stop_timer()
            link.move_task(PENDING_REVIEW)
            # the Task controller already told the lead on review-before-done projects
            review_flagged = bool(task.flags.review_requested)
        if not review_flagged:
            link.notify_leads(
                _("{0} ready for review: {1}").format(link.label, task.subject)
            )

    def on_merged(self, link: PullRequestLink):
        task = link.task
        merged_by = (self.pr.get("merged_by") or {}).get("login") or self.login
        link.comment(_("merged by @{0}.").format(merged_by))
        if link.row.link_kind != "Closes":
            return
        self.tell_ticket(link)
        if not self.settings.complete_on_merge or task.status in DONE:
            return
        needs_review = bool(
            task.project
            and frappe.db.get_value("Project", task.project, "review_before_done")
        )
        # the lead still signs off on review projects; approve_task completes it later
        target = PENDING_REVIEW if needs_review else "Completed"
        if task.status == target:
            return
        link.stop_timer()
        moved = link.move_task(target)
        # the Task controller already told the lead unless the task came off a hold
        if moved and target == PENDING_REVIEW and not task.flags.review_requested:
            link.notify_leads(
                    _("{0} merged, ready for review: {1}").format(
                        link.label, task.subject
                    )
                )

    def tell_ticket(self, link: PullRequestLink):
        """The agent on the linked ticket can tell the customer the fix is in."""
        ticket = link.task.get("hd_ticket")
        if not ticket or not frappe.db.exists("HD Ticket", ticket):
            return
        frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": ticket,
                "content": _("Fix merged in {0} ({1}) for task {2}: {3}").format(
                    f'<a href="{escape_html(link.row.url or "")}">{escape_html(link.label)}</a>',
                    escape_html(self.repo),
                    frappe.bold(link.task.name),
                    escape_html(self.title),
                ),
                "commented_by": frappe.session.user,
            }
        ).insert(ignore_permissions=True)

    def on_closed_unmerged(self, link: PullRequestLink):
        """Never cancel: pause the task and let the lead decide."""
        task = link.task
        reason = self.closing_reason(link)
        note = f"{self.hold_prefix(link)}: {reason}"
        other_open = frappe.qb.get_query(
            PULL_REQUEST,
            fields=["name"],
            filters={
                "task": task.name,
                "state": ("in", OPEN_STATES),
                "name": ("!=", link.row.name or ""),
            },
            limit=1,
        ).run(pluck="name")
        if task.status in DONE or task.status == ON_HOLD or other_open:
            link.comment(_("closed without merging: {0}").format(reason))
            return
        link.move_task(ON_HOLD, hold_reason="Other", hold_note=note)

    def hold_prefix(self, link: PullRequestLink) -> str:
        return _("{0} closed without merging").format(link.label)

    def closing_reason(self, link: PullRequestLink) -> str:
        """The last comment on the PR if we may read it, else the last review note, else the title."""
        return (
            self.last_pr_comment()
            or link.row.last_review_note
            or self.title
            or link.label
        )

    # --- unlinked PRs ---

    def handle_unlinked(self, delivery) -> list[PullRequestLink]:
        """A PR with no task number gets a task (if configured) or reaches the admins."""
        self.ask_for_task_number()
        project = self.settings.unlinked_pr_project
        if project and frappe.db.exists("Project", project):
            return self.link_rows({self.create_unlinked_task(project): "Closes"})
        notify_users(
            admin_users(),
            DELIVERY,
            delivery.name,
            _("PR #{0} in {1} names no task: {2}").format(
                self.number, self.repo, self.title
            ),
        )
        return []

    def create_unlinked_task(self, project: str) -> str:
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": _("Unlinked PR #{0}: {1}").format(self.number, self.title)[
                    :140
                ],
                "project": project,
                "status": "Open",
                "is_key": 0,
                "description": _("Created for {0} by @{1}: {2}").format(
                    escape_html(f"{self.repo}#{self.number}"),
                    escape_html(self.login or ""),
                    escape_html(self.pr.get("html_url") or ""),
                ),
            }
        ).insert(ignore_permissions=True)
        return task.name

    # --- pull_request_review ---

    def on_review(self, review: dict) -> bool:
        verdict = (review.get("state") or "").lower()
        if verdict not in ("approved", "changes_requested"):
            return False
        links = self.link_rows()
        reviewer = (review.get("user") or {}).get("login") or self.login
        note = plain_text(review.get("body"))
        for link in links:
            if verdict == "approved":
                self.on_approved(link, reviewer)
            else:
                self.on_changes_requested(link, reviewer, note)
            link.save()
        return bool(links)

    def on_approved(self, link: PullRequestLink, reviewer: str):
        if link.row.review_state == "Approved":
            return
        link.row.review_state = "Approved"
        link.comment(_("approved by @{0}.").format(reviewer))
        link.notify_assignees(
            _("{0} approved by @{1}: {2}").format(
                link.label, reviewer, link.task.subject
            )
        )

    def on_changes_requested(self, link: PullRequestLink, reviewer: str, note: str):
        if link.row.review_state == "Changes requested":
            return
        link.row.review_state = "Changes requested"
        if note:
            link.row.last_review_note = note
        text = _("changes requested by @{0}").format(reviewer)
        link.comment(f"{text}: {note}" if note else f"{text}.")
        task = link.task
        if task.status in ("Open", PENDING_REVIEW):
            link.move_task("Working")
        subject = _("Changes requested on {0}: {1}").format(link.label, task.subject)
        link.notify_assignees(f"{subject} - {note}" if note else subject)

    # --- GitHub API (optional; needs the token) ---

    def github_request(self, method: str, path: str, **kwargs):
        token = self.settings.get_password("github_token", raise_exception=False)
        if not token or not REPO_NAME.match(self.repo):
            return None
        try:
            response = requests.request(
                method,
                f"{GITHUB_API}/repos/{self.repo}/{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            # a GitHub hiccup must not stop the task update
            frappe.log_error(
                title=_("GitHub API call failed: {0} {1}").format(method, path)
            )
            return None

    def ask_for_task_number(self):
        self.github_request(
            "POST",
            f"issues/{self.number}/comments",
            json={
                "body": _(
                    "This pull request doesn't name a TBO Support task. Add it to the title, "
                    "description or branch, e.g. `Closes TASK-2026-00012`, so the task follows "
                    "this PR. If there's no task for it, add the `no-task` label."
                )
            },
        )

    def last_pr_comment(self) -> str:
        """The newest conversation comment: with one per page, page N is the last of N."""
        count = int(self.pr.get("comments") or 0)
        if not count:
            return ""
        comments = self.github_request(
            "GET",
            f"issues/{self.number}/comments",
            params={"per_page": 1, "page": count},
        )
        if not comments or not isinstance(comments, list):
            return ""
        return plain_text(comments[-1].get("body"))


# --- helpers ---


def github_time(value: str):
    """GitHub sends UTC ("2026-09-30T10:00:00Z"); Datetime fields hold system time."""
    return convert_utc_to_system_timezone(get_datetime(value)).replace(tzinfo=None)


def plain_text(value: str | None, limit: int = NOTE_LIMIT) -> str:
    """Review bodies are Markdown; notifications and hold notes want one short plain line."""
    if not value:
        return ""
    text = " ".join(html.unescape(strip_html(md_to_html(value) or "")).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def admin_users() -> list[str]:
    """Enabled System and Agent Managers, who hear about PRs no task claims."""
    user = frappe.qb.DocType("User")
    has_role = frappe.qb.DocType("Has Role")
    return (
        frappe.qb.from_(has_role)
        .join(user)
        .on(user.name == has_role.parent)
        .select(user.name)
        .distinct()
        .where(
            (has_role.parenttype == "User")
            & (has_role.role.isin(ADMIN_ROLES))
            & (user.enabled == 1)
            & (user.user_type == "System User")
        )
        .run(pluck="name")
    )


def get_pull_requests(tasks: list[str], open_only: bool = False) -> dict[str, list]:
    """PRs per task in one query, newest activity first (for task detail and kanban)."""
    if not tasks:
        return {}
    filters = {"task": ("in", tasks)}
    if open_only:
        filters["state"] = ("in", OPEN_STATES)
    rows = frappe.qb.get_query(
        PULL_REQUEST,
        fields=[
            "task",
            "repo",
            "number",
            "title",
            "url",
            "state",
            "review_state",
            "ci_state",
            "link_kind",
            "last_event_at",
        ],
        filters=filters,
        order_by="last_event_at desc",
    ).run(as_dict=True)
    by_task: dict[str, list] = {}
    for row in rows:
        by_task.setdefault(row.pop("task"), []).append(row)
    return by_task
