# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Releases (Phase 7): every merge into a branch a customer site runs goes out the same way.

Every ten minutes `watch` reads the tip of each branch that a Production site
card deploys through Press, for the repositories listed in HDS Copilot
Settings → Releases. Commits the bench does not run yet become a release: an
HDS Deploy Request without a Copilot run, holding the commits and the pull
requests that brought them, the task and ticket they close, and the
customers' sites on that bench. A release still waiting for CI or for its
approval takes in later commits; one already approved is followed by a new
release. Copilot's own merged fixes keep their own path (the run's Deploy).

Then every five minutes `run_due` moves releases on. The CI gate: every pull
request's last commit (CI runs there, not on the merge), every push and the
branch tip when CI ran on it must be green; a senior may override red CI with
a reason. One approval follows, by an approver who wrote none of it (a senior
for a push, a sensitive change or a shared bench), on the release's card in
Teams or the Copilot panel. Approved releases join the nightly train
(helpdesk.copilot.deploy): one Press deploy per bench, then the check after.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_url, now_datetime

from helpdesk.copilot import approvals, deploy, github, press
from helpdesk.copilot import settings as copilot_settings
from helpdesk.copilot.github import GitHubError
from helpdesk.copilot.press import PressError

DEPLOY = deploy.DEPLOY
# a release still takes in later commits until it is approved
GROWING = ("Waiting for CI", "Staging", "Waiting for approval")
MAX_COMMITS = 100
SEEN_KEY = "copilot_release_seen"
TROUBLE_HOURS = 6


def enabled() -> bool:
    return bool(copilot_settings.get_settings().get("releases_enabled"))


def repositories() -> set[str]:
    """The repositories in the pipeline, as `owner/name` in lower case."""
    from helpdesk.copilot.fixes import _repo_name

    text = copilot_settings.get_settings().get("release_repositories") or ""
    return {_repo_name(line) for line in text.splitlines() if line.strip()}


def targets() -> dict[tuple[str, str, str], list[dict]]:
    """(repository, branch, bench) → the Production sites on that bench that run the branch."""
    from helpdesk.copilot.fixes import _repo_name

    wanted = repositories()
    if not wanted:
        return {}
    cards = {
        card.name: card
        for card in frappe.get_all(
            "HDS Site Registry",
            filters={
                "environment": "Production",
                "press_site": ["is", "set"],
                "press_release_group": ["is", "set"],
            },
            fields=["name", "customer_name", "press_site", "press_release_group"],
        )
        if card.press_site != deploy.hub_site()
    }
    found = {}
    for row in frappe.get_all(
        "HDS Site App",
        filters={"parenttype": "HDS Site Registry", "parent": ["in", list(cards)]},
        fields=["parent", "app", "repository", "branch", "deployed_commit"],
        order_by="parent asc",
    ):
        repo, card = _repo_name(row.repository), cards[row.parent]
        if repo not in wanted or not row.branch:
            continue
        found.setdefault((repo, row.branch, card.press_release_group), []).append(
            {
                "registry": card.name,
                "customer": card.customer_name,
                "site": card.press_site,
                "app": row.app,
                "deployed_commit": row.deployed_commit or "",
            }
        )
    return found


# --- the cron -----------------------------------------------------------------------


def watch():
    """Cron: new commits on the deployed branches become releases, one branch at a time."""
    if not enabled():
        return
    for key, sites in targets().items():
        try:
            look(key, sites)
            frappe.db.commit()  # one branch at a time - nosemgrep
        except GitHubError as e:
            # not read this time (GitHub down, or the App not installed there): said once in a
            # while; look() reads GitHub before it writes anything, so nothing is half done
            _trouble(key, e.message)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=_("Copilot release of {0} {1}").format(key[0], key[1])
            )


def look(key: tuple[str, str, str], sites: list[dict]) -> str | None:
    """Makes or grows the release of one branch on one bench; its name, or None when nothing is new."""
    repo, branch, group = key
    head = github.branch_head(repo, branch)
    if not head or _seen(key) == head:
        return None
    growing = latest(key, GROWING)
    if growing and growing.apps[0].to_commit == head:
        return _remember(key, head)
    in_flight = None if growing else latest(key, deploy.OPEN)
    if growing:
        base = growing.apps[0].from_commit
    elif in_flight:
        base = in_flight.apps[0].to_commit
    else:
        base = running_commit(group, sites)
    if not base or _same(base, head):
        return _remember(key, head)
    compared = github.compare(repo, base, head)
    if compared["status"] in ("identical", "behind"):
        return _remember(key, head)
    changes = commit_changes(repo, branch, compared["commits"][-MAX_COMMITS:])
    if not growing and all(change.get("run") for change in changes):
        return _remember(
            key, head
        )  # only Copilot's merged fixes: their runs deploy them
    doc = (
        grow(growing, head, changes)
        if growing
        else create(key, sites, base, head, changes)
    )
    _remember(key, head)
    return doc.name


def latest(key: tuple[str, str, str], statuses: tuple):
    """The newest release of the branch on the bench in one of `statuses`."""
    repo, branch, group = key
    name = frappe.db.get_value(
        DEPLOY,
        {
            "repository": repo,
            "branch": branch,
            "release_group": group,
            "status": ["in", statuses],
        },
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc(DEPLOY, name) if name else None


def running_commit(group: str, sites: list[dict]) -> str:
    """What the bench runs now: Press's answer, or the site card's when Press can't be asked."""
    app = sites[0]["app"]
    if press.configured():
        try:
            info = press.deploy_information(group)
            row = next(
                (
                    a
                    for a in info.get("apps") or []
                    if (a.get("app") or a.get("name")) == app
                ),
                None,
            )
            if row and (current := press.app_commits(row)[0]):
                return current
        except PressError:
            pass
    return next((s["deployed_commit"] for s in sites if s["deployed_commit"]), "")


def commit_changes(repo: str, branch: str, commits: list[dict]) -> list[dict]:
    """Each commit with the pull request that merged it into `branch`, its task and, for Copilot's fixes, the run."""
    from helpdesk.github_sync import TASK_REF

    found = []
    for commit in commits:
        sha = commit.get("sha") or ""
        info = commit.get("commit") or {}
        entry = {
            "sha": sha,
            "title": ((info.get("message") or "").splitlines() or [""])[0][:200],
            "author": (commit.get("author") or {}).get("login")
            or ((info.get("author") or {}).get("email") or "").lower(),
            "email": ((info.get("author") or {}).get("email") or "").lower(),
        }
        pull = next(
            (
                p
                for p in github.commit_pulls(repo, sha)
                if p.get("merged_at") and (p.get("base") or {}).get("ref") == branch
            ),
            None,
        )
        if pull:
            number = int(pull["number"])
            entry["pull"] = {
                "number": number,
                "title": (pull.get("title") or "")[:200],
                "url": pull.get("html_url") or "",
                "author": (pull.get("user") or {}).get("login") or "",
                # CI ran on the pull request's last commit, not on the merge
                "head_sha": (pull.get("head") or {}).get("sha") or "",
            }
            refs = TASK_REF.findall(
                "\n".join(
                    [
                        pull.get("title") or "",
                        pull.get("body") or "",
                        (pull.get("head") or {}).get("ref") or "",
                    ]
                )
            )
            if refs:
                entry["task"] = refs[0].upper()
            if run := frappe.db.get_value(
                "HDS Copilot Approval",
                {"repo": repo, "number": number, "status": "Merged"},
                "run",
            ):
                entry["run"] = run
        found.append(entry)
    return found


def _fields(changes: list[dict], others: list[str], sites: list[dict]) -> dict:
    """What a release says about its commits: where they came from, who wrote them, what they close."""
    pushes = [c for c in changes if not c.get("pull")]
    task = next(
        (
            c["task"]
            for c in changes
            if c.get("task") and frappe.db.exists("Task", c["task"])
        ),
        None,
    )
    authors = []
    for change in changes:
        for who in ((change.get("pull") or {}).get("author"), change.get("author")):
            if who and who not in authors:
                authors.append(who)
    customers = {s["customer"] for s in sites}
    shared = [site for site in others if site != deploy.hub_site()]
    return {
        "source": "Push" if pushes else "Pull request",
        "task": task,
        "ticket": frappe.db.get_value("Task", task, "hd_ticket") if task else None,
        "authors": "\n".join(authors),
        "changes": json.dumps(changes, indent=1),
        # a push nobody reviewed, or other customers' sites on the bench: a senior decides
        "needs_senior": int(bool(pushes) or len(customers) > 1 or bool(shared)),
    }


def other_sites(group: str, ours: list[str]) -> list[str]:
    """The bench's other sites, as Press lists them (empty when Press can't be asked)."""
    if not press.configured():
        return []
    try:
        info = press.deploy_information(group)
    except PressError:
        return []
    return [s.get("name") for s in info.get("sites") or [] if s.get("name") not in ours]


def create(key, sites: list[dict], base: str, head: str, changes: list[dict]):
    repo, branch, group = key
    others = other_sites(group, [s["site"] for s in sites])
    doc = frappe.get_doc(
        {
            "doctype": DEPLOY,
            "status": "Waiting for CI",
            "ci_status": "Pending",
            "repository": repo,
            "branch": branch,
            "release_group": group,
            "requested_at": now_datetime(),
            "other_sites": "\n".join(others),
            "sites": [
                {
                    "site": s["site"],
                    "customer": s["customer"],
                    "registry": s["registry"],
                }
                for s in sites
            ],
            "apps": [
                {
                    "app": sites[0]["app"],
                    "repository": repo,
                    "from_commit": base,
                    "to_commit": head,
                }
            ],
            **_fields(changes, others, sites),
        }
    ).insert(ignore_permissions=True)
    doc.add_comment(
        "Info",
        _("{0} commits on {1} {2} wait for CI.").format(len(changes), repo, branch),
    )
    return doc


def grow(doc, head: str, changes: list[dict]):
    """Later commits join a release not yet approved; it waits for CI again, and any approval asked for starts over."""
    sites = [{"customer": row.customer, "site": row.site} for row in doc.sites]
    others = [s for s in (doc.other_sites or "").splitlines() if s]
    doc.apps[0].to_commit = head
    cancel_staging(doc)
    doc.update(
        {
            "status": "Waiting for CI",
            "ci_status": "Pending",
            "ci_detail": None,
            "ci_override_by": None,
            "ci_override_reason": None,
            "approval_hash": None,
            "staging": None,
            "staging_status": None,
            "staging_detail": None,
            "staging_request": None,
            "check_lease_hash": None,
            **_fields(changes, others, sites),
        }
    )
    doc.save(ignore_permissions=True)
    doc.add_comment(
        "Info",
        _("New commits up to {0} joined the release; it waits for CI again.").format(
            head[:12]
        ),
    )
    return doc


# --- small helpers ------------------------------------------------------------------


def _same(a: str, b: str) -> bool:
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def _field_key(key: tuple[str, str, str]) -> str:
    return "|".join(key)


def _seen(key) -> str | None:
    seen = frappe.cache().hget(SEEN_KEY, _field_key(key))
    return seen.decode() if isinstance(seen, bytes) else seen


def _remember(key, head: str) -> None:
    """The branch's tip is handled: the next runs skip GitHub's compare until it moves."""
    frappe.cache().hset(SEEN_KEY, _field_key(key), head)
    return None


def _trouble(key, message: str):
    marker = frappe.cache().make_key(f"copilot_release_trouble:{_field_key(key)}")
    # SET NX with an expiry: the same trouble is logged once every few hours - nosemgrep
    if frappe.cache().set(marker, 1, ex=TROUBLE_HOURS * 3600, nx=True):
        frappe.log_error(
            title=_("Copilot could not read {0} {1} on GitHub").format(key[0], key[1]),
            message=message,
        )


# --- the CI gate ---------------------------------------------------------------------


def run_due():
    """Cron: releases waiting for CI are checked; approvals waiting too long are reminded."""
    if not enabled():
        return
    for name in frappe.get_all(
        DEPLOY,
        filters={"status": "Waiting for CI", "run": ["is", "not set"]},
        order_by="creation asc",
        pluck="name",
    ):
        try:
            gate(frappe.get_doc(DEPLOY, name))
            frappe.db.commit()  # one release at a time - nosemgrep
        except GitHubError:
            pass  # GitHub could not be asked this time; the next run tries again
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=_("Copilot release {0} could not move on").format(name)
            )
    expire_checks()
    remind()


def ci_result(release) -> dict:
    """`{state: Passed | Pending | Failed, detail}` for the release's commits.

    CI runs on a pull request's last commit, not on the merge, so each pull
    request is judged there; a push by its own commit; the branch tip too when
    CI ran on it. A commit with no check at all fails: nothing deploys unchecked.
    """
    commits = []
    for change in frappe.parse_json(release.changes or "[]") or []:
        sha = (change.get("pull") or {}).get("head_sha") or change.get("sha")
        if sha and sha not in commits:
            commits.append(sha)
    results = {sha: github.checks(release.repository, sha) for sha in commits}
    tip = release.apps[0].to_commit
    if tip not in results:
        checked = github.checks(release.repository, tip)
        if checked["total"]:
            results[tip] = checked
    failing, pending, unchecked, total = [], [], [], 0
    for sha, result in results.items():
        total += result["total"]
        if result["failing"]:
            failing.append(f"{sha[:7]}: {', '.join(result['failing'][:3])}")
        elif result["pending"]:
            pending.append(sha[:7])
        elif not result["total"]:
            unchecked.append(sha[:7])
    if failing or unchecked:
        detail = "; ".join(
            failing
            + (
                [_("no CI ran on {0}").format(", ".join(unchecked))]
                if unchecked
                else []
            )
        )
        return {"state": "Failed", "detail": detail[:1000]}
    if pending:
        return {
            "state": "Pending",
            "detail": _("still running on {0}").format(", ".join(pending)),
        }
    return {
        "state": "Passed",
        "detail": _("{0} checks green on {1} commits").format(total, len(results)),
    }


def gate(release):
    result = ci_result(release)
    if result["state"] == "Pending":
        release.db_set("ci_detail", result["detail"])
        return
    if result["state"] == "Failed":
        if release.ci_status != "Failed":
            release.db_set({"ci_status": "Failed", "ci_detail": result["detail"]})
            tell(
                release,
                authors(release),
                _(
                    "CI failed for the release of {0} {1}: {2}. Push a fix, or a senior can override it with a reason."
                ).format(release.repository, release.branch, result["detail"][:200]),
            )
        return
    release.db_set({"ci_status": "Passed", "ci_detail": result["detail"]})
    start_staging(release)


def override_ci(release, user: str, reason: str):
    """A senior lets a release through red or missing CI, or a staging check that failed or
    never ran, to its approval; the reason is kept and the approval needs a senior."""
    staging = release.status == "Staging" and release.staging_status in (
        "Failed",
        "Not run",
    )
    if release.status != "Waiting for CI" and not staging:
        frappe.throw(
            _(
                "Only a release waiting for CI, or whose staging check failed or never ran, can be let through."
            )
        )
    if user not in approvals.seniors():
        frappe.throw(
            _("Only a senior approver may let a release through without its checks."),
            frappe.PermissionError,
        )
    if not (reason or "").strip():
        frappe.throw(_("Say why the release may go on without its checks."))
    release.db_set(
        {
            "ci_status": release.ci_status if staging else "Overridden",
            "ci_override_by": user,
            "ci_override_reason": reason.strip()[:1000],
            "needs_senior": 1,
        }
    )
    release.add_comment(
        "Info",
        (
            _("{0} let it through without its staging check: {1}")
            if staging
            else _("{0} let it through without green CI: {1}")
        ).format(frappe.utils.get_fullname(user), reason.strip()),
    )
    ask_approval(release)


# --- the approval --------------------------------------------------------------------


def authors(release) -> set[str]:
    """The people who wrote it: the assignees of the tasks it closes, and users with a commit's email."""
    people = set()
    for change in frappe.parse_json(release.changes or "[]") or []:
        if change.get("task"):
            people |= set(
                frappe.parse_json(
                    frappe.db.get_value("Task", change["task"], "_assign") or "[]"
                )
            )
        if change.get("email") and (
            user := frappe.db.get_value("User", {"email": change["email"]})
        ):
            people.add(user)
    return people


def approval_hash(release) -> str:
    """What the approver sees: the commits, the sites and the CI result; any change asks again."""
    payload = {
        "repository": release.repository,
        "branch": release.branch,
        "bench": release.release_group,
        "commits": [release.apps[0].from_commit, release.apps[0].to_commit],
        "sites": sorted(row.site for row in release.sites),
        "ci": release.ci_status,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def pick_approver(needs_senior: bool, excluded: set[str]) -> str | None:
    """The least loaded approver who wrote none of it; a senior when one is needed."""
    allowed = (
        approvals.seniors()
        if needs_senior
        else list(dict.fromkeys(approvals.approvers() + approvals.seniors()))
    )
    candidates = [user for user in allowed if user not in excluded] or [
        user for user in approvals.managers() if user not in excluded
    ]
    if not candidates:
        return None

    def load(user: str):
        waiting = frappe.db.count(
            DEPLOY, {"assigned_to": user, "status": "Waiting for approval"}
        )
        last = frappe.db.get_value(
            DEPLOY, {"assigned_to": user}, "assigned_at", order_by="assigned_at desc"
        )
        return (waiting, get_datetime(last) if last else get_datetime("2000-01-01"))

    return min(candidates, key=load)


def ask_approval(release):
    from helpdesk.copilot import risk

    files = github.compare(
        release.repository, release.apps[0].from_commit, release.apps[0].to_commit
    )["files"]
    assessed = risk.assess(files)
    needs_senior = bool(release.needs_senior or assessed["sensitive"])
    approver = pick_approver(needs_senior, authors(release))
    release.db_set(
        {
            "status": "Waiting for approval",
            "risk_level": assessed["level"],
            "risk_reasons": "\n".join(assessed["reasons"])[:1000],
            "needs_senior": int(needs_senior),
            "assigned_to": approver,
            "assigned_at": now_datetime(),
            "reminded_at": None,
        }
    )
    release.db_set("approval_hash", approval_hash(release))
    if not approver:
        tell(
            release,
            approvals.managers(),
            _(
                "A release of {0} waits for approval, but no approver is free to take it."
            ).format(release.repository),
        )
        return
    announce(release, approver)


def may_decide(release, user: str) -> str | None:
    """Why `user` may not decide the release, or None when they may."""
    if user in authors(release):
        return _("You wrote part of this release, so someone else must approve it.")
    if release.needs_senior and user not in approvals.seniors():
        return _("This release needs a senior approver ({0}).").format(
            (
                release.risk_reasons or _("a push, or a bench other customers share")
            ).splitlines()[0]
        )
    if user not in set(approvals.approvers()) | set(approvals.seniors()) | set(
        approvals.managers()
    ):
        return _(
            "Only the Copilot approvers and the Agent Managers may decide releases."
        )
    return None


def decide(
    name: str,
    user: str,
    approve: bool,
    note: str = "",
    when: str = "tonight",
    expected_hash: str | None = None,
    via: str = "Desk",
) -> dict:
    """Approve (deploy tonight, or now for seniors) or reject (with a reason) a release; the first decision wins."""
    release = frappe.get_doc(DEPLOY, name, for_update=True)
    if release.run:
        frappe.throw(_("A Copilot fix is approved on its ticket."))
    if release.status != "Waiting for approval":
        if release.decided_by:
            frappe.throw(
                _("{0} already decided this release at {1}.").format(
                    frappe.utils.get_fullname(release.decided_by),
                    frappe.utils.format_datetime(release.decided_at, "d MMM, HH:mm"),
                )
            )
        frappe.throw(
            _("This release is not waiting for an approval ({0}).").format(
                release.status
            )
        )
    if expected_hash and expected_hash != release.approval_hash:
        frappe.throw(_("The release changed after you saw it; look at it again."))
    if reason := may_decide(release, user):
        frappe.throw(reason, frappe.PermissionError)
    note = (note or "").strip()
    decided = {
        "decided_by": user,
        "decided_at": now_datetime(),
        "decided_via": via,
        "decision_note": note[:1000],
    }
    if not approve:
        if not note:
            frappe.throw(_("Say why, so the people who wrote it can act on it."))
        release.db_set({"status": "Rejected", "finished_at": now_datetime(), **decided})
        tell(
            release,
            authors(release),
            _("{0} rejected the release of {1} {2}: {3}").format(
                frappe.utils.get_fullname(user),
                release.repository,
                release.branch,
                note,
            ),
        )
        refresh_cards(release.name)
        return {"status": "Rejected"}
    now = str(when).strip().lower() == "now"
    if now and not deploy.may_deploy_now(user):
        frappe.throw(
            _(
                "Only senior approvers and Agent Managers may deploy now; approve it for tonight."
            ),
            frappe.PermissionError,
        )
    at = now_datetime() if now else deploy.next_opening()
    release.db_set(
        {
            "status": "Scheduled",
            "when": "Now" if now else "Tonight",
            "scheduled_for": at,
            "requested_by": user,
            "requested_at": now_datetime(),
            **decided,
        }
    )
    if release.ticket:
        from helpdesk.copilot import customer

        customer.comment(
            release.ticket,
            frappe.utils.escape_html(
                _("Release {0} with this change deploys {1}.").format(
                    release.name, deploy.local_time(at)
                )
            ),
        )
    refresh_cards(release.name)
    return {"status": "Scheduled", "at": str(at)}


def remind():
    """Approvals waiting longer than the reminder hours are sent again, at most once in that time."""
    hours = copilot_settings.get_settings().get("approval_reminder_hours") or 4
    due = add_to_date(now_datetime(), hours=-hours)
    for release in frappe.get_all(
        DEPLOY,
        filters={
            "status": "Waiting for approval",
            "assigned_to": ["is", "set"],
            "assigned_at": ["<", due],
        },
        fields=["name", "assigned_to", "reminded_at"],
    ):
        if release.reminded_at and get_datetime(release.reminded_at) > due:
            continue
        frappe.db.set_value(
            DEPLOY, release.name, "reminded_at", now_datetime(), update_modified=False
        )
        announce(frappe.get_doc(DEPLOY, release.name), release.assigned_to)


# --- telling people ------------------------------------------------------------------


def tell(release, people, message: str):
    from helpdesk.work_reminders import notify_users

    people = [p for p in dict.fromkeys(people or []) if p]
    if people:
        notify_users(people, DEPLOY, release.name, message, once=False)


def announce(release, person: str):
    """The release's card to the approver (Teams, else the Copilot panel), and the usual notice."""
    from helpdesk.copilot import assistant

    tell(
        release,
        [person],
        _("A release of {0} {1} waits for your approval").format(
            release.repository, release.branch
        ),
    )
    try:
        assistant.send(person, release_card(release), release=release.name)
    except Exception:
        frappe.log_error(title=f"Copilot could not send the card of {release.name}")


def release_card(release) -> dict:
    """A release waiting for approval: what changed, CI, risk, the sites; Approve, Deploy now, Reject."""
    from helpdesk.copilot import assistant

    if isinstance(release, str):
        release = frappe.get_doc(DEPLOY, release)
    if release.status != "Waiting for approval":
        return decided_card(release)
    changes = frappe.parse_json(release.changes or "[]") or []
    pulls = list(
        dict.fromkeys(
            f"#{c['pull']['number']} {c['pull']['title']}"[:90]
            for c in changes
            if c.get("pull")
        )
    )
    pushes = [c for c in changes if not c.get("pull")]
    lines = pulls[:5] + (
        [_("{0} more").format(len(pulls) - 5)] if len(pulls) > 5 else []
    )
    if pushes:
        lines.append(_("{0} commits pushed without a pull request").format(len(pushes)))
    customers = sorted({row.customer for row in release.sites if row.customer})
    data = {"release": release.name, "hash": release.approval_hash}
    return assistant.card(
        _("Release of {0} ({1}) waits for approval").format(
            release.repository, ", ".join(customers) or release.release_group
        ),
        lines,
        facts=[
            (_("Branch"), release.branch),
            (
                _("CI"),
                (release.ci_detail or release.ci_status)
                if release.ci_status != "Overridden"
                else _("overridden: {0}").format(release.ci_override_reason),
            ),
            (_("Risk"), release.risk_level),
            (_("Sites"), ", ".join(row.site for row in release.sites)),
            (_("Bench"), release.release_group),
            (_("Needs a senior"), _("yes") if release.needs_senior else None),
            (_("Task"), release.task),
        ],
        links=[
            (
                _("Open the changes"),
                f"https://github.com/{release.repository}/compare/"
                f"{release.apps[0].from_commit[:12]}...{release.apps[0].to_commit[:12]}",
            ),
            (_("Open the release"), get_url(f"/app/hds-deploy-request/{release.name}")),
        ],
        actions=[
            assistant.button(
                _("Approve for tonight"), "release_approve", "positive", **data
            ),
            assistant.button(_("Deploy now"), "release_now", **data),
            assistant.button(_("Reject"), "release_reject", "destructive", **data),
        ],
        inputs=[
            {"id": "reason", "label": _("Reason (needed to reject)"), "multiline": True}
        ],
    )


def decided_card(release) -> dict:
    from helpdesk.copilot import assistant

    who = (
        frappe.utils.get_fullname(release.decided_by)
        if release.decided_by
        else _("TBO Support")
    )
    lines = [_("{0}: {1}").format(_(release.status), who)]
    if release.decision_note:
        lines.append(release.decision_note)
    if release.status == "Scheduled" and release.scheduled_for:
        lines.append(_("Deploys {0}").format(deploy.local_time(release.scheduled_for)))
    return assistant.card(
        _("Release of {0}: {1}").format(release.repository, _(release.status).lower()),
        lines,
        links=[
            (_("Open the release"), get_url(f"/app/hds-deploy-request/{release.name}"))
        ],
        tone="good" if release.status in ("Scheduled", "Succeeded") else "default",
    )


def refresh_cards(name: str):
    """After a decision, every copy of the release's card shows it (first decision wins)."""
    from helpdesk.copilot import assistant, teams

    try:
        reply = decided_card(frappe.get_doc(DEPLOY, name))
        for row in frappe.get_all(
            assistant.MESSAGE,
            filters={"release": name, "direction": "Out", "card": ["is", "set"]},
            fields=["name", "user", "teams_activity"],
        ):
            frappe.db.set_value(
                assistant.MESSAGE,
                row.name,
                "card",
                json.dumps(reply, ensure_ascii=False),
                update_modified=False,
            )
            if row.teams_activity and teams.enabled():
                teams.update_card(row.user, row.teams_activity, reply)
            frappe.publish_realtime(
                "helpdesk:copilot-chat",
                {"message": row.name},
                user=row.user,
                after_commit=True,
            )
    except Exception:
        frappe.log_error(title=f"Copilot could not update the cards of {name}")


# --- the end: called by helpdesk.copilot.deploy for a release without a run ---------------


def succeeded(release, results: list[dict]):
    """Deployed and checked: the people are told, and Copilot's fixes inside it are resolved."""
    from helpdesk.copilot import customer, runs

    if release.staging_for:  # the UAT deploy of a release: it passed its staging
        release.db_set(
            {
                "status": "Succeeded",
                "finished_at": now_datetime(),
                "check_results": json.dumps(results, indent=1),
            }
        )
        return staging_done(frappe.get_doc(DEPLOY, release.staging_for), True, results)

    release.db_set(
        {
            "status": "Succeeded",
            "finished_at": now_datetime(),
            "check_results": json.dumps(results, indent=1),
        }
    )
    for change in frappe.parse_json(release.changes or "[]") or []:
        run = (
            frappe.get_doc("HDS Copilot Run", change["run"])
            if change.get("run")
            else None
        )
        if not run or run.state != "Merged":
            continue
        runs.transition(
            run, "Deploying", runs.SYSTEM, note=f"with release {release.name}"
        )
        runs.transition(run, "Verifying", runs.SYSTEM, note="Press updated the sites")
        run = runs.transition(
            run,
            "Resolved",
            runs.SYSTEM,
            note=f"deployed and checked with release {release.name}",
            deployed_at=now_datetime(),
            deployed_by=release.decided_by,
        )
        if run.get("kind") != "revert":
            customer.send_stage(run, "Resolved", {"resolution": _("The fix is live.")})
    if release.ticket:
        customer.comment(
            release.ticket,
            frappe.utils.escape_html(
                _("Release {0} is live on {1} and checked.").format(
                    release.name, ", ".join(row.site for row in release.sites)
                )
            ),
        )
    tell(
        release,
        authors(release) | {release.decided_by},
        _("The release of {0} {1} is live and checked.").format(
            release.repository, release.branch
        ),
    )


def failed(release, reason: str, links: str = "", after_check: bool = False):
    """The deploy or the check after failed: the people are told, with Press's links. When
    the site ran the new code and the check after failed, each pull request is reverted."""
    reason = str(reason)[:1000]
    release.db_set({"status": "Failed", "error": reason, "finished_at": now_datetime()})
    if release.staging_for:  # the UAT deploy of a release: it failed its staging
        return staging_done(
            frappe.get_doc(DEPLOY, release.staging_for),
            False,
            [
                {
                    "check": _("the deploy to the UAT site"),
                    "result": "fail",
                    "detail": reason,
                }
            ],
        )
    release.add_comment(
        "Info",
        frappe.utils.escape_html(_("The deploy failed: {0}").format(reason))
        + (f"<br>{_('Press:')} {links}" if links else ""),
    )
    if release.ticket:
        from helpdesk.copilot import customer

        customer.comment(
            release.ticket,
            frappe.utils.escape_html(
                _("Release {0} with this change failed: {1}").format(
                    release.name, reason
                )
            ),
        )
    from helpdesk.work_reminders import notify_users

    reverts = undo(release) if after_check else []
    people = list(authors(release)) + [release.decided_by] + approvals.managers()
    notify_users(
        [p for p in dict.fromkeys(people) if p],
        DEPLOY,
        release.name,
        _("The release of {0} {1} failed: {2}").format(
            release.repository, release.branch, reason[:160]
        )
        + (
            " " + _("Reverted in {0}.").format(", ".join(r["url"] for r in reverts))
            if reverts
            else ""
        ),
        escalate=True,
        once=False,
    )


def press_button(user: str, channel: str, verb: str, data: dict, inputs: dict) -> dict:
    """A button on a release's card in Teams or the Copilot panel; the same decision as on the release."""
    from helpdesk.copilot import assistant

    release = frappe.get_doc(DEPLOY, data.get("release"))
    if release.status != "Waiting for approval":
        return {"replies": [], "card": decided_card(release)}  # first decision wins
    reason = (inputs.get("reason") or "").strip()
    approve = verb != "release_reject"
    if not approve and not reason:
        return {
            "replies": [
                assistant.text_card(
                    _(
                        "Please write the reason in the box, then press Reject: the people who wrote it get it."
                    )
                )
            ],
            "card": None,
        }
    when = "now" if verb == "release_now" else "tonight"
    arguments = {
        "release": release.name,
        "approve": approve,
        "when": when,
        "note": reason,
    }
    try:
        with assistant.as_user(user):
            decide(
                release.name,
                user,
                approve,
                reason,
                when=when,
                expected_hash=data.get("hash"),
                via=channel,
            )
    except (frappe.PermissionError, frappe.ValidationError) as e:
        frappe.clear_last_message()
        assistant.log_action(
            user,
            channel,
            "decide_release",
            "Refused",
            arguments,
            str(e),
            None,
            release.ticket,
        )
        return {"replies": [assistant.text_card(str(e), "warning")], "card": None}
    assistant.log_action(
        user,
        channel,
        "decide_release",
        "OK",
        arguments,
        release.name,
        None,
        release.ticket,
    )
    return {"replies": [], "card": decided_card(frappe.get_doc(DEPLOY, release.name))}


# --- staging (H25): the customer's UAT site, else the sandbox check by a worker -------------

CHECK_LEASE_MINUTES = 60


def uat_sites(release) -> tuple[str | None, list[dict]]:
    """The UAT bench and sites of the release's customers whose cards run the same branch."""
    from helpdesk.copilot.fixes import _repo_name

    customers = {row.customer for row in release.sites if row.customer}
    if not customers:
        return None, []
    found = {}
    for card in frappe.get_all(
        "HDS Site Registry",
        filters={
            "environment": "UAT",
            "customer_name": ["in", list(customers)],
            "press_site": ["is", "set"],
            "press_release_group": ["is", "set"],
        },
        fields=["name", "customer_name", "press_site", "press_release_group"],
        order_by="name asc",
    ):
        for row in frappe.get_all(
            "HDS Site App",
            filters={"parent": card.name, "parenttype": "HDS Site Registry"},
            fields=["repository", "branch"],
        ):
            if (
                _repo_name(row.repository) == release.repository
                and row.branch == release.branch
            ):
                found.setdefault(card.press_release_group, []).append(
                    {
                        "site": card.press_site,
                        "customer": card.customer_name,
                        "registry": card.name,
                    }
                )
    if not found:
        return None, []
    group = sorted(found)[0]
    return group, found[group]


def start_staging(release):
    """After green CI and before the approval: the UAT site in the next window, else the sandbox check."""
    if not copilot_settings.get_settings().get("release_staging"):
        release.db_set(
            {
                "staging_status": "Not run",
                "staging_detail": json.dumps(
                    [
                        {
                            "check": _("staging"),
                            "result": "not_run",
                            "detail": _("switched off in HDS Copilot Settings"),
                        }
                    ]
                ),
            }
        )
        return ask_approval(release)
    group, sites = uat_sites(release)
    if group:
        at = deploy.next_opening()
        uat = frappe.get_doc(
            {
                "doctype": DEPLOY,
                "status": "Scheduled",
                "when": "Tonight",
                "scheduled_for": at,
                "requested_at": now_datetime(),
                "source": release.source,
                "repository": release.repository,
                "branch": release.branch,
                "release_group": group,
                "staging_for": release.name,
                "ticket": release.ticket,
                "task": release.task,
                "authors": release.authors,
                "changes": release.changes,
                "ci_status": release.ci_status,
                "sites": sites,
                "apps": [
                    {
                        "app": release.apps[0].app,
                        "repository": release.repository,
                        "to_commit": release.apps[0].to_commit,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        release.db_set(
            {
                "status": "Staging",
                "staging": "UAT site",
                "staging_status": "Queued",
                "staging_request": uat.name,
            }
        )
        release.add_comment(
            "Info",
            _("Staging on the UAT site {0} {1}.").format(
                ", ".join(s["site"] for s in sites), deploy.local_time(at)
            ),
        )
        return
    release.db_set(
        {"status": "Staging", "staging": "Sandbox", "staging_status": "Queued"}
    )


def cancel_staging(release):
    """New commits: a UAT deploy not yet started is cancelled, a sandbox check's lease dropped."""
    if (
        release.staging_request
        and frappe.db.get_value(DEPLOY, release.staging_request, "status")
        in deploy.WAITING
    ):
        frappe.db.set_value(
            DEPLOY,
            release.staging_request,
            {"status": "Cancelled", "finished_at": now_datetime()},
        )


def staging_done(release, passed: bool, rows: list[dict]):
    """The staging result: passed goes to the approval; failed waits for new commits or a senior."""
    if release.status != "Staging":
        return  # new commits arrived meanwhile: this result is for older code
    release.db_set(
        {
            "staging_status": "Passed" if passed else "Failed",
            "staging_detail": json.dumps(rows, indent=1, default=str),
            "check_lease_hash": None,
        }
    )
    if passed:
        return ask_approval(release)
    failing = "; ".join(
        f"{r.get('check')}: {r.get('detail') or ''}"[:200]
        for r in rows
        if r.get("result") == "fail"
    )
    tell(
        release,
        authors(release),
        _(
            "The release of {0} {1} failed its staging check: {2}. Push a fix, or a senior can let it through with a reason."
        ).format(release.repository, release.branch, failing[:300]),
    )


def _lease(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def claim_check(worker_id: str) -> dict:
    """The oldest release waiting for its sandbox check, leased to the worker; {} when none."""
    for name in frappe.get_all(
        DEPLOY,
        filters={"status": "Staging", "staging": "Sandbox", "staging_status": "Queued"},
        order_by="modified asc",
        limit=5,
        pluck="name",
    ):
        if (
            frappe.db.get_value(DEPLOY, name, "staging_status", for_update=True)
            != "Queued"
        ):
            continue  # another worker got it first
        token = frappe.generate_hash(length=32)
        release = frappe.get_doc(DEPLOY, name)
        release.db_set(
            {
                "staging_status": "Running",
                "check_worker": worker_id[:140],
                "check_started_at": now_datetime(),
                "check_lease_expires": add_to_date(
                    now_datetime(), minutes=CHECK_LEASE_MINUTES
                ),
                "check_lease_hash": _lease(token),
            }
        )
        return {
            "kind": "release_check",
            "release": name,
            "lease_token": token,
            "lease_expires": str(release.check_lease_expires),
            "context": check_context(release),
        }
    return {}


def check_context(release) -> dict:
    """What the worker builds: the site card's apps at the commits they run, this app at the release's commit."""
    from helpdesk.copilot import github_app
    from helpdesk.copilot.fixes import _repo_name

    app = release.apps[0]
    card = release.sites[0].registry if release.sites else None
    apps = []
    for row in frappe.get_all(
        "HDS Site App",
        filters={"parent": card, "parenttype": "HDS Site Registry"},
        fields=["app", "repository", "branch", "deployed_commit"],
        order_by="idx asc",
    ):
        mine = row.app == app.app
        apps.append(
            {
                "app": row.app,
                "repository": _repo_name(row.repository) if row.repository else None,
                "branch": row.branch,
                "commit": app.to_commit if mine else row.deployed_commit,
            }
        )
    if not any(a["app"] == app.app for a in apps):
        apps.append(
            {
                "app": app.app,
                "repository": release.repository,
                "branch": release.branch,
                "commit": app.to_commit,
            }
        )
    token = None
    if github_app.configured():
        try:
            token = github_app.read_token(release.repository)
        except Exception:
            token = None  # a public repository is cloned without a key
    return {
        "release": release.name,
        "repository": release.repository,
        "branch": release.branch,
        "app": app.app,
        "commit": app.to_commit,
        "customer": release.sites[0].customer if release.sites else None,
        "site": release.sites[0].site if release.sites else None,
        "apps": apps,
        "repo_token": token,
    }


def check_result(name: str, lease_token: str, evidence: list, tested_on: str = ""):
    """The worker's sandbox check: migrate, the app's tests, no new errors."""
    release = frappe.get_doc(DEPLOY, name, for_update=True)
    if (
        release.staging_status != "Running"
        or not release.check_lease_hash
        or release.check_lease_hash != _lease(lease_token or "")
    ):
        frappe.throw(
            _("This check's lease is no longer valid."), frappe.PermissionError
        )
    rows = [
        {
            "check": str(item.get("check") or "")[:200],
            "result": item.get("result")
            if item.get("result") in ("pass", "fail", "not_run")
            else "fail",
            "detail": str(item.get("detail") or "")[:500],
        }
        for item in evidence or []
        if isinstance(item, dict)
    ]
    if tested_on:
        rows.append(
            {"check": _("tested on"), "result": "not_run", "detail": tested_on[:200]}
        )
    passes = any(r["result"] == "pass" for r in rows)
    fails = any(r["result"] == "fail" for r in rows)
    if not passes and not fails:
        # the check could not be done (the runner or GitHub unreachable): not the code's fault
        release.db_set(
            {
                "staging_status": "Not run",
                "staging_detail": json.dumps(rows, indent=1, default=str),
                "check_lease_hash": None,
            }
        )
        tell(
            release,
            approvals.seniors(),
            _(
                "The sandbox check of the release of {0} {1} could not run ({2}); a senior can let it through with a reason."
            ).format(
                release.repository,
                release.branch,
                "; ".join(r["detail"] for r in rows if r["detail"])[:200],
            ),
        )
        return {"staging_status": "Not run"}
    staging_done(release, passes and not fails, rows)
    return {"staging_status": "Passed" if passes and not fails else "Failed"}


def expire_checks():
    """A check whose worker went quiet is queued again; one no worker took in time is marked not run."""
    now = now_datetime()
    for name in frappe.get_all(
        DEPLOY,
        filters={
            "status": "Staging",
            "staging_status": "Running",
            "check_lease_expires": ["<", now],
        },
        pluck="name",
    ):
        frappe.db.set_value(
            DEPLOY, name, {"staging_status": "Queued", "check_lease_hash": None}
        )
    hours = copilot_settings.get_settings().get("release_check_hours") or 6
    for release in frappe.get_all(
        DEPLOY,
        filters={
            "status": "Staging",
            "staging": "Sandbox",
            "staging_status": "Queued",
            "modified": ["<", add_to_date(now, hours=-hours)],
        },
        pluck="name",
    ):
        doc = frappe.get_doc(DEPLOY, release)
        doc.db_set(
            {
                "staging_status": "Not run",
                "staging_detail": json.dumps(
                    [
                        {
                            "check": _("the sandbox check"),
                            "result": "not_run",
                            "detail": _("no worker took it within {0} hours").format(
                                hours
                            ),
                        }
                    ]
                ),
            }
        )
        tell(
            doc,
            approvals.seniors(),
            _(
                "No worker checked the release of {0} {1} within {2} hours; a senior can let it through with a reason."
            ).format(doc.repository, doc.branch, hours),
        )


# --- undo (H25): the check after failed, so each pull request is reverted -----------------


def undo(release) -> list[dict]:
    """GitHub's own revert of each pull request in the release, newest first; `[{number, url}]`.

    The reverts are ordinary pull requests: reviewed, merged, and released like any other.
    A push has no pull request to revert; the people are told instead.
    """
    numbers = []
    for change in reversed(frappe.parse_json(release.changes or "[]") or []):
        number = (change.get("pull") or {}).get("number")
        if number and number not in numbers:
            numbers.append(number)
    opened = []
    for number in numbers:
        try:
            opened.append(
                github.revert_pull(
                    release.repository,
                    number,
                    f"Revert #{number}: release {release.name} failed its check",
                    _(
                        "TBO Support deployed release {0} and the check after it failed: {1}\n\nThis reverts #{2}."
                    ).format(release.name, (release.error or "")[:500], number),
                )
            )
        except GitHubError as e:
            release.add_comment(
                "Info",
                frappe.utils.escape_html(
                    _("Could not revert #{0}: {1}").format(number, e.message)
                ),
            )
    if opened:
        release.add_comment(
            "Info",
            _("Reverted: {0}").format(
                ", ".join(
                    f'<a href="{frappe.utils.escape_html(r["url"])}">#{r["number"]}</a>'
                    for r in opened
                )
            ),
        )
    return opened


# --- the weekly record (H25): Monday's pilot email gets a releases section ----------------


def week_numbers(week_start, week_end) -> dict:
    """The week's releases (not Copilot fixes, not UAT deploys): how many, how they ended, the waits, the bypasses."""
    from frappe.utils import add_days

    start = get_datetime(str(week_start))
    end = get_datetime(str(add_days(week_end, 1)))
    base = {"run": ["is", "not set"], "staging_for": ["is", "not set"]}
    made = frappe.get_all(
        DEPLOY,
        filters={**base, "creation": ["between", [start, end]]},
        fields=["name", "source", "ci_override_by"],
    )
    ended = frappe.get_all(
        DEPLOY,
        filters={**base, "finished_at": ["between", [start, end]]},
        fields=["name", "status", "release_group", "press_reference"],
    )
    waits = sorted(
        (get_datetime(r.decided_at) - get_datetime(r.assigned_at)).total_seconds()
        / 3600
        for r in frappe.get_all(
            DEPLOY,
            filters={
                **base,
                "decided_at": ["between", [start, end]],
                "assigned_at": ["is", "set"],
            },
            fields=["decided_at", "assigned_at"],
        )
    )
    reverted = frappe.db.count(
        "Comment",
        {
            "reference_doctype": DEPLOY,
            "content": ["like", "Reverted:%"],
            "creation": ["between", [start, end]],
        },
    )
    return {
        "made": len(made),
        "pushes": sum(1 for r in made if r.source == "Push"),
        "overrides": sum(1 for r in made if r.ci_override_by),
        "succeeded": sum(1 for r in ended if r.status == "Succeeded"),
        "failed": sum(1 for r in ended if r.status == "Failed"),
        "rejected": sum(1 for r in ended if r.status == "Rejected"),
        "reverted": reverted,
        "median_wait_hours": round(waits[len(waits) // 2], 1) if waits else None,
        "bypasses": bypasses(start, end),
    }


def bypasses(start, end) -> int | None:
    """Press builds on the pipeline's benches that no deploy from TBO Support asked for; None when Press can't say."""
    if not (enabled() and press.configured()):
        return None
    groups = {key[2] for key in targets()}
    ours = frappe.get_all(
        DEPLOY,
        filters={
            "release_group": ["in", list(groups) or [""]],
            "started_at": ["between", [start, end]],
        },
        fields=["release_group", "train", "name"],
    )
    asked = len({r.train or r.name for r in ours})
    try:
        builds = sum(
            len(
                press.get_list(
                    "Deploy Candidate Build",
                    filters={"group": group, "creation": [">=", str(start)]},
                    fields=["name", "creation"],
                    limit=200,
                )
                or []
            )
            for group in groups
        )
    except PressError:
        return None
    return max(builds - asked, 0)


def week_html(week_start, week_end) -> str:
    """The releases section of the weekly pilot email; empty when releases are off."""
    if not enabled():
        return ""
    numbers = week_numbers(week_start, week_end)
    escape = frappe.utils.escape_html
    lines = [
        _("{0} releases made ({1} from pushes, {2} let through by a senior)").format(
            numbers["made"], numbers["pushes"], numbers["overrides"]
        ),
        _("{0} live and checked, {1} failed ({2} reverted), {3} rejected").format(
            numbers["succeeded"],
            numbers["failed"],
            numbers["reverted"],
            numbers["rejected"],
        ),
        _("Median wait for an approval: {0} hours").format(
            numbers["median_wait_hours"]
            if numbers["median_wait_hours"] is not None
            else "-"
        ),
    ]
    if numbers["bypasses"] is not None:
        lines.append(
            _(
                "Deploys on these benches that went around TBO Support (Press dashboard): {0}"
            ).format(numbers["bypasses"])
        )
    return "<h4>{0}</h4><ul>{1}</ul>".format(
        escape(_("Releases")),
        "".join(f"<li>{escape(line)}</li>" for line in lines),
    )
