# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""A Copilot fix, from its task to the merge.

At Preparing Fix the run gets a fix task; a developer (later the worker) opens
a pull request that says `Closes TASK-…`. The GitHub sync links it to the task
and calls `on_pull_request`; from then on the run follows the pull request:
held with a label so no bot merges it, one approval per head commit, merged by
the hub with the approved commit pinned, then Mark deployed once an engineer
has deployed it. `refresh` reads GitHub directly, for a webhook that never came.
"""

import contextlib
import json
import re

import frappe
from frappe import _
from frappe.utils import escape_html, formatdate, now_datetime

from helpdesk.copilot import approvals, github, risk, runs
from helpdesk.copilot import settings as copilot_settings
from helpdesk.copilot.github import GitHubError

FIX_STATES = ("Preparing Fix", "Awaiting Approval", "Approved")
FOLLOWED = FIX_STATES + ("Merged",)
FIX_TASK_PREFIX = "Copilot fix: "
REVERT_TASK_PREFIX = "Copilot revert: "
DEFAULT_COMMIT_EMAIL = "copilot@teambackoffice.com"
EVIDENCE_RESULTS = ("pass", "fail", "not_run")
DEFAULT_HOLD_LABEL = "no-auto-merge"


class NoProject(frappe.ValidationError):
    """The customer has no open project and no hand-over project is set: nowhere to put the fix task."""


def hold_label() -> str:
    return (
        copilot_settings.get_settings().get("hold_label") or DEFAULT_HOLD_LABEL
    ).strip()


def run_for_task(task: str):
    """The run whose fix task this is, while the fix is still in flight."""
    name = frappe.db.get_value(
        "HDS Copilot Run",
        {"task": task, "state": ["in", FOLLOWED]},
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc("HDS Copilot Run", name) if name else None


def is_fix_task(task: str) -> bool:
    return bool(run_for_task(task))


def sync_on() -> bool:
    """Copilot follows pull requests through the GitHub sync; switched off, neither acts on GitHub."""
    return bool(
        frappe.db.get_single_value("HD GitHub Settings", "enabled", cache=False)
    )


# --- the fix task -----------------------------------------------------------------


def create_fix_task(
    run, actor: str = runs.SYSTEM, prefix: str = FIX_TASK_PREFIX
) -> str:
    """A Task for the fix in the customer's project, for the customer's developer; returns its name."""
    from helpdesk.api.work import create_task_from_ticket
    from helpdesk.copilot import customer
    from helpdesk.tasky.api import _is_project_member

    if run.state != "Preparing Fix":
        frappe.throw(
            _(
                "A fix task is made when Copilot is preparing a fix (the run is {0})."
            ).format(run.state)
        )
    if run.task and frappe.db.get_value("Task", run.task, "status") not in (
        "Completed",
        "Cancelled",
    ):
        return run.task
    ticket = frappe.get_doc("HD Ticket", run.ticket)
    project = customer.project_for(ticket.customer)
    if not project:
        frappe.throw(
            _(
                "Give the customer an open project, or set the hand-over project in HDS Copilot Settings."
            ),
            NoProject,
        )
    developer = (
        frappe.db.get_value("HD Customer", ticket.customer, "custom_assigned_developer")
        if ticket.customer
        else None
    )
    assignee = developer if developer and _is_project_member(project, developer) else ""
    with customer.as_automation_user():
        result = create_task_from_ticket(
            ticket.name,
            project,
            task_name=(prefix + (ticket.subject or ticket.name))[:140],
            description=_task_description(run),
            assigned_to=assignee,
            pause_ticket=False,
        )
    task = result.get("task")
    task = task.get("name") if isinstance(task, dict) else task
    how = "<p><b>{0}</b> {1}</p>".format(
        escape_html(_("To fix it:")),
        escape_html(
            _(
                "open a pull request whose description says Closes {0}. TBO Support holds it with the {1} label until one person approves it on the ticket; the hub then merges it."
            ).format(task, hold_label())
        ),
    )
    frappe.db.set_value(
        "Task",
        task,
        "description",
        (frappe.db.get_value("Task", task, "description") or "") + how,
    )
    run.db_set("task", task, update_modified=False)
    runs.add_event(
        run,
        "fix_task",
        {"task": task, "project": project, "assigned_to": assignee},
        actor,
    )
    customer.comment(
        run.ticket, _("Copilot fix task {0} created in {1}.").format(task, project)
    )
    if assignee:
        from helpdesk.work_reminders import notify_users

        notify_users(
            [assignee],
            "Task",
            task,
            _("Copilot asks you to fix ticket {0}").format(ticket.name),
            once=False,
        )
    return task


def _plain(value) -> str:
    """A diagnosis value as words: lists joined with commas, not Python's brackets."""
    if isinstance(value, list | tuple):
        return ", ".join(_plain(v) for v in value if v)
    if isinstance(value, dict):
        return "; ".join(_plain(v) for v in value.values() if v)
    return str(value)


def _task_description(run) -> str:
    evidence = frappe.parse_json(run.evidence or "[]") or []
    proposal = frappe.parse_json(run.proposal or "{}") or {}
    items = "".join(
        "<li>{0}</li>".format(
            escape_html(" ".join(_plain(v) for v in item.values() if v))
        )
        for item in evidence[:20]
        if isinstance(item, dict)
    )
    parts = [
        "<p><b>{0}</b> ({1}, {2}%): {3}</p>".format(
            escape_html(_("Copilot's diagnosis")),
            escape_html(run.root_cause_category or ""),
            int(round((run.confidence or 0) * 100)),
            escape_html(run.summary or ""),
        )
    ]
    if items:
        parts.append(f"<ul>{items}</ul>")
    if proposal:
        parts.append(
            "<p><b>{0}</b> {1}</p>".format(
                escape_html(_("Proposal:")),
                escape_html(" ".join(_plain(v) for v in proposal.values() if v)),
            )
        )
    return "".join(parts)


# --- Copilot's own fix (Phase 1c-2) ---------------------------------------------------------


def commit_email() -> str:
    return (
        copilot_settings.get_settings().get("copilot_commit_email")
        or DEFAULT_COMMIT_EMAIL
    ).strip()


def copilot_branch(run) -> str:
    """The branch Copilot pushes a fix to: its own, never one a person or a site uses."""
    number = int(run.name.rsplit("-", 1)[-1])
    return f"copilot/{run.task}-r{number}-a{run.fix_attempts or 1}"


def site_repositories(run) -> list[str]:
    """`owner/name` of every app repository on the run's site card."""
    if not run.registry:
        return []
    return [
        name
        for name in (
            _repo_name(repository)
            for repository in frappe.get_all(
                "HDS Site App",
                filters={"parent": run.registry, "parenttype": "HDS Site Registry"},
                pluck="repository",
            )
        )
        if "/" in name
    ]


def fix_context(run) -> dict:
    """What the worker needs beyond the run's context to write the fix."""
    settings = copilot_settings.get_settings()
    return {
        "task": run.task,
        "closes": f"Closes {run.task}",
        "branch": copilot_branch(run),
        "attempt": run.fix_attempts or 1,
        "max_usd": settings.get("max_fix_usd") or 0,
        "commit_email": commit_email(),
        "repositories": site_repositories(run),
    }


def open_pull_request(run) -> bool:
    return bool(
        run.pull_request
        and frappe.db.get_value("HD Pull Request", run.pull_request, "state")
        in ("Open", "Draft")
    )


def request_copilot_fix(run, user: str | None = None):
    """Queues a fix job: a worker reproduces the bug on a sandbox copy, fixes it and opens the pull request."""
    from helpdesk.copilot import customer

    run = frappe.get_doc("HDS Copilot Run", run.name)
    if run.state != "Preparing Fix":
        frappe.throw(
            _("Copilot fixes a run that is preparing a fix (this one is {0}).").format(
                run.state
            )
        )
    if run.fix_status in ("Queued", "Working"):
        return run
    if open_pull_request(run):
        frappe.throw(
            _("A pull request is already open for this fix; review that one instead.")
        )
    limit = copilot_settings.get_settings().get("max_fix_attempts") or 2
    if (run.fix_attempts or 0) >= limit:
        frappe.throw(
            _("Copilot has tried {0} times; a developer takes it from here.").format(
                limit
            )
        )
    actor = runs.AGENT if user else runs.SYSTEM
    if not run.task or frappe.db.get_value("Task", run.task, "status") in (
        "Completed",
        "Cancelled",
    ):
        create_fix_task(run, actor)
    run = frappe.get_doc("HDS Copilot Run", run.name)
    run.db_set(
        {"fix_requested": 1, "fix_status": "Queued", "fix_requested_by": user},
        update_modified=False,
    )
    runs.add_event(run, "fix_requested", {"by": user or "settings"}, actor)
    customer.comment(
        run.ticket,
        escape_html(
            _(
                "Copilot will try to fix this on a sandbox copy of the site, then open the pull request for the one approval."
            )
        ),
    )
    runs.publish_run(run)
    return run


def _evidence_row(row: dict) -> dict:
    result = str(row.get("result") or "").strip().lower()
    return {
        "check": str(row.get("check") or "")[:140],
        "result": result if result in EVIDENCE_RESULTS else "not_run",
        "detail": str(row.get("detail") or "")[:500],
    }


def on_change(run, change: dict):
    """The worker opened its pull request: keep what it tested, end the lease, follow the pull request at once."""
    from helpdesk.copilot import customer

    repository = _repo_name(change.get("repository"))
    number = int(change.get("number") or 0)
    head = str(change.get("head_sha") or "").strip()
    if not (repository and number and head):
        frappe.throw(
            _(
                "A change needs the repository, the pull request number and its head commit."
            )
        )
    if repository not in site_repositories(run):
        frappe.throw(
            _("{0} is not one of this site's repositories.").format(repository),
            frappe.PermissionError,
        )
    kept = {
        "repository": repository,
        "number": number,
        "head_sha": head,
        "branch": str(change.get("branch") or "")[:255],
        "summary": str(change.get("summary") or "")[:4000],
        "evidence": [
            _evidence_row(row)
            for row in (change.get("evidence") or [])[:30]
            if isinstance(row, dict)
        ],
        "tested_on": str(change.get("tested_on") or "")[:200],
        "people_checks": [
            str(item)[:300] for item in (change.get("people_checks") or [])[:10]
        ],
        "risk_notes": str(change.get("risk_notes") or "")[:2000],
        "cost": change.get("cost") if isinstance(change.get("cost"), dict) else {},
    }
    run.db_set(
        {
            "change": json.dumps(kept, indent=1),
            "fix_status": "Opened",
            "lease_token_hash": None,
            "lease_expires": None,
        },
        update_modified=False,
    )
    runs.add_event(
        run,
        "change_submitted",
        {
            "repository": repository,
            "number": number,
            "head_sha": head,
            "checks": [[row["check"], row["result"]] for row in kept["evidence"]],
        },
        runs.WORKER,
    )
    customer.comment(
        run.ticket,
        '{0} <a href="https://github.com/{1}/pull/{2}">{1}#{2}</a>'.format(
            escape_html(_("Copilot opened its fix:")), escape_html(repository), number
        ),
    )
    if sync_on():
        with contextlib.suppress(
            GitHubError
        ):  # else the webhook or the refresh follows it
            replay(repository, github.get_pull(repository, number))
    return frappe.get_doc("HDS Copilot Run", run.name)


def push_key(run, repository: str) -> dict:
    """The worker's one-hour key to push its branch to one of the site's repositories."""
    from helpdesk.copilot import github_app

    repository = _repo_name(repository)
    if repository not in site_repositories(run):
        frappe.throw(
            _("{0} is not one of this site's repositories.").format(repository),
            frappe.PermissionError,
        )
    key = github_app.push_token(repository)
    runs.add_event(
        run,
        "push_key",
        {"repository": repository, "expires_at": key.get("expires_at")},
        runs.SYSTEM,
    )
    return {"repository": repository, **key}


def fix_failed(run, reason: str, actor: str = runs.WORKER):
    """Copilot could not fix it: the developer takes over, with what Copilot tried."""
    from helpdesk.copilot import customer
    from helpdesk.work_reminders import notify_users

    reason = (reason or "").strip()[:1000] or _("no reason given")
    run.db_set(
        {
            "fix_status": "Failed",
            "fix_requested": 0,
            "lease_token_hash": None,
            "lease_expires": None,
        },
        update_modified=False,
    )
    runs.add_event(run, "fix_failed", {"reason": reason}, actor)
    text = _("Copilot could not fix it: {0}").format(reason)
    if run.task:
        frappe.get_doc("Task", run.task).add_comment("Comment", escape_html(text))
        notify_users(
            sorted(approvals.authors(run)),
            "Task",
            run.task,
            _("Copilot could not fix ticket {0}; over to you").format(run.ticket),
            once=False,
        )
    customer.comment(run.ticket, escape_html(text))
    runs.publish_run(run)


def fix_lease_lost(run):
    """The worker stopped reporting mid-fix: queued again while attempts are left, else handed over."""
    limit = copilot_settings.get_settings().get("max_fix_attempts") or 2
    if (run.fix_attempts or 0) < limit:
        run.db_set(
            {
                "fix_status": "Queued",
                "lease_token_hash": None,
                "lease_expires": None,
                "worker_id": None,
            },
            update_modified=False,
        )
        runs.add_event(
            run, "fix_lease_expired", {"attempt": run.fix_attempts}, runs.SYSTEM
        )
        return
    fix_failed(
        run,
        _("the worker stopped reporting ({0} attempts)").format(run.fix_attempts),
        runs.SYSTEM,
    )


def _change_for(run, pull: dict) -> dict | None:
    """What Copilot reported testing, when this pull request is the one it opened."""
    change = frappe.parse_json(run.get("change") or "{}") or {}
    if (
        change
        and change.get("repository") == (pull.get("repo") or "").lower()
        and int(change.get("number") or 0) == int(pull.get("number") or 0)
    ):
        return change
    return None


# --- following the pull request -----------------------------------------------------------


def pull_info(pr: dict, repo: str = "") -> dict:
    """The parts of a GitHub pull request (webhook or API) a fix follows."""
    if pr.get("merged") or pr.get("merged_at"):
        state = "Merged"
    elif pr.get("state") == "closed":
        state = "Closed"
    else:
        state = "Draft" if pr.get("draft") else "Open"
    base = pr.get("base") or {}
    return {
        "repo": repo or ((base.get("repo") or {}).get("full_name") or ""),
        "number": int(pr.get("number") or 0),
        "head_sha": (pr.get("head") or {}).get("sha") or "",
        "base_branch": base.get("ref") or "",
        "title": pr.get("title") or "",
        "url": pr.get("html_url") or "",
        "author": (pr.get("user") or {}).get("login") or "",
        "state": state,
        "labels": [label.get("name") for label in pr.get("labels") or [] if label],
        "merge_commit_sha": pr.get("merge_commit_sha") or "",
        "mergeable_state": pr.get("mergeable_state") or "",
    }


def on_pull_request(pr: dict, action: str, rows: list):
    """Called by the GitHub sync after a pull-request delivery, with the HD Pull Request rows it linked."""
    for row in rows:
        if row.link_kind != "Closes" or not row.name:
            continue
        run = run_for_task(row.task)
        if run:
            follow(run, row.name, pull_info(pr, row.repo))


def on_checks(repo: str, head_sha: str, rows: list):
    """Called by the GitHub sync when a workflow finished: the card shows the new
    checks, and an approved fix may now merge."""
    for row in rows:
        if row.link_kind != "Closes":
            continue
        run = run_for_task(row.task)
        if not run:
            continue
        approval = approvals.current(run)
        if approval and approval.head_sha == head_sha and approval.status == "Pending":
            record_checks(approval)
        if run.state == "Approved":
            try_merge(run)


def record_checks(approval, result: dict | None = None) -> dict | None:
    """Keeps the checks on the approval current, so the card says what GitHub says now."""
    if result is None:
        try:
            result = github.checks(approval.repo, approval.head_sha)
        except GitHubError:
            return None
    payload = frappe.parse_json(approval.payload or "{}") or {}
    if payload.get("checks") != result:
        payload["checks"] = result
        approval.db_set("payload", json.dumps(payload, indent=1), update_modified=False)
    return result


def follow(run, row_name: str, pull: dict):
    """Moves the run with its pull request: an approval per head commit, draft, merged or closed.

    One pull request per fix: while the run's own is open (or merged), another that
    closes the same task is left alone; it is followed once the first is closed.
    """
    if run.pull_request and run.pull_request != row_name:
        own = frappe.db.get_value("HD Pull Request", run.pull_request, "state")
        if run.state not in FIX_STATES or own in ("Open", "Draft", "Merged"):
            _note_ignored(run, row_name)
            return
    if run.state not in FIX_STATES:
        if pull["state"] == "Merged":
            # records its merge commit, when the hub's merge did not
            on_merged(run, pull)
        return
    if run.pull_request != row_name:
        run.db_set("pull_request", row_name, update_modified=False)
    if pull["state"] == "Merged":
        return on_merged(run, pull)
    if pull["state"] == "Closed":
        return on_closed(run, pull)
    hold(pull)
    approval = approvals.current(run)
    if pull["state"] == "Draft":
        if approval:
            approvals.supersede(approval, _("the pull request went back to draft"))
        if run.state != "Preparing Fix":
            runs.transition(
                run, "Preparing Fix", runs.SYSTEM, note="the pull request is a draft"
            )
        return
    if approval and approval.head_sha == pull["head_sha"]:
        if approval.status == "Approved":
            try_merge(run)
        return
    if approval:
        approvals.supersede(
            approval, _("new commits ({0})").format(pull["head_sha"][:12])
        )
    if approvals.was_rejected(run, pull["head_sha"]):
        # the developer was told why; their next push opens a new approval
        if run.state != "Preparing Fix":
            runs.transition(
                run,
                "Preparing Fix",
                runs.SYSTEM,
                note="the pull request is back at a rejected commit",
            )
        return
    open_for(run, row_name, pull)


def _note_ignored(run, row_name: str):
    """An event, once per pull request, for one that is not this fix's."""
    if frappe.db.exists(
        "HDS Copilot Event",
        {
            "run": run.name,
            "event_type": "pull_request_ignored",
            "payload": ["like", f'%"{row_name}"%'],
        },
    ):
        return
    runs.add_event(
        run,
        "pull_request_ignored",
        {"pull_request": row_name, "following": run.pull_request},
        runs.SYSTEM,
    )


def open_for(run, row_name: str, pull: dict):
    """An approval for the pull request's head commit, with its files, risk and checks."""
    files = checks = None
    try:
        files = github.pull_files(pull["repo"], pull["number"])
        found = risk.assess(files)
    except GitHubError as e:
        found = {
            "level": "unknown",
            "sensitive": True,  # unknown files are treated as sensitive: a senior decides
            "reasons": [
                _("GitHub could not list the changed files: {0}").format(e.message)
            ],
        }
    try:
        checks = github.checks(pull["repo"], pull["head_sha"])
    except GitHubError:
        checks = None
    wrong = wrong_branch(run, pull["repo"], pull["base_branch"])
    if wrong:
        found["reasons"] = [*(found.get("reasons") or []), wrong]
    extra = {"copilot_only": False}
    change = _change_for(run, pull)
    if change:
        extra["change"] = {
            key: change.get(key)
            for key in (
                "summary",
                "evidence",
                "tested_on",
                "people_checks",
                "risk_notes",
            )
        }
        extra["change"]["tested_commit"] = change.get("head_sha")
    with contextlib.suppress(GitHubError):
        extra["copilot_only"] = github.copilot_only(pull["repo"], pull, commit_email())
    from helpdesk.copilot import changes

    data = changes.waiting_for_code(run)
    if data:
        # code and data on one approval: a senior's, for this commit and these records
        found["sensitive"] = True
        found["reasons"] = [
            *(found.get("reasons") or []),
            _("it also corrects {0} records on the customer's site").format(
                data.ready_count
            ),
        ]
        extra["change_set"] = data.name
        extra["change_set_digest"] = changes.digest_of(data)
    approval = approvals.open_approval(run, row_name, pull, files, found, checks, extra)
    if run.state != "Awaiting Approval":
        runs.transition(
            run,
            "Awaiting Approval",
            runs.SYSTEM,
            note=f"approval {approval.name}",
            approval=approval.name,
        )
    return approval


def hold(pull: dict):
    """Keeps the org merge bot and the auto-merge workflow off the pull request until the hub merges it."""
    label = hold_label()
    if not label or label in pull.get("labels", []):
        return
    try:
        github.add_label(pull["repo"], pull["number"], label)
        pull.setdefault("labels", []).append(label)
    except GitHubError as e:
        frappe.log_error(
            title=_("Copilot could not hold {0}#{1}").format(
                pull["repo"], pull["number"]
            ),
            message=e.message,
        )


def live_head(approval) -> str | None:
    """The pull request's head commit on GitHub now; None when GitHub can't be asked."""
    try:
        return pull_info(
            github.get_pull(approval.repo, approval.number), approval.repo
        )["head_sha"]
    except GitHubError:
        return None


def reopen_for_new_head(run, approval, reason: str):
    approvals.supersede(approval, reason)
    try:
        pull = pull_info(github.get_pull(approval.repo, approval.number), approval.repo)
    except GitHubError:
        return
    follow(frappe.get_doc("HDS Copilot Run", run.name), approval.pull_request, pull)


# --- merging -------------------------------------------------------------------------


def try_merge(run) -> str:
    """Merges an approved fix when GitHub still has the approved commit, every check passed and the merge is clean."""
    run = frappe.get_doc("HDS Copilot Run", run.name)
    approval = approvals.current(run)
    if not approval or approval.status != "Approved" or run.state != "Approved":
        return "not approved"
    try:
        pull = pull_info(github.get_pull(approval.repo, approval.number), approval.repo)
    except GitHubError as e:
        _blocked(approval, run, e.message, lasting=False)
        return "waiting"
    if pull["state"] == "Merged":
        on_merged(run, pull)
        return "merged"
    if pull["state"] == "Closed":
        on_closed(run, pull)
        return "closed"
    if pull["state"] == "Draft":
        # the approval lapses, as on the webhook
        follow(run, approval.pull_request, pull)
        return "draft"
    if pull["head_sha"] != approval.head_sha:
        reopen_for_new_head(run, approval, _("new commits after the approval"))
        return "superseded"
    wrong = wrong_branch(run, approval.repo, pull["base_branch"])
    if wrong:
        _blocked(approval, run, wrong)
        return "blocked"
    try:
        result = github.checks(approval.repo, approval.head_sha)
    except GitHubError as e:
        _blocked(approval, run, e.message, lasting=False)
        return "waiting"
    record_checks(approval, result)
    if result["failing"]:
        _blocked(
            approval, run, _("checks failing: {0}").format(", ".join(result["failing"]))
        )
        return "blocked"
    if result["pending"]:
        return "waiting"
    merge_state = pull["mergeable_state"]
    if merge_state in ("", "unknown", "unstable"):
        # GitHub is still working it out (unstable: it has not caught up with the
        # passed checks yet); the next check or refresh tries again
        if merge_state == "unstable" and result.get("partial"):
            _blocked(
                approval,
                run,
                _(
                    "GitHub reports a check that has not passed, outside the GitHub Actions this token can read"
                ),
                lasting=False,
            )
        return "waiting"
    if merge_state != "clean":
        _blocked(approval, run, _merge_state_reason(merge_state))
        return "blocked"
    try:
        commit = github.merge(
            approval.repo,
            approval.number,
            approval.head_sha,
            title=f"{pull['title']} (#{approval.number})",
        )
    except GitHubError as e:
        if e.status == 409:
            reopen_for_new_head(run, approval, _("the head moved while merging"))
            return "superseded"
        _blocked(approval, run, e.message)
        return "blocked"
    approval.db_set(
        {
            "status": "Merged",
            "merge_commit": commit,
            "merged_at": now_datetime(),
            "merge_error": None,
        },
        update_modified=False,
    )
    # no commit here: this can run inside the GitHub sync's savepoints, and a
    # merge the hub failed to record is recorded again by the next refresh or webhook
    pull["merge_commit_sha"] = commit
    on_merged(run, pull, by_hub=True)
    with contextlib.suppress(GitHubError):
        # the task sync completes the task now, not when (or if) GitHub's webhook arrives
        replay(approval.repo, github.get_pull(approval.repo, approval.number))
    # if this fails, the merged pull request keeps a harmless label
    with contextlib.suppress(GitHubError):
        github.remove_label(approval.repo, approval.number, hold_label())
    return "merged"


def site_branch(run, repo: str) -> str | None:
    """The branch the customer's site runs for `repo`, from the run's site card; None when unknown."""
    if not run.registry:
        return None
    for app in frappe.get_all(
        "HDS Site App",
        filters={"parent": run.registry, "parenttype": "HDS Site Registry"},
        fields=["repository", "branch"],
    ):
        if app.branch and _repo_name(app.repository) == repo.lower():
            return app.branch
    return None


def _repo_name(url_or_name: str | None) -> str:
    """`owner/name` from a GitHub URL (https or ssh) or a bare `owner/name`, lower case."""
    name = re.sub(r"\.git$", "", (url_or_name or "").strip().rstrip("/"))
    return re.sub(r"^(https?://(www\.)?|git@)github\.com[/:]", "", name).lower()


def wrong_branch(run, repo: str, base_branch: str) -> str | None:
    """Why a fix into `base_branch` would not reach the customer's site, or None.

    A merge into another branch than the site runs would never reach it. An
    evaluation or demo run reads a base commit of its own and is not checked.
    """
    expected = None if run.get("base_commit") else site_branch(run, repo)
    if expected and base_branch and base_branch != expected:
        return _(
            "the pull request targets {0}, but the customer's site runs {1}"
        ).format(base_branch, expected)
    return None


def _merge_state_reason(merge_state: str) -> str:
    """What GitHub's mergeable_state means for the people who must act on it."""
    reasons = {
        "dirty": _("the pull request has merge conflicts with its base branch"),
        "behind": _("the branch is behind its base branch; update it"),
        "blocked": _("GitHub requires a review or a check that is missing"),
    }
    return reasons.get(merge_state) or _("GitHub says the merge is {0}").format(
        merge_state
    )


def _blocked(approval, run, message: str, lasting: bool = True):
    """Records why an approved fix cannot merge; a lasting reason is told once to the approver and the developer."""
    message = (message or "")[:500]
    if approval.merge_error == message:
        return
    approval.db_set("merge_error", message, update_modified=False)
    runs.add_event(
        run,
        "merge_blocked",
        {"approval": approval.name, "reason": message},
        runs.SYSTEM,
    )
    if lasting:
        approvals.announce(
            approval,
            _("The approved Copilot fix on ticket {0} cannot merge yet: {1}").format(
                run.ticket, message
            ),
            also=sorted(approvals.authors(run)),
        )


# --- outcomes -------------------------------------------------------------------------


def on_merged(run, pull: dict, by_hub: bool = False):
    """The fix is merged: with the approval it is the normal end; without it, the managers are told."""
    from helpdesk.copilot import customer

    run = frappe.get_doc("HDS Copilot Run", run.name)
    if run.state not in FIX_STATES:
        if pull.get("merge_commit_sha") and not run.merge_commit:
            run.db_set("merge_commit", pull["merge_commit_sha"], update_modified=False)
        return
    approval = approvals.current(run) or (
        frappe.get_doc("HDS Copilot Approval", run.approval) if run.approval else None
    )
    approved = bool(
        approval
        and approval.status in ("Approved", "Merged")
        and (not pull.get("head_sha") or approval.head_sha == pull["head_sha"])
    )
    if approval and approval.status == "Approved":
        approval.db_set(
            {
                "status": "Merged",
                "merge_commit": pull.get("merge_commit_sha"),
                "merged_at": now_datetime(),
            },
            update_modified=False,
        )
    elif approval and approval.status == "Pending":
        approvals.supersede(approval, _("merged without the approval"))
    run = runs.transition(
        run,
        "Merged",
        runs.SYSTEM,
        note=("merged by the hub" if by_hub else "merged on GitHub")
        + ("" if approved else " without the approval"),
        merge_commit=pull.get("merge_commit_sha") or None,
    )
    if not approved:
        runs.add_event(
            run,
            "merged_without_approval",
            {"pull_request": run.pull_request},
            runs.SYSTEM,
        )
        customer.comment(
            run.ticket,
            "<b>{0}</b>".format(
                escape_html(
                    _(
                        "This Copilot fix was merged on GitHub without the one approval on the ticket."
                    )
                )
            ),
        )
        runs.tell_people(
            run,
            _("A Copilot fix on ticket {0} was merged without its approval").format(
                run.ticket
            ),
        )
    when = approval.deploy_date if approval and approval.deploy_date else None
    customer.send_stage(
        run,
        "Fix scheduled",
        {"date": formatdate(when) if when else _("our next update")},
    )
    if approved:
        from helpdesk.copilot import deploy

        deploy.auto_request(run, approval)


def on_closed(run, pull: dict):
    """Closed without merging: the approval lapses and the run waits for another pull request."""
    approval = approvals.current(run)
    if approval:
        approvals.supersede(approval, _("the pull request was closed without merging"))
    if run.state in ("Awaiting Approval", "Approved"):
        runs.transition(
            run,
            "Preparing Fix",
            runs.SYSTEM,
            note="the pull request was closed without merging",
        )


def on_rejected(run, approval, note: str):
    """Back to Preparing Fix; the reason reaches the developer on the task and on the pull request."""
    from helpdesk.work_reminders import notify_users

    who = frappe.utils.get_fullname(frappe.session.user)
    run = runs.transition(
        run, "Preparing Fix", runs.AGENT, note=f"rejected: {note}"[:140]
    )
    if run.task:
        frappe.get_doc("Task", run.task).add_comment(
            "Comment", escape_html(_("Fix rejected by {0}: {1}").format(who, note))
        )
        notify_users(
            sorted(approvals.authors(run)),
            "Task",
            run.task,
            _("Your Copilot fix for ticket {0} was rejected: {1}").format(
                run.ticket, note[:120]
            ),
            once=False,
        )
    with contextlib.suppress(GitHubError):
        github.comment(
            approval.repo,
            approval.number,
            _("This fix was not approved on TBO Support by {0}: {1}").format(who, note),
        )


def revert_run_of(run):
    """The undo of this run's fix, while it is still under way."""
    name = frappe.db.get_value(
        "HDS Copilot Run",
        {"reverts": run.name, "state": ["not in", ("Closed", "Cancelled", "Failed")]},
        "name",
    )
    return frappe.get_doc("HDS Copilot Run", name) if name else None


def can_undo(run) -> bool:
    return bool(
        run.merge_commit
        and run.get("kind") != "revert"
        and run.state in ("Escalated", "Resolved")
        and run.approval
        and not revert_run_of(run)
    )


def undo(run, user: str, reason: str):
    """Undo a merged fix: GitHub's revert pull request, followed by a revert run through the same one approval.

    The revert run has its own task; its pull request goes through the hold, the
    approval and the merge like any fix, then Deploy. The customer hears nothing
    from it: the ticket stays with a person.
    """
    from helpdesk.copilot import customer

    run = frappe.get_doc("HDS Copilot Run", run.name)
    reason = (reason or "").strip()[:500]
    if not reason:
        frappe.throw(_("Please say why the fix is undone."))
    if not can_undo(run):
        frappe.throw(_("Only a merged fix that went wrong can be undone, once."))
    approval = frappe.get_doc("HDS Copilot Approval", run.approval)
    revert = frappe.get_doc(
        {
            "doctype": "HDS Copilot Run",
            "ticket": run.ticket,
            "customer": run.customer,
            "connection": run.connection,
            "registry": run.registry,
            "kind": "revert",
            "state": "Preparing Fix",
            "shadow": run.shadow,
            "reverts": run.name,
            "root_cause_category": run.root_cause_category,
            "summary": _("Undo the fix of {0}: {1}").format(run.name, reason),
            "queued_at": now_datetime(),
        }
    ).insert(ignore_permissions=True)
    runs.add_event(
        revert, "state_change", {"from": None, "to": "Preparing Fix"}, runs.AGENT
    )
    runs.update_ticket(revert)  # the ticket's card follows the undo from now on
    task = create_fix_task(revert, runs.AGENT, prefix=REVERT_TASK_PREFIX)
    pull = github.revert_pull(
        approval.repo,
        approval.number,
        title=f"{task}: revert {approval.repo}#{approval.number}"[:250],
        body="\n".join(
            [
                _("Reverts {0}#{1}, the Copilot fix of ticket {2}: {3}").format(
                    approval.repo, approval.number, run.ticket, reason
                ),
                "",
                f"Closes {task}",
                f"Ticket: {run.ticket}",
                f"Copilot-Run: {revert.name}",
            ]
        ),
    )
    runs.add_event(
        run,
        "undo_requested",
        {
            "by": user,
            "reason": reason,
            "revert_run": revert.name,
            "pull": pull["number"],
        },
        runs.AGENT,
    )
    runs.add_event(revert, "revert_opened", {"reverts": run.name, **pull}, runs.AGENT)
    customer.comment(
        run.ticket,
        '{0} <a href="{1}">{2}#{3}</a>'.format(
            escape_html(_("Undo requested: the revert pull request")),
            escape_html(pull["url"]),
            escape_html(approval.repo),
            pull["number"],
        ),
    )
    if sync_on():
        with contextlib.suppress(GitHubError):
            refresh(frappe.get_doc("HDS Copilot Run", revert.name))
    revert = frappe.get_doc("HDS Copilot Run", revert.name)
    runs.publish_run(revert)
    return revert


def mark_deployed(run, user: str, note: str = ""):
    """An engineer deployed the merged fix: the run is Resolved and the customer is asked to confirm."""
    from helpdesk.copilot import customer

    if run.state != "Merged":
        frappe.throw(
            _("Only a merged fix can be marked deployed (this run is {0}).").format(
                run.state
            )
        )
    from helpdesk.copilot import deploy

    if deploy.open_request(run):
        frappe.throw(
            _(
                "A Copilot deploy of this fix is waiting or running; cancel it first, or let it finish."
            )
        )
    note = (note or "").strip()[:500]
    from helpdesk.copilot import changes

    data = changes.approved_with_code(run)
    if data:
        run = runs.transition(
            run,
            "Applying",
            runs.AGENT,
            note=f"deployed by {user}; correcting the data",
            deployed_at=now_datetime(),
            deployed_by=user,
        )
        changes.apply_after_code(data, user)
        return frappe.get_doc("HDS Copilot Run", run.name)
    run = runs.transition(
        run,
        "Resolved",
        runs.AGENT,
        note=f"deployed by {user}",
        deployed_at=now_datetime(),
        deployed_by=user,
    )
    resolution = _("The fix is live.") + (f" {note}" if note else "")
    customer.send_stage(run, "Resolved", {"resolution": resolution})
    return run


# --- reading GitHub directly ------------------------------------------------------------


def refresh(run) -> str:
    """Reads the fix's pull request from GitHub and replays it as its webhook would
    have (finding it by its task when no webhook ever linked it)."""
    if run.state not in FIX_STATES:
        return "nothing to follow"
    if not sync_on():
        return "the GitHub sync is off (Settings → GitHub)"
    found = _pull_to_read(run)
    if not found:
        return "no pull request yet"
    try:
        pr = github.get_pull(*found)
    except GitHubError as e:
        return f"GitHub: {e.message}"
    replay(found[0], pr)
    return "refreshed"


def _pull_to_read(run) -> tuple[str, int] | None:
    """The run's pull request, unless it was closed: a developer may close one and
    open another for the same task, which a webhook linked or GitHub's search finds."""
    own = (
        frappe.db.get_value(
            "HD Pull Request",
            run.pull_request,
            ["repo", "number", "state"],
            as_dict=True,
        )
        if run.pull_request
        else None
    )
    if own and own.state != "Closed":
        return own.repo, own.number
    other = (
        frappe.db.get_value(
            "HD Pull Request",
            {
                "task": run.task,
                "link_kind": "Closes",
                "state": ["in", ("Open", "Draft")],
            },
            ["repo", "number"],
            as_dict=True,
            order_by="modified desc",
        )
        if run.task
        else None
    )
    if other:
        return other.repo, other.number
    return discover(run) or ((own.repo, own.number) if own else None)


def discover(run) -> tuple[str, int] | None:
    """A pull request that says `Closes <fix task>` but never reached the hub by webhook."""
    from helpdesk.copilot import github_app
    from helpdesk.github_sync import PullRequestSync

    if not run.task:
        return None
    settings = frappe.get_single("HD GitHub Settings")
    # the App searches each owner it is installed on; a personal token searches once
    for owner in (_owners(run) if github_app.configured() else []) or [None]:
        try:
            found = github.request(
                "GET",
                "/search/issues",
                params={"q": f'"{run.task}" is:pr is:open', "per_page": 10},
                owner=owner,
            )
        except GitHubError:
            continue
        for item in (found or {}).get("items") or []:
            repo = "/".join((item.get("repository_url") or "").split("/")[-2:])
            if not repo or not settings.allows_repo(repo):
                continue
            try:
                pr = github.get_pull(repo, item.get("number"))
            except GitHubError:
                continue
            if PullRequestSync(repo, pr).task_refs().get(run.task) == "Closes":
                return repo, int(pr.get("number") or 0)
    return None


def _owners(run) -> list[str]:
    """The GitHub owners to search: those of the site's app repositories, else the allowed ones."""
    owners = [
        _repo_name(repository).split("/")[0]
        for repository in (
            frappe.get_all(
                "HDS Site App",
                filters={"parent": run.registry, "parenttype": "HDS Site Registry"},
                pluck="repository",
            )
            if run.registry
            else []
        )
        if "/" in _repo_name(repository)
    ]
    if not owners:
        allowed = frappe.db.get_single_value("HD GitHub Settings", "allowed_repos")
        owners = [
            line.strip().split("/")[0]
            for line in (allowed or "").splitlines()
            if "/" in line
        ]
    return list(dict.fromkeys(owner.lower() for owner in owners if owner))


def replay(repo: str, pr: dict):
    """What the pull request's webhook would have done, for one the hub missed: the
    task sync when the hub's record is behind GitHub (it acts once per change of
    state, so the real webhook arriving later changes nothing), then the fix."""
    from helpdesk.github_sync import PULL_REQUEST, PullRequestSync

    if not sync_on():
        return
    sync = PullRequestSync(repo, pr)
    head = (pr.get("head") or {}).get("sha") or ""
    rows = frappe.get_all(
        PULL_REQUEST,
        filters={"repo": repo, "number": sync.number},
        fields=["name", "repo", "task", "link_kind", "state", "head_sha"],
    )
    if rows and all(row.state == sync.state and row.head_sha == head for row in rows):
        on_pull_request(pr, "edited", rows)  # nothing new for the task sync
        return
    if sync.state in ("Merged", "Closed"):
        action = "closed"
    elif not rows:
        action = "opened"
    elif any(row.state in ("Merged", "Closed") for row in rows):
        action = "reopened"
    else:
        action = "synchronize"
    sync.on_pull_request(action, None)


def refresh_open():
    """Cron: every fix still in flight reads its pull request, so a missed webhook never strands an approval."""
    if not sync_on():
        return
    for name in frappe.get_all(
        "HDS Copilot Run",
        filters={"state": ["in", FIX_STATES], "task": ["is", "set"]},
        pluck="name",
    ):
        try:
            refresh(frappe.get_doc("HDS Copilot Run", name))
            frappe.db.commit()  # one run at a time - nosemgrep
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=_("Copilot could not refresh the fix of {0}").format(name)
            )
