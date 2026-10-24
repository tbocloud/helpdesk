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
GROWING = ("Waiting for CI", "Waiting for approval")
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
    doc.update(
        {
            "status": "Waiting for CI",
            "ci_status": "Pending",
            "ci_detail": None,
            "ci_override_by": None,
            "ci_override_reason": None,
            "approval_hash": None,
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
    ask_approval(release)


def override_ci(release, user: str, reason: str):
    """A senior lets a release with red or missing CI go to its approval; the reason is kept."""
    if release.status != "Waiting for CI":
        frappe.throw(_("Only a release waiting for CI can be let through."))
    if user not in approvals.seniors():
        frappe.throw(
            _("Only a senior approver may let a release through without green CI."),
            frappe.PermissionError,
        )
    if not (reason or "").strip():
        frappe.throw(_("Say why the release may go without green CI."))
    release.db_set(
        {
            "ci_status": "Overridden",
            "ci_override_by": user,
            "ci_override_reason": reason.strip()[:1000],
            "needs_senior": 1,
        }
    )
    release.add_comment(
        "Info",
        _("{0} let it through without green CI: {1}").format(
            frappe.utils.get_fullname(user), reason.strip()
        ),
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


def failed(release, reason: str, links: str = ""):
    """The deploy or the check after failed: the people are told, with Press's links."""
    reason = str(reason)[:1000]
    release.db_set({"status": "Failed", "error": reason, "finished_at": now_datetime()})
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

    people = list(authors(release)) + [release.decided_by] + approvals.managers()
    notify_users(
        [p for p in dict.fromkeys(people) if p],
        DEPLOY,
        release.name,
        _("The release of {0} {1} failed: {2}").format(
            release.repository, release.branch, reason[:160]
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
